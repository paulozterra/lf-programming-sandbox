from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_bytes, sha256_json
from .worker_spec import TaskSpecError, canonical_relative_path

WORKER_RECEIPT_SCHEMA_VERSION = 1
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {
    "schema_version",
    "task_id",
    "task_sha256",
    "base_head_sha",
    "source_snapshot_sha256",
    "instruction_sha256",
    "model_provider",
    "requested_model",
    "resolved_model",
    "status",
    "reason",
    "attempts",
    "changed_paths",
    "patch_sha256",
    "candidate_changed_paths",
    "candidate_patch_sha256",
    "patch_delivered",
    "commit_allowed",
    "push_allowed",
    "merge_allowed",
    "production_allowed",
    "independent_audit_required",
    "receipt_sha256",
}


def worker_receipt_sha256(receipt: dict[str, Any]) -> str:
    return sha256_json({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def seal_worker_receipt(value: dict[str, Any]) -> dict[str, Any]:
    receipt = dict(value)
    receipt["receipt_sha256"] = worker_receipt_sha256(receipt)
    return receipt


def _paths(value: Any, field: str, problems: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        problems.append(f"{field}_NOT_ARRAY")
        return ()
    try:
        paths = tuple(canonical_relative_path(item, field) for item in value)
    except TaskSpecError:
        problems.append(f"{field}_INVALID")
        return ()
    if paths != tuple(sorted(set(paths))):
        problems.append(f"{field}_NOT_SORTED_UNIQUE")
    return paths


def validate_worker_receipt(receipt: Any, patch: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(receipt, dict):
        return ["RECEIPT_NOT_OBJECT"]
    if set(receipt) != _FIELDS:
        problems.append("RECEIPT_FIELDS_INVALID")
    if type(receipt.get("schema_version")) is not int or receipt.get("schema_version") != WORKER_RECEIPT_SCHEMA_VERSION:
        problems.append("SCHEMA_VERSION_INVALID")
    for field in ("task_sha256", "source_snapshot_sha256", "instruction_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
            problems.append(f"{field.upper()}_INVALID")
    head = receipt.get("base_head_sha")
    if not isinstance(head, str) or _HEX40.fullmatch(head) is None:
        problems.append("BASE_HEAD_SHA_INVALID")
    for field in ("task_id", "model_provider", "requested_model", "reason"):
        if not isinstance(receipt.get(field), str) or not receipt[field]:
            problems.append(f"{field.upper()}_INVALID")
    status = receipt.get("status")
    if status not in ("PASS", "FAIL", "BLOCKED"):
        problems.append("STATUS_INVALID")
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list):
        problems.append("ATTEMPTS_NOT_ARRAY")
        attempts = []
    else:
        for index, attempt in enumerate(attempts, 1):
            if not isinstance(attempt, dict) or attempt.get("attempt") != index:
                problems.append("ATTEMPT_SEQUENCE_INVALID")
                break
    changed = _paths(receipt.get("changed_paths"), "changed_paths", problems)
    candidate_changed = _paths(receipt.get("candidate_changed_paths"), "candidate_changed_paths", problems)
    for field in ("commit_allowed", "push_allowed", "merge_allowed", "production_allowed"):
        if receipt.get(field) is not False:
            problems.append(f"{field.upper()}_MUST_BE_FALSE")
    if receipt.get("independent_audit_required") is not True:
        problems.append("INDEPENDENT_AUDIT_REQUIRED_MUST_BE_TRUE")
    if type(receipt.get("patch_delivered")) is not bool:
        problems.append("PATCH_DELIVERED_INVALID")
    if not isinstance(patch, str):
        problems.append("PATCH_NOT_TEXT")
        patch = ""
    patch_digest = receipt.get("patch_sha256")
    candidate_digest = receipt.get("candidate_patch_sha256")
    if candidate_digest is not None and (
        not isinstance(candidate_digest, str) or _HEX64.fullmatch(candidate_digest) is None
    ):
        problems.append("CANDIDATE_PATCH_SHA256_INVALID")
    if status == "PASS":
        if receipt.get("patch_delivered") is not True or not patch:
            problems.append("PASS_WITHOUT_DELIVERED_PATCH")
        actual_patch_digest = sha256_bytes(patch.encode("utf-8"))
        if patch_digest != actual_patch_digest:
            problems.append("PATCH_SHA256_MISMATCH")
        if candidate_digest != patch_digest or candidate_changed != changed or not changed:
            problems.append("PASS_CANDIDATE_DELIVERY_MISMATCH")
        resolved_model = receipt.get("resolved_model")
        if not isinstance(resolved_model, str) or not resolved_model:
            problems.append("PASS_RESOLVED_MODEL_MISSING")
        if not attempts:
            problems.append("PASS_ATTEMPTS_MISSING")
        else:
            acceptance = attempts[-1].get("acceptance") if isinstance(attempts[-1], dict) else None
            if not isinstance(acceptance, list) or not acceptance:
                problems.append("PASS_ACCEPTANCE_MISSING")
            elif any(not isinstance(item, dict) or item.get("status") != "PASS" for item in acceptance):
                problems.append("PASS_ACCEPTANCE_NONPASS")
    else:
        if receipt.get("patch_delivered") is not False or patch or patch_digest is not None or changed:
            problems.append("NONPASS_DELIVERED_PATCH")
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        problems.append("RECEIPT_SHA256_INVALID")
    elif worker_receipt_sha256(receipt) != digest:
        problems.append("RECEIPT_SHA256_MISMATCH")
    return problems
