from __future__ import annotations

from typing import Any

from .ci_reconcile import (
    CANONICAL_CI_CHECK_NAME,
    reconcile_ci_evidence,
)
from .github_reader import GitHubReadClient, GitHubReadError, GitHubReader
from .hashutil import sha256_evidence_envelope, sha256_json
from .models import Evidence, GateResult, RunnerInput, Status
from .source_integrity import local_source_tree, reconcile_source_tree


def _evidence(
    code: str,
    status: Status,
    source_ref: str,
    head_sha: str,
    payload: dict[str, Any],
) -> Evidence:
    source_system = "GITHUB"
    producer = "RUNNER_GITHUB_EVIDENCE"
    return Evidence(
        code=code,
        status=status,
        source_system=source_system,
        source_ref=source_ref,
        sha256=sha256_evidence_envelope(
            code=code,
            status=status,
            source_system=source_system,
            source_ref=source_ref,
            head_sha=head_sha,
            producer=producer,
            metadata=payload,
        ),
        head_sha=head_sha,
        producer=producer,
        metadata=payload,
    )


def _canonical_test_execution_receipt(
    check_payload: dict[str, Any],
    reconciliation: dict[str, Any],
    head_sha: str,
    *,
    approval_grade_reader: bool,
) -> dict[str, Any]:
    if not approval_grade_reader:
        return {
            "status": "NON_APPROVAL_GRADE_READER",
            "executed_pass_test_ids": [],
            "executed_pass_test_ids_sha256": sha256_json([]),
            "structured_receipts": [],
            "canonical_quality_check_count": 0,
        }

    suite_ids = {
        value
        for value in reconciliation.get("exact_head_workflow_check_suite_ids", [])
        if isinstance(value, int)
    }
    runs = check_payload.get("runs") or []
    exact_checks = [
        item
        for item in runs
        if isinstance(item, dict)
        and item.get("name") == CANONICAL_CI_CHECK_NAME
        and item.get("head_sha") == head_sha
        and item.get("check_suite_id") in suite_ids
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
        and item.get("execution_receipt_status") == "PRESENT"
        and item.get("executed_head_sha") == head_sha
    ]
    if not exact_checks:
        return {
            "status": "MISSING_CANONICAL_QUALITY_CHECK",
            "executed_pass_test_ids": [],
            "executed_pass_test_ids_sha256": sha256_json([]),
            "structured_receipts": [],
            "canonical_quality_check_count": 0,
        }

    receipt_statuses = {item.get("test_execution_receipt_status") for item in exact_checks}
    structured_receipts = [
        {
            "receipt": item.get("structured_test_receipt"),
            "receipt_sha256": item.get("structured_test_receipt_sha256"),
            "artifact_id": item.get("artifact_id"),
            "artifact_digest": item.get("artifact_digest"),
            "artifact_archive_sha256": item.get("artifact_archive_sha256"),
            "run_id": item.get("run_id"),
            "run_attempt": item.get("run_attempt"),
            "job_id": item.get("job_id"),
            "check_suite_id": item.get("check_suite_id"),
        }
        for item in exact_checks
        if item.get("test_execution_receipt_status") == "PRESENT"
        and isinstance(item.get("structured_test_receipt"), dict)
    ]
    passed_ids = sorted(
        {
            value
            for item in exact_checks
            for value in (item.get("executed_pass_test_ids") or [])
            if isinstance(value, str) and value
        }
    )
    nonpass_ids = sorted(
        {
            value
            for item in exact_checks
            for value in (item.get("executed_nonpass_test_ids") or [])
            if isinstance(value, str) and value
        }
    )
    if "INVALID" in receipt_statuses or "AMBIGUOUS" in receipt_statuses:
        status = "INVALID"
    elif "UNAVAILABLE" in receipt_statuses:
        status = "UNAVAILABLE"
    elif receipt_statuses == {"PRESENT"} and passed_ids and len(structured_receipts) == len(exact_checks):
        status = "PRESENT"
    else:
        status = "INCOMPLETE"
    return {
        "status": status,
        "executed_pass_test_ids": passed_ids,
        "executed_pass_test_ids_sha256": sha256_json(passed_ids),
        "executed_nonpass_test_ids": nonpass_ids,
        "structured_receipts": structured_receipts,
        "structured_receipt_errors": sorted(
            {
                error
                for item in exact_checks
                for error in (item.get("structured_test_receipt_errors") or [])
                if isinstance(error, str)
            }
        ),
        "canonical_quality_check_count": len(exact_checks),
        "source_check_ids": sorted(
            item["id"] for item in exact_checks if isinstance(item.get("id"), int)
        ),
    }


def _combine_ci_and_structured_test_status(
    ci_status: Status,
    test_receipt_status: Any,
    *,
    approval_grade_reader: bool,
) -> Status:
    if not approval_grade_reader:
        return ci_status
    if ci_status == "FAIL" or test_receipt_status == "INVALID":
        return "FAIL"
    if ci_status != "PASS" or test_receipt_status != "PRESENT":
        return "BLOCKED"
    return "PASS"


