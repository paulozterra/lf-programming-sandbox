#!/usr/bin/env python3
"""No-model guards for the two-lot LF sandbox pilot (never read hidden oracles)."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Mapping

LIMIT_BYTES = 240_000
MAX_CONTEXT_FILES = 12
MAX_WRITE_FILES = 6
A_FILES = tuple(
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/" + name
    for name in ("Reminder.java", "ReminderRepository.java", "InMemoryReminderRepository.java")
)
B_TEST = "apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderControllerVisibleTest.java"


class LotBlocked(ValueError):
    pass


def block(code: str) -> None:
    raise LotBlocked(code)


def _files(root: Path, patterns: list[str], *, must_exist: bool) -> list[Path]:
    collected: dict[str, Path] = {}
    for raw in patterns:
        if (not isinstance(raw, str) or not raw or raw.startswith("/")
            or "\\" in raw or ".." in Path(raw).parts):
            block("LOTE_DEMASIADO_GRANDE")
        matches = list(root.glob(raw)) if "*" in raw or "?" in raw else [root / raw]
        if must_exist and not any(p.is_file() for p in matches):
            block("LOTE_CONTEXTO_FALTANTE")
        for path in matches:
            if not path.exists():
                continue  # New write target, charged 0 current bytes.
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                block("LOTE_DEMASIADO_GRANDE")
            collected[path.relative_to(root).as_posix()] = path
    return list(collected.values())


def check_lot_size(root: Path, task: Mapping, prompt: bytes) -> dict:
    """Measure actual UTF-8 files + prompt, include current write-path bytes."""
    if not isinstance(prompt, bytes):
        block("LOTE_DEMASIADO_GRANDE")
    c = task["context_path_patterns"]
    w = task["write_path_patterns"]
    if (not isinstance(c, list) or not isinstance(w, list)
        or len(c) > MAX_CONTEXT_FILES or len(w) > MAX_WRITE_FILES):
        block("LOTE_DEMASIADO_GRANDE")
    contexts = _files(root, c, must_exist=True)
    writes = _files(root, w, must_exist=False)
    if len(contexts) > MAX_CONTEXT_FILES or len(writes) > MAX_WRITE_FILES:
        block("LOTE_DEMASIADO_GRANDE")
    # Count a file only once if its path appears in both groups.
    files = {p.relative_to(root).as_posix(): p for p in [*contexts, *writes]}
    size = len(prompt) + sum(p.stat().st_size for p in files.values())
    if size > LIMIT_BYTES:
        block("LOTE_DEMASIADO_GRANDE")
    return {"total_bytes": size, "context_file_count": len(contexts),
            "write_file_count": len(w), "status": "LOT_SIZE_PASS"}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], check=False,
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        block("HANDOFF_LOT_A_MISSING")
    return result.stdout.strip()


def check_handoff(root: Path) -> str:
    """All three A files must have arrived on the first-parent chain via one ex4a PR.

    No source patch is reconstructed and no oracle contents are examined.
    """
    if any(not (root / p).is_file() or (root / p).is_symlink() for p in A_FILES):
        block("HANDOFF_LOT_A_MISSING")
    commits = []
    for p in A_FILES:
        commits_for_path = _git(root, "log", "--first-parent", "--format=%H",
                                "--diff-filter=A", "--", p).splitlines()
        if len(commits_for_path) != 1:
            block("HANDOFF_LOT_A_MISSING")
        commits.append(commits_for_path[0])
    if len(set(commits)) != 1:
        block("HANDOFF_LOT_A_MISSING")
    message = _git(root, "show", "-s", "--format=%B", commits[0])
    # A recognizable, reviewable merge/squash commit carrying a numbered PR.
    if not re.search(r"(?i)ex4a|lot[e -]*a|reminder.*repository", message):
        block("HANDOFF_LOT_A_MISSING")
    if not re.search(r"(?i)(?:merge pull request #\d+|\(#\d+\))", message):
        block("HANDOFF_LOT_A_MISSING")
    return commits[0]


def validate_pre_model(root: Path, task_name: str, task: Mapping, prompt: bytes) -> dict:
    if task_name not in ("ex4a", "ex4b"):
        block("LOT_TASK_NOT_ALLOWED")
    if task_name == "ex4b":
        check_handoff(root)
        if not (root / B_TEST).is_file():
            block("HANDOFF_LOT_A_MISSING")
    return check_lot_size(root, task, prompt)


def main():
    import json
    import sys
    base = Path(__file__).resolve().parents[2]
    name = os.environ.get("PILOT_TASK")
    if name not in ("ex4a", "ex4b"):
        block("LOT_TASK_NOT_ALLOWED")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from task_selector import select
    task = select(name)
    # Count original Worker instructions, owner task objective and serialized
    # task spec as prompt bytes; conservative for extra JSON framing.
    sys.path.insert(0, str(base / "vendor/programming-agent/src"))
    from programming_agent_runner.worker import WORKER_SYSTEM_INSTRUCTION
    prompt = (WORKER_SYSTEM_INSTRUCTION + "\n" + task["objective"] +
              "\n" + json.dumps(task, ensure_ascii=False, sort_keys=True)).encode("utf-8")
    outcome = validate_pre_model(base, name, task, prompt)
    print(f"LOT_PREFLIGHT_PASS task={name} total_bytes={outcome['total_bytes']} "
          f"context_files={outcome['context_file_count']} "
          f"write_paths={outcome['write_file_count']}")


if __name__ == "__main__":
    try:
        main()
    except LotBlocked as exc:
        raise SystemExit(str(exc)) from None
