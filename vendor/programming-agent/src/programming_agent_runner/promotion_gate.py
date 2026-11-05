from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .authority_signatures import AuthoritySignatureError, verify_authority_receipt
from .hashutil import sha256_json

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PromotionGateError(ValueError):
    """Raised when technical evidence is incorrectly treated as promotion authority."""


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PromotionGateError(f"{field} must be lowercase SHA-256")
    return value


def _head(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA40.fullmatch(value) is None:
        raise PromotionGateError(f"{field} must be lowercase 40-hex")
    return value


def _manifest_digest_valid(manifest: dict[str, Any]) -> bool:
    digest = manifest.get("manifest_sha256")
    return isinstance(digest, str) and digest == sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )


def authorize_promotion(
    technical_manifest: Any,
    independent_audit: Any,
    human_approval: Any,
    *,
    builder_identities: Iterable[str] = (),
    trusted_auditor_public_keys: Mapping[str, str] | None = None,
    trusted_human_public_keys: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(technical_manifest, dict) or not _manifest_digest_valid(technical_manifest):
        raise PromotionGateError("technical manifest is invalid or tampered")
    if technical_manifest.get("technical_status") != "PASS":
        raise PromotionGateError("technical_status must be PASS")
    if technical_manifest.get("promotion_status") != "BLOCKED":
        raise PromotionGateError("technical manifest must not self-authorize promotion")
    head = _head(technical_manifest.get("head_sha"), "technical_manifest.head_sha")
    manifest_sha = _digest(technical_manifest.get("manifest_sha256"), "manifest_sha256")

    if not trusted_auditor_public_keys:
        raise PromotionGateError("trusted auditor public keys are required")
    if not trusted_human_public_keys:
        raise PromotionGateError("trusted human public keys are required")

    try:
        verify_authority_receipt(
            independent_audit,
            trusted_auditor_public_keys,
            expected_kind="AUDIT_VERDICT",
            expected_head_sha=head,
        )
    except AuthoritySignatureError as exc:
        raise PromotionGateError(f"independent audit authority invalid: {exc}") from exc
    if not isinstance(independent_audit, dict):
        raise PromotionGateError("independent audit must be an object")
    if independent_audit.get("independent") is not True or independent_audit.get("verdict") != "PASS":
        raise PromotionGateError("independent audit PASS is required")
    if independent_audit.get("technical_manifest_sha256") != manifest_sha:
        raise PromotionGateError("independent audit technical manifest mismatch")
    auditor = independent_audit.get("auditor_identity")
    if not isinstance(auditor, str) or not auditor:
        raise PromotionGateError("auditor_identity is required")
    builders = {identity for identity in builder_identities if identity}
    if auditor in builders:
        raise PromotionGateError("auditor is not independent from Builder identity")
    audit_evidence = _digest(independent_audit.get("evidence_sha256"), "independent_audit.evidence_sha256")

    try:
        verify_authority_receipt(
            human_approval,
            trusted_human_public_keys,
            expected_kind="HUMAN_DECISION",
            expected_head_sha=head,
        )
    except AuthoritySignatureError as exc:
        raise PromotionGateError(f"human approval authority invalid: {exc}") from exc
    if not isinstance(human_approval, dict) or human_approval.get("approved") is not True:
        raise PromotionGateError("explicit human approval is required")
    if human_approval.get("technical_manifest_sha256") != manifest_sha:
        raise PromotionGateError("human approval technical manifest mismatch")
    actor = human_approval.get("actor_identity")
    reference = human_approval.get("approval_ref")
    if not isinstance(actor, str) or not actor or not isinstance(reference, str) or not reference:
        raise PromotionGateError("human approval actor and reference are required")

    receipt: dict[str, Any] = {
        "schema_version": 2,
        "status": "AUTHORIZED",
        "head_sha": head,
        "technical_manifest_sha256": manifest_sha,
        "independent_audit_evidence_sha256": audit_evidence,
        "independent_audit_receipt_sha256": sha256_json(independent_audit),
        "human_approval_receipt_sha256": sha256_json(human_approval),
        "auditor_identity": auditor,
        "auditor_key_id": independent_audit.get("key_id"),
        "human_actor_identity": actor,
        "human_key_id": human_approval.get("key_id"),
        "human_approval_ref": reference,
        "deployment_included": False,
        "authority": "PROMOTION_GATE_ONLY",
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return receipt


def validate_promotion_receipt(value: Any, *, expected_head_sha: str | None = None) -> list[str]:
    if not isinstance(value, dict):
        return ["RECEIPT_NOT_OBJECT"]
    problems: list[str] = []
    digest = value.get("receipt_sha256")
    if not isinstance(digest, str) or digest != sha256_json(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    ):
        problems.append("RECEIPT_SHA256_MISMATCH")
    if value.get("status") != "AUTHORIZED" or value.get("authority") != "PROMOTION_GATE_ONLY":
        problems.append("PROMOTION_NOT_AUTHORIZED")
    if value.get("deployment_included") is not False:
        problems.append("DEPLOYMENT_AUTHORITY_OVERCLAIM")
    if expected_head_sha is not None and value.get("head_sha") != expected_head_sha:
        problems.append("HEAD_MISMATCH")
    return sorted(problems)
