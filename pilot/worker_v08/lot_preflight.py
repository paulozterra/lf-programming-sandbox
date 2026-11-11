#!/usr/bin/env python3
"""No-model gates for two independent WorkerTaskSpec V1 reminder lots.

Only tracked repository files are counted. Never read hidden oracles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from derive_context import denial, MAX_BYTES, MAX_WRITE

# Reuse the exact Worker path-pattern semantics without changing vendor/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vendor/programming-agent/src"))
from programming_agent_runner.worker_spec import path_matches_pattern, canonical_relative_path, TaskSpecError

ROOT = Path(__file__).resolve().parents[2]
LOT_PATH = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
LOT_A = tuple(LOT_PATH + name for name in
              ("Reminder.java", "ReminderRepository.java", "InMemoryReminderRepository.java"))
MAX_CONTEXT_FILES = 32
MAX_WRITE_FILES = MAX_WRITE
ALLOWED_WRITE = (".java", ".ts", ".tsx", ".sql")


class LotBlocked(ValueError):
    pass


def blocked(reason: str) -> None:
    raise LotBlocked(reason)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args],
                            check=True, capture_output=True, text=True, timeout=30)
    return result.stdout


def sha_registration(task: str, catalog: dict) -> str:
    expected = {"ex4a": "cd0e9d7fc73aa92280b162e8c0f3f79d98cd7046b5626737666df97080f2af54",
                "ex4b": "8df8ec9858e8dd0078e955b285bac110becc781b55280b17edd9b811d44a900c"}
    if task not in expected:
        blocked("LOTE_TAREA_DESCONOCIDA")
    entry = catalog.get("tasks", {}).get(task, {})
    actual = entry.get("holdout_sha256")
    if actual != expected[task]:
        blocked("LOTE_HOLDOUT_SHA_DRIFT")
    return actual


def check_handoff(root: Path, handoff: dict | None = None) -> str:
    """Lot A must be part of a real PR merge on first-parent main history."""
    if handoff is not None:
        predecessor = handoff.get("previous_lot")
        produced = handoff.get("expected_files")
        if not isinstance(predecessor, str) or not predecessor or not isinstance(produced, list) or not produced:
            blocked("HANDOFF_LOT_A_MISSING")
        if any(not isinstance(p, str) or p.startswith("/") or
               ".." in PurePosixPath(p).parts or denial(p) or
               not (root / p).is_file() or (root / p).is_symlink() for p in produced):
            blocked("HANDOFF_LOT_A_MISSING")
        return predecessor
    if any(not (root / item).is_file() or (root / item).is_symlink() for item in LOT_A):
        blocked("HANDOFF_LOT_A_MISSING")
    history = git(root, "log", "--first-parent", "-n", "150", "--format=%H")
    for sha in history.splitlines():
        message = git(root, "show", "-s", "--format=%B", sha)
        if not (re.search(r"(?i)(?:ex4a|lot[eo][ -]?a|lote[ -]?a)", message)
                and re.search(r"(?:Merge pull request #\d+|\(#\d+\))", message)):
            continue
        # GitHub squash merges have one parent, regular merges two; compare
        # the base parent against the actual committed lot A content.
        try:
            parent = git(root, "rev-parse", sha + "^1").strip()
            added = set(git(root, "diff", "--name-only", "--diff-filter=A",
                            parent, sha, "--", *LOT_A).splitlines())
        except subprocess.CalledProcessError:
            blocked("HANDOFF_LOT_A_MISSING")
        if added == set(LOT_A):
            return sha
    blocked("HANDOFF_LOT_A_MISSING")


_SHA40 = re.compile(r"[0-9a-f]{40}\Z")


def _git_bytes(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, timeout=30).stdout
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        blocked("LOTE_BASE_INVALIDA")


def base_tree(root: Path, base: str) -> dict[str, tuple[str, str]]:
    """Inspect committed task base, never the mutable checkout or index."""
    if not isinstance(base, str) or _SHA40.fullmatch(base) is None:
        blocked("LOTE_BASE_INVALIDA")
    if _git_bytes(root, "cat-file", "-t", base).strip() != b"commit":
        blocked("LOTE_BASE_INVALIDA")
    # CI pull-request checkouts are detached and may have only origin/main.
    # Never accept the PR's HEAD as the trust boundary.
    main = None
    for candidate in ("refs/remotes/origin/main", "refs/heads/main"):
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", candidate],
            check=False, capture_output=True, timeout=30)
        if probe.returncode == 0:
            main = probe.stdout.decode("ascii").strip()
            break
    if main is None:
        blocked("LOTE_BASE_INVALIDA")
    try:
        subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                        base, main], check=True, capture_output=True, timeout=30)
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        blocked("LOTE_BASE_INVALIDA")
    records = _git_bytes(root, "ls-tree", "-rz", "--full-tree", base).split(b"\0")
    entries = {}
    for row in records:
        if not row:
            continue
        try:
            metadata, raw_path = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            blocked("LOTE_BASE_INVALIDA")
        entries[path] = (mode, oid) if kind == "blob" else (mode, "")
    return entries


def _base_blob_bytes(root: Path, base: str, name: str, entries: dict) -> int:
    mode, oid = entries[name]
    if mode not in ("100644", "100755") or not re.fullmatch(r"[0-9a-f]{40}", oid):
        blocked("LOTE_CONTEXTO_FALTANTE")
    try:
        size = int(_git_bytes(root, "cat-file", "-s", oid).decode("ascii").strip())
        data = _git_bytes(root, "show", base + ":" + name)
    except (ValueError, UnicodeError):
        blocked("LOTE_BASE_INVALIDA")
    if size != len(data):
        blocked("LOTE_BASE_INVALIDA")
    return size


def check_size(root: Path, task: dict, *, prompt: str) -> dict:
    contexts = task.get("context_path_patterns")
    writes = task.get("write_path_patterns")
    if not isinstance(contexts, list) or not isinstance(writes, list):
        blocked("LOTE_DEMASIADO_GRANDE")
    if len(writes) > MAX_WRITE_FILES:
        blocked("LOTE_DEMASIADO_GRANDE")
    if not contexts or not writes or len(set(contexts)) != len(contexts) or len(set(writes)) != len(writes):
        blocked("LOTE_CONTEXTO_O_ESCRITURA_INVALIDO")
    base = task.get("base_head_sha")
    entries = base_tree(root, base)
    expanded = set()
    for pattern in contexts:
        try:
            canonical_relative_path(pattern)
        except TaskSpecError:
            blocked("LOTE_CONTEXTO_FALTANTE")
        matches = [name for name in entries if path_matches_pattern(name, pattern)]
        if not matches:
            blocked("LOTE_CONTEXTO_FALTANTE")
        for name in matches:
            mode, _ = entries[name]
            if mode not in ("100644", "100755") or denial(name, is_spec=True):
                blocked("LOTE_CONTEXTO_FALTANTE")
            expanded.add(name)
        if len(expanded) > MAX_CONTEXT_FILES:
            blocked("LOTE_DEMASIADO_GRANDE")
    for name in writes:
        try:
            canonical_relative_path(name)
        except TaskSpecError:
            blocked("LOTE_ESCRITURA_FUERA_DE_SCOPE")
        if not name.endswith(ALLOWED_WRITE) or denial(name):
            blocked("LOTE_ESCRITURA_FUERA_DE_SCOPE")
        if name in entries and entries[name][0] not in ("100644", "100755"):
            blocked("LOTE_ESCRITURA_FUERA_DE_SCOPE")
    counted = expanded | (set(writes) & set(entries))
    bytes_total = len(prompt.encode("utf-8"))
    for name in sorted(counted):
        bytes_total += _base_blob_bytes(root, base, name, entries)
        if bytes_total > MAX_BYTES:
            blocked("LOTE_DEMASIADO_GRANDE")
    return {"context_files": len(expanded), "write_files": len(writes), "bytes": bytes_total}


def check_task(root: Path, task: dict, *, prompt: str = "") -> dict:
    """Generic gate using the task's immutable ancestor of main."""
    spec = task.get("task_spec", task)
    if not isinstance(spec, dict):
        blocked("LOTE_CONTEXTO_O_ESCRITURA_INVALIDO")
    # Validate the base before accessing handoff or any context bytes.
    base = spec.get("base_head_sha")
    tree = base_tree(root, base)
    handoff = task.get("handoff", spec.get("handoff"))
    if handoff is not None:
        if not isinstance(handoff, dict):
            blocked("HANDOFF_LOT_A_MISSING")
        prior = handoff.get("previous_lot")
        produced = handoff.get("expected_files")
        if not isinstance(prior, str) or not prior or not isinstance(produced, list) or not produced:
            blocked("HANDOFF_LOT_A_MISSING")
        if any(not isinstance(path, str) or path not in tree or
               tree[path][0] not in ("100644", "100755") or denial(path)
               for path in produced):
            blocked("HANDOFF_LOT_A_MISSING")
    return check_size(root, spec, prompt=prompt)


