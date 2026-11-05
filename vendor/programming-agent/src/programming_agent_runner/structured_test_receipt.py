from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_json

STRUCTURED_TEST_RECEIPT_SCHEMA_VERSION = 1
STRUCTURED_TEST_RECEIPT_FILENAME = "quality-test-receipt.json"
STRUCTURED_TEST_HARNESS_REF = "tools/structured_unittest.py"

TEST_SUCCESS = "SUCCESS"
TEST_FAILURE = "FAILURE"
TEST_ERROR = "ERROR"
TEST_SKIPPED = "SKIPPED"
TEST_EXPECTED_FAILURE = "EXPECTED_FAILURE"
TEST_UNEXPECTED_SUCCESS = "UNEXPECTED_SUCCESS"
TEST_STATUSES = {
    TEST_SUCCESS,
    TEST_FAILURE,
    TEST_ERROR,
    TEST_SKIPPED,
    TEST_EXPECTED_FAILURE,
    TEST_UNEXPECTED_SUCCESS,
}

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def structured_test_receipt_sha256(receipt: dict[str, Any]) -> str:
    """Return the canonical digest while excluding only the digest field itself."""
    return sha256_json({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def _is_positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _required_string(receipt: dict[str, Any], key: str, errors: list[str]) -> str | None:
    value = receipt.get(key)
    if not isinstance(value, str) or not value:
        errors.append(f"{key}_invalid")
        return None
    return value


def validate_structured_test_receipt(
    receipt: Any,
    *,
    expected_repository: str | None = None,
    expected_head_sha: str | None = None,
    expected_run_id: int | None = None,
    expected_run_attempt: int | None = None,
    expected_job_name: str | None = None,
) -> list[str]:
    """Validate a structured receipt without consulting free-form test output."""
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]

    errors: list[str] = []
    expected_keys = {
        "schema_version",
        "repository",
        "head_sha",
        "executed_head_sha",
        "source_snapshot_sha256",
        "run_id",
        "run_attempt",
        "job_name",
        "harness_ref",
        "harness_sha256",
        "discovered_test_ids",
        "results",
        "summary",
        "receipt_sha256",
    }
    actual_keys = set(receipt)
    if actual_keys != expected_keys:
        errors.append("receipt_fields_mismatch")

    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != STRUCTURED_TEST_RECEIPT_SCHEMA_VERSION
    ):
        errors.append("schema_version_invalid")

    repository = _required_string(receipt, "repository", errors)
    if repository is not None and _REPOSITORY.fullmatch(repository) is None:
        errors.append("repository_format_invalid")
    if expected_repository is not None and repository != expected_repository:
        errors.append("repository_mismatch")

    head_sha = _required_string(receipt, "head_sha", errors)
    if head_sha is not None and _SHA40.fullmatch(head_sha) is None:
        errors.append("head_sha_format_invalid")
    if expected_head_sha is not None and head_sha != expected_head_sha:
        errors.append("head_sha_mismatch")

    executed_head_sha = _required_string(receipt, "executed_head_sha", errors)
    if executed_head_sha is not None and _SHA40.fullmatch(executed_head_sha) is None:
        errors.append("executed_head_sha_format_invalid")
    if executed_head_sha != head_sha:
        errors.append("executed_head_sha_mismatch")

    source_snapshot = _required_string(receipt, "source_snapshot_sha256", errors)
    if source_snapshot is not None and _SHA256.fullmatch(source_snapshot) is None:
        errors.append("source_snapshot_sha256_invalid")

    run_id = receipt.get("run_id")
    if not _is_positive_int(run_id):
        errors.append("run_id_invalid")
    if expected_run_id is not None and run_id != expected_run_id:
        errors.append("run_id_mismatch")

    run_attempt = receipt.get("run_attempt")
    if not _is_positive_int(run_attempt):
        errors.append("run_attempt_invalid")
    if expected_run_attempt is not None and run_attempt != expected_run_attempt:
        errors.append("run_attempt_mismatch")

    job_name = _required_string(receipt, "job_name", errors)
    if expected_job_name is not None and job_name != expected_job_name:
        errors.append("job_name_mismatch")

    harness_ref = _required_string(receipt, "harness_ref", errors)
    if harness_ref != STRUCTURED_TEST_HARNESS_REF:
        errors.append("harness_ref_invalid")
    harness_sha = _required_string(receipt, "harness_sha256", errors)
    if harness_sha is not None and _SHA256.fullmatch(harness_sha) is None:
        errors.append("harness_sha256_invalid")

    discovered_raw = receipt.get("discovered_test_ids")
    discovered: list[str] = []
    if not isinstance(discovered_raw, list):
        errors.append("discovered_test_ids_invalid")
    else:
        discovered = [value for value in discovered_raw if isinstance(value, str) and value]
        if len(discovered) != len(discovered_raw):
            errors.append("discovered_test_id_invalid")
        if discovered != sorted(discovered) or len(set(discovered)) != len(discovered):
            errors.append("discovered_test_ids_not_unique_sorted")
        if not discovered:
            errors.append("discovered_test_ids_empty")

    results_raw = receipt.get("results")
    results: list[dict[str, str]] = []
    if not isinstance(results_raw, list):
        errors.append("results_invalid")
    else:
        for value in results_raw:
            if not isinstance(value, dict) or set(value) != {"test_id", "status"}:
                errors.append("result_fields_invalid")
                continue
            test_id = value.get("test_id")
            status = value.get("status")
            if not isinstance(test_id, str) or not test_id:
                errors.append("result_test_id_invalid")
                continue
            if not isinstance(status, str) or status not in TEST_STATUSES:
                errors.append("result_status_invalid")
                continue
            results.append({"test_id": test_id, "status": status})

    result_ids = [item["test_id"] for item in results]
    if result_ids != sorted(result_ids) or len(set(result_ids)) != len(result_ids):
        errors.append("result_test_ids_not_unique_sorted")
    if result_ids != discovered:
        errors.append("result_discovery_mismatch")

    summary = receipt.get("summary")
    summary_keys = {
        "discovered",
        "executed",
        "success",
        "failure",
        "error",
        "skipped",
        "expected_failure",
        "unexpected_success",
        "overall_status",
    }
    if not isinstance(summary, dict) or set(summary) != summary_keys:
        errors.append("summary_invalid")
    else:
        expected_counts = {
            "discovered": len(discovered),
            "executed": len(results),
            "success": sum(item["status"] == TEST_SUCCESS for item in results),
            "failure": sum(item["status"] == TEST_FAILURE for item in results),
            "error": sum(item["status"] == TEST_ERROR for item in results),
            "skipped": sum(item["status"] == TEST_SKIPPED for item in results),
            "expected_failure": sum(item["status"] == TEST_EXPECTED_FAILURE for item in results),
            "unexpected_success": sum(item["status"] == TEST_UNEXPECTED_SUCCESS for item in results),
        }
        for key, expected in expected_counts.items():
            if type(summary.get(key)) is not int or summary.get(key) != expected:
                errors.append(f"summary_{key}_mismatch")
        expected_overall = (
            "PASS"
            if results and all(item["status"] == TEST_SUCCESS for item in results)
            else "FAIL"
        )
        if summary.get("overall_status") != expected_overall:
            errors.append("summary_overall_status_mismatch")

    digest = _required_string(receipt, "receipt_sha256", errors)
    if digest is not None and _SHA256.fullmatch(digest) is None:
        errors.append("receipt_sha256_invalid")
    elif digest != structured_test_receipt_sha256(receipt):
        errors.append("receipt_sha256_mismatch")

    return sorted(set(errors))


def successful_test_ids(receipt: dict[str, Any]) -> set[str]:
    results = receipt.get("results") or []
    return {
        item["test_id"]
        for item in results
        if isinstance(item, dict)
        and isinstance(item.get("test_id"), str)
        and item.get("status") == TEST_SUCCESS
    }


def nonpass_test_ids(receipt: dict[str, Any]) -> set[str]:
    results = receipt.get("results") or []
    return {
        item["test_id"]
        for item in results
        if isinstance(item, dict)
        and isinstance(item.get("test_id"), str)
        and item.get("status") in TEST_STATUSES - {TEST_SUCCESS}
    }
