from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hashutil import sha256_bytes, sha256_json
from .worker_secrets import secret_text_reason, sensitive_path_reason
from .worker_spec import TaskSpecError, WorkerTaskSpec, canonical_relative_path, path_matches_any

PROPOSAL_SCHEMA_VERSION = 1
PROPOSAL_FIELDS = {"schema_version", "summary", "patch", "changed_paths"}
PROPOSAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "integer", "enum": [PROPOSAL_SCHEMA_VERSION]},
        "summary": {"type": "string"},
        "patch": {"type": "string"},
        "changed_paths": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["schema_version", "summary", "patch", "changed_paths"],
    "additionalProperties": False,
}
_DIFF_HEADER = re.compile(r"diff --git a/([^\s\"']+) b/([^\s\"']+)\Z")
_FORBIDDEN_DIRECTIVES = (
    "GIT binary patch",
    "Binary files ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "similarity index ",
    "dissimilarity index ",
    "old mode ",
    "new mode ",
    "Submodule ",
)


class PatchValidationError(ValueError):
    """Raised before any model-proposed bytes are applied."""


@dataclass(frozen=True)
class PatchProposal:
    schema_version: int
    summary: str
    patch: str
    changed_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["changed_paths"] = list(self.changed_paths)
        return value

    @property
    def sha256(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True)
class PatchFacts:
    changed_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]
    patch_sha256: str


