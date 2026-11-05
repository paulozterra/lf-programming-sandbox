from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from .hashutil import sha256_json

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED_FINDINGS = {"AUD24-F01", "AUD24-F03", "AUD24-F05"}


def changed_protected_paths(current: Mapping[str, Any], prior: Mapping[str, Any] | None) -> list[str]:
    if prior is None:
        return []
    previous = prior.get("protected_artifacts")
    candidate = current.get("protected_artifacts")
    if not isinstance(previous, dict) or not isinstance(candidate, dict):
        return []
    protected_paths = set(previous) | set(candidate)
    return sorted(
        path
        for path in protected_paths
        if path not in previous or path not in candidate or previous[path] != candidate[path]
    )


def validate_external_receipt(
    receipt: Any,
    *,
    expected_head: str,
    expected_base: str,
    baseline_sha256: str,
    changed_paths: list[str],
) -> list[str]:
    expected_fields = {
        "schema_version",
        "control_id",
        "issuer",
        "policy_id",
        "authority_function_sha256",
        "exact_head",
        "base_head",
        "authorized_findings",
        "allowed_protected_paths",
        "source_evidence_digest",
        "current_baseline_sha256",
        "outcome",
        "reason_code",
        "output_digest",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_fields:
        return ["BASELINE_AUTH_RECEIPT_FIELDS_INVALID"]
    errors: list[str] = []
    if receipt.get("schema_version") != 1:
        errors.append("BASELINE_AUTH_SCHEMA_INVALID")
    if receipt.get("control_id") != "EXTERNAL_BASELINE_AUTHORIZATION":
        errors.append("BASELINE_AUTH_CONTROL_INVALID")
    if receipt.get("issuer") != "supabase-ekb-independent-audit":
        errors.append("BASELINE_AUTH_ISSUER_INVALID")
    if receipt.get("exact_head") != expected_head:
        errors.append("BASELINE_AUTH_HEAD_MISMATCH")
    if receipt.get("base_head") != expected_base:
        errors.append("BASELINE_AUTH_BASE_MISMATCH")
    if receipt.get("current_baseline_sha256") != baseline_sha256:
        errors.append("BASELINE_AUTH_BASELINE_DIGEST_MISMATCH")
    for key in ("policy_id", "authority_function_sha256", "source_evidence_digest"):
        value = receipt.get(key)
        if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
            errors.append(f"BASELINE_AUTH_DIGEST_INVALID:{key}")
    findings = receipt.get("authorized_findings")
    if not isinstance(findings, list) or set(findings) != _REQUIRED_FINDINGS:
        errors.append("BASELINE_AUTH_FINDINGS_INVALID")
    allowed = receipt.get("allowed_protected_paths")
    if not isinstance(allowed, list) or len(allowed) != len(set(allowed)) or not all(isinstance(item, str) and item for item in allowed):
        errors.append("BASELINE_AUTH_PATHS_INVALID")
        allowed = []
    if not set(changed_paths).issubset(set(allowed)):
        errors.append("BASELINE_AUTH_SCOPE_MISMATCH")
    if receipt.get("outcome") != "AUTHORIZED" or receipt.get("reason_code") != "INDEPENDENT_AUDIT_REMEDIATION_AUTHORIZED":
        errors.append("BASELINE_AUTH_OUTCOME_INVALID")
    output = receipt.get("output_digest")
    if not isinstance(output, str) or _HEX64.fullmatch(output) is None:
        errors.append("BASELINE_AUTH_OUTPUT_DIGEST_INVALID")
    elif sha256_json({key: receipt[key] for key in receipt if key != "output_digest"}) != output:
        errors.append("BASELINE_AUTH_OUTPUT_DIGEST_MISMATCH")
    return sorted(set(errors))


def prepare_regression_baseline(
    current: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    receipt: Mapping[str, Any] | None,
    *,
    expected_head: str,
    expected_base: str,
    baseline_sha256: str,
) -> tuple[dict[str, Any], list[str]]:
    changed = changed_protected_paths(current, prior)
    candidate = deepcopy(dict(current))
    candidate["change_authorization"] = None
    if not changed:
        return candidate, []
    if receipt is None:
        return candidate, ["EXTERNAL_BASELINE_AUTHORIZATION_REQUIRED"]
    errors = validate_external_receipt(
        receipt,
        expected_head=expected_head,
        expected_base=expected_base,
        baseline_sha256=baseline_sha256,
        changed_paths=changed,
    )
    if errors:
        return candidate, errors
    candidate["change_authorization"] = {
        "decision_ref": "EXTERNAL_BASELINE_AUTHORIZATION",
        "evidence_ref": f"receipt:{receipt['output_digest']}",
        "reason": "Protected baseline changes are authorized by external exact-head EKB-backed remediation evidence.",
    }
    return candidate, []
