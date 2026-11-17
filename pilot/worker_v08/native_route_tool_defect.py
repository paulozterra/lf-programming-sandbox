"""T37: governed forgiveness of attempts spent on a defective route tool.

A record pilot/worker_v08/route_tool_defects/<task>.json, merged through the
Train like any other change, lists exact Worker runs whose visible failure
came from a trusted route tool (ROUTE_TOOLS) that was later fixed on main.
It is honoured only if:

* the registration was re-pinned to the fixed base (current_base_sha equals
  the registered base_head_sha and differs from superseded_base_sha);
* the tool bytes differ between both bases (superseded/current tool SHA-256);
* each forgiven run is named by run id, proposal commit and task pack SHA.

The record is produced by pilot/orchestrator/route_tool_defect.py, which
proves that the very same proposal fails with the superseded tool and passes
with the fixed one. Forgiven runs stay in history but do not consume an
attempt. Nothing here reads, decrypts or infers a hidden exam.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

try:
    from native_route_defect import ROUTE_TOOLS
except ImportError:  # imported as pilot.worker_v08.native_route_tool_defect
    from pilot.worker_v08.native_route_defect import ROUTE_TOOLS

SCHEMA = "LF_NATIVE_ROUTE_TOOL_DEFECT_V1"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
KEYS = frozenset({"schema_version", "task", "tool", "blocked_code",
                  "superseded_base_sha", "current_base_sha",
                  "superseded_tool_sha256", "current_tool_sha256",
                  "forgiven", "reason"})
ROW_KEYS = frozenset({"run_id", "proposal_commit_sha", "task_pack_sha256"})


def verified_route_tool_defects(root: Path, task: str, record: dict) -> dict[int, dict]:
    """Return {run_id: {proposal_commit_sha, task_pack_sha256}} or {}."""
    if not isinstance(task, str) or not TASK.fullmatch(task) or not isinstance(record, dict):
        return {}
    file = Path(root) / "pilot/worker_v08/route_tool_defects" / (task + ".json")
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 4096:
        return {}
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    if (not isinstance(data, dict) or set(data) != KEYS
            or data.get("schema_version") != SCHEMA or data.get("task") != task
            or data.get("tool") not in ROUTE_TOOLS
            or not isinstance(data.get("blocked_code"), str)
            or not CODE.fullmatch(data["blocked_code"])
            or not isinstance(data.get("reason"), str) or not data["reason"].strip()):
        return {}
    old, new = data.get("superseded_base_sha"), data.get("current_base_sha")
    old_tool, new_tool = data.get("superseded_tool_sha256"), data.get("current_tool_sha256")
    spec = record.get("task_spec")
    if (not all(isinstance(x, str) and SHA40.fullmatch(x) for x in (old, new))
            or not all(isinstance(x, str) and SHA64.fullmatch(x) for x in (old_tool, new_tool))
            or old == new or old_tool == new_tool
            or not isinstance(spec, dict) or spec.get("base_head_sha") != new):
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
