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
import selectors
import time
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

TOTAL_TIMEOUT_SECONDS = 600


class TotalTimeout(TimeoutError):
    pass


def _remaining(deadline: float, cap: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TotalTimeout()
    return min(remaining, cap)

from programming_agent_runner.worker_patch import (
    PatchValidationError,
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
    diagnostics: tuple[str, ...] = ()


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
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "XDG_CONFIG_HOME": str(home),
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(cwd: Path, env: dict, *args: str, deadline: float) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=cwd, env=env, capture_output=True, check=True, timeout=_remaining(deadline, 60),
    ).stdout


def _materialize(source: Path, workspace: Path, env: dict, base: str, root: str, extra: tuple[str, ...] = (), *, deadline: float) -> None:
    """Export only regular tracked files of the configured component, no .git or control tree."""
    if _git(source, env, "rev-parse", "HEAD", deadline=deadline).decode().strip() != base:
        raise ValueError("base drift")
    entries = _git(source, env, "ls-tree", "-r", "-z", base, "--", root, *extra, deadline=deadline)
    for entry in entries.split(b"\0"):
        _remaining(deadline, 60)
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        path = raw_path.decode("utf-8")
        parts = PurePosixPath(path).parts
        if (mode not in ("100644", "100755") or kind != "blob"
                or not (_within(path, root) or path in extra) or any(p in (".git", "..") for p in parts)
                or path.startswith("/")):
            raise ValueError("unsafe component tree")
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git(source, env, "cat-file", "blob", oid, deadline=deadline))
        target.chmod(0o755 if mode == "100755" else 0o644)
    _git(workspace, env, "init", "-q", "--template=", deadline=deadline)
    _git(workspace, env, "add", "-f", "--", ".", deadline=deadline)
    _git(workspace, env, "-c", "user.name=LF", "-c", "user.email=lf@example.invalid",
         "commit", "-qm", "format baseline", deadline=deadline)


def _run(command: AcceptanceCommand, workspace: Path, env: dict, *, deadline: float | None = None) -> tuple[int, str]:
    """Read incrementally, fail closed on overflow, kill process group on exit."""
    limit = min(command.max_output_bytes, 32000)
    command_deadline = time.monotonic() + command.timeout_seconds
    if deadline is not None:
        _remaining(deadline, command.timeout_seconds)
        command_deadline = min(deadline, command_deadline)
    proc = subprocess.Popen(
        list(command.argv), cwd=workspace, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    deadline = command_deadline
    data = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise subprocess.TimeoutExpired(command.argv, command.timeout_seconds)
                chunk = os.read(proc.stdout.fileno(), min(4096, limit - len(data) + 1))
                if not chunk:
                    break
                if len(data) + len(chunk) > limit:
                    raise ValueError("format output limit exceeded")
                data.extend(chunk)
        code = proc.wait(timeout=max(0, deadline - time.monotonic()))
        return code, data.decode("utf-8", errors="replace")
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()


def _safe_change(path: str, component: dict) -> bool:
    # Only known inert data and Java sources are admitted to the disposable
    # format execution. Unknown build/config/scripts are deferred to the
    # unchanged Worker, not declared invalid by this optional gate.
    if path.endswith(".java") and any(
        _within(path, root) for root in component["source_roots"]
    ):
        return True
    parts = PurePosixPath(path).parts
    if any(part.startswith(".") for part in parts):
        return False
    return path.endswith((".md", ".txt", ".sql", ".json", ".yaml", ".yml")) and not _within(
        path, component["root"]
    )


def _apply(workspace: Path, env: dict, parsed, facts, *, deadline: float) -> None:
    """Equivalent strict Git application; vendor helper omits HOME/XDG isolation.

    Keep its parse/inspect policy and whitespace checks, but use our explicit
    environment for every Git operation, including application.
    """
    from programming_agent_runner.worker_secrets import secret_text_reason
    args = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "core.attributesFile=/dev/null", "apply", "--index",
            "--whitespace=error-all"]
    for flags in (["--check"], []):
        result = subprocess.run(args + flags + ["-"], cwd=workspace, env=env,
                                input=parsed.patch.encode("utf-8"), capture_output=True,
                                timeout=_remaining(deadline, 60), check=False)
        if result.returncode:
            raise PatchValidationError("patch application rejected")
    raw = _git(workspace, env, "diff", "--cached", "--name-only", "-z", "--no-renames", deadline=deadline)
    if tuple(sorted(p.decode() for p in raw.split(b"\0") if p)) != facts.changed_paths:
        raise PatchValidationError("changed paths mismatch")
    _git(workspace, env, "diff", "--cached", "--check", deadline=deadline)
    for path in facts.changed_paths:
        _remaining(deadline, 60)
        target = workspace / path
        if target.is_symlink() or (target.is_file() and
                secret_text_reason(target.read_text(encoding="utf-8", errors="replace"))):
            raise PatchValidationError("unsafe changed file")


@dataclass(frozen=True)
class Diagnosis:
    paths: tuple[str, ...]
    locations: tuple[str, ...]
    complete: bool