def parse_patch_proposal(value: Any, spec: WorkerTaskSpec) -> PatchProposal:
    if not isinstance(value, dict) or set(value) != PROPOSAL_FIELDS:
        raise PatchValidationError(f"proposal fields must be exactly {sorted(PROPOSAL_FIELDS)}")
    if type(value["schema_version"]) is not int or value["schema_version"] != PROPOSAL_SCHEMA_VERSION:
        raise PatchValidationError(f"proposal schema_version must be {PROPOSAL_SCHEMA_VERSION}")
    summary = value["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary.encode("utf-8")) > 4000:
        raise PatchValidationError("proposal summary must be non-empty and at most 4000 UTF-8 bytes")
    if secret_text_reason(summary):
        raise PatchValidationError("proposal summary contains a probable secret")
    patch = value["patch"]
    if not isinstance(patch, str) or not patch or "\0" in patch:
        raise PatchValidationError("proposal patch must be a non-empty text diff")
    try:
        patch_bytes = patch.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PatchValidationError("proposal patch is not valid UTF-8") from exc
    if len(patch_bytes) > spec.max_patch_bytes:
        raise PatchValidationError("proposal patch exceeds max_patch_bytes")
    changed = value["changed_paths"]
    if not isinstance(changed, list) or not changed or len(changed) > spec.max_changed_files:
        raise PatchValidationError("changed_paths is empty or exceeds max_changed_files")
    try:
        canonical = tuple(canonical_relative_path(path, "changed_paths[]") for path in changed)
    except TaskSpecError as exc:
        raise PatchValidationError(str(exc)) from exc
    if canonical != tuple(sorted(set(canonical))):
        raise PatchValidationError("changed_paths must be sorted and unique")
    return PatchProposal(PROPOSAL_SCHEMA_VERSION, summary, patch, canonical)


def _header_path(value: str, prefix: str, field: str) -> str:
    if not value.startswith(prefix):
        raise PatchValidationError(f"{field} must start with {prefix}")
    try:
        return canonical_relative_path(value[len(prefix) :], field)
    except TaskSpecError as exc:
        raise PatchValidationError(str(exc)) from exc


def inspect_patch(proposal: PatchProposal, spec: WorkerTaskSpec) -> PatchFacts:
    text = proposal.patch
    if "\r" in text:
        raise PatchValidationError("patch must use LF line endings")
    if not text.endswith("\n"):
        raise PatchValidationError("patch must end with a newline")
    secret_reason = secret_text_reason(text)
    if secret_reason:
        raise PatchValidationError(f"patch contains a probable secret: {secret_reason}")
    for directive in _FORBIDDEN_DIRECTIVES:
        if any(line.startswith(directive) for line in text.splitlines()):
            raise PatchValidationError(f"patch directive is forbidden: {directive.strip()}")

    lines = text.splitlines()
    header_indexes = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if not header_indexes or header_indexes[0] != 0:
        raise PatchValidationError("patch must consist only of git unified-diff blocks")
    header_indexes.append(len(lines))
    changed: list[str] = []
    deleted: list[str] = []
    for block_number in range(len(header_indexes) - 1):
        start = header_indexes[block_number]
        end = header_indexes[block_number + 1]
        block = lines[start:end]
        header_match = _DIFF_HEADER.fullmatch(block[0])
        if header_match is None:
            raise PatchValidationError("quoted, spaced, or malformed diff paths are unsupported")
        old_header = _header_path(f"a/{header_match.group(1)}", "a/", "diff old path")
        new_header = _header_path(f"b/{header_match.group(2)}", "b/", "diff new path")
        if old_header != new_header:
            raise PatchValidationError("renames and path disagreement are forbidden")
        logical_path = old_header
        if logical_path in changed:
            raise PatchValidationError(f"duplicate diff block for {logical_path}")
        if not path_matches_any(logical_path, spec.write_path_patterns):
            raise PatchValidationError(f"path is outside write_path_patterns: {logical_path}")
        if path_matches_any(logical_path, spec.protected_path_patterns):
            raise PatchValidationError(f"path is protected from model writes: {logical_path}")
        sensitive = sensitive_path_reason(logical_path)
        if sensitive:
            raise PatchValidationError(f"sensitive path is forbidden: {logical_path}")

        hunk_indexes = [index for index, line in enumerate(block[1:], 1) if line.startswith("@@ ")]
        if not hunk_indexes:
            raise PatchValidationError(f"diff block for {logical_path} has no hunk")
        metadata = block[1 : hunk_indexes[0]]
        old_markers = [line for line in metadata if line.startswith("--- ")]
        new_markers = [line for line in metadata if line.startswith("+++ ")]
        if len(old_markers) != 1 or len(new_markers) != 1:
            raise PatchValidationError(f"diff block for {logical_path} needs exactly one --- and +++ marker")
        old_marker = old_markers[0][4:]
        new_marker = new_markers[0][4:]
        deleting = new_marker == "/dev/null"
        creating = old_marker == "/dev/null"
        if deleting and creating:
            raise PatchValidationError(f"diff block for {logical_path} cannot have two /dev/null markers")
        if deleting:
            if not spec.allow_deletions:
                raise PatchValidationError(f"deletion is not authorized: {logical_path}")
            if _header_path(old_marker, "a/", "--- path") != logical_path:
                raise PatchValidationError(f"--- path disagrees for {logical_path}")
            deleted.append(logical_path)
        elif creating:
            if _header_path(new_marker, "b/", "+++ path") != logical_path:
                raise PatchValidationError(f"+++ path disagrees for {logical_path}")
        else:
            if _header_path(old_marker, "a/", "--- path") != logical_path:
                raise PatchValidationError(f"--- path disagrees for {logical_path}")
            if _header_path(new_marker, "b/", "+++ path") != logical_path:
                raise PatchValidationError(f"+++ path disagrees for {logical_path}")
        for line in block:
            if line.startswith(("new file mode ", "deleted file mode ")):
                mode = line.rsplit(" ", 1)[-1]
                if mode not in ("100644", "100755"):
                    raise PatchValidationError(f"unsafe file mode in {logical_path}: {mode}")
            if line.startswith("index ") and line.endswith(" 160000"):
                raise PatchValidationError(f"gitlink is forbidden: {logical_path}")
        changed.append(logical_path)

    actual = tuple(sorted(changed))
    if actual != proposal.changed_paths:
        raise PatchValidationError("changed_paths does not exactly match the diff headers")
    return PatchFacts(actual, tuple(sorted(deleted)), sha256_bytes(text.encode("utf-8")))


def _git(workspace: Path, args: list[str], *, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=workspace,
        env={
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        },
        input=stdin,
        capture_output=True,
        check=False,
    )


def apply_patch_to_workspace(workspace: Path, proposal: PatchProposal, facts: PatchFacts) -> None:
    patch_bytes = proposal.patch.encode("utf-8")
    check = _git(workspace, ["apply", "--check", "--index", "--whitespace=error-all", "-"], stdin=patch_bytes)
    if check.returncode != 0:
        message = check.stderr.decode("utf-8", errors="replace")[:2000]
        raise PatchValidationError(f"git apply --check rejected the patch: {message}")
    applied = _git(workspace, ["apply", "--index", "--whitespace=error-all", "-"], stdin=patch_bytes)
    if applied.returncode != 0:
        message = applied.stderr.decode("utf-8", errors="replace")[:2000]
        raise PatchValidationError(f"git apply rejected the patch after check: {message}")
    paths = _git(workspace, ["diff", "--cached", "--name-only", "-z", "--no-renames"])
    if paths.returncode != 0:
        raise PatchValidationError("cannot reconcile staged changed paths")
    current = tuple(sorted(item.decode("utf-8") for item in paths.stdout.split(b"\0") if item))
    if not set(facts.changed_paths).issubset(current):
        raise PatchValidationError("applied patch changed-path reconciliation failed")
    whitespace = _git(workspace, ["diff", "--cached", "--check"])
    if whitespace.returncode != 0:
        message = whitespace.stdout.decode("utf-8", errors="replace")[:2000]
        raise PatchValidationError(f"staged patch has whitespace errors: {message}")
    for path in current:
        candidate = workspace / path
        if candidate.is_symlink():
            raise PatchValidationError(f"applied patch produced a symlink: {path}")
        if candidate.exists() and candidate.is_file():
            reason = secret_text_reason(candidate.read_text(encoding="utf-8", errors="replace"))
            if reason:
                raise PatchValidationError(f"changed file contains a probable secret ({reason}): {path}")
