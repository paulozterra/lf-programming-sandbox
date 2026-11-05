from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .authority_signatures import AuthoritySignatureError, verify_authority_receipt
from .hashutil import sha256_json

PromotionState = Literal["CANDIDATE", "AUDIT_REQUIRED", "PROMOTION_PENDING", "ACTIVE", "REJECTED"]


class LearningLoopError(ValueError):
    """Raised when a finding cannot be converted into a controlled prevention candidate."""


@dataclass(frozen=True)
class Finding:
    code: str
    title: str
    root_cause_family: str
    detectability: str
    evidence_sha256: str
    head_sha: str
    source_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreventionCandidate:
    code: str
    finding_code: str
    rule_text: str
    regression_test_id: str
    state: PromotionState
    audit_status: str | None
    human_promotion: bool
    retrieval_eligible: bool
    candidate_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any, field: str, maximum: int = 20_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise LearningLoopError(f"{field} invalid")
    return value


def finding_from_dict(value: Any) -> Finding:
    if not isinstance(value, dict):
        raise LearningLoopError("finding must be an object")
    evidence = _text(value.get("evidence_sha256"), "evidence_sha256", 64)
    head = _text(value.get("head_sha"), "head_sha", 40)
    if len(evidence) != 64 or any(char not in "0123456789abcdef" for char in evidence):
        raise LearningLoopError("evidence_sha256 must be lowercase SHA-256")
    if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
        raise LearningLoopError("head_sha must be lowercase 40-hex")
    return Finding(
        _text(value.get("code"), "code", 256),
        _text(value.get("title"), "title"),
        _text(value.get("root_cause_family"), "root_cause_family", 256),
        _text(value.get("detectability"), "detectability", 256),
        evidence,
        head,
        _text(value.get("source_ref"), "source_ref", 8192),
    )


def build_prevention_candidate(finding: Finding, rule_text: str, regression_test_id: str) -> PreventionCandidate:
    rule = _text(rule_text, "rule_text")
    test_id = _text(regression_test_id, "regression_test_id", 1024)
    code = f"PR-{finding.code}"
    payload = {
        "code": code,
        "finding_code": finding.code,
        "rule_text": rule,
        "regression_test_id": test_id,
        "state": "AUDIT_REQUIRED",
        "audit_status": None,
        "human_promotion": False,
        "retrieval_eligible": False,
        "finding_evidence_sha256": finding.evidence_sha256,
        "finding_head_sha": finding.head_sha,
    }
    return PreventionCandidate(
        code,
        finding.code,
        rule,
        test_id,
        "AUDIT_REQUIRED",
        None,
        False,
        False,
        sha256_json(payload),
    )


def apply_audit(
    candidate: PreventionCandidate,
    authority_receipt: Any,
    *,
    trusted_auditor_public_keys: Mapping[str, str] | None = None,
) -> PreventionCandidate:
    if candidate.state != "AUDIT_REQUIRED":
        raise LearningLoopError("audit can only be applied to AUDIT_REQUIRED candidate")
    if not trusted_auditor_public_keys:
        raise LearningLoopError("trusted auditor public keys are required")
    try:
        verify_authority_receipt(
            authority_receipt,
            trusted_auditor_public_keys,
            expected_kind="AUDIT_VERDICT",
            expected_subject_sha256=candidate.candidate_sha256,
        )
    except AuthoritySignatureError as exc:
        raise LearningLoopError(f"audit authority invalid: {exc}") from exc
    if not isinstance(authority_receipt, dict) or authority_receipt.get("independent") is not True:
        raise LearningLoopError("independent audit receipt is required")
    audit_status = authority_receipt.get("verdict")
    if audit_status not in {"PASS", "FAIL", "BLOCKED"}:
        raise LearningLoopError("audit_status invalid")
    evidence = _text(authority_receipt.get("evidence_sha256"), "audit_evidence_sha256", 64)
    if len(evidence) != 64 or any(char not in "0123456789abcdef" for char in evidence):
        raise LearningLoopError("audit_evidence_sha256 must be lowercase SHA-256")
    _text(authority_receipt.get("auditor_identity"), "auditor_identity", 1024)
    state: PromotionState = (
        "PROMOTION_PENDING" if audit_status == "PASS" else "REJECTED" if audit_status == "FAIL" else "AUDIT_REQUIRED"
    )
    payload = {
        "previous_candidate_sha256": candidate.candidate_sha256,
        "audit_status": audit_status,
        "audit_evidence_sha256": evidence,
        "audit_authority_receipt_sha256": sha256_json(authority_receipt),
        "state": state,
    }
    return PreventionCandidate(
        candidate.code,
        candidate.finding_code,
        candidate.rule_text,
        candidate.regression_test_id,
        state,
        audit_status,
        False,
        False,
        sha256_json(payload),
    )


