from __future__ import annotations

from typing import Any

from .models import Status

PASS_CONCLUSIONS = {"success"}
FAIL_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "startup_failure",
    "stale",
}
LEGACY_FAIL_STATES = {"error", "failure"}
CANONICAL_CI_WORKFLOW_NAME = "canonical-ci"
CANONICAL_CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
CANONICAL_CI_CHECK_NAME = "quality"


def _is_truncated(payload: dict[str, Any], runs: list[dict[str, Any]]) -> bool:
    total = payload.get("total_count")
    return isinstance(total, int) and total > len(runs)


def _new_details(workflows: list[dict[str, Any]], checks: list[dict[str, Any]], legacy: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "workflow_count": len(workflows),
        "check_count": len(checks),
        "legacy_status_count": len(legacy),
        "exact_head_workflow_count": 0,
        "missing_exact_head_workflow": False,
        "exact_head_workflow_check_suite_ids": [],
        "exact_head_workflows_missing_check_suite": [],
        "noncanonical_exact_head_candidates": [],
        "exact_head_check_count": 0,
        "missing_exact_head_check": False,
        "quality_check_suite_mismatches": [],
        "execution_receipt_required": True,
        "missing_execution_receipts": [],
        "execution_receipt_mismatches": [],
        "noncanonical_exact_head_checks": [],
        "head_mismatches": [],
        "pending": [],
        "failed": [],
        "unclassified_conclusions": [],
        "truncated_channels": [],
    }


def _inspect_modern_runs(kind: str, items: list[dict[str, Any]], head_sha: str, details: dict[str, Any]) -> None:
    for item in items:
        item_head = item.get("head_sha")
        if item_head not in {None, head_sha}:
            details["head_mismatches"].append({"kind": kind, "item": item})
            continue
        if item.get("status") != "completed":
            details["pending"].append({"kind": kind, "item": item})
            continue
        conclusion = item.get("conclusion")
        if conclusion in FAIL_CONCLUSIONS:
            details["failed"].append({"kind": kind, "item": item})
        elif conclusion not in PASS_CONCLUSIONS:
            details["unclassified_conclusions"].append({"kind": kind, "item": item})


def _inspect_legacy_statuses(items: list[dict[str, Any]], details: dict[str, Any]) -> None:
    for item in items:
        state = item.get("state")
        if state in LEGACY_FAIL_STATES:
            details["failed"].append({"kind": "legacy_status", "item": item})
        elif state == "pending":
            details["pending"].append({"kind": "legacy_status", "item": item})
        elif state != "success":
            details["unclassified_conclusions"].append({"kind": "legacy_status", "item": item})


def _mark_truncation(payload: dict[str, Any], items: list[dict[str, Any]], channel: str, details: dict[str, Any]) -> None:
    if _is_truncated(payload, items):
        details["truncated_channels"].append(channel)


def _is_canonical_exact_head_workflow(item: dict[str, Any], head_sha: str) -> bool:
    return (
        item.get("event") == "push"
        and item.get("head_sha") == head_sha
        and item.get("name") == CANONICAL_CI_WORKFLOW_NAME
        and item.get("path") == CANONICAL_CI_WORKFLOW_PATH
    )


def _mark_exact_head_workflows(
    items: list[dict[str, Any]],
    head_sha: str,
    details: dict[str, Any],
) -> set[int]:
    push_candidates = [
        item
        for item in items
        if item.get("event") == "push" and item.get("head_sha") == head_sha
    ]
    identity_matches = [
        item for item in push_candidates if _is_canonical_exact_head_workflow(item, head_sha)
    ]
    suite_ids = {
        item["check_suite_id"]
        for item in identity_matches
        if isinstance(item.get("check_suite_id"), int)
    }
    details["exact_head_workflow_count"] = len(identity_matches)
    details["missing_exact_head_workflow"] = not identity_matches or not suite_ids
    details["exact_head_workflow_check_suite_ids"] = sorted(suite_ids)
    details["exact_head_workflows_missing_check_suite"] = [
        item for item in identity_matches if not isinstance(item.get("check_suite_id"), int)
    ]
    details["noncanonical_exact_head_candidates"] = [
        item for item in push_candidates if item not in identity_matches
    ]
    return suite_ids


