"""A3 source-only consumer of existing A2→A3 canonical handoff and LF readback.

No new source resolver, Router, classifier, SQL, network, model, or A4
dispatch. The host performs existing governed source reads. This module only
organizes *supplied* source rows and never attests identity or currentness.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from typing import Any

SCHEMA = "TARGETED_EVIDENCE_SET_V1"
INPUTS = {"REQUEST_CONTEXT_V1", "ANALYSIS_CHANGE_CLASSIFICATION_V1"}
MATERIAL_SECTIONS = {
    "fields": list, "errors": list, "visual": dict,
    "context": dict, "metadata": dict, "profiles": list,
    "analytics": list, "evidence": list,
}


def _material_contract(value: Any, screen_ref: str) -> dict:
    """Keep ALL material contract definitions, typed by source status.

    Consolidated screen contract only; source metadata is checked at the
    authorized provider seam. This is not approval, source attestation, A4
    admission, or an independent judge.
    """
    if not isinstance(value, dict) or set(value) != set(MATERIAL_SECTIONS):
        return blocked("A3_MATERIAL_CONTRACT_SECTIONS_INCOMPLETE")
    for key, typ in MATERIAL_SECTIONS.items():
        if not isinstance(value[key], typ):
            return blocked("A3_MATERIAL_CONTRACT_SECTION_TYPE_INVALID")
    statuses = []
    seen_paths = set()

    def scan(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            status = node.get("status")
            if isinstance(status, str):
                if not status.strip():
                    raise ValueError("A3_MATERIAL_EMPTY_STATUS")
                if pointer in seen_paths:
                    raise ValueError("A3_MATERIAL_DUPLICATE_PATH")
                seen_paths.add(pointer)
                statuses.append({
                    "pointer": pointer,
                    "source_ref": screen_ref + "#contract/" + pointer,
                    "source_status": status,
                    "source_only_candidate": status == "VIGENTE",
                    "implementation_approved": False,
                })
            for key, item in node.items():
                scan(item, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                scan(item, pointer + "/" + str(index))

    try:
        for section in MATERIAL_SECTIONS:
            scan(value[section], section)
    except (ValueError, RecursionError):
        return blocked("A3_MATERIAL_CONTRACT_STATUS_STRUCTURE_INVALID")
    return {
        "status": "MATERIAL_CONTRACT_PROJECTED_UNATTESTED",
        "source_ref": screen_ref,
        "source_function": "lf_ops.fn_screen_contract_v1",
        "contract_sections": deepcopy(value),
        "status_items": statuses,
        "counts": {
            "sections": len(MATERIAL_SECTIONS),
            "status_items": len(statuses),
            "vigente_source_candidates": sum(x["source_only_candidate"] for x in statuses),
            "pending_or_other_status": sum(not x["source_only_candidate"] for x in statuses),
        },
        "source_attested": False, "runtime_authorized": False,
        "a4_allowed": False,
    }


def blocked(code: str) -> dict:
    return {
        "schema_version": SCHEMA, "status": "BLOCKED",
        "blocking_codes": [code], "sufficiency_verdict": "BLOCKED",
        "evidence_items": [], "source_refs": [], "currentness_refs": [],
        "target_granularity": None, "authority_state": "UNKNOWN",
        "implementation_state": "UNKNOWN", "target_resolution": None,
        "authority_binding_refs": [],
        "as_is_baseline_or_new_implementation_evidence": None,
        "unresolved_material_gaps": [code], "a4_allowed": False,
        "source_attested": False, "independent_judge_verified": False,
        "runtime_qualified": False, "no_write_performed": True,
    }


def run(canonical_inputs: Any, resolved_sources: Any = None,
        *, business: str = "LF") -> dict:
    """Project already retrieved evidence; no authority is derived from args.

    canonical_inputs contains EXACTLY A3's two canonical input contracts.
    resolved_sources is an untrusted readback sidecar supplied by the existing
    authorized source adapter, NOT a third canonical input or an RPC handle.
    """
    if business != "LF":
        return blocked("A3_BUSINESS_NOT_ENABLED_FOR_LF_SKILL")
    if not isinstance(canonical_inputs, dict) or set(canonical_inputs) != INPUTS:
        return blocked("A3_EXACT_TWO_CANONICAL_INPUTS_REQUIRED")
    context = canonical_inputs["REQUEST_CONTEXT_V1"]
    cls = canonical_inputs["ANALYSIS_CHANGE_CLASSIFICATION_V1"]
    if (not isinstance(context, dict) or not isinstance(cls, dict)
            or context.get("schema_version") != "REQUEST_CONTEXT_V1"
            or cls.get("schema_version") != "ANALYSIS_CHANGE_CLASSIFICATION_V1"
            or context.get("no_solution_inferred") is not True
            or not isinstance(context.get("objective"), dict)
            or not isinstance(context.get("constraints"), list)
            or not isinstance(context.get("source_refs"), list)
            or not isinstance(context.get("target_hints"), list)):
        return blocked("A3_CANONICAL_INPUT_SHAPE_INVALID")
    target = cls.get("target_ref")
    if (not isinstance(target, str) or not target
            or target not in context["target_hints"]
            or cls.get("target_granularity") != "SCREEN"):
        return blocked("A3_TARGET_SCOPE_OR_GRANULARITY_UNRESOLVED")
    if not isinstance(resolved_sources, dict):
        return blocked("A3_GOVERNED_SOURCE_READBACK_REQUIRED")
    if (resolved_sources.get("schema_version") != "LF_SCREEN_SOURCE_READBACK_V1"
            or resolved_sources.get("business") != "LF"
            or resolved_sources.get("source_function") != "lf_ops.fn_screen_contract_v1"):
        return blocked("A3_LF_SOURCE_IDENTITY_CONFLICT")
    canonical_target = resolved_sources.get("target_ref")
    if not isinstance(canonical_target, str) or not canonical_target.strip():
        return blocked("A3_CANONICAL_TARGET_REQUIRED")
    ref = resolved_sources.get("screen_ref")
    if ref != "supabase://lf_ops.pantallas/" + canonical_target:
        return blocked("A3_EXACT_SCREEN_REF_MISMATCH")
    # A1 intentionally retains the literal target mention, not a guessed ID.
    # Resolution belongs to the existing A3 authorized source-readback seam.
    # This adapter checks an untrusted source projection; it cannot attest it.
    identity = None
    if canonical_target != target:
        identity = resolved_sources.get("target_identity_binding")
        if (not isinstance(identity, dict)
                or identity.get("requested_target_ref") != target
                or target not in context["objective"].get("problem_statement", "")
                or identity.get("resolved_target_ref") != canonical_target
                or identity.get("source_ref") != ref
                or identity.get("source_function") != resolved_sources["source_function"]
                or identity.get("resolution_state") != "SOURCE_MATCH_CANDIDATE_UNATTESTED"
                or identity.get("source_attested") is not False):
            return blocked("A3_RAW_TARGET_IDENTITY_BINDING_MISSING_OR_UNVERIFIED")
    if (not isinstance(resolved_sources.get("screen_status"), str)
            or not isinstance(resolved_sources.get("contract_version"), str)):
        return blocked("A3_SCREEN_METADATA_MISSING")
    rows = resolved_sources.get("linked_rules")
    policies = resolved_sources.get("policy_links")
    if not isinstance(rows, list) or not isinstance(policies, list):
        return blocked("A3_LINKED_RULES_AND_POLICIES_REQUIRED")
    seen, approved, excluded = set(), [], []
    for item in rows:
        if not isinstance(item, dict):
            return blocked("A3_RULE_ROW_INVALID")
        code, status, pending = item.get("code"), item.get("status"), item.get("pending_decision")
        source, assoc = item.get("source_ref"), item.get("association_ref")
        if (not isinstance(code, str) or not code or code in seen
                or status not in ("VIGENTE", "CANDIDATO", "SUSPENDIDO", "INACTIVO")
                or type(pending) is not bool
                or not isinstance(source, str)
                or not source.startswith("supabase://lf_ops.reglas/")
                or not isinstance(assoc, str)
                or not assoc.startswith("supabase://lf_ops.reglas_pantallas/")):
            return blocked("A3_RULE_SOURCE_ROW_CONFLICT_OR_DUPLICATED")
        seen.add(code)
        row = {
            "rule_code": code, "title": item.get("title"),
            "description": item.get("description"),
            "rule_status": status, "pending_decision": pending,
            "source_ref": source, "association_ref": assoc,
            "evidence_kind": "DIRECT_SCREEN_RULE",
            "source_attestation_state": "PROVIDER_READBACK_UNATTESTED",
        }
        if status == "VIGENTE" and pending is False:
            approved.append(row)
        else:
            row["exclusion_reason"] = (
                "DECISION_PENDING" if pending else "RULE_NOT_VIGENTE"
            )
            excluded.append(row)
    # Mandatory rule-inheritance readback: effective = explicit + declarative
    # applicability + derived global, from the EXISTING T-REMED/IG read path.
    # Never mistake recommendations from similar screens for effective links.
    effective = resolved_sources.get("effective_rule_readback")
    if not isinstance(effective, dict):
        return blocked("A3_EFFECTIVE_RULE_INHERITANCE_READ_REQUIRED")
    screen_id = effective.get("screen_id")
    effective_ref = (
        "supabase://programacion.fn_input_effective_rule_links_v1/"
        + str(screen_id) + "/INPUT_GOVERNANCE"
    )
    if (type(screen_id) is not int or screen_id < 1
            or effective.get("source_function") != "programacion.fn_input_effective_rule_links_v1"
            or effective.get("business") != "LF"
            or effective.get("target_ref") != canonical_target
            or effective.get("consumer") != "INPUT_GOVERNANCE"
            or effective.get("source_ref") != effective_ref
            or effective.get("source_attested") is not False):
        return blocked("A3_EFFECTIVE_RULE_INHERITANCE_SOURCE_INVALID")
    links = effective.get("rules")
    if not isinstance(links, list) or not links:
        return blocked("A3_EFFECTIVE_RULE_INHERITANCE_ITEMS_MISSING")
    direct_by_code = {row["rule_code"]: row for row in approved + excluded}
    effective_codes, effective_direct, inherited_approved, inherited_excluded = set(), set(), [], []
    for link in links:
        if not isinstance(link, dict):
            return blocked("A3_EFFECTIVE_RULE_ITEM_INVALID")
        code = link.get("code")
        source = link.get("source_ref")
        status = link.get("status")
        pending = link.get("pending_decision")
        origin = link.get("binding_source")
        if (not isinstance(code, str) or not code or code in effective_codes
                or origin not in ("LEGACY_EXPLICIT", "DECLARATIVE_APPLICABILITY_V1", "DERIVED_GLOBAL")
                or status not in ("VIGENTE", "CANDIDATO", "SUSPENDIDO", "INACTIVO")
                or type(pending) is not bool
                or not isinstance(source, str) or not source.startswith("supabase://lf_ops.reglas/")
                or not source.removeprefix("supabase://lf_ops.reglas/").isdigit()):
            return blocked("A3_EFFECTIVE_RULE_ITEM_UNSUPPORTED_OR_DUPLICATE")
        effective_codes.add(code)
        if origin != "DERIVED_GLOBAL":
            direct = direct_by_code.get(code)
            if (direct is None or direct["source_ref"] != source
                    or direct["rule_status"] != status
                    or direct["pending_decision"] != pending):
                return blocked("A3_EFFECTIVE_DIRECT_RULE_DRIFT")
            effective_direct.add(code)
            continue
        if code in direct_by_code:
            return blocked("A3_DERIVED_GLOBAL_RULE_STATE_OR_SCOPE_CONFLICT")
        row = {
            "rule_code": code,
            "title": link.get("title"),
            "description": link.get("description"),
            "rule_status": status,
            "pending_decision": pending,
            "source_ref": source,
            "association_ref": effective_ref,
            "binding_source": origin,
            "evidence_kind": "INHERITED_GLOBAL_EFFECTIVE_RULE",
            "source_attestation_state": "PROVIDER_READBACK_UNATTESTED",
        }
        # User-approved partial scope: pending/non-current inherited rules
        # are excluded with evidence; they do not block unrelated VIGENTE.
        if status == "VIGENTE" and not pending:
            inherited_approved.append(row)
        else:
            row["exclusion_reason"] = (
                "DECISION_PENDING" if pending else "RULE_NOT_VIGENTE"
            )
            inherited_excluded.append(row)
    if effective_direct != set(direct_by_code):
        return blocked("A3_EFFECTIVE_RULE_INVENTORY_INCOMPLETE")
    if len(effective_codes) != (
        len(direct_by_code) + len(inherited_approved) + len(inherited_excluded)
    ):
        return blocked("A3_EFFECTIVE_RULE_CARDINALITY_MISMATCH")
    policy_states = []
    for p in policies:
        if (not isinstance(p, dict)
                or not isinstance(p.get("status"), str)
                or not isinstance(p.get("source_ref"), str)
                or not p["source_ref"].startswith("supabase://lf_ops.pantallas_politicas/")):
            return blocked("A3_POLICY_LINK_SOURCE_INVALID")
        policy_states.append({
            "source_ref": p["source_ref"], "policy_kind": p.get("policy_kind"),
            "status": p["status"], "is_approved_binding": p["status"] == "VIGENTE",
        })
    policy_reader_path = Path(__file__).resolve().parents[1] / "adapters/policy_readback_v1.py"
    policy_spec = importlib.util.spec_from_file_location("a3_policy_readback", policy_reader_path)
    if policy_spec is None or policy_spec.loader is None:
        return blocked("A3_POLICY_READER_MODULE_UNAVAILABLE")
    policy_module = importlib.util.module_from_spec(policy_spec)
    try:
        policy_spec.loader.exec_module(policy_module)
        policy_resolution = policy_module.project(
            effective, policies, resolved_sources.get("policy_resolution_readback"),
            target_ref=canonical_target, screen_ref=ref,
        )
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return blocked("A3_POLICY_READER_FAILED")
    if policy_resolution.get("status") == "BLOCKED":
        return blocked(policy_resolution["blocking_code"])
    policy_states = policy_resolution["policy_link_resolution"]
    policy_deferred = set(policy_resolution["rule_codes_policy_dependency_pending"])
    all_approved_rules = approved + inherited_approved
    scoped_policy_clear, scoped_policy_deferred, annotated_evidence = [], [], []
    for source_row in all_approved_rules:
        row = deepcopy(source_row)
        if row["rule_code"] in policy_deferred:
            row["policy_dependency_disposition"] = "DEFER_UNAPPROVED_OR_UNRESOLVED_POLICY"
            scoped_policy_deferred.append(row)
        else:
            row["policy_dependency_disposition"] = "NO_KNOWN_POLICY_DEPENDENCY_BLOCKER"
            scoped_policy_clear.append(row)
        row["runtime_implementation_approved"] = False
        annotated_evidence.append(row)
    gaps = [
        "SOURCE_READBACK_CURRENTNESS_AND_AUTHORITY_NOT_ATTESTED",
        "GITHUB_CURRENT_IMPLEMENTATION_AND_AS_IS_MISSING",
    ]
    # Scope accepted by the user: pending definitions are excluded, not a
    # universal prerequisite to continue the approved part of the screen.
    alerts = []
    material = None
    if "contract_sections" not in resolved_sources:
        gaps.append("CONSOLIDATED_SCREEN_MATERIAL_READBACK_MISSING")
    else:
        material = _material_contract(resolved_sources["contract_sections"], ref)
        if material["status"] == "BLOCKED":
            return blocked(material["blocking_codes"][0])
        if material["counts"]["pending_or_other_status"]:
            alerts.append("SCREEN_MATERIAL_PENDING_ITEMS_SOURCE_ONLY_NOT_IMPLEMENTABLE")
    if resolved_sources["screen_status"] != "VIGENTE":
        alerts.append("SCREEN_DEFINITION_NOT_VIGENTE")
    if any(not p["approved_for_binding"] for p in policy_states):
        alerts.append("SCREEN_POLICY_ASSOCIATIONS_EXCLUDED_PENDING_APPROVAL")
    if policy_resolution["rule_codes_policy_dependency_pending"]:
        alerts.append("POLICY_DEPENDENT_RULES_WITH_UNAPPROVED_BINDING_OR_POLICY_EXCLUDED")
    if excluded or inherited_excluded:
        alerts.append("PENDING_RULES_EXCLUDED_AS_USER_REQUESTED")
    if inherited_approved:
        alerts.append("DERIVED_GLOBAL_EFFECTIVE_READBACK_NOT_RUNTIME_ATTESTATION")
    consolidated = resolved_sources.get("consolidated_rule_status_counts")
    if consolidated is not None:
        if (not isinstance(consolidated, dict)
                or any(not isinstance(k, str) or type(v) is not int or v < 0
                       for k, v in consolidated.items())):
            return blocked("A3_CONSOLIDATED_COUNTS_INVALID")
        if sum(consolidated.values()) > len(rows):
            alerts.append("TRANSVERSAL_RULE_APPLICABILITY_REQUIRES_EXACT_BINDING")
    as_is = None
    if "as_is_readback" in resolved_sources:
        # The governed host supplies the readback; no new resolver is created.
        helper = Path(__file__).resolve().parents[1] / "adapters/as_is_projection_v1.py"
        spec = importlib.util.spec_from_file_location("a3_as_is_projection", helper)
        if spec is None or spec.loader is None:
            return blocked("A3_AS_IS_PROJECTION_MODULE_UNAVAILABLE")
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            as_is = mod.project(resolved_sources["as_is_readback"], canonical_target)
        except (OSError, ValueError, TypeError, AttributeError):
            return blocked("A3_AS_IS_PROJECTION_MODULE_UNAVAILABLE")
        if as_is.get("status") == "BLOCKED":
            return blocked(as_is["blocking_code"])
        gaps.remove("GITHUB_CURRENT_IMPLEMENTATION_AND_AS_IS_MISSING")
        gaps.extend(as_is["material_gaps"])
    return {
        "schema_version": SCHEMA,
        "status": "SOURCE_READBACK_PROCESSED_UNATTESTED",
        "blocking_codes": gaps[:],
        "scope_alerts": alerts,
        "sufficiency_verdict": "NEED_MORE_EVIDENCE",
        "business": "LF", "target_ref": canonical_target,
        "declared_target_hint": target,
        "target_identity_binding": {
            "requested_target_ref": target,
            "resolved_target_ref": canonical_target,
            "source_ref": ref,
            "resolution_state": "SOURCE_MATCH_CANDIDATE_UNATTESTED",
            "source_attested": False,
        },
        "target_granularity": cls["target_granularity"],
        "authority_state": "UNKNOWN", "implementation_state": "UNKNOWN",
        "evidence_items": annotated_evidence,
        "excluded_rule_items": excluded + inherited_excluded,
        "policy_scope_clear_rule_candidates": scoped_policy_clear,
        "policy_deferred_rule_items": scoped_policy_deferred,
        "inheritance_readback": {
            "source_ref": effective_ref,
            "source_function": effective["source_function"],
            "consumer": effective["consumer"],
            "binding_sources": ["LEGACY_EXPLICIT", "DECLARATIVE_APPLICABILITY_V1", "DERIVED_GLOBAL"],
            "source_attested": False,
            "similarity_recommendations_are_not_effective_rules": True,
        },
        "policy_link_items": policy_states,
        "policy_resolution": policy_resolution,
        "material_contract_readback": material,
        "counts": {
            "direct_rules_total": len(rows),
            "direct_rules_vigente_no_pending": len(approved),
            "direct_rules_excluded": len(excluded),
            "effective_rules_total": len(effective_codes),
            "effective_rules_vigente_no_pending": len(approved) + len(inherited_approved),
            "effective_rules_excluded": len(excluded) + len(inherited_excluded),
            "inherited_derived_global_vigente": len(inherited_approved),
            "inherited_derived_global_excluded": len(inherited_excluded),
            "policy_links_total": len(policies),
            "material_sections_total": material["counts"]["sections"] if material else 0,
            "material_items_pending_or_other_status": material["counts"]["pending_or_other_status"] if material else 0,
            "policy_links_not_vigente": sum(not p["approved_for_binding"] for p in policy_states),
            "policy_objects_resolved": policy_resolution["counts"]["policy_objects"],
            "policy_objects_vigente": policy_resolution["counts"]["policy_objects_vigente"],
            "policy_objects_excluded": policy_resolution["counts"]["policy_objects_excluded"],
            "rule_policy_dependency_occurrences": policy_resolution["counts"]["referenced_policy_occurrences"],
            "rules_with_unapproved_or_unresolved_policy": policy_resolution["counts"]["rules_with_unapproved_or_unresolved_policy"],
            "policy_clear_source_candidates": len(scoped_policy_clear),
            "policy_deferred_source_candidates": len(scoped_policy_deferred),
            "consolidated_rule_status_counts": deepcopy(consolidated),
        },
        "source_refs": [ref, effective_ref]
                       + [x["source_ref"] for x in approved + inherited_approved]
                       + [x["source_ref"] for x in policy_resolution["approved_policy_objects"]]
                       + (as_is["source_refs"] if as_is else []),
        "currentness_refs": [],
        "authority_binding_refs": [],
        "target_resolution": {
            "target_ref": canonical_target,
            "declared_target_hint": target,
            "source_ref": ref,
            "declared_screen_status": resolved_sources["screen_status"],
            "contract_version": resolved_sources["contract_version"],
            "authority_state": "UNKNOWN", "implementation_state": "UNKNOWN",
            "screen_readback_not_source_attestation": True,
            "related_as_is_component_count": len(as_is["related_components"]) if as_is else 0,
            "authority_candidate_ref": as_is["authority_candidate"]["source_ref"] if as_is else None,
        },
        "as_is_baseline_or_new_implementation_evidence": deepcopy(as_is) if as_is else None,
        "unresolved_material_gaps": gaps,
        "declared_constraints": deepcopy(context["constraints"]),
        "source_readback_function": resolved_sources["source_function"],
        "a4_allowed": False, "source_attested": False,
        "independent_judge_verified": False, "runtime_qualified": False,
        "no_write_performed": True,
    }
