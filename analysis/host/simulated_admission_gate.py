"""F2 D-AN6(a): bounded, digest-sealed *simulation* of admission A5→A6.

Never modifies upstream A1–A5, promotes pending rules, attests real sources,
or claims authority. A digest binds bytes but is not a trusted signature.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


MODE = "SIMULATED_SANDBOX_ONLY"
STAGES = ("A1", "A2", "A3", "A4", "A5")
ALLOW = frozenset({
    "SOURCE_READBACK_CURRENTNESS_AND_AUTHORITY_NOT_ATTESTED",
    "A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED",
    "A2_TYPED_EVIDENCE_CURRENTNESS_OR_SPECIALIST_PENDING",
    "GITHUB_CURRENT_IMPLEMENTATION_AND_AS_IS_MISSING",
})
STATUS = {
    "A1": "VALID_OUTPUT",
    "A2": "NEED_MORE_EVIDENCE",
    "A3": "SOURCE_READBACK_PROCESSED_UNATTESTED",
    "A4": "PLANNED_BUILD_IMPACT_UNATTESTED",
    "A5": "UNRESOLVED",
}
FALSE_FLAGS = {
    "source_attested": False, "currentness_attested": False,
    "production_authority": False, "handoff_allowed": False,
    "merge_allowed": False, "deploy_allowed": False,
    "downstream_authorized": False,
}


class AdmissionBlocked(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def _blocked(code):
    raise AdmissionBlocked(code)


def output_digests(stages):
    if not isinstance(stages, dict) or set(stages) != set(STAGES):
        _blocked("F2_STAGE_SET_INVALID")
    return {stage: digest(stages[stage]) for stage in STAGES}


def _a2_narrow(signals, a2):
    # Mirrors A2's existing signal digest; no pseudo-currentness allowed.
    if (not isinstance(signals, dict)
            or digest(signals) != a2.get("classification", {}).get("signals_sha256")):
        _blocked("F2_A2_SIGNAL_DIGEST_MISMATCH")
    x = signals.get("depth_signals")
    if not isinstance(x, dict):
        _blocked("F2_A2_SIGNALS_UNAVAILABLE")
    if (x.get("materiality_level") not in ("LOW", "MEDIUM", "HIGH")
            or x.get("scope_bounded") != "TRUE"
            or x.get("reversibility_state") not in ("DEMONSTRATED", "NOT_DEMONSTRATED")
            or x.get("authority_state") not in ("UNKNOWN", "INSUFFICIENT")
            or x.get("currentness_decision") not in ("UNKNOWN_FAIL_CLOSED", "UNRESOLVED")
            or x.get("material_contradiction") is not False
            or x.get("known_cross_scope_impact") is not False
            or x.get("unresolved_material_signal_count") != 0
            or x.get("required_specialist_count") != 0):
        _blocked("F2_A2_NON_AUTHORITY_UNRESOLVED")
    if a2.get("blocking_codes") != [
        "A2_TYPED_EVIDENCE_CURRENTNESS_OR_SPECIALIST_PENDING"
    ]:
        _blocked("F2_A2_BLOCKING_SET_INVALID")


def _target(stages):
    """Derive the target from the typed A1 payload, never a fixture constant."""
    hints = stages.get("A1", {}).get("payload", {}).get("target_hints")
    if (not isinstance(hints, list) or len(hints) != 1
            or not isinstance(hints[0], str) or not hints[0]):
        _blocked("F2_SOURCE_IDENTITY_OR_AUTHORITY_INVALID")
    return hints[0]


def _assess(stages, signals):
    output_digests(stages)
    for stage in STAGES:
        row = stages[stage]
        if not isinstance(row, dict):
            _blocked("F2_STAGE_OUTPUT_INVALID:" + stage)
        if row.get("status") == "BLOCKED":
            _blocked("F2_UPSTREAM_BLOCKED:" + stage)
        if row.get("status") != STATUS[stage]:
            _blocked("F2_UPSTREAM_STATUS_UNEXPECTED:" + stage)
    a1, a2, a3, a4, a5 = (stages[k] for k in STAGES)
    if (a1.get("payload", {}).get("target_hints") != [_target(stages)]
            or a2.get("classification", {}).get("target_ref") != _target(stages)
            or any(x.get("target_ref") != _target(stages) for x in (a3, a4, a5))
            or a3.get("source_attested") is not False
            or a4.get("source_attested") is not False
            or a5.get("source_attested") is not False
            or a5.get("a6_allowed") is not False):
        _blocked("F2_SOURCE_IDENTITY_OR_AUTHORITY_INVALID")
    _a2_narrow(signals, a2)
    if (a4.get("target_change_action") != "CREATE"
            or a4.get("analysis_mode") != "PLANNED_BUILD"
            or a4.get("no_impact_claimed") is not False
            or a4.get("target_code_destination") is not None):
        _blocked("F2_NOT_NEW_BUILD")
    if a3.get("as_is_baseline_or_new_implementation_evidence") is not None:
        _blocked("F2_AS_IS_NOT_MISSING")
    a3_codes = a3.get("blocking_codes")
    if not isinstance(a3_codes, list) or set(a3_codes) != {
        "SOURCE_READBACK_CURRENTNESS_AND_AUTHORITY_NOT_ATTESTED",
        "GITHUB_CURRENT_IMPLEMENTATION_AND_AS_IS_MISSING",
    }:
        _blocked("F2_A3_BLOCKING_SET_INVALID")
    impacts = a4.get("unresolved_material_impacts")
    if not isinstance(impacts, list) or [x.get("code") for x in impacts
            if isinstance(x, dict)] != ["A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED"]:
        _blocked("F2_A4_BLOCKING_SET_INVALID")
    if (a5.get("blocking_codes") != ["A4:A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED"]
            or a5.get("material_adr_triggers_true") != []
            or a5.get("material_adr_triggers_unknown") != []
            or a5.get("pending_owner_decisions") != []):
        _blocked("F2_A5_OTHER_UNRESOLVED")
    approved = a3.get("policy_scope_clear_rule_candidates")
    excluded = a3.get("excluded_rule_items")
    profiles = a5.get("rule_profiles", {}).get("rules")
    if (not isinstance(approved, list) or not isinstance(excluded, list)
            or not isinstance(profiles, list)):
        _blocked("F2_RULE_SCOPE_MISSING")
    by_code = {x.get("rule_code"): x for x in profiles if isinstance(x, dict)}
    if len(by_code) != len(profiles):
        _blocked("F2_RULE_PROFILE_DUPLICATE")
    a_codes = {x.get("rule_code") for x in approved}
    e_codes = {x.get("rule_code") for x in excluded}
    if (len(a_codes) != len(approved) or len(e_codes) != len(excluded)
            or a_codes & e_codes or set(by_code) != a_codes | e_codes
            or len(a_codes) != 6 or len(e_codes) != 2
            or any(by_code[c].get("implementation_scope") != "APPROVED_SCOPE"
                   or by_code[c].get("rule_source_ref") != row.get("source_ref")
                   for row in approved for c in [row.get("rule_code")])
            or any(by_code[c].get("implementation_scope") != "EXCLUDED_PENDING"
                   for c in e_codes)):
        _blocked("F2_EXCLUDED_RULE_PROMOTION_OR_DRIFT")
    return sorted(ALLOW)


def seal_envelope(stages, signals):
    lifts = _assess(stages, signals)
    body = {
        "schema_version": "SIMULATED_ADMISSION_ENVELOPE_V1",
        "attestation_mode": MODE,
        "target_ref": _target(stages),
        "materiality_level": signals["depth_signals"]["materiality_level"],
        "stage_sha256": output_digests(stages),
        "a2_signals_sha256": digest(signals),
        "requested_lifts": lifts,
        "authority_flags": deepcopy(FALSE_FLAGS),
    }
    return {**body, "envelope_sha256": digest(body)}


def admit(stages, signals, envelope):
    if not isinstance(envelope, dict):
        _blocked("F2_ADMISSION_ENVELOPE_MISSING")
    body = {k: v for k, v in envelope.items() if k != "envelope_sha256"}
    if (set(envelope) != set(body) | {"envelope_sha256"}
            or envelope.get("envelope_sha256") != digest(body)):
        _blocked("F2_ADMISSION_ENVELOPE_DIGEST_INVALID")
    if (body.get("schema_version") != "SIMULATED_ADMISSION_ENVELOPE_V1"
            or body.get("attestation_mode") != MODE
            or body.get("target_ref") != _target(stages)
            or body.get("materiality_level") != signals.get("depth_signals", {}).get("materiality_level")
            or body.get("authority_flags") != FALSE_FLAGS):
        _blocked("F2_ADMISSION_ENVELOPE_IDENTITY_INVALID")
    if body.get("stage_sha256") != output_digests(stages):
        _blocked("F2_STAGE_DIGEST_MISMATCH")
    if body.get("a2_signals_sha256") != digest(signals):
        _blocked("F2_A2_SIGNAL_DIGEST_MISMATCH")
    lifts = _assess(stages, signals)
    requested = body.get("requested_lifts")
    if not isinstance(requested, list) or requested != lifts:
        _blocked("F2_LIFT_OUTSIDE_CLOSED_ALLOWLIST")
    return {
        "schema_version": "SIMULATED_ADMISSION_V1",
        "attestation_mode": MODE,
        "target_ref": _target(stages),
        "a6_admitted": True,
        "materiality_level": signals["depth_signals"]["materiality_level"],
        "lifted_codes": lifts,
        "stage_sha256": output_digests(stages),
        "a2_signals_sha256": digest(signals),
        "envelope_sha256": envelope["envelope_sha256"],
        "authority_flags": deepcopy(FALSE_FLAGS),
        "excluded_rule_codes": sorted(x["rule_code"] for x in
                                      stages["A3"]["excluded_rule_items"]),
        "simulation": True,
    }


def verify(stages, signals, envelope, receipt):
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "SIMULATED_ADMISSION_V1":
        _blocked("F2_ADMISSION_REQUIRED")
    expected = admit(stages, signals, envelope)
    if receipt != expected:
        _blocked("F2_ADMISSION_RECEIPT_DRIFT")
    return True
