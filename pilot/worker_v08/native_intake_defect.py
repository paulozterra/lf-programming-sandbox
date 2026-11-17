"""T38: governed forgiveness of attempts spent on a patch that could not apply.

Since T38 the push guard rejects such a proposal before the Worker
(NATIVE_PUSH_PATCH_NOT_APPLICABLE), so it can no longer spend an attempt.
Runs that spent one before T38 can be forgiven by a record
pilot/worker_v08/intake_defects/<task>.json, merged through the Train, if:

* base_head_sha equals the registered base (the patch was checked against it);
* each forgiven run is named by run id, proposal commit and task pack SHA.

The record is produced by pilot/orchestrator/route_tool_defect.py prove-patch,
which re-checks that the very patch does not apply to that base.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

SCHEMA = "LF_NATIVE_INTAKE_DEFECT_V1"
CODE = "NATIVE_PUSH_PATCH_NOT_APPLICABLE"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
KEYS = frozenset({"schema_version", "task", "code", "base_head_sha", "forgiven", "reason"})
ROW_KEYS = frozenset({"run_id", "proposal_commit_sha", "task_pack_sha256"})


def verified_intake_defects(root: Path, task: str, record: dict) -> dict[int, dict]:
    if not isinstance(task, str) or not TASK.fullmatch(task) or not isinstance(record, dict):
        return {}
    file = Path(root) / "pilot/worker_v08/intake_defects" / (task + ".json")
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 4096:
        return {}
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    spec = record.get("task_spec")
    if (not isinstance(data, dict) or set(data) != KEYS or data.get("schema_version") != SCHEMA
            or data.get("task") != task or data.get("code") != CODE
            or not isinstance(data.get("reason"), str) or not data["reason"].strip()
            or not isinstance(data.get("base_head_sha"), str)
            or not SHA40.fullmatch(data["base_head_sha"])
            or not isinstance(spec, dict) or spec.get("base_head_sha") != data["base_head_sha"]):
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
