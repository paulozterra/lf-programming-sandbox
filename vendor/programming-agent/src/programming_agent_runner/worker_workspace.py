from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashutil import is_transient_path, sha256_bytes, sha256_file, source_snapshot_sha256
from .worker_secrets import secret_text_reason, sensitive_path_reason
from .worker_spec import TaskSpecError, WorkerTaskSpec, canonical_relative_path, path_matches_any


class WorkspaceError(RuntimeError):
    """Raised when the source identity or disposable workspace cannot be proven."""


@dataclass(frozen=True)
class SourceIdentity:
    head_sha: str
    source_snapshot_sha256: str
    tracked_paths: tuple[str, ...]


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }


def _git(root: Path, args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        cwd=root,
        env=_git_environment(),
        capture_output=True,
        check=check,
    )


def _source_paths(root: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for candidate in sorted(root.rglob("*")):
        relative = candidate.relative_to(root)
        if is_transient_path(relative):
            continue
        if candidate.is_symlink():
            raise WorkspaceError(f"source repository contains a symlink: {relative.as_posix()}")
        if candidate.is_file():
            paths.append(relative.as_posix())
    return tuple(paths)


def verify_source_repository(root: Path, spec: WorkerTaskSpec) -> SourceIdentity:
    root = root.resolve()
    if not root.is_dir():
        raise WorkspaceError("repo_path is not a directory")
    head = _git(root, ["rev-parse", "--verify", "HEAD"])
    if head.returncode != 0:
        raise WorkspaceError("repo_path is not a readable Git worktree")
    actual_head = head.stdout.decode("ascii", errors="strict").strip()
    if actual_head != spec.base_head_sha:
        raise WorkspaceError(f"BASE_HEAD_DRIFT: expected {spec.base_head_sha}, observed {actual_head}")
    status = _git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    if status.returncode != 0 or status.stdout:
        raise WorkspaceError("SOURCE_WORKTREE_NOT_CLEAN")
    try:
        actual_snapshot = source_snapshot_sha256(root)
    except (OSError, ValueError) as exc:
        raise WorkspaceError(f"SOURCE_SNAPSHOT_UNREADABLE: {exc}") from exc
    if actual_snapshot != spec.source_snapshot_sha256:
        raise WorkspaceError(
            f"SOURCE_SNAPSHOT_DRIFT: expected {spec.source_snapshot_sha256}, observed {actual_snapshot}"
        )
    tracked = _git(root, ["ls-files", "-z", "--cached"])
    if tracked.returncode != 0:
        raise WorkspaceError("cannot enumerate tracked source files")
    try:
        tracked_paths = tuple(sorted(item.decode("utf-8") for item in tracked.stdout.split(b"\0") if item))
        canonical_tracked = tuple(canonical_relative_path(path, "tracked path") for path in tracked_paths)
    except (UnicodeDecodeError, TaskSpecError) as exc:
        raise WorkspaceError(f"tracked path is not canonical UTF-8: {exc}") from exc
    if len(set(canonical_tracked)) != len(canonical_tracked):
        raise WorkspaceError("tracked source path universe contains duplicates")
    source_paths = _source_paths(root)
    if source_paths != canonical_tracked:
        missing = sorted(set(canonical_tracked) - set(source_paths))[:10]
        extra = sorted(set(source_paths) - set(canonical_tracked))[:10]
        raise WorkspaceError(f"TRACKED_SOURCE_UNIVERSE_MISMATCH missing={missing} extra={extra}")
    return SourceIdentity(actual_head, actual_snapshot, canonical_tracked)


def _copy_paths(source: Path, destination: Path, paths: tuple[str, ...]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative in paths:
        source_file = source / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, target, follow_symlinks=False)
        mode = source_file.stat().st_mode
        target.chmod(stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if mode & stat.S_IXUSR else 0))


def create_disposable_workspace(source: Path, destination: Path, identity: SourceIdentity) -> None:
    _copy_paths(source.resolve(), destination, identity.tracked_paths)
    copied_snapshot = source_snapshot_sha256(destination)
    if copied_snapshot != identity.source_snapshot_sha256:
        raise WorkspaceError("DISPOSABLE_COPY_SNAPSHOT_MISMATCH")
    _initialize_disposable_git(destination)


