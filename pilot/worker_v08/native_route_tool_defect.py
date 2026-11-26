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
import hashlib
import subprocess

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
PREACCEPTANCE_TOOL = "pilot/worker_v08/reuse_guard.py"
PREACCEPTANCE_SCHEMA = "LF_NATIVE_PREACCEPTANCE_DEFECT_V1"
PREACCEPTANCE_KEYS = frozenset({"schema_version", "task", "tool", "blocked_code",
    "base_head_sha", "superseded_control_sha", "current_control_sha",
    "superseded_tool_sha256", "current_tool_sha256", "registration_sha256", "request_path", "forgiven", "reason"})
ROW_KEYS = frozenset({"run_id", "proposal_commit_sha", "task_pack_sha256"})


def _verified_legacy(root: Path, task: str, record: dict) -> dict[int, dict]:
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


def historical_bytes(root: Path, commit: str, path: str) -> bytes:
    """Read a regular Git blob, never mutable checkout bytes or symlink targets."""
    entry = subprocess.run(["git", "ls-tree", commit, "--", path], cwd=root,
                           capture_output=True, check=True).stdout
    if not entry.startswith(b"100644 blob ") and not entry.startswith(b"100755 blob "):
        raise ValueError("HISTORICAL_BLOB_INVALID")
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root,
                          capture_output=True, check=True).stdout


def historical_controls(root: Path, old: str, new: str, anchor: str = "HEAD") -> None:
    """Both controls must be on the trusted first-parent main history."""
    if old == new:
        raise ValueError("CONTROL_HISTORY_INVALID")
    for start, end in ((old, new), (new, anchor)):
        history = subprocess.run(["git", "rev-list", "--first-parent", end], cwd=root,
                                 capture_output=True, check=True).stdout.splitlines()
        if start.encode("ascii") not in history:
            raise ValueError("CONTROL_HISTORY_INVALID")


def _verified_preacceptance(root: Path, task: str, record: dict, data: dict) -> dict[int, dict]:
    """Historical, Train-owned evidence survives later tool maintenance."""
    spec = record.get("task_spec")
    if (set(data) != PREACCEPTANCE_KEYS or data.get("task") != task
            or data.get("tool") != PREACCEPTANCE_TOOL
            or data.get("blocked_code") != "DUPLICA_COMPONENTE_EXISTENTE"
            or not isinstance(spec, dict)
            or data.get("base_head_sha") != spec.get("base_head_sha")
            or not isinstance(data.get("reason"), str) or not data["reason"].strip()):
        return {}
    if not all(isinstance(data.get(k), str) and SHA40.fullmatch(data[k])
               for k in ("base_head_sha", "superseded_control_sha", "current_control_sha")):
        return {}
    if not all(isinstance(data.get(k), str) and SHA64.fullmatch(data[k])
               for k in ("superseded_tool_sha256", "current_tool_sha256", "registration_sha256")):
        return {}
    old, new = data["superseded_control_sha"], data["current_control_sha"]
    if data["superseded_tool_sha256"] == data["current_tool_sha256"]:
        return {}
    path = data.get("request_path")
    if not isinstance(path, str) or not re.fullmatch(
            r"pilot/runs/req-[1-9][0-9]*/proposal_requests/" + re.escape(task)
            + r"[.]proposal-request[.]json", path):
        return {}
    try:
        historical_controls(root, old, new)
        for commit, key in ((old, "superseded_tool_sha256"), (new, "current_tool_sha256")):
            if hashlib.sha256(historical_bytes(root, commit, PREACCEPTANCE_TOOL)).hexdigest() != data[key]:
                return {}
        reg = historical_bytes(root, old, f"pilot/worker_v08/native_tasks/{task}.json")
        if (hashlib.sha256(reg).hexdigest() != data["registration_sha256"]
                or json.loads(reg) != record):
            return {}
        request = json.loads(historical_bytes(root, old, path))
        if (request.get("task_name") != task or request.get("base_head_sha") != spec["base_head_sha"]):
            return {}
        pack = request.get("task_pack_sha256")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.CalledProcessError):
        return {}
    rows = data.get("forgiven")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        return {}
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != ROW_KEYS
                or type(row.get("run_id")) is not int or row["run_id"] <= 0
                or row["run_id"] in result
                or not isinstance(row.get("proposal_commit_sha"), str)
                or not SHA40.fullmatch(row["proposal_commit_sha"])
                or not isinstance(row.get("task_pack_sha256"), str)
                or not SHA64.fullmatch(row["task_pack_sha256"])
                or row["task_pack_sha256"] != pack):
            return {}
        result[row["run_id"]] = {"proposal_commit_sha": row["proposal_commit_sha"],
                                 "task_pack_sha256": row["task_pack_sha256"]}
    return result


def verified_route_tool_defects(root: Path, task: str, record: dict) -> dict[int, dict]:
    """Legacy file and immutable per-run preacceptance records can coexist."""
    result = _verified_legacy(root, task, record)
    if not isinstance(task, str) or not TASK.fullmatch(task) or not isinstance(record, dict):
        return result
    folder = Path(root) / "pilot/worker_v08/route_tool_defects" / task
    if folder.is_symlink() or not folder.is_dir():
        return result
    conflicts = set()
    for file in sorted(folder.glob("*.json")):
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 4096:
            continue
        try:
            data = json.loads(file.read_text("utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != PREACCEPTANCE_SCHEMA:
                continue
            rows = _verified_preacceptance(root, task, record, data)
        except (OSError, ValueError):
            continue
        if len(rows) != 1 or file.stem != str(next(iter(rows))):
            continue
        for run_id, row in rows.items():
            if run_id in result and result[run_id] != row:
                conflicts.add(run_id)
            else:
                result[run_id] = row
    return {k: v for k, v in result.items() if k not in conflicts}
