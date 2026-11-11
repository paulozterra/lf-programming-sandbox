#!/usr/bin/env python3
"""Contract-level cross-field checks for Analysis's *unqualified* model proposal.

No source content or provider identity is proven by this function. A9's canonical
snapshot validator, an independent judge, and PG-01 remain separate.
"""
from __future__ import annotations


STAGES = tuple(f"A{i}" for i in range(1, 10))
READY = "READY_CANDIDATE"


def validate(payload):
    errors: list[dict[str, str]] = []

    def reject(code, path="$"):
        errors.append({"code": code, "path": path})

    if not isinstance(payload, dict):
        return {"status": "FAIL", "errors": [{"code": "ANALYSIS_PAYLOAD_NOT_OBJECT", "path": "$"}]}
    if payload.get("schema_version") != "ANALYSIS_IMPLEMENTATION_PACKAGE_V1":
        reject("ANALYSIS_SCHEMA_ID_MISMATCH")
    if payload.get("candidate_only") is not True:
        reject("ANALYSIS_CANDIDATE_ONLY_REQUIRED")

    stages = payload.get("stage_trace")
    if not isinstance(stages, list) or [x.get("stage") if isinstance(x, dict) else None for x in stages] != list(STAGES):
        reject("ANALYSIS_A1_A9_SEQUENCE_REQUIRED", "$.stage_trace")

    scopes = payload.get("scope_proposals", [])
    if not isinstance(scopes, list) or not scopes or any(not isinstance(s, dict) for s in scopes):
        reject("ANALYSIS_SCOPES_REQUIRED")
        scopes = []
    ids = [s.get("scope_id") for s in scopes]
    if len(ids) != len(set(ids)) or None in ids:
        reject("ANALYSIS_DUPLICATE_OR_EMPTY_SCOPE")
    by_scope = {s.get("scope_id"): s for s in scopes if s.get("scope_id")}
    actual_front_refs = {sid: set() for sid in by_scope}
    blocked_scopes = set()

    classification = payload.get("classification") or {}
    if not isinstance(classification, dict):
        classification = {}
    unknown_state = (classification.get("authority_state") == "UNKNOWN" or
                     classification.get("implementation_state") == "UNKNOWN")
    if unknown_state and classification.get("depth") == "L1":
        reject("ANALYSIS_UNKNOWN_MATERIAL_DEPTH_CANNOT_BE_L1")
    if unknown_state and any(s.get("readiness_candidate") == READY for s in scopes):
        reject("ANALYSIS_UNKNOWN_TARGET_STATE_FALSE_READY")

    fronts = payload.get("material_fronts")
    if not isinstance(fronts, list):
        fronts = []
        reject("ANALYSIS_MATERIAL_FRONT_LIST_REQUIRED")
    front_ids = [f.get("front_id") for f in fronts if isinstance(f, dict)]
    if len(front_ids) != len(fronts) or len(set(front_ids)) != len(front_ids):
        reject("ANALYSIS_FRONT_DUPLICATE_OR_INVALID")
    for front in fronts:
        if not isinstance(front, dict):
            continue
        fid = front.get("front_id")
        ref_ids = front.get("scope_ids") or []
        for scope_id in ref_ids:
            if scope_id not in by_scope:
                reject("ANALYSIS_FRONT_UNKNOWN_SCOPE")
            else:
                actual_front_refs[scope_id].add(fid)
        if front.get("closure") == "BLOCKED":
            if not front.get("blockers"):
                reject("ANALYSIS_BLOCKED_FRONT_NEEDS_BLOCKER")
            blocked_scopes.update(ref_ids)
        if front.get("closure") == "CLOSED" and front.get("blockers"):
            reject("ANALYSIS_CLOSED_FRONT_HAS_BLOCKERS")
        if front.get("obligation_mode") in {"REUSE_AS_IS", "NOT_APPLICABLE"}:
            if front.get("closure") != "CLOSED" or not front.get("evidence_refs"):
                reject("ANALYSIS_REUSE_OR_NA_REQUIRES_CURRENT_EVIDENCE")
        if front.get("closure") == "CLOSED" and front.get("obligation_mode") == "REQUIRED":
            if not front.get("evidence_refs"):
                reject("ANALYSIS_CLOSED_REQUIRED_FRONT_NEEDS_EVIDENCE")

    for scope_id, scope in by_scope.items():
        refs = scope.get("material_front_refs") or []
        if len(refs) != len(set(refs)) or set(refs) != actual_front_refs.get(scope_id, set()):
            reject("ANALYSIS_SCOPE_FRONT_BIDIRECTIONAL_MISMATCH")
        if scope.get("readiness_candidate") == READY:
            if scope_id in blocked_scopes or scope.get("blockers") or not refs:
                reject("ANALYSIS_FALSE_READY_SCOPE")

    for key, code in (
        ("material_unknowns", "ANALYSIS_UNKNOWN_MATERIAL_FALSE_READY"),
        ("decisions_pending", "ANALYSIS_UNRESOLVED_HUMAN_DECISION_FALSE_READY"),
    ):
        for item in payload.get(key) or []:
            if not isinstance(item, dict) or item.get("scope_id") not in by_scope:
                reject("ANALYSIS_UNMAPPED_MATERIAL_ITEM")
            elif by_scope[item["scope_id"]].get("readiness_candidate") == READY:
                reject(code)

    requirements = payload.get("requirements") or []
    for req in requirements:
        if not isinstance(req, dict) or req.get("scope_id") not in by_scope:
            reject("ANALYSIS_REQUIREMENT_UNKNOWN_SCOPE")
    if any(s.get("readiness_candidate") == READY for s in scopes) and not requirements:
        reject("ANALYSIS_READY_REQUIRES_TYPED_REQUIREMENTS")

    stop = payload.get("research_stop") or {}
    if not isinstance(stop, dict):
        stop = {}
    if stop.get("decision") == "STOP" and not (
        stop.get("decision_stable") is True
        and stop.get("all_material_fronts_accounted") is True
        and not stop.get("unresolved_decision_changing_questions")
    ):
        reject("ANALYSIS_STOP_WITH_UNRESOLVED_MATERIAL")
    if (payload.get("material_unknowns") or payload.get("decisions_pending")) and stop.get("decision") == "STOP":
        # Stopping research with explicit BLOCKED/REQUIRES_DECISION is legal, but
        # only if it is explicit and all material fronts accounted for.
        if not stop.get("all_material_fronts_accounted"):
            reject("ANALYSIS_STOP_COVERAGE_INCOMPLETE")

    readiness = [s.get("readiness_candidate") for s in scopes]
    ready_count = readiness.count(READY)
    proposed = payload.get("package_readiness_candidate")
    if proposed == "READY_CANDIDATE" and ready_count != len(scopes):
        reject("ANALYSIS_PACKAGE_READINESS_FALSE_READY")
    if proposed == "PARTIAL_READY_CANDIDATE" and (ready_count == 0 or ready_count == len(scopes)):
        reject("ANALYSIS_PACKAGE_PARTIAL_NOT_JUSTIFIED")
    if proposed not in {"READY_CANDIDATE", "PARTIAL_READY_CANDIDATE"} and ready_count > 0:
        reject("ANALYSIS_PACKAGE_READY_SCOPE_HIDDEN")

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "admission_scope": "PROFILE_CANDIDATE_ONLY",
        "independent_semantic_judge": "NOT_EXECUTED",
        "pg01_consumer_verified": False,
        "downstream_authorized": False,
    }