def _initialize_disposable_git(destination: Path) -> None:
    template = destination.parent / f"{destination.name}-empty-git-template"
    template.mkdir(parents=False, exist_ok=False)
    initialized = _git(destination, ["init", "--quiet", "--initial-branch=worker", f"--template={template}"])
    if initialized.returncode != 0:
        raise WorkspaceError("cannot initialize disposable Git workspace")
    for key, value in (("user.name", "Programming Agent Worker"), ("user.email", "worker@invalid.local")):
        if _git(destination, ["config", "--local", key, value]).returncode != 0:
            raise WorkspaceError("cannot configure disposable Git workspace")
    if _git(destination, ["add", "--all"]).returncode != 0:
        raise WorkspaceError("cannot stage disposable baseline")
    commit = _git(destination, ["commit", "--quiet", "--no-gpg-sign", "-m", "worker baseline"])
    if commit.returncode != 0:
        raise WorkspaceError("cannot commit disposable baseline")
    shutil.rmtree(template)


def _tracked_workspace_paths(workspace: Path) -> tuple[str, ...]:
    result = _git(workspace, ["ls-files", "-z", "--cached"])
    if result.returncode != 0:
        raise WorkspaceError("cannot inventory disposable workspace")
    try:
        return tuple(sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item))
    except UnicodeDecodeError as exc:
        raise WorkspaceError("workspace contains a non-UTF-8 path") from exc


def build_model_context(workspace: Path, spec: WorkerTaskSpec) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    payload_bytes = 0
    matched_paths = [
        path for path in _tracked_workspace_paths(workspace) if path_matches_any(path, spec.context_path_patterns)
    ]
    if not matched_paths:
        raise WorkspaceError("CONTEXT_PATTERNS_MATCH_NO_TRACKED_FILES")
    for relative in matched_paths:
        sensitive = sensitive_path_reason(relative)
        if sensitive:
            raise WorkspaceError(f"CONTEXT_CONTAINS_SENSITIVE_PATH: {relative}")
        path = workspace / relative
        if not path.exists():
            continue
        data = path.read_bytes()
        payload_bytes += len(relative.encode("utf-8")) + len(data)
        if payload_bytes > spec.max_context_bytes:
            raise WorkspaceError("CONTEXT_EXCEEDS_MAX_CONTEXT_BYTES")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            files.append({"path": relative, "sha256": sha256_bytes(data), "binary": True, "content": None})
            continue
        secret = secret_text_reason(content)
        if secret:
            raise WorkspaceError(f"CONTEXT_CONTAINS_PROBABLE_SECRET ({secret}): {relative}")
        files.append({"path": relative, "sha256": sha256_file(path), "binary": False, "content": content})
    diff = _git(workspace, ["diff", "--cached", "--no-ext-diff", "--no-renames", "--"])
    if diff.returncode != 0:
        raise WorkspaceError("cannot materialize current cumulative patch")
    if len(diff.stdout) + payload_bytes > spec.max_context_bytes:
        raise WorkspaceError("CONTEXT_PLUS_PATCH_EXCEEDS_MAX_CONTEXT_BYTES")
    try:
        cumulative_patch = diff.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("cumulative patch is not UTF-8") from exc
    return {
        "files": files,
        "current_changed_paths": list(changed_paths(workspace)),
        "current_patch": cumulative_patch,
    }


def changed_paths(workspace: Path) -> tuple[str, ...]:
    paths = _git(workspace, ["diff", "--cached", "--name-only", "-z", "--no-renames", "--"])
    if paths.returncode != 0:
        raise WorkspaceError("cannot reconcile changed paths")
    try:
        return tuple(sorted(item.decode("utf-8") for item in paths.stdout.split(b"\0") if item))
    except UnicodeDecodeError as exc:
        raise WorkspaceError("changed path is not UTF-8") from exc


def cumulative_patch(workspace: Path) -> str:
    result = _git(workspace, ["diff", "--cached", "--no-ext-diff", "--no-renames", "--"])
    if result.returncode != 0:
        raise WorkspaceError("cannot export cumulative patch")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("cumulative patch is not UTF-8") from exc


def replay_cumulative_patch(workspace: Path, patch: str) -> None:
    if not patch:
        return
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "apply",
            "--index",
            "--whitespace=error-all",
            "-",
        ],
        cwd=workspace,
        env=_git_environment(),
        input=patch.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[:2000]
        raise WorkspaceError(f"cannot replay cumulative patch: {detail}")


def copy_candidate_for_commands(workspace: Path, destination: Path) -> None:
    paths = _tracked_workspace_paths(workspace)
    existing = tuple(path for path in paths if (workspace / path).is_file())
    _copy_paths(workspace, destination, existing)
    _initialize_disposable_git(destination)
