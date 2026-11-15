"""T17.1: shared, fail-closed selection of GitHub CI evidence.

GitHub may publish an action_required workflow event for the same SHA after
an actual workflow_dispatch. A non-executed event must not eclipse executed
CI. Do not infer a green result from an unexecuted event.
"""
from __future__ import annotations


NON_EXECUTED = frozenset(("action_required", "skipped", "neutral", "cancelled"))
EXECUTED_RESULTS = frozenset(("success", "failure", "timed_out"))


def executed_ci_run(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    state, conclusion = row.get("status"), row.get("conclusion")
    if conclusion in NON_EXECUTED:
        return False
    if state == "completed":
        return conclusion in EXECUTED_RESULTS
    if state == "in_progress":
        # An actual in-progress run must prevent retirement based on an
        # older failed run, regardless of its eventual result.
        return True
    return False


def last_executed_ci_run(rows: list[dict]) -> dict | None:
    """Return the last executed run by GitHub chronology, or None."""
    valid = [row for row in rows if executed_ci_run(row)]
    return max(valid, key=lambda x: (
        str(x.get("created_at") or ""),
        x.get("id") if type(x.get("id")) is int else 0,
    ), default=None)


def executed_check(row: dict) -> bool:
    """Only actual check execution can supersede an earlier check."""
    if not isinstance(row, dict) or row.get("conclusion") in NON_EXECUTED:
        return False
    if row.get("status") == "completed":
        return row.get("conclusion") in EXECUTED_RESULTS
    return row.get("status") in ("in_progress", "queued", "pending")


def latest_executed_checks(rows: list[dict], required: tuple[str, ...],
                           sha: str) -> dict[str, dict]:
    """Per-job last executable check on the exact PR head SHA."""
    result = {}
    for row in rows:
        if not executed_check(row):
            continue
        if (row.get("name") not in required or row.get("head_sha") != sha
                or (row.get("app") or {}).get("slug") != "github-actions"
                or type(row.get("id")) is not int):
            continue
        key = row["name"]
        if key not in result or row["id"] > result[key]["id"]:
            result[key] = row
    return result
