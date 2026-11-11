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
from derive_context import denial, MAX_BYTES, MAX_CONTEXT, MAX_WRITE

ROOT = Path(__file__).resolve().parents[2]
LOT_PATH = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
LOT_A = tuple(LOT_PATH + name for name in
              ("Reminder.java", "ReminderRepository.java", "InMemoryReminderRepository.java"))
MAX_CONTEXT_FILES = MAX_CONTEXT
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


def check_size(root: Path, task: dict, *, prompt: str) -> dict:
    contexts = task.get("context_path_patterns")
    writes = task.get("write_path_patterns")
    if not isinstance(contexts, list) or not isinstance(writes, list):
        blocked("LOTE_DEMASIADO_GRANDE")
    if len(contexts) > MAX_CONTEXT_FILES or len(writes) > MAX_WRITE_FILES:
        blocked("LOTE_DEMASIADO_GRANDE")
    if not contexts or not writes or len(set(contexts)) != len(contexts) or len(set(writes)) != len(writes):
        blocked("LOTE_CONTEXTO_O_ESCRITURA_INVALIDO")
    # All extensions and areas share the same limits. Never read untracked files.
    tracked = set(git(root, "ls-files").splitlines())
    bytes_total = len(prompt.encode("utf-8"))
    counted = set()
    for name in contexts:
        if (not isinstance(name, str) or name.startswith("/") or
                ".." in PurePosixPath(name).parts or name not in tracked or
                denial(name, is_spec=True)):
            blocked("LOTE_CONTEXTO_FALTANTE")
        path = root / name
        if not path.is_file() or path.is_symlink():
            blocked("LOTE_CONTEXTO_FALTANTE")
        counted.add(name)
    if len(counted) > MAX_CONTEXT_FILES:
        blocked("LOTE_DEMASIADO_GRANDE")
    for name in writes:
        if (not isinstance(name, str) or name.startswith("/") or
                ".." in PurePosixPath(name).parts or
                not name.endswith(ALLOWED_WRITE) or denial(name)):
            blocked("LOTE_ESCRITURA_FUERA_DE_SCOPE")
        path = root / name
        if path.is_symlink():
            blocked("LOTE_ESCRITURA_FUERA_DE_SCOPE")
        if path.exists() and not path.is_file():
            blocked("LOTE_ESCRITURA_FUERA_DE_SCOPE")
        if path.exists():
            counted.add(name)
    for name in counted:
        bytes_total += (root / name).stat().st_size
    if bytes_total > MAX_BYTES:
        blocked("LOTE_DEMASIADO_GRANDE")
    return {"context_files": len(contexts), "write_files": len(writes), "bytes": bytes_total}


def check_task(root: Path, task: dict, *, prompt: str = "") -> dict:
    """Generic fail-closed lot gate; handoff is task-owned, not EX5c-owned."""
    spec = task.get("task_spec", task)
    if not isinstance(spec, dict):
        blocked("LOTE_CONTEXTO_O_ESCRITURA_INVALIDO")
    handoff = task.get("handoff", spec.get("handoff"))
    if handoff is not None:
        if not isinstance(handoff, dict):
            blocked("HANDOFF_LOT_A_MISSING")
        check_handoff(root, handoff)
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
