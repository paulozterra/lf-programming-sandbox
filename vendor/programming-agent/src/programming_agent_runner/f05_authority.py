from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .authority_signatures import AuthoritySignatureError, verify_authority_receipt
from .hashutil import sha256_json

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_KIND = "AUD24_F05_BASELINE_AUTHORIZATION"


class F05AuthorityError(ValueError):
    """Raised when protected baseline changes lack independent signed authorization."""


def f05_subject_sha256(
    *,
    head_sha: str,
    base_sha: str,
    baseline_sha256: str,
    prior_baseline_sha256: str,
    changed_protected_paths: Sequence[str],
    protected_artifacts_sha256: str,
) -> str:
    return sha256_json(
        {
            "schema_version": 1,
            "finding_code": "AUD24-F05",
            "head_sha": head_sha,
            "base_sha": base_sha,
            "baseline_sha256": baseline_sha256,
            "prior_baseline_sha256": prior_baseline_sha256,
            "changed_protected_paths": sorted(set(changed_protected_paths)),
            "protected_artifacts_sha256": protected_artifacts_sha256,
            "authority_model": "INDEPENDENT_ED25519_AUDITOR_V1",
        }
    )


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise F05AuthorityError(f"{field} must be lowercase SHA-256")
    return value


def validate_f05_authority_receipt(
    receipt: Any,
    trusted_public_keys: Mapping[str, str],
    *,
    expected_head_sha: str,
    expected_base_sha: str,
    expected_subject_sha256: str,
    expected_baseline_sha256: str,
    expected_prior_baseline_sha256: str,
    expected_changed_protected_paths: Sequence[str],
    expected_protected_artifacts_sha256: str,
    builder_identities: tuple[str, ...] = (),
) -> dict[str, Any]:
    try:
        verify_authority_receipt(
            receipt,
            trusted_public_keys,
            expected_kind=_KIND,
            expected_head_sha=expected_head_sha,
            expected_subject_sha256=expected_subject_sha256,
        )
    except AuthoritySignatureError as exc:
        raise F05AuthorityError(str(exc)) from exc

    if not isinstance(receipt, dict):
        raise F05AuthorityError("F05 authority receipt must be an object")
    if receipt.get("finding_code") != "AUD24-F05":
        raise F05AuthorityError("F05 finding_code mismatch")
    if receipt.get("base_sha") != expected_base_sha:
        raise F05AuthorityError("F05 base SHA mismatch")
    if receipt.get("verdict") != "AUTHORIZED" or receipt.get("independent") is not True:
        raise F05AuthorityError("independent F05 AUTHORIZED verdict is required")

    auditor_identity = receipt.get("auditor_identity")
    if not isinstance(auditor_identity, str) or not auditor_identity.strip():
        raise F05AuthorityError("auditor_identity is required")
    if auditor_identity in {item for item in builder_identities if item}:
        raise F05AuthorityError("auditor identity must be independent from Builder")

    if _sha(receipt.get("baseline_sha256"), "baseline_sha256") != expected_baseline_sha256:
        raise F05AuthorityError("F05 baseline digest mismatch")
    if _sha(receipt.get("prior_baseline_sha256"), "prior_baseline_sha256") != expected_prior_baseline_sha256:
        raise F05AuthorityError("F05 prior baseline digest mismatch")
    if _sha(receipt.get("protected_artifacts_sha256"), "protected_artifacts_sha256") != expected_protected_artifacts_sha256:
        raise F05AuthorityError("F05 protected artifacts digest mismatch")
    _sha(receipt.get("evidence_sha256"), "evidence_sha256")

    allowed = receipt.get("allowed_protected_paths")
    if not isinstance(allowed, list) or not all(isinstance(item, str) and item for item in allowed):
        raise F05AuthorityError("allowed_protected_paths must be a non-empty string list")
    if len(allowed) != len(set(allowed)):
        raise F05AuthorityError("allowed_protected_paths contains duplicates")
    expected = sorted(set(expected_changed_protected_paths))
    if sorted(allowed) != expected:
        raise F05AuthorityError("F05 protected path scope mismatch")

    authorized_findings = receipt.get("authorized_findings")
    if not isinstance(authorized_findings, list) or "AUD24-F05" not in authorized_findings:
        raise F05AuthorityError("AUD24-F05 must be explicitly authorized")

    receipt_contract_version = receipt.get("receipt_contract_version")
    if type(receipt_contract_version) is not int or receipt_contract_version < 1:
        raise F05AuthorityError("receipt_contract_version must be >= 1")

    return receipt
