"""Pure fail-closed validation for a trusted per-task attempt ledger.

S2 must supply the ledger from a trusted CI-controlled location; a proposal
branch file cannot be trusted as the attempt counter.
"""
from __future__ import annotations

import re

_SHA = re.compile(r"[0-9a-f]{64}\\Z")


def validate_attempt_history(task_id: str, requested_attempt: int, prior: list[dict]) -> None:
    if (not isinstance(task_id, str) or not task_id
        or type(requested_attempt) is not int or not 1 <= requested_attempt <= 3
        or not isinstance(prior, list) or len(prior) != requested_attempt - 1):
        raise ValueError("NATIVE_ATTEMPT_LIMIT_OR_HISTORY_INVALID")
    for position, entry in enumerate(prior, start=1):
        if (not isinstance(entry, dict) or set(entry) != {
            "task_id", "attempt", "task_pack_sha256", "run_id"
        } or entry["task_id"] != task_id or type(entry["attempt"]) is not int
            or entry["attempt"] != position
            or not isinstance(entry["task_pack_sha256"], str)
            or _SHA.fullmatch(entry["task_pack_sha256"]) is None
            or type(entry["run_id"]) is not int or entry["run_id"] <= 0):
            raise ValueError("NATIVE_ATTEMPT_LIMIT_OR_HISTORY_INVALID")
    if len(set(e["run_id"] for e in prior)) != len(prior):
        raise ValueError("NATIVE_ATTEMPT_RUN_REUSED")
