"""A8 ANALYSIS_STOP_RULE_V1. Stop policy driven only by material evidence.

Complete accounting is NOT closure. A7 may account for a BLOCKED front, but
this sandbox rule never STOPs with a BLOCKED front or unmapped A6 obligation.
No curiosity searches, duplicate reads, broad scans, or production authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from analysis.host.simulated_admission_gate import MODE, AdmissionBlocked, digest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_stop_rule_contract_v1.json"
STOP_REQUIREMENTS = [
    "decision_stable=true",
    "all_material_fronts_accounted=true",
    "unresolved_decision_changing_questions[]=empty",
    "additional_available_evidence_capable_of_changing_material_decision[]=empty",
]


def fail(code):
    raise AdmissionBlocked(code)


def _contract():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (contract.get("output_contract") != "ANALYSIS_STOP_RULE_V1"
            or contract.get("decision", {}).get("values")
            != ["STOP", "CONTINUE", "REQUIRES_DECISION", "BLOCKED"]
            or contract["decision"]["stop_requires"] != STOP_REQUIREMENTS
            or not all(contract["continuation_policy"].values())):
        fail("F3_A8_PINNED_STOP_CONTRACT_DRIFT")
    return contract


def _result(decision, stable, coverage_ref, accounted, questions, available,
            evidence, reason, requested=None, blocking_code=None,
            stable_basis="NOT_STABLE", lifted_codes=None):
    if requested is None:
        requested = []
    out = {
        "schema_version": "ANALYSIS_STOP_RULE_V1",
        "simulation_mode": MODE,
        "materiality_level": "HIGH",
        "requires_independent_exam": True,
        "decision": decision,
        "decision_stable": stable,
        "decision_stable_basis": stable_basis,
        "decision_stable_lifted_codes": list(lifted_codes or []),
        "material_front_coverage_ref": coverage_ref,
        "all_material_fronts_accounted": accounted,
        "unresolved_decision_changing_questions": questions,
        "additional_available_evidence_capable_of_changing_material_decision": available,
        "evidence_refs": sorted(set(evidence)),
        "reason": reason,
        "requested_material_evidence_refs": sorted(set(requested)),
        "blocking_code": blocking_code,
        "continuation_policy": {
            "continue_only_for_material_evidence": True,
            "no_curiosity_search": True,
            "no_duplicate_read": True,
            "no_full_scan_without_material_trigger": True,
        },
        "runtime_activated": False,
        "production_authority": False,
    }
    out["stop_rule_fingerprint_sha256"] = digest(out)
    return out



def _simulated_stability(a5, a7, admission):
    """Source-bound stability projection, NEVER an owner decision or real attestation.

    The A5 decisions[] ledger always contains a context row. Only a NOT_REQUIRED
    row with no owner choice, no open ADR triggers and exclusively lifted
    unresolved A4 codes is non-decision-changing. All other unknowns remain open.
    """
    if not isinstance(admission, dict):
        fail("F3_A8_ADMISSION_REQUIRED")
    if (admission.get("schema_version") != "SIMULATED_ADMISSION_V1"
            or admission.get("attestation_mode") != MODE
            or admission.get("a6_admitted") is not True
            or admission.get("authority_flags", {}).get("production_authority") is not False
            or admission.get("envelope_sha256") != a7.get("admission_envelope_sha256")):
        fail("F3_A8_ADMISSION_INVALID")
    lifts = admission.get("lifted_codes")
    if (not isinstance(lifts, list) or not all(isinstance(x, str) and x for x in lifts)
            or len(lifts) != len(set(lifts))):
        fail("F3_A8_ADMISSION_LIFTS_INVALID")
    for front in a7["material_fronts"]:
        if front.get("closure_basis") == "SIMULATED_ADMISSION_LIFT":
            if (front.get("lifted_code") not in lifts
                    or front.get("admission_evidence_ref") != "sha256:" + digest(admission)
                    or front.get("admission_evidence_ref") not in front.get("evidence_refs", [])):
                fail("F3_A8_ADMISSION_FRONT_BINDING_INVALID")
    if a5.get("status") != "UNRESOLVED":
        return False, [], "NOT_STABLE"
    codes = a5.get("blocking_codes")
    if not isinstance(codes, list) or not codes or any(not isinstance(c, str) for c in codes):
        fail("F3_A8_A5_BLOCKING_CODES_INVALID")
    normalized = [c.split(":", 1)[1] if c.startswith("A4:") else c for c in codes]
    if not all(c in lifts for c in normalized):
        return False, [], "NOT_STABLE"
    # A5 always projects informational decision_items (obligation, excluded
    # scope, evidence to obtain). Their presence is NOT an owner decision.
    # Refuse any item that could actually change a governed choice.
    items = a5.get("decision_items")
    if not isinstance(items, list):
        return False, [], "NOT_STABLE"
    if (a5.get("pending_owner_decisions") != []
            or a5.get("architecture_decision_items") != []
            or any(not isinstance(item, dict)
                   or item.get("owner_decision_required") is not False
                   or item.get("material_question") is not None
                   or item.get("decision_classification") not in (
                       "NO_NEW_DECISION_REQUIRED_SOURCE_CANDIDATE",
                       "EXCLUDED_FROM_APPROVED_SCOPE",
                       "TARGETED_EVIDENCE_REQUIRED",
                       "CANONICAL_CONTEXT_PRESERVED",
                   )
                   for item in items)):
        return False, [], "NOT_STABLE"
    if a5.get("material_adr_triggers_true") != [] or a5.get("material_adr_triggers_unknown") != []:
        return False, [], "NOT_STABLE"
    # Existing A5 decision_context and decisions[] are descriptive records,
    # not owner decision_items. Reject any actionable decision in that ledger.
    rows = a5.get("decisions")
    context = a5.get("decision_context")
    if (not isinstance(rows, list) or len(rows) != 1
            or not isinstance(context, dict) or rows[0] != context
            or context.get("adr_disposition") != "NOT_REQUIRED"
            or context.get("status") != "UNRESOLVED"
            or context.get("selected_option_ref") is not None
            or context.get("options_considered") != []
            or context.get("authority_refs") != []):
        return False, [], "NOT_STABLE"
    open_questions = a5.get("unresolved_material_questions")
    row_questions = context.get("unresolved_questions")
    if (not isinstance(open_questions, list)
            or not isinstance(row_questions, list)
            or open_questions != codes or row_questions != codes):
        return False, [], "NOT_STABLE"
    return True, sorted(set(normalized)), "SIMULATED_ADMISSION_LIFT"


def run(a3, a5, a7, admission):
    try:
        _contract()
        if (not isinstance(a3, dict) or not isinstance(a5, dict)
                or not isinstance(a7, dict)
                or a3.get("status") != "SOURCE_READBACK_PROCESSED_UNATTESTED"
                or a5.get("status") not in ("UNRESOLVED", "REQUIRES_DECISION")
                or a7.get("schema_version") != "MATERIAL_FRONT_COVERAGE_V1"
                or a7.get("simulation_mode") != MODE
                or a7.get("materiality_level") != "HIGH"
                or a7.get("requires_independent_exam") is not True):
            fail("F3_A8_INPUT_INVALID")
        fingerprint = a7.get("coverage_fingerprint_sha256")
        if fingerprint != digest({k:v for k,v in a7.items()
                                 if k != "coverage_fingerprint_sha256"}):
            fail("F3_A8_COVERAGE_DIGEST_INVALID")
        fronts = a7.get("material_fronts")
        candidates = a7.get("front_candidate_refs")
        if not isinstance(fronts, list) or not isinstance(candidates, list):
            fail("F3_A8_FRONT_LIST_INVALID")
        refs = [x.get("candidate_ref") for x in fronts if isinstance(x, dict)]
        if (len(refs) != len(fronts) or len(refs) != len(set(refs))
                or len(candidates) != len(set(candidates))
                or set(refs) != set(candidates)):
            fail("F3_A8_FRONT_ACCOUNTING_INVALID")
        included = {x["rule_code"] for x in
                    a3.get("policy_scope_clear_rule_candidates", [])}
        linked = {code for f in fronts if f.get("status") == "REQUIRED"
                  for code in f.get("obligation_refs", [])}
        missing = sorted(included - linked)
        if not included or linked - included:
            fail("F3_A8_SCOPE_RULES_INVALID")
        all_accounted = (a7.get("all_material_fronts_accounted") is True
                         and a7.get("unmapped_material_signals") == []
                         and not missing)
        blocked = [f for f in fronts if f.get("closure") == "BLOCKED"]
        evidence = list(a3.get("source_refs", [])) + list(a5.get("evidence_refs", []))
        stable, stable_lifts, stable_basis = _simulated_stability(a5, a7, admission)
        questions = []
        if (a5.get("status") == "REQUIRES_DECISION"
                or a5.get("material_adr_triggers_true")):
            questions = sorted(set(a5.get("unresolved_material_questions", [])))
            if not questions:
                questions = ["A5:OWNER_DECISION_REQUIRED"]
        requested = []
        for front in blocked:
            for blocker in front.get("blockers", []):
                if not isinstance(blocker, str) or not blocker:
                    fail("F3_A8_UNTYPED_MATERIAL_BLOCKER")
                requested.append(blocker)
        for code in missing:
            requested.append("A6_UNMAPPED_OBLIGATION:" + code)
        available = []  # no additional CURRENT evidence was supplied by F1/F2
        if questions:
            return _result("REQUIRES_DECISION", False, fingerprint, all_accounted,
                           questions, available, evidence,
                           "A5 requires explicit owner decision; STOP is forbidden", requested,
                           stable_basis=stable_basis, lifted_codes=stable_lifts)
        if not all_accounted:
            return _result("CONTINUE", False, fingerprint, False, [], available,
                           evidence,
                           "Material front coverage incomplete or A6 obligation unlinked; seek exact missing evidence",
                           requested, stable_basis=stable_basis, lifted_codes=stable_lifts)
        if blocked:
            return _result("CONTINUE", False, fingerprint, True, [], available,
                           evidence,
                           "Explicit BLOCKED material fronts remain: " +
                           ", ".join(sorted(set(requested))) + "; no STOP without closure",
                           requested, stable_basis=stable_basis, lifted_codes=stable_lifts)
        if not stable:
            # Admission did not close every A5 issue: never invent stability.
            remaining = sorted(set(a5.get("unresolved_material_questions", [])))
            requested.extend(remaining)
            return _result("CONTINUE", False, fingerprint, True, [], available,
                           evidence,
                           "A5 decision not stable; target material evidence only: " +
                           ", ".join(sorted(set(requested))),
                           requested, stable_basis=stable_basis, lifted_codes=stable_lifts)
        if available or questions:
            fail("F3_A8_STOP_GUARD_VIOLATION")
        return _result("STOP", True, fingerprint, True, [], [], evidence,
                       "All material fronts accounted, no BLOCKED front, A5 stable by simulated admission lift; no decision-changing questions or available evidence",
                       stable_basis=stable_basis, lifted_codes=stable_lifts)
    except (AdmissionBlocked, KeyError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, AdmissionBlocked) else "F3_A8_INPUT_INVALID"
        return _result("BLOCKED", False, None, False, [], [], [],
                       "Invalid or untrusted A8 input: " + code, blocking_code=code)