def apply_human_promotion(
    candidate: PreventionCandidate,
    authority_receipt: Any,
    *,
    trusted_human_public_keys: Mapping[str, str] | None = None,
) -> PreventionCandidate:
    if candidate.state != "PROMOTION_PENDING" or candidate.audit_status != "PASS":
        raise LearningLoopError("human promotion requires prior independent audit PASS")
    if not trusted_human_public_keys:
        raise LearningLoopError("trusted human public keys are required")
    try:
        verify_authority_receipt(
            authority_receipt,
            trusted_human_public_keys,
            expected_kind="HUMAN_DECISION",
            expected_subject_sha256=candidate.candidate_sha256,
        )
    except AuthoritySignatureError as exc:
        raise LearningLoopError(f"human promotion authority invalid: {exc}") from exc
    if not isinstance(authority_receipt, dict):
        raise LearningLoopError("human authority receipt must be an object")
    approved = authority_receipt.get("approved")
    if not isinstance(approved, bool):
        raise LearningLoopError("human authority receipt approved must be boolean")
    reference = _text(authority_receipt.get("approval_ref"), "approval_ref", 8192)
    _text(authority_receipt.get("actor_identity"), "actor_identity", 1024)
    state: PromotionState = "ACTIVE" if approved else "REJECTED"
    payload = {
        "previous_candidate_sha256": candidate.candidate_sha256,
        "approved": approved,
        "approval_ref": reference,
        "human_authority_receipt_sha256": sha256_json(authority_receipt),
        "state": state,
    }
    return PreventionCandidate(
        candidate.code,
        candidate.finding_code,
        candidate.rule_text,
        candidate.regression_test_id,
        state,
        candidate.audit_status,
        approved,
        approved,
        sha256_json(payload),
    )


def retrieval_record_for_candidate(
    candidate: PreventionCandidate, *, project: str, observed_at: str, snapshot_sha256: str
) -> dict[str, Any]:
    if candidate.state != "ACTIVE" or not candidate.retrieval_eligible:
        raise LearningLoopError("only ACTIVE human-promoted prevention can enter future retrieval")
    return {
        "source": "preventions",
        "record_id": candidate.code,
        "title": candidate.code,
        "content": candidate.rule_text,
        "project": _text(project, "project", 4096),
        "domain": "transversal",
        "active": True,
        "approved": True,
        "applicable": True,
        "effective_at": observed_at,
        "expires_at": None,
        "provenance": {
            "source_ref": f"transversal://prevention/{candidate.code}",
            "snapshot_sha256": _text(snapshot_sha256, "snapshot_sha256", 64),
            "observed_at": observed_at,
        },
        "canonical_key": candidate.code,
    }


def recurrence_metrics(findings: Iterable[Finding]) -> dict[str, Any]:
    values = list(findings)
    counts: dict[str, int] = {}
    for finding in values:
        counts[finding.root_cause_family] = counts.get(finding.root_cause_family, 0) + 1
    recurrent = {family: count for family, count in counts.items() if count > 1}
    metrics: dict[str, Any] = {
        "schema_version": 1,
        "findings": len(values),
        "root_cause_families": counts,
        "recurrent_families": recurrent,
        "recurrence_rate": sum(recurrent.values()) / len(values) if values else 0.0,
    }
    metrics["metrics_sha256"] = sha256_json(metrics)
    return metrics
