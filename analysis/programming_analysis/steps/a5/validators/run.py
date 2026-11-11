"""A5: source-only deterministic decision and ADR projection.

No new resolver, decision engine, SQL, owner approval, persistence, or
runtime transition. A5 consumes A1/A2/A3/A4 + host-authorized readback.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT = Path(__file__).resolve().parents[1] / "contracts/deterministic_decision_sources_v1.json"
SCHEMA = "ANALYSIS_DECISION_CONTEXT_V1"
PACKET = "A5_GOVERNED_DECISION_READBACK_V1"
REQUIRED = {"REQUEST_CONTEXT_V1", "ANALYSIS_CHANGE_CLASSIFICATION_V1",
            "TARGETED_EVIDENCE_SET_V1", "SHARED_CHANGE_IMPACT_ANALYSIS"}


def _digest(row: dict) -> str:
    value = {k: v for k, v in row.items() if k != "decision_fingerprint_sha256"}
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _blocked(code: str, subject: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA, "status": "BLOCKED",
        "subject_ref": subject, "blocking_codes": [code],
        "decisions": [], "unresolved_material_questions": [code],
        "source_attested": False, "independent_judge_verified": False,
        "a6_allowed": False, "no_write_performed": True,
    }


def _decision(subject: str, scope: list[str], *, status: str,
              disposition: str, refs: list[str], material_question: str,
              unresolved: list[str], adr_ref: str | None = None,
              selected: str | None = None, options: list[str] | None = None,
              rationale: str | None = None,
              authority_refs: list[str] | None = None,
              currentness_refs: list[str] | None = None) -> dict:
    row = {
        "decision_id": "A5:" + subject,
        "subject_ref": subject,
        "scope_refs": scope,
        "material_question": material_question,
        "status": status,
        "options_considered": options if options is not None else [],
        "selected_option_ref": selected,
        "rationale": rationale or "Source-only candidate; no owner choice inferred",
        "authority_refs": authority_refs if authority_refs is not None else [],
        "evidence_refs": refs,
        "currentness_refs": currentness_refs if currentness_refs is not None else [],
        "unresolved_questions": unresolved,
        "adr_disposition": disposition,
        "adr_ref": adr_ref,
        "persistence_ref": None,  # No append-only ASOF receipt written by A5.
    }
    row["decision_fingerprint_sha256"] = _digest(row)
    return row


def _run_base(inputs: Any, readback: Any = None, *, business: str = "LF") -> dict:
    if business != "LF":
        return _blocked("A5_BUSINESS_NOT_ENABLED_FOR_LF_SKILL")
    try:
        policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _blocked("A5_SOURCE_CONTRACT_UNAVAILABLE")
    if (policy.get("schema_version") != "A5_DETERMINISTIC_DECISION_SOURCES_V1"
            or policy.get("canonical_inputs") != [
                "REQUEST_CONTEXT_V1", "ANALYSIS_CHANGE_CLASSIFICATION_V1",
                "TARGETED_EVIDENCE_SET_V1", "SHARED_CHANGE_IMPACT_ANALYSIS"
            ] or len(policy.get("material_adr_triggers", [])) != 7):
        return _blocked("A5_SOURCE_CONTRACT_DRIFT")
    if not isinstance(inputs, dict) or set(inputs) != REQUIRED:
        return _blocked("A5_EXACT_FOUR_CANONICAL_INPUTS_REQUIRED")
    a1, a2, a3, a4 = (inputs[k] for k in (
        "REQUEST_CONTEXT_V1", "ANALYSIS_CHANGE_CLASSIFICATION_V1",
        "TARGETED_EVIDENCE_SET_V1", "SHARED_CHANGE_IMPACT_ANALYSIS"))
    if (any(not isinstance(v, dict) for v in (a1, a2, a3, a4))
            or a1.get("schema_version") != "REQUEST_CONTEXT_V1"
            or a2.get("schema_version") != "ANALYSIS_CHANGE_CLASSIFICATION_V1"
            or a3.get("schema_version") != "TARGETED_EVIDENCE_SET_V1"
            or a4.get("schema_version") != "SHARED_CHANGE_IMPACT_ANALYSIS"):
        return _blocked("A5_INPUT_SCHEMA_INVALID")
    target = a3.get("target_ref")
    if (not isinstance(target, str) or not target
            or a3.get("business") != "LF" or a4.get("business") != "LF"
            or a4.get("target_ref") != target
            or a2.get("target_ref") not in (target, a3.get("declared_target_hint"))
            or target not in a1.get("target_hints", [target])
               and a3.get("declared_target_hint") not in a1.get("target_hints", [])):
        return _blocked("A5_TARGET_OR_BUSINESS_IDENTITY_DRIFT", str(target))
    if (a3.get("status") != "SOURCE_READBACK_PROCESSED_UNATTESTED"
            or a4.get("status") not in (
                "PLANNED_BUILD_IMPACT_UNATTESTED", "PROJECTED_UNATTESTED", "IMPACT_UNKNOWN")
            or not isinstance(a3.get("source_refs"), list)
            or not isinstance(a4.get("evidence_refs"), list)):
        return _blocked("A5_A3_A4_SOURCE_NOT_READY_FOR_PROJECTION", target)
    if not isinstance(a4.get("unresolved_material_impacts"), list):
        return _blocked("A5_A4_MATERIAL_GAP_INVENTORY_REQUIRED", target)
    source_refs = list(dict.fromkeys(
        x for x in a3["source_refs"] + a4["evidence_refs"] if isinstance(x, str) and x))
    if not source_refs:
        return _blocked("A5_EVIDENCE_REFS_MISSING", target)
    # Missing authority readback is an evidence gap, not an invented human
    # decision or ADR. Pending A3 rules remain outside implemented scope.
    if readback is None:
        reason = "A5_ADR_MATERIAL_TRIGGER_READBACK_REQUIRED"
        row = _decision(target, [target], status="UNRESOLVED",
                        disposition="ADR_BLOCKED", refs=source_refs,
                        material_question="Is any governed architecture decision material?",
                        unresolved=[reason], rationale="No exact authority readback supplied")
        return {
            "schema_version": SCHEMA, "status": "UNRESOLVED",
            "target_ref": target, "business": "LF",
            "decision_context": row, "decisions": [row],
            "unresolved_material_questions": [reason],
            "evidence_refs": source_refs, "blocking_codes": [reason],
            "source_attested": False, "independent_judge_verified": False,
            "a6_allowed": False, "no_write_performed": True,
        }
    if (not isinstance(readback, dict)
            or readback.get("schema_version") != PACKET
            or readback.get("business") != "LF"
            or readback.get("target_ref") != target
            or readback.get("source_attested") is not False):
        return _blocked("A5_AUTHORITY_READBACK_IDENTITY_INVALID", target)
    review = readback.get("adr_trigger_review")
    if not isinstance(review, dict):
        return _blocked("A5_ADR_TRIGGER_REVIEW_REQUIRED", target)
    triggers = review.get("flags")
    if not isinstance(triggers, dict) or set(triggers) != set(policy["material_adr_triggers"]):
        return _blocked("A5_ADR_TRIGGER_SET_INCOMPLETE", target)
    if any(type(v) is not bool and v != "UNKNOWN" for v in triggers.values()):
        return _blocked("A5_ADR_TRIGGER_VALUE_INVALID", target)
    evidence_ref = review.get("evidence_ref")
    if (not isinstance(evidence_ref, str)
            or evidence_ref not in source_refs
            or review.get("source_attested") is not False):
        return _blocked("A5_ADR_TRIGGER_PROVENANCE_NOT_BOUND", target)
    positive = sorted(k for k, v in triggers.items() if v is True)
    unknown = sorted(k for k, v in triggers.items() if v == "UNKNOWN")
    unresolved = ["A5_ADR_TRIGGER_UNKNOWN:" + k for k in unknown]
    for gap in a4["unresolved_material_impacts"]:
        if not isinstance(gap, dict) or not isinstance(gap.get("code"), str):
            return _blocked("A5_A4_GAP_ITEM_INVALID", target)
        unresolved.append("A4:" + gap["code"])
    # Pending definitions alone are not decision conflicts. Do not turn
    # missing existing-code destinations into required ADRs/human approvals.
    adr_ref = readback.get("existing_adr_ref")
    assertion = readback.get("adr_assertion")
    adr_search = readback.get("adr_search")
    authority_refs = []
    disposition, status, rationale = "ADR_BLOCKED", "UNRESOLVED", "ADR evidence not resolved"
    if unknown:
        unresolved.append("A5_MATERIAL_ADR_CLASSIFICATION_UNVERIFIED")
    elif not positive:
        if adr_ref is not None or assertion is not None or adr_search is not None:
            # Extraneous ADR claim cannot promote or overrule proven local scope.
            return _blocked("A5_NONMATERIAL_ADR_CLAIM_CONFLICT", target)
        disposition = "NOT_REQUIRED"
        rationale = "All seven ADR triggers explicitly negative; local HOW remains PG-03"
    elif adr_ref is not None:
        if (not isinstance(adr_ref, str) or not adr_ref
                or not isinstance(assertion, dict)
                or assertion.get("schema_version") != "ENGINEERING_CURRENT_ADR_ASSERT_V1"
                or assertion.get("status") != "PASS"
                or assertion.get("adr") != adr_ref
                or str(assertion.get("estado", "")).lower() != "vigente"
                or not assertion.get("created_at")):
            return _blocked("A5_EXISTING_ADR_CURRENT_ASSERTION_INVALID", target)
        authority_refs.append("adr://" + adr_ref)
        disposition = "REUSE_CURRENT_ADR"
        rationale = "Existing current ADR assertion supplied by authorized provider; no new ADR"
    elif (isinstance(adr_search, dict)
          and adr_search.get("state") == "NO_CURRENT_ADR"
          and adr_search.get("source_function") == "transversal.decision_log"
          and adr_search.get("target_ref") == target
          and adr_search.get("source_attested") is False
          and adr_search.get("evidence_ref") in source_refs):
        disposition, status = "NEW_ADR_REQUIRED", "REQUIRES_DECISION"
        unresolved.append("A5_NEW_ARCHITECTURE_DECISION_REQUIRES_OWNER")
        rationale = "Material ADR trigger and source-bound absence; A5 cannot approve new ADR"
    else:
        unresolved.append("A5_CURRENT_ADR_ASSERTION_OR_NEGATIVE_LOOKUP_REQUIRED")
    # Historical ASOF is never equivalent to current decision approval.
    asof = readback.get("asof_resolution")
    if asof is not None:
        if (not isinstance(asof, dict)
                or asof.get("schema_version") != "LF_DECISION_CONTEXT_ASOF_RESOLUTION_V1"
                or asof.get("state") not in ("UNKNOWN", "RESOLVED")
                or (asof.get("state") == "RESOLVED"
                    and (asof.get("resolution_basis") != "IMMUTABLE_RECORDED_CONTEXT"
                         or asof.get("latest_reinterpreted") is not False
                         or asof.get("subject_ref") != target))):
            return _blocked("A5_ASOF_HISTORICAL_READBACK_INVALID", target)
        if asof.get("state") == "RESOLVED":
            authority_refs.append("asof://" + str(asof.get("context_id")))
            unresolved.append("A5_HISTORICAL_ASOF_NOT_CURRENT_DECISION")
    # Currentness and owner approval are external runtime responsibilities:
    # even when an ADR can be reused, never fabricate STABLE or A6_ALLOWED.
    unresolved = list(dict.fromkeys(unresolved))
    if status != "REQUIRES_DECISION":
        status = "UNRESOLVED"
    row = _decision(
        target, [target], status=status, disposition=disposition,
        refs=source_refs, authority_refs=authority_refs, material_question=(
            "Approve architecture change: " + ", ".join(positive)
            if positive else "No architecture change required by reviewed material scope"),
        unresolved=unresolved, adr_ref=adr_ref if disposition == "REUSE_CURRENT_ADR" else None,
        rationale=rationale,
    )
    return {
        "schema_version": SCHEMA, "status": status, "target_ref": target,
        "business": "LF", "decision_context": row, "decisions": [row],
        "material_adr_triggers_true": positive,
        "material_adr_triggers_unknown": unknown,
        "excluded_pending_definitions_are_decisions": False,
        "unresolved_material_questions": unresolved,
        "evidence_refs": source_refs, "blocking_codes": unresolved,
        "source_attested": False, "independent_judge_verified": False,
        "a6_allowed": False, "no_write_performed": True,
    }



def run(inputs: Any, readback: Any = None, *, business: str = "LF") -> dict:
    """Expose source-material per-item decisions without changing ADR core.

    The deterministic adapter cannot attest source currentness or authorize
    A6. Semantic adjudication of material questions remains an independent
    check, not an LLM call hidden inside this step.
    """
    base = _run_base(inputs, readback, business=business)
    if base.get("status") == "BLOCKED" or business != "LF":
        return base
    helper = Path(__file__).resolve().parents[1] / "adapters/material_decision_enrichment_v1.py"
    spec = importlib.util.spec_from_file_location("a5_material_enrichment_v1", helper)
    if spec is None or spec.loader is None:
        return _blocked("A5_MATERIAL_ENRICHMENT_ADAPTER_UNAVAILABLE",
                        base.get("target_ref"))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        output = mod.enrich(base, inputs, readback)
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return _blocked("A5_MATERIAL_ENRICHMENT_FAILED", base.get("target_ref"))
    if output.get("status") == "BLOCKED":
        return output
    if isinstance(output.get("decision_context"), dict):
        dc = output["decision_context"]
        dc["decision_fingerprint_sha256"] = _digest(dc)
        output["decisions"] = [deepcopy(dc)]
    return output
