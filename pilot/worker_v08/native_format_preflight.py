"""Phase 1: isolated, read-only Java format preflight.

Inputs are a trusted registered WorkerTaskSpec, validated T54 project config,
and an untrusted proposal body. The caller owns envelope/pack verification,
admission, durable evidence and feedback delivery. No oracle is needed.
Only the Maven Spotless check adapter is supported in this phase.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from programming_agent_runner.worker_patch import (
    PatchValidationError,
    apply_patch_to_workspace,
    inspect_patch,
    parse_patch_proposal,
)
from programming_agent_runner.worker_spec import AcceptanceCommand, WorkerTaskSpec


@dataclass(frozen=True)
class FormatResult:
    status: str
    reason: str
    command: str = ""
    paths: tuple[str, ...] = ()


def _within(path: str, root: str) -> bool:
    return path.startswith(root + "/")


def _select(spec: WorkerTaskSpec, config: dict):
    """Accept only the exact registered check shape for a configured Maven POM."""
    matches = [c for c in spec.acceptance_commands if "spotless:check" in c.argv]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("ambiguous format command")
    command = matches[0]
    components = [
        item for item in config["components"].values()
        if item["kind"] == "maven"
        and command.argv == ("mvn", "-B", "-q", "-f", item["build_file"], "spotless:check")
    ]
    if len(components) != 1:
        raise ValueError("unsupported format command")
    return command, components[0]


def _env(home: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(cwd: Path, env: dict, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=cwd, env=env, capture_output=True, check=True, timeout=60,
    ).stdout


def _materialize(source: Path, workspace: Path, env: dict, base: str, root: str) -> None:
    """Export only regular tracked files of the configured component, no .git or control tree."""
    if _git(source, env, "rev-parse", "HEAD").decode().strip() != base:
        raise ValueError("base drift")
    entries = _git(source, env, "ls-tree", "-r", "-z", base, "--", root)
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        path = raw_path.decode("utf-8")
        parts = PurePosixPath(path).parts
        if (mode not in ("100644", "100755") or kind != "blob"
                or not _within(path, root) or any(p in (".git", "..") for p in parts)
                or path.startswith("/")):
            raise ValueError("unsafe component tree")
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git(source, env, "cat-file", "blob", oid))
        target.chmod(0o755 if mode == "100755" else 0o644)
    _git(workspace, env, "init", "-q")
    _git(workspace, env, "add", "-f", "--", root)
    _git(workspace, env, "-c", "user.name=LF", "-c", "user.email=lf@example.invalid",
         "commit", "-qm", "format baseline")


def _run(command: AcceptanceCommand, workspace: Path, env: dict) -> tuple[int, str]:
    """Bound runtime and retained output; terminate the process group on timeout."""
    limit = min(command.max_output_bytes, 32000)
    # Temporary output is not forwarded to Actions or persisted as feedback.
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(
            list(command.argv), cwd=workspace, env=env,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = proc.wait(timeout=command.timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            raise
        # Maven may put the decisive diagnostic at the end of its output.
        size = output.seek(0, os.SEEK_END)
        output.seek(max(0, size - limit))
        return code, output.read(limit).decode("utf-8", errors="replace")


def prevalidate(source: Path, spec: WorkerTaskSpec, proposal: dict, config: dict) -> FormatResult:
    """Never mutate source or proposal. Only PASS/SKIPPED may continue downstream.

    The adapter deliberately refuses mixed/non-Java changes when a Spotless
    command is selected: executing a proposal-modified build/config is unsafe.
    This is a disposable workspace and clean environment, not an OS sandbox.
    Integrators must run it before loading private material.
    """
    try:
        parsed = parse_patch_proposal(proposal, spec)
        facts = inspect_patch(parsed, spec)
    except PatchValidationError:
        return FormatResult("INVALID_PROPOSAL", "PATCH_SCOPE_OR_SCHEMA")
    try:
        selected = _select(spec, config)
    except (ValueError, KeyError, TypeError):
        return FormatResult("INFRA_ERROR", "FORMAT_CONFIG_UNSUPPORTED")
    if selected is None:
        return FormatResult("SKIPPED", "NO_REGISTERED_FORMAT_COMMAND")
    command, component = selected
    if any(not path.endswith(".java") or not any(
        _within(path, root) for root in component["source_roots"]
    ) for path in facts.changed_paths):
        return FormatResult("INVALID_PROPOSAL", "FORMAT_UNSAFE_CHANGE", command.name)
    try:
        with tempfile.TemporaryDirectory(prefix="lf-format-") as tmp:
            workspace = Path(tmp) / "source"
            home = Path(tmp) / "home"
            workspace.mkdir()
            home.mkdir()
            env = _env(home)
            _materialize(source, workspace, env, spec.base_head_sha, component["root"])
            if not (workspace / component["build_file"]).is_file():
                return FormatResult("INFRA_ERROR", "FORMAT_BUILD_FILE_MISSING", command.name)
            try:
                apply_patch_to_workspace(workspace, parsed, facts)
            except PatchValidationError:
                return FormatResult("INVALID_PROPOSAL", "PATCH_APPLICATION_REJECTED", command.name)
            code, output = _run(command, workspace, env)
    except subprocess.TimeoutExpired:
        return FormatResult("INFRA_ERROR", "FORMAT_TIMEOUT", command.name)
    except (OSError, subprocess.SubprocessError, ValueError):
        return FormatResult("INFRA_ERROR", "FORMAT_EXECUTION_FAILED", command.name)
    if code == 0:
        return FormatResult("PASS", "FORMAT_OK", command.name)
    # Fail closed: do not count generic Maven/plugin/dependency failures as format.
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    if code == 1 and re.search(r"(?im)^\[ERROR\].*The following files had format violations:", clean):
        # Only return paths already validated by the trusted patch inspector;
        # never return arbitrary Maven output or source fragments.
        paths = tuple(p for p in facts.changed_paths if p in clean or
                      p.removeprefix(component["root"] + "/") in clean)
        return FormatResult("FORMAT_FAIL", "SPOTLESS_VIOLATIONS", command.name, paths)
    return FormatResult("INFRA_ERROR", "FORMAT_NONZERO_UNCLASSIFIED", command.name)