def preflight(root: Path, task_name: str) -> dict:
    from task_selector import select

    task = select(task_name, require_holdout=True)
    catalog = json.loads((root / "pilot/worker_v08/tasks.json").read_text(encoding="utf-8"))
    sha_registration(task_name, catalog)
    if task_name == "ex4b":
        check_handoff(root)
    # Include the fixed vendored system prompt and serialized WorkerTaskSpec
    # objective/fields in the conservative premodel byte accounting.
    sys.path.insert(0, str(root / "vendor/programming-agent/src"))
    from programming_agent_runner.worker import WORKER_SYSTEM_INSTRUCTION
    prompt = WORKER_SYSTEM_INSTRUCTION + "\n" + json.dumps(task, ensure_ascii=False)
    return check_task(root, task, prompt=prompt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("ex4a", "ex4b"))
    parser.add_argument("--task-file", type=Path)
    args = parser.parse_args()
    try:
        if bool(args.task) == bool(args.task_file):
            blocked("LOTE_TAREA_DESCONOCIDA")
        if args.task_file:
            registration = json.loads(args.task_file.read_text(encoding="utf-8"))
            result = check_task(ROOT, registration)
        else:
            result = preflight(ROOT, args.task)
    except LotBlocked as exc:
        print(str(exc))
        return 1
    print("LOTE_PREFLIGHT_PASS context_files={context_files} write_files={write_files} bytes={bytes}".format(**result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