def _has_canonical_check_identity(
    item: dict[str, Any],
    head_sha: str,
    canonical_suite_ids: set[int],
) -> bool:
    return (
        item.get("head_sha") == head_sha
        and item.get("name") == CANONICAL_CI_CHECK_NAME
        and item.get("check_suite_id") in canonical_suite_ids
    )


def _mark_exact_head_checks(
    items: list[dict[str, Any]],
    head_sha: str,
    canonical_suite_ids: set[int],
    details: dict[str, Any],
    *,
    require_execution_receipt: bool,
) -> None:
    details["execution_receipt_required"] = require_execution_receipt
    head_checks = [item for item in items if item.get("head_sha") == head_sha]
    quality_checks = [item for item in head_checks if item.get("name") == CANONICAL_CI_CHECK_NAME]
    identity_matches = [
        item for item in quality_checks if _has_canonical_check_identity(item, head_sha, canonical_suite_ids)
    ]
    exact: list[dict[str, Any]] = []
    for item in identity_matches:
        if not require_execution_receipt:
            exact.append(item)
            continue
        executed_head = item.get("executed_head_sha")
        if executed_head == head_sha:
            exact.append(item)
        elif isinstance(executed_head, str):
            details["execution_receipt_mismatches"].append(item)
        else:
            details["missing_execution_receipts"].append(item)

    details["exact_head_check_count"] = len(exact)
    details["missing_exact_head_check"] = not exact
    details["quality_check_suite_mismatches"] = [
        item for item in quality_checks if not _has_canonical_check_identity(item, head_sha, canonical_suite_ids)
    ]
    details["noncanonical_exact_head_checks"] = [
        item for item in head_checks if item not in exact
    ]


def _derive_status(details: dict[str, Any]) -> Status:
    if (
        details["head_mismatches"]
        or details["failed"]
        or details["execution_receipt_mismatches"]
    ):
        return "FAIL"
    if (
        details["pending"]
        or details["unclassified_conclusions"]
        or details["truncated_channels"]
        or details["missing_exact_head_workflow"]
        or details["missing_exact_head_check"]
        or details["missing_execution_receipts"]
    ):
        return "BLOCKED"
    return "PASS"


def reconcile_ci_evidence(
    workflow_payload: dict[str, Any],
    check_payload: dict[str, Any],
    combined_payload: dict[str, Any],
    head_sha: str,
    *,
    require_execution_receipt: bool = True,
) -> tuple[Status, dict[str, Any]]:
    workflows = list(workflow_payload.get("runs") or [])
    checks = list(check_payload.get("runs") or [])
    legacy_statuses = list(combined_payload.get("statuses") or [])
    details = _new_details(workflows, checks, legacy_statuses)

    missing_channels = [
        name
        for name, values in (("workflow_runs", workflows), ("check_runs", checks))
        if not values
    ]
    if missing_channels:
        details["missing_channels"] = missing_channels
        return "BLOCKED", details

    _mark_truncation(workflow_payload, workflows, "workflow_runs", details)
    _mark_truncation(check_payload, checks, "check_runs", details)
    _mark_truncation(combined_payload, legacy_statuses, "legacy_statuses", details)
    canonical_suite_ids = _mark_exact_head_workflows(workflows, head_sha, details)
    _mark_exact_head_checks(
        checks,
        head_sha,
        canonical_suite_ids,
        details,
        require_execution_receipt=require_execution_receipt,
    )
    _inspect_modern_runs("workflow", workflows, head_sha, details)
    _inspect_modern_runs("check", checks, head_sha, details)
    _inspect_legacy_statuses(legacy_statuses, details)
    return _derive_status(details), details