def _diagnose(output: str, changed: tuple[str, ...], root: str) -> Diagnosis | None:
    """Allow only complete attributable Spotless reports; never export source text."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    marker = "The following files had format violations:"
    if marker not in clean:
        return None
    allowed = {p.removeprefix(root + "/"): p for p in changed if _within(p, root)}
    current = None
    paths = set()
    locations = []
    complete = True
    ended = False
    active = False
    for line in clean.splitlines():
        if marker in line:
            if active:
                complete = False
            active = True
            continue
        if not active or ended:
            continue
        if line.startswith("[ERROR] Run 'mvn spotless:apply' to fix these violations."):
            ended = True
            continue
        # Include ALL file header candidates, even non-Java/unknown paths.
        header = re.fullmatch(r"\[ERROR\] {5}(\S.*)", line)
        if header:
            current = allowed.get(header.group(1))
            if current is None or current in paths:
                complete = False
            else:
                paths.add(current)
            continue
        hunk = re.fullmatch(r"\[ERROR\] {9}@@ -(\d{1,8})(?:,(\d{1,8}))? \+(\d{1,8})(?:,(\d{1,8}))? @@", line)
        if hunk:
            if current is None or len(locations) >= 32:
                complete = False
            else:
                a, b, c, d = hunk.groups()
                locations.append(f"{current}: original line {a}, {b or '1'} lines; formatted line {c}, {d or '1'} lines")
            continue
        # Only unified-diff body lines are expected inside the report.
        if not re.fullmatch(r"\[ERROR\] {9}[ +\-].*", line):
            complete = False
    complete = (complete and ended and bool(paths) and
                all(any(row.startswith(p + ":") for row in locations) for p in paths))
    return Diagnosis(tuple(sorted(paths)), tuple(locations), complete)


def prevalidate(source: Path, spec: WorkerTaskSpec, proposal: dict, config: dict,
                *, total_timeout_seconds: float = TOTAL_TIMEOUT_SECONDS) -> FormatResult:
    """Run the proposal first; only a complete attributable failure checks base.

    One shared monotonic deadline covers both runs and Git preparation.
    SKIPPED defers to the unchanged Worker. Only FORMAT_FAIL is attributable.
    """
    deadline = time.monotonic() + min(total_timeout_seconds, TOTAL_TIMEOUT_SECONDS)
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
    if any(not _safe_change(path, component) for path in facts.changed_paths):
        return FormatResult("SKIPPED", "FORMAT_UNSAFE_TO_PREFLIGHT", command.name)
    root = component["root"]
    extra = tuple(p for p in facts.changed_paths if not _within(p, root))
    try:
        _remaining(deadline, 60)
        with tempfile.TemporaryDirectory(prefix="lf-format-") as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = _env(home)
            workspace = Path(tmp) / "source"
            workspace.mkdir()
            _materialize(source, workspace, env, spec.base_head_sha, root, extra, deadline=deadline)
            if not (workspace / component["build_file"]).is_file():
                return FormatResult("INFRA_ERROR", "FORMAT_BUILD_FILE_MISSING", command.name)
            try:
                _apply(workspace, env, parsed, facts, deadline=deadline)
            except PatchValidationError:
                return FormatResult("INVALID_PROPOSAL", "PATCH_APPLICATION_REJECTED", command.name)
            code, output = _run(command, workspace, env, deadline=deadline)
            _remaining(deadline, 60)
            if code == 0:
                return FormatResult("PASS", "FORMAT_OK", command.name)
            diagnosis = _diagnose(output, facts.changed_paths, root) if code == 1 else None
            if diagnosis is None:
                return FormatResult("INFRA_ERROR", "FORMAT_NONZERO_UNCLASSIFIED", command.name)
            if not diagnosis.complete:
                return FormatResult("INFRA_ERROR", "FORMAT_UNATTRIBUTED_OR_INCOMPLETE", command.name)
            baseline = Path(tmp) / "baseline"
            baseline.mkdir()
            _materialize(source, baseline, env, spec.base_head_sha, root, extra, deadline=deadline)
            if not (baseline / component["build_file"]).is_file():
                return FormatResult("INFRA_ERROR", "FORMAT_BUILD_FILE_MISSING", command.name)
            base_code, base_output = _run(command, baseline, env, deadline=deadline)
            _remaining(deadline, 60)
            if base_code != 0:
                if base_code == 1 and _diagnose(base_output, (), root) is not None:
                    return FormatResult("BASELINE_FAIL", "SPOTLESS_BASELINE_VIOLATIONS", command.name)
                return FormatResult("INFRA_ERROR", "FORMAT_BASELINE_EXECUTION_FAILED", command.name)
            return FormatResult("FORMAT_FAIL", "SPOTLESS_VIOLATIONS", command.name,
                                diagnosis.paths, diagnosis.locations)
    except TotalTimeout:
        return FormatResult("INFRA_ERROR", "FORMAT_TOTAL_TIMEOUT", command.name)
    except subprocess.TimeoutExpired:
        reason = "FORMAT_TOTAL_TIMEOUT" if time.monotonic() >= deadline else "FORMAT_TIMEOUT"
        return FormatResult("INFRA_ERROR", reason, command.name)
    except (OSError, subprocess.SubprocessError, ValueError):
        return FormatResult("INFRA_ERROR", "FORMAT_EXECUTION_FAILED", command.name)
