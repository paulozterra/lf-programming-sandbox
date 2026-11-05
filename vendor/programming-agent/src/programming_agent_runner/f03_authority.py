from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_json

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_KIND = "AUD24_F03_CONTEXT_VERDICT"


class F03AuthorityError(ValueError):
    """Raised when AUD24-F03 lacks valid separate-context auditor evidence."""


def f03_subject_sha256(
    *,
    head_sha: str,
    baseline_sha256: str,
    execution_evidence_config_sha256: str,
) -> str:
    return sha256_json(
        {
            "schema_version": 2,
            "finding_code": "AUD24-F03",
            "head_sha": head_sha,
            "baseline_sha256": baseline_sha256,
            "execution_evidence_config_sha256": execution_evidence_config_sha256,
            "authority_model": "SEPARATE_CONTEXT_AUDITOR_V1",
        }
    )


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise F03AuthorityError(f"{field} must be lowercase SHA-256")
    return value


def _required_true(receipt: dict[str, Any], field: str) -> None:
    if receipt.get(field) is not True:
        raise F03AuthorityError(f"{field} must be true")


def validate_f03_authority_receipt(
    receipt: Any,
    *,
    expected_head_sha: str,
    expected_subject_sha256: str,
    builder_identities: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise F03AuthorityError("F03 audit receipt must be an object")
    if receipt.get("schema_version") != 2:
        raise F03AuthorityError("F03 schema_version mismatch")
    if receipt.get("kind") != _KIND:
        raise F03AuthorityError("F03 kind mismatch")
    if receipt.get("head_sha") != expected_head_sha:
        raise F03AuthorityError("F03 HEAD mismatch")
    if receipt.get("subject_sha256") != expected_subject_sha256:
        raise F03AuthorityError("F03 subject mismatch")
    if receipt.get("finding_code") != "AUD24-F03":
        raise F03AuthorityError("F03 finding_code mismatch")
    if receipt.get("verdict") != "PASS" or receipt.get("independent") is not True:
        raise F03AuthorityError("independent F03 PASS is required")

    auditor_identity = receipt.get("auditor_identity")
    if not isinstance(auditor_identity, str) or not auditor_identity.strip():
        raise F03AuthorityError("auditor_identity is required")
    if auditor_identity in {item for item in builder_identities if item}:
        raise F03AuthorityError("auditor identity must be independent from Builder")

    auditor_context_id = receipt.get("auditor_context_id")
    builder_context_id = receipt.get("builder_context_id")
    if not isinstance(auditor_context_id, str) or not auditor_context_id.strip():
        raise F03AuthorityError("auditor_context_id is required")
    if not isinstance(builder_context_id, str) or not builder_context_id.strip():
        raise F03AuthorityError("builder_context_id is required")
    if auditor_context_id == builder_context_id:
        raise F03AuthorityError("auditor context must differ from Builder context")

    audit_channel = receipt.get("audit_channel")
    if not isinstance(audit_channel, str) or not audit_channel.strip():
        raise F03AuthorityError("audit_channel is required")

    for field in (
        "github_readback_verified",
        "supabase_readback_verified",
        "ekb_readback_verified",
        "semantic_nonreconstructibility_verified",
        "hidden_output_nonexposure_verified",
        "replay_binding_verified",
    ):
        _required_true(receipt, field)

    if receipt.get("hidden_output") != "HASH_ONLY":
        raise F03AuthorityError("hidden output must remain HASH_ONLY")

    _digest(receipt.get("evidence_sha256"), "evidence_sha256")
    _digest(receipt.get("hidden_challenge_commitment"), "hidden_challenge_commitment")
    _digest(receipt.get("criteria_coverage_sha256"), "criteria_coverage_sha256")

    receipt_contract_version = receipt.get("receipt_contract_version")
    if type(receipt_contract_version) is not int or receipt_contract_version < 1:
        raise F03AuthorityError("receipt_contract_version must be >= 1")

    output_digest = receipt.get("output_digest")
    _digest(output_digest, "output_digest")
    expected_output = sha256_json({key: value for key, value in receipt.items() if key != "output_digest"})
    if output_digest != expected_output:
        raise F03AuthorityError("F03 output_digest mismatch")

    return receipt
