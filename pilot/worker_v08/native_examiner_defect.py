"""T32: governed forgiveness of attempts spent on a defective hidden exam.

A record pilot/worker_v08/examiner_defects/<task>.json, merged through the
Train like any other change, may list exact Worker runs whose failure was
caused by the independent examiner's exam. It is honoured only if:

* the registration now binds a different exam (current_holdout_sha256 equals
  the registered holdout_sha256 and differs from superseded_holdout_sha256);
* each forgiven run is named by run id, proposal commit and task pack SHA.

Forgiven runs stay in GitHub history but do not consume a constructor
attempt. Nothing here reads, decrypts or infers an exam.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

SCHEMA = "LF_NATIVE_EXAMINER_DEFECT_V1"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
KEYS = frozenset({"schema_version", "task", "superseded_holdout_sha256",
                  "current_holdout_sha256", "forgiven", "reason"})
ROW_KEYS = frozenset({"run_id", "proposal_commit_sha", "task_pack_sha256"})


def verified_examiner_defects(root: Path, task: str, record: dict) -> dict[int, dict]:
    """Return {run_id: {proposal_commit_sha, task_pack_sha256}} or {}."""
    if not isinstance(task, str) or not TASK.fullmatch(task) or not isinstance(record, dict):
        return {}
    file = root / "pilot/worker_v08/examiner_defects" / (task + ".json")
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 4096:
        return {}
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    if (not isinstance(data, dict) or set(data) != KEYS
            or data.get("schema_version") != SCHEMA or data.get("task") != task
            or not isinstance(data.get("reason"), str) or not data["reason"].strip()):
        return {}
    current, old = data.get("current_holdout_sha256"), data.get("superseded_holdout_sha256")
    if (not isinstance(current, str) or not SHA64.fullmatch(current)
            or not isinstance(old, str) or not SHA64.fullmatch(old)
            or current == old or record.get("holdout_sha256") != current):
        return {}
    rows = data.get("forgiven")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        return {}
    result: dict[int, dict] = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != ROW_KEYS
                or type(row.get("run_id")) is not int or row["run_id"] <= 0
                or row["run_id"] in result
                or not isinstance(row.get("proposal_commit_sha"), str)
                or not SHA40.fullmatch(row["proposal_commit_sha"])
                or not isinstance(row.get("task_pack_sha256"), str)
                or not SHA64.fullmatch(row["task_pack_sha256"])):
            return {}
        result[row["run_id"]] = {"proposal_commit_sha": row["proposal_commit_sha"],
                                 "task_pack_sha256": row["task_pack_sha256"]}
    return result
