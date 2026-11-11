"""A4: deterministic projection of the EXISTING shared impact core.

The authorized LF host reads the fixed S1-S5 source set. A4 does no
discovery, SQL, network, GitHub lookup, execution or attestation.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/deterministic_source_set_v1.json"
SCHEMA = "SHARED_CHANGE_IMPACT_ANALYSIS"
CORE = "SHARED_CHANGE_IMPACT_MAP_V1"
SIDECAR = "A4_EXISTING_IMPACT_CORE_READBACK_V1"
BUILD_INTENTS = frozenset({"CREATE", "CREATE_SCREEN", "IMPLEMENT", "IMPLEMENT_NEW", "BUILD_NEW"})


def _blocked(code: str, *, target: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA, "status": "BLOCKED",
        "target_ref": target, "blocking_codes": [code],
        "direct_impacts": [], "indirect_impacts": [], "consumers": [],
        "dependency_paths": [], "evidence_refs": [],
        "unresolved_material_impacts": [{"code": code, "target_ref": target}],
        "source_attested": False, "impact_verified": False,
        "a5_allowed": False, "no_write_performed": True,
    }


def _gap(code: str, *, target: str, source: str) -> dict:
    return {"code": code, "target_ref": target, "source_id": source,
            "resolution": "TARGETED_RETURN_TO_A3_OR_EXACT_PROVIDER",
            "impact_state": "UNKNOWN"}


def _change_action(change_type: Any, policy: dict) -> str:
    """Map declared A2 operation through a closed, externally inspectable set."""
    aliases = policy.get("change_operation", {}).get("intent_aliases", {})
    if not isinstance(change_type, str):
        return "UNKNOWN"
    matches = [action for action, values in aliases.items()
               if isinstance(values, list) and change_type in values]
    return matches[0] if len(matches) == 1 else "UNKNOWN"


def _planned_build(a3: dict, a2: dict, target: str, target_action: str) -> dict:
    """Project the *to-be-built* obligations; no target code/destination exists.

    A2's build intention is not independent proof that no implementation
    exists. A3 approved scope is still source-only, never runtime permission.
    """
    rule_items = a3.get("policy_scope_clear_rule_candidates")
    material = a3.get("material_contract_readback")
    if not isinstance(rule_items, list):
        return {
            **_blocked("A4_APPROVED_RULE_SCOPE_READBACK_REQUIRED", target=target),
            "requested_change_type": a2.get("change_type"),
            "target_change_action": target_action,
            "change_action_basis": "A2_DECLARED_TARGET_INTENT_UNVERIFIED",
            "analysis_mode": "PLANNED_BUILD",
            "target_code_destination": None,
            "implementation_scope_progress_possible": False,
        }
    direct, excluded = [], []
    for rule in rule_items:
        if (not isinstance(rule, dict)
                or not isinstance(rule.get("rule_code"), str)
                or not isinstance(rule.get("source_ref"), str)
                or rule.get("rule_status") != "VIGENTE"
                or rule.get("pending_decision") is not False):
            return _blocked("A4_BUILD_RULE_SOURCE_STATUS_INVALID", target=target)
        if rule.get("policy_dependency_disposition") not in (
            None, "NO_KNOWN_POLICY_DEPENDENCY_BLOCKER"
        ):
            return _blocked("A4_BUILD_RULE_POLICY_SCOPE_INVALID", target=target)
        direct.append({
            "affected_ref": rule["source_ref"],
            "requirement_code": rule["rule_code"],
            "evidence_origin": "S1_A3",
            "impact_class": "PLANNED_NEW_IMPLEMENTATION_OBLIGATION",
            "change_action": "CREATE",
            "definition_action": "REUSE",
            "change_action_basis": "A2_NEW_TARGET_INTENT_PLUS_A3_APPROVED_DEFINITION",
            "existing_code_delta": False,
            "source_status": "VIGENTE",
            "source_attested": False,
        })
    if material is not None:
        if (not isinstance(material, dict)
                or material.get("status") != "MATERIAL_CONTRACT_PROJECTED_UNATTESTED"
                or not isinstance(material.get("status_items"), list)):
            return _blocked("A4_MATERIAL_PROJECTION_INVALID", target=target)
        for item in material["status_items"]:
            if (not isinstance(item, dict)
                    or not isinstance(item.get("source_ref"), str)
                    or not isinstance(item.get("source_status"), str)):
                return _blocked("A4_MATERIAL_ITEM_SOURCE_INVALID", target=target)
            projection = {
                "affected_ref": item["source_ref"],
                "evidence_origin": "S1_A3",
                "impact_class": "PLANNED_MATERIAL_DEFINITION",
                "change_action": "CREATE" if item["source_status"] == "VIGENTE" else "UNKNOWN",
                "definition_action": "REUSE" if item["source_status"] == "VIGENTE" else "UNKNOWN",
                "change_action_basis": "A2_NEW_TARGET_INTENT_PLUS_A3_APPROVED_DEFINITION"
                    if item["source_status"] == "VIGENTE" else "EXCLUDED_SOURCE_NOT_APPROVED",
                "source_status": item["source_status"],
                "existing_code_delta": False,
                "source_attested": False,
            }
            if item["source_status"] == "VIGENTE":
                direct.append(projection)
            else:
                excluded.append(projection)
    gaps = []
    if material is None:
        gaps.append(_gap("A4_SCREEN_MATERIAL_NOT_READ", target=target, source="S1_A3"))
    if not direct:
        gaps.append(_gap("A4_APPROVED_SCOPE_HAS_NO_MATERIAL_OBLIGATIONS",
                         target=target, source="S1_A3"))
    # The source readback has not established runtime currentness, or scoped
    # external dependencies. Preserve uncertainty but do not invent code paths.
    gaps.append(_gap("A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED",
                     target=target, source="S3_INV_OBJECT"))
    return {
        "schema_version": SCHEMA,
        "core_output_contract": CORE,
        "status": "PLANNED_BUILD_IMPACT_UNATTESTED",
        "business": "LF", "target_ref": target,
        "requested_change_type": a2.get("change_type"),
        "target_change_action": target_action,
        "change_action_basis": "A2_DECLARED_TARGET_INTENT_UNVERIFIED",
        "analysis_mode": "PLANNED_BUILD",
        "target_code_state": "NOT_ESTABLISHED_BY_SOURCE",
        "target_code_destination": None,
        "technical_root_ref": None,
        "direct_impacts": direct, "indirect_impacts": [],
        "consumers": [], "dependency_paths": [],
        "excluded_pending_obligations": excluded,
        "evidence_refs": deepcopy(a3["source_refs"]),
        "unresolved_material_impacts": gaps,
        "counts": {"direct": len(direct), "indirect": 0, "consumers": 0,
                   "dependency_paths": 0,
                   "excluded_pending": len(excluded)},
        "implementation_scope_progress_possible": bool(direct),
        "no_code_path_required_to_analyze": True,
        "no_impact_claimed": False,
        "source_set_ref": "steps/a4/contracts/deterministic_source_set_v1.json",
        "source_attested": False, "impact_verified": False,
        "a5_allowed": False, "no_write_performed": True,
    }


def run(a3: Any, a2: Any, readback: Any = None, *, business: str = "LF") -> dict:
    """Read supplied exact-source evidence, never search repositories or tables.

    The result is an UNATTESTED candidate even if every readback row looks
    consistent; source auth/currentness, judge and operation gates live in
    the existing governed host.
    """
    if business != "LF":
        return _blocked("A4_BUSINESS_NOT_ENABLED_FOR_LF_SKILL")
    policy = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (policy.get("schema_version") != "A4_DETERMINISTIC_SOURCE_SET_V1"
            or [x.get("id") for x in policy.get("sources", [])] != [
                "S1_A3", "S2_A2", "S3_INV_OBJECT",
                "S4_IMPACT_CORE", "S5_DEPENDENCIES"
            ]):
        return _blocked("A4_SOURCE_SET_CONTRACT_DRIFT")
    if (not isinstance(a3, dict) or not isinstance(a2, dict)
            or a3.get("schema_version") != "TARGETED_EVIDENCE_SET_V1"
            or a2.get("schema_version") != "ANALYSIS_CHANGE_CLASSIFICATION_V1"):
        return _blocked("A4_EXACT_A3_A2_INPUTS_REQUIRED")
    target = a3.get("target_ref")
    classified = a2.get("target_ref")
    if (a3.get("business") != "LF" or not isinstance(target, str)
            or not target or not isinstance(classified, str)
            or classified not in (target, a3.get("declared_target_hint"))):
        return _blocked("A4_TARGET_OR_BUSINESS_BINDING_INVALID", target=target)
    if a3.get("status") != "SOURCE_READBACK_PROCESSED_UNATTESTED":
        return _blocked("A4_A3_NOT_ADMISSIBLE_EVIDENCE_CANDIDATE", target=target)
    if not isinstance(a3.get("source_refs"), list) or not a3["source_refs"]:
        return _blocked("A4_A3_EVIDENCE_REFS_REQUIRED", target=target)
    target_action = _change_action(a2.get("change_type"), policy)
    if target_action == "UNKNOWN":
        return {
            **_blocked("A4_CHANGE_OPERATION_NOT_CLASSIFIABLE", target=target),
            "status": "NEED_MORE_EVIDENCE",
            "requested_change_type": a2.get("change_type"),
            "target_change_action": "UNKNOWN",
            "change_action_basis": "UNRECOGNIZED_A2_OPERATION",
        }
    build_intent = a2.get("change_type") in BUILD_INTENTS
    if readback is None:
        if build_intent:
            return _planned_build(a3, a2, target, target_action)
        return {
            **_blocked("A4_EXACT_HOST_SOURCE_READBACK_REQUIRED", target=target),
            "status": "NEED_MORE_EVIDENCE",
            "requested_change_type": a2.get("change_type"),
            "target_change_action": target_action,
            "change_action_basis": "A2_DECLARED_TARGET_INTENT_UNVERIFIED",
        }
    if (not isinstance(readback, dict)
            or readback.get("schema_version") != SIDECAR
            or readback.get("business") != "LF"
            or readback.get("target_ref") != target
            or readback.get("source_attested") is not False):
        return _blocked("A4_HOST_SOURCE_IDENTITY_INVALID", target=target)
    # A build remains a new-target operation even if related reusable
    # existing assets are inventoried. Their identity is not the new target.
    # A separate typed asset binding is needed to assess their graph impact.
    if build_intent:
        return _planned_build(a3, a2, target, target_action)
    inv = readback.get("inventory_object")
    binding = readback.get("identity_binding")
    if inv is None and binding is None:
        return {
            **_blocked("A4_TARGET_NOT_MAPPED_TO_INVENTORY_OBJECT", target=target),
            "status": "IMPACT_UNKNOWN",
            "requested_change_type": a2.get("change_type"),
            "target_change_action": target_action,
            "change_action_basis": "A2_DECLARED_TARGET_INTENT_UNVERIFIED",
            "unresolved_material_impacts": [
                _gap("A4_TARGET_NOT_MAPPED_TO_INVENTORY_OBJECT",
                     target=target, source="S3_INV_OBJECT")
            ],
        }
    if not isinstance(inv, dict) or not isinstance(binding, dict):
        return _blocked("A4_INVENTORY_IDENTITY_READBACK_INCOMPLETE", target=target)
    root = inv.get("object_ref")
    if (not isinstance(root, str) or not root or inv.get("active") is not True
            or not isinstance(inv.get("object_type"), str)
            or not inv["object_type"]):
        return _blocked("A4_INVENTORY_OBJECT_NOT_EXACT_ACTIVE", target=target)
    if (binding.get("target_ref") != target
            or binding.get("inventory_object_ref") != root
            or binding.get("source_ref") not in a3["source_refs"]
            or binding.get("source_attested") is not False):
        return _blocked("A4_INVENTORY_TARGET_BINDING_MISSING_OR_DRIFTED", target=target)
    impact = readback.get("impact_readback")
    deps = readback.get("dependency_readback")
    if not isinstance(impact, dict) or not isinstance(deps, dict):
        return {
            **_blocked("A4_DEPENDENCY_SOURCE_READBACK_MISSING", target=target),
            "status": "IMPACT_UNKNOWN",
            "requested_change_type": a2.get("change_type"),
            "target_change_action": target_action,
            "change_action_basis": "A2_DECLARED_TARGET_INTENT_UNVERIFIED",
        }
    expected = [
        (impact, "inventory.fn_impact_analysis_v1",
         {"p_object_ref": root, "p_max_depth": 3, "p_min_confidence": 0.8}),
        (deps, "inventory.fn_dependencies_v1",
         {"p_object_ref": root, "p_direction": "BOTH", "p_max_depth": 2}),
    ]
    for item, fn, params in expected:
        if (item.get("source_function") != fn
                or item.get("parameters") != params
                or item.get("source_attested") is not False
                or not isinstance(item.get("rows"), list)):
            return _blocked("A4_GRAPH_PROVIDER_OR_PARAMETERS_DRIFT", target=target)
    direct, indirect, consumers, paths = [], [], [], []
    for item in impact["rows"]:
        if (not isinstance(item, dict)
                or type(item.get("depth")) is not int
                or not 1 <= item["depth"] <= 3
                or not isinstance(item.get("affected_ref"), str)
                or not item["affected_ref"]
                or not isinstance(item.get("affected_type"), str)
                or not isinstance(item.get("via_relation"), str)
                or type(item.get("min_confidence")) not in (float, int)
                or not 0.8 <= item["min_confidence"] <= 1.0):
            return _blocked("A4_IMPACT_CORE_ROW_INVALID", target=target)
        projected = {
            "affected_ref": item["affected_ref"],
            "affected_type": item["affected_type"],
            "via_relation": item["via_relation"],
            "depth": item["depth"],
            "confidence": item["min_confidence"],
            "evidence_origin": "S4_IMPACT_CORE",
            "impact_class": "POTENTIAL_GRAPH_RELATION_NOT_BEHAVIOR_PROOF",
            "change_action": "UNKNOWN",
            "definition_action": "UNKNOWN",
            "change_action_basis": "GRAPH_RELATION_ONLY_NO_ITEM_DELTA",
        }
        (direct if item["depth"] == 1 else indirect).append(projected)
    for item in deps["rows"]:
        if (not isinstance(item, dict)
                or type(item.get("depth")) is not int
                or not 1 <= item["depth"] <= 2
                or item.get("direction") not in ("IN", "OUT")
                or not isinstance(item.get("source_ref"), str)
                or not isinstance(item.get("target_ref"), str)
                or not isinstance(item.get("relation_type"), str)
                or type(item.get("confidence")) not in (float, int)
                or not 0 <= item["confidence"] <= 1.0):
            return _blocked("A4_DEPENDENCY_ROW_INVALID", target=target)
        projected = {
            "depth": item["depth"], "direction": item["direction"],
            "source_ref": item["source_ref"],
            "target_ref": item["target_ref"],
            "relation_type": item["relation_type"],
            "confidence": item["confidence"],
            "evidence_type": item.get("evidence_type"),
            "evidence_origin": "S5_DEPENDENCIES",
            "change_action": "UNKNOWN",
            "change_action_basis": "DEPENDENCY_EDGE_NOT_A_REQUESTED_CHANGE",
        }
        paths.append(projected)
        if item["direction"] == "IN":
            consumers.append(deepcopy(projected))
    unresolved = []
    if inv.get("currentness") != "CURRENT":
        unresolved.append(_gap("A4_INVENTORY_OBJECT_CURRENTNESS_NOT_VERIFIED",
                               target=target, source="S3_INV_OBJECT"))
    if not isinstance(a3.get("as_is_baseline_or_new_implementation_evidence"), dict):
        unresolved.append(_gap("A4_AS_IS_IMPLEMENTATION_EVIDENCE_MISSING",
                               target=target, source="S1_A3"))
    if not impact["rows"] and not deps["rows"]:
        unresolved.append(_gap("A4_EMPTY_GRAPH_DOES_NOT_ESTABLISH_NO_IMPACT",
                               target=target, source="S4_IMPACT_CORE"))
    for code in a3.get("unresolved_material_gaps", []):
        if isinstance(code, str) and code:
            unresolved.append(_gap(code, target=target, source="S1_A3"))
    refs = list(dict.fromkeys(
        [r for r in a3["source_refs"] if isinstance(r, str)]
        + [root]
    ))
    return {
        "schema_version": SCHEMA,
        "core_output_contract": CORE,
        "status": "PROJECTED_UNATTESTED" if not unresolved else "IMPACT_UNKNOWN",
        "business": "LF", "target_ref": target,
        "requested_change_type": a2.get("change_type"),
        "target_change_action": target_action,
        "change_action_basis": "A2_DECLARED_TARGET_INTENT_UNVERIFIED",
        "technical_root_ref": root,
        "direct_impacts": direct, "indirect_impacts": indirect,
        "consumers": consumers, "dependency_paths": paths,
        "evidence_refs": refs,
        "unresolved_material_impacts": unresolved,
        "counts": {"direct": len(direct), "indirect": len(indirect),
                   "consumers": len(consumers), "dependency_paths": len(paths)},
        "source_set_ref": "steps/a4/contracts/deterministic_source_set_v1.json",
        "source_attested": False, "impact_verified": False,
        "a5_allowed": False, "no_write_performed": True,
    }