def evaluate_github(input_: RunnerInput, github: GitHubReadClient | None) -> tuple[list[GateResult], list[Evidence]]:
    if github is None:
        return [
            GateResult("G_RUNNER_GITHUB_HEAD_RECONCILE", "BLOCKED", "GitHub reader unavailable; canonical HEAD cannot be reconciled"),
            GateResult("G_RUNNER_CI_RECONCILE", "BLOCKED", "GitHub reader unavailable; CI cannot be reconciled"),
        ], []

    gates: list[GateResult] = []
    evidence: list[Evidence] = []
    try:
        remote_sha = github.resolve_ref(input_.repo_full_name, input_.ref)
        head_payload = {
            "repo": input_.repo_full_name,
            "ref": input_.ref,
            "expected_head": input_.head_sha,
            "remote_head": remote_sha,
        }
        head_status: Status = "PASS" if remote_sha == input_.head_sha else "FAIL"
        head_evidence = _evidence(
            "E_GITHUB_HEAD",
            head_status,
            f"{input_.repo_full_name}@{input_.ref}",
            input_.head_sha,
            head_payload,
        )
        evidence.append(head_evidence)

        local_tree = local_source_tree(input_.repo_path)
        remote_tree = github.source_tree(input_.repo_full_name, input_.head_sha)
        source_status_value, source_reconciliation = reconcile_source_tree(local_tree, remote_tree)
        source_status: Status = source_status_value  # type: ignore[assignment]
        source_payload = {
            "repo": input_.repo_full_name,
            "head_sha": input_.head_sha,
            "local": local_tree,
            "remote": remote_tree,
            "reconciliation": source_reconciliation,
        }
        source_evidence = _evidence(
            "E_GITHUB_SOURCE_TREE",
            source_status,
            f"{input_.repo_full_name}@{input_.head_sha}",
            input_.head_sha,
            source_payload,
        )
        evidence.append(source_evidence)
        combined_head_status: Status = head_status if head_status == "FAIL" else source_status
        head_reason = (
            "STALE_HEAD_REAUDIT_REQUIRED"
            if head_status == "FAIL"
            else source_reconciliation.get("reason", "SOURCE_TREE_RECONCILIATION_UNKNOWN")
        )
        gates.append(
            GateResult(
                "G_RUNNER_GITHUB_HEAD_RECONCILE",
                combined_head_status,
                head_reason,
                (head_evidence.code, source_evidence.code),
            )
        )

        workflow_payload = github.workflow_runs(input_.repo_full_name, input_.head_sha)
        check_payload = github.check_runs(input_.repo_full_name, input_.head_sha)
        combined_payload = github.combined_status(input_.repo_full_name, input_.head_sha)
        approval_grade_reader = isinstance(github, GitHubReader)
        ci_status, reconciliation = reconcile_ci_evidence(
            workflow_payload,
            check_payload,
            combined_payload,
            input_.head_sha,
            require_execution_receipt=approval_grade_reader,
        )
        test_execution_receipt = _canonical_test_execution_receipt(
            check_payload,
            reconciliation,
            input_.head_sha,
            approval_grade_reader=approval_grade_reader,
        )
        reconciliation["structured_test_receipt_status"] = test_execution_receipt.get("status")
        ci_status = _combine_ci_and_structured_test_status(
            ci_status,
            test_execution_receipt.get("status"),
            approval_grade_reader=approval_grade_reader,
        )
        ci_payload: dict[str, Any] = {
            "combined_status": combined_payload,
            "workflow_runs": workflow_payload,
            "check_runs": check_payload,
            "approval_grade_reader": approval_grade_reader,
            "reconciliation": reconciliation,
            "test_execution_receipt": test_execution_receipt,
        }
        ci_evidence = _evidence(
            "E_GITHUB_CI",
            ci_status,
            f"{input_.repo_full_name}@{input_.head_sha}",
            input_.head_sha,
            ci_payload,
        )
        evidence.append(ci_evidence)
        ci_reason = {
            "PASS": "Canonical CI identity, executed HEAD and structured test artifact reconcile to the pinned HEAD",
            "FAIL": "CI evidence contains failure, identity mismatch, or invalid structured test evidence",
            "BLOCKED": "CI evidence is incomplete, pending, unclassified, or missing an approval-grade HEAD/test receipt",
            "NOT_APPLICABLE": "CI is not applicable",
        }[ci_status]
        gates.append(GateResult("G_RUNNER_CI_RECONCILE", ci_status, ci_reason, (ci_evidence.code,)))
        return gates, evidence
    except GitHubReadError as exc:
        return [
            GateResult("G_RUNNER_GITHUB_HEAD_RECONCILE", "BLOCKED", f"GitHub read failed: {exc}"),
            GateResult("G_RUNNER_CI_RECONCILE", "BLOCKED", f"GitHub read failed: {exc}"),
        ], evidence
