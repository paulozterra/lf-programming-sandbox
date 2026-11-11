"""A2 Golden dimensional projection (SOURCE-ONLY candidate, not an execution gate).

Keeps the existing ANALYSIS_CHANGE_CLASSIFICATION_V1 unchanged. Reads an exact
catalog SHA; unknown conditional triggers must remain UNRESOLVED_TRIGGER. No
external provenance, authority, native judge receipt, or A3 permission is inferred.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import importlib.util
from pathlib import Path
from typing import Any

CATALOG_SHA256 = "67c235e0b855086176a5f6b0f348095bdb96f711187c5772fd48987d2d1ef6ba"
CANONICAL_A2_BLOB = "0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051"
SCHEMA = "A2_GOLDEN_DIMENSIONAL_CANDIDATE_V1"
CANONICAL_RESULT_SCHEMA = "ANALYSIS_CHANGE_CLASSIFICATION_V1"
COND_IDS = (
    "D01-E04", "D02-E02", "D02-E04", "D02-E05", "D03-E03", "D03-E05",
    "D04-E03", "D04-E04", "D04-E05", "D05-E03", "D05-E04", "D06-E04",
    "D06-E05", "D07-E03", "D07-E04", "D08-E02", "D08-E03", "D09-E02",
    "D09-E03", "D09-E04", "D09-E05", "D10-E05", "D11-E02", "D11-E03",
    "D11-E04", "D12-E03",
)
SIGNALS = (
    "materiality_level", "scope_bounded", "authority_state", "reversibility_state",
    "currentness_decision", "material_contradiction", "known_cross_scope_impact",
    "unresolved_material_signal_count", "required_specialist_count",
)
CONDITIONAL_SET = set(COND_IDS)


def _digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def _blocked(code: str) -> dict:
    return {
        "schema_version": SCHEMA, "status": "BLOCKED", "blocking_codes": [code],
        "catalog_source_attested": False, "a1_source_attested": False,
        "independent_judge_verified": False, "execution_run_verified": False,
        "dimensions": [], "elements": [], "a3_requests": [],
        "a3_allowed": False, "next_step": None, "no_write_performed": True,
    }


def load_catalog(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError("GOLDEN_CATALOG_SHA256_DRIFT")
    c = json.loads(raw)
    if c.get("schema_version") != "A2_GOLDEN_DYNAMIC_DIMENSION_CATALOG_PROPOSAL_V0_2" or c.get("canonical_a2_contract_blob") != CANONICAL_A2_BLOB:
        raise ValueError("GOLDEN_CATALOG_CANONICAL_CONTRACT_DRIFT")
    dims, elems = c.get("dimensions"), c.get("elements")
    if not isinstance(dims, list) or not isinstance(elems, list) or len(dims)!=12 or len(elems)!=59:
        raise ValueError("GOLDEN_CATALOG_CARDINALITY_DRIFT")
    d_ids = [d["dimension_id"] for d in dims]
    ids = [e["id"] for e in elems]
    if len(set(d_ids))!=12 or len(set(ids))!=59:
        raise ValueError("GOLDEN_CATALOG_DUPLICATE_ID")
    by_dim = Counter(e["dimension"] for e in elems)
    if any(by_dim[d["dimension_id"]] != len(d["element_ids"]) or
           set(d["element_ids"]) != {e["id"] for e in elems if e["dimension"] == d["dimension_id"]}
           for d in dims):
        raise ValueError("GOLDEN_CATALOG_DIMENSION_MAPPING_DRIFT")
    found = {e["id"] for e in elems if e["applicability_category"] == "CONDITIONAL"}
    if found != CONDITIONAL_SET or sum(e["applicability_category"] == "ALWAYS" for e in elems)!=33:
        raise ValueError("GOLDEN_CATALOG_TRIGGER_BINDING_DRIFT")
    return c


def _declared_true_facts(context: dict) -> set[str]:
    """Only exact, cited A1 fact codes, never NLP inference or authoritative proof."""
    refs = set(context.get("source_refs", []))
    return {fact["fact_code"] for fact in context.get("provided_facts", [])
            if isinstance(fact, dict) and fact.get("source_ref") in refs
            and fact.get("value") in ("TRUE", "true")
            and isinstance(fact.get("fact_code"), str)}


def _activation_true(eid: str, signals: dict, context: dict, bundle: dict) -> tuple[bool, list[str]]:
    """Positive-only typed trigger decisions. False is UNRESOLVED without a trusted negative receipt."""
    s = signals
    facts = _declared_true_facts(context)
    targets = context.get("target_hints", [])
    unknown = (s["materiality_level"] == "UNKNOWN" or s["authority_state"] == "UNKNOWN"
               or s["scope_bounded"] == "UNKNOWN" or s["reversibility_state"] == "UNKNOWN"
               or s["currentness_decision"] in ("UNKNOWN_FAIL_CLOSED", "UNRESOLVED")
               or s["known_cross_scope_impact"] == "UNKNOWN")
    cross = s["known_cross_scope_impact"] is not False
    material = s["materiality_level"]
    authority = s["authority_state"]
    current = s["currentness_decision"]
    specialty = s["required_specialist_count"]
    conds = {
        "D01-E04": (bool(context.get("ambiguities")) or "MATERIAL_AMBIGUITY" in facts, ["a1.ambiguities", "A1:MATERIAL_AMBIGUITY"]),
        "D02-E02": (bundle["target_granularity"] in ("SECTION", "CONTROL") or bundle["nested_parent_ref"] is not None, ["a2.target_granularity", "a2.nested_parent_ref"]),
        "D02-E04": (len(targets)>1 or "MULTIPLE_TARGETS" in facts, ["a1.target_hints", "A1:MULTIPLE_TARGETS"]),
        "D02-E05": (cross, ["depth_signals.known_cross_scope_impact"]),
        "D03-E03": (material in ("MEDIUM", "HIGH", "UNKNOWN") or "KNOWN_IMPACT" in facts, ["depth_signals.materiality_level"]),
        "D03-E05": (material=="UNKNOWN" or s["material_contradiction"], ["depth_signals.materiality_level", "depth_signals.material_contradiction"]),
        "D04-E03": (material in ("MEDIUM", "HIGH") or cross or s["material_contradiction"] or "KNOWN_RISK" in facts, ["depth_signals.materiality_level", "depth_signals.known_cross_scope_impact"]),
        "D04-E04": (material=="HIGH" or cross or s["material_contradiction"], ["depth_signals.materiality_level", "depth_signals.material_contradiction"]),
        "D04-E05": ("RISK_REGISTER_EMPTY" in facts, ["A1:RISK_REGISTER_EMPTY"]),
        "D05-E03": (authority in ("UNKNOWN", "INSUFFICIENT") or "DECISION_REQUIRED" in facts, ["depth_signals.authority_state", "A1:DECISION_REQUIRED"]),
        "D05-E04": ("AUTHORITY_CONFLICT" in facts, ["A1:AUTHORITY_CONFLICT"]),
        "D06-E04": (current!="CURRENT" or "SOURCE_REVISION" in facts, ["depth_signals.currentness_decision", "A1:SOURCE_REVISION"]),
        "D06-E05": ("SOURCE_CONFLICT" in facts, ["A1:SOURCE_CONFLICT"]),
        "D07-E03": ("SOURCE_REVISION" in facts, ["A1:SOURCE_REVISION"]),
        "D07-E04": (current!="CURRENT" or "SOURCE_CONFLICT" in facts, ["depth_signals.currentness_decision"]),
        "D08-E02": (s["reversibility_state"]=="DEMONSTRATED", ["depth_signals.reversibility_state"]),
        "D08-E03": (s["reversibility_state"] in ("NOT_DEMONSTRATED", "UNKNOWN") or "PERSISTENT_EFFECT" in facts, ["depth_signals.reversibility_state"]),
        "D09-E02": (len(targets)>1 or cross or "KNOWN_DEPENDENCY" in facts, ["a1.target_hints", "depth_signals.known_cross_scope_impact"]),
        "D09-E03": (specialty>0, ["depth_signals.required_specialist_count"]),
        "D09-E04": (specialty>0, ["depth_signals.required_specialist_count"]),
        "D09-E05": (specialty>0, ["depth_signals.required_specialist_count"]),
        "D10-E05": (unknown or s["unresolved_material_signal_count"]>0 or (material=="HIGH" and authority=="UNKNOWN"), ["depth_signals.materiality_level", "depth_signals.authority_state"]),
        "D11-E02": (unknown or current!="CURRENT" or authority=="INSUFFICIENT" or s["material_contradiction"] or s["unresolved_material_signal_count"]>0, ["depth_signals.currentness_decision", "depth_signals.unresolved_material_signal_count"]),
        "D11-E03": (True, ["A2:source_attested=false", "A3:currentness_acquisition_required"]),
        "D11-E04": ("ABSENCE_CLAIM" in facts, ["A1:ABSENCE_CLAIM"]),
        "D12-E03": (True, ["A2:source_attested=false", "A3:target_and_authority_readback_required"]),
    }
    if eid not in conds:
        raise ValueError("GOLDEN_CONDITIONAL_RULE_NOT_BOUND")
    return conds[eid]


def _known_values(context: dict, bundle: dict, a2: dict) -> dict:
    s = bundle["depth_signals"]
    c = a2["classification"]
    return {
        "D01-E01": deepcopy(context.get("objective")),
        "D01-E02": {"target_ref": c["target_ref"], "identity_status": "DECLARED_NOT_CURRENT_VERIFIED"},
        "D01-E03": c["change_type"],
        "D02-E01": c["target_granularity"],
        "D03-E01": s["materiality_level"],
        "D04-E01": s["material_contradiction"],
        "D04-E02": s["known_cross_scope_impact"],
        "D05-E01": s["authority_state"],
        "D05-E05": "NO_EXECUTION_AUTHORITY",
        "D07-E01": s["currentness_decision"],
        "D08-E01": s["reversibility_state"],
        "D08-E04": False,
        "D09-E01": s["required_specialist_count"],
        "D10-E03": c["depth_level"],
        "D12-E01": a2["status"],
        "D12-E05": None,  # external judge, never producer-supplied
    }


def build_golden(a1_result: Any, a2_result: Any, signal_bundle: Any, *, catalog_path: str | Path) -> dict:
    """Build typed source-only candidate with all 59 IDs; never authorize A3."""
    try:
        catalog = load_catalog(catalog_path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return _blocked("GOLDEN_CATALOG_SOURCE_UNAVAILABLE_OR_DRIFTED")
    if not all(isinstance(x, dict) for x in (a1_result, a2_result, signal_bundle)):
        return _blocked("GOLDEN_INPUT_ENVELOPES_MISSING")
    a1_mode = a1_result.get("interpretation_state")
    if (a1_result.get("status") != "VALID_OUTPUT"
            or a1_mode not in ("PRESTRUCTURED_UNATTESTED", "SEMANTIC_REVIEWED_CANDIDATE")
            or a1_result.get("semantic_review_required") is not False):
        return _blocked("GOLDEN_A1_SEMANTIC_GATE_NOT_RESOLVED")
    if a1_mode == "SEMANTIC_REVIEWED_CANDIDATE":
        # The semantic path remains untrusted: validate integrity, not judge authority.
        guard_path = Path(__file__).with_name("a2_semantic_input_integrity_v1.py")
        spec = importlib.util.spec_from_file_location("a2_semantic_binding_guard", guard_path)
        if spec is None or spec.loader is None:
            return _blocked("GOLDEN_A1_SEMANTIC_GUARD_UNAVAILABLE")
        guard = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(guard)
            check = guard.check(a1_result, a2_result, signal_bundle)
        except (OSError, ValueError, TypeError, AttributeError):
            return _blocked("GOLDEN_A1_SEMANTIC_GUARD_UNAVAILABLE")
        if check.get("status") != "CHECKED_SOURCE_ONLY":
            return _blocked("GOLDEN_A1_SEMANTIC_BINDING_INVALID")
    context = a1_result.get("payload")
    classification = a2_result.get("classification")
    s = signal_bundle.get("depth_signals")
    if not isinstance(context, dict) or not isinstance(classification, dict) or not isinstance(s, dict) or set(s) != set(SIGNALS):
        return _blocked("GOLDEN_CANONICAL_FIELDS_MISSING")
    if a2_result.get("status") not in ("CANDIDATE_UNATTESTED", "NEED_MORE_EVIDENCE") or classification.get("schema_version") != CANONICAL_RESULT_SCHEMA:
        return _blocked("GOLDEN_CANONICAL_A2_NOT_QUALIFIED")
    biz = a1_result.get("business")
    if not isinstance(biz,str) or not biz or biz!=signal_bundle.get("business") or biz!=a2_result.get("business"):
        return _blocked("GOLDEN_BUSINESS_CONFLICT")
    # Reject synthetic same-business SALY envelopes in the LF Golden projection.
    if biz != "LF":
        return _blocked("GOLDEN_BUSINESS_NOT_ENABLED_FOR_SKILL")
    if classification.get("target_ref") != signal_bundle.get("target_ref") or classification.get("target_ref") not in context.get("target_hints", []):
        return _blocked("GOLDEN_TARGET_CONFLICT")
    if classification.get("signals_sha256") != _digest(signal_bundle):
        return _blocked("GOLDEN_INPUT_DIGEST_MISMATCH")
    if not isinstance(signal_bundle.get("evidence_refs"), list) or not signal_bundle["evidence_refs"] or any(not isinstance(x,str) or not x for x in signal_bundle["evidence_refs"]):
        return _blocked("GOLDEN_EVIDENCE_REFS_MISSING")
    if a2_result.get("source_attested") is not False or a2_result.get("independent_judge_verified") is not False or a2_result.get("next_step") is not None:
        return _blocked("GOLDEN_FORGED_OPERATIONAL_AUTHORITY")
    values = _known_values(context, signal_bundle, a2_result)
    elements=[]
    for e in catalog["elements"]:
        conditional = e["applicability_category"]=="CONDITIONAL"
        evidence_refs=deepcopy(signal_bundle["evidence_refs"])
        if conditional:
            truth, triggers = _activation_true(e["id"],s,context,signal_bundle)
            applicability = "CONDITIONAL_REQUIRED" if truth else "UNRESOLVED_TRIGGER"
            trigger_state = "TRUE_TYPED_SOURCE_UNATTESTED" if truth else "UNKNOWN_NEGATIVE_PROOF_NOT_AVAILABLE"
        else:
            applicability = "REQUIRED"
            trigger_state = "ALWAYS"
            triggers = ["catalog.activation=SIEMPRE"]
        item={
            "element_id":e["id"],"dimension_id":e["dimension"],"title":e["title"],
            "applicability":applicability,"fulfilment":"PENDING_EVIDENCE",
            "trigger_state":trigger_state,"trigger_inputs":triggers,
            "evidence_refs":evidence_refs,"evidence_tier":"DECLARED_UNATTESTED",
            "value":deepcopy(values.get(e["id"])),
            "a3_handoff":e["a3_handoff"],"reason":"SOURCE_ATTESTATION_OR_INDEPENDENT_JUDGE_PENDING",
        }
        elements.append(item)
    byid={x["element_id"]:x for x in elements}
    dimensions=[{"dimension_id":d["dimension_id"],"name":d["name"],"elements":[deepcopy(byid[eid]) for eid in d["element_ids"]]} for d in catalog["dimensions"]]
    requests=[{"element_id":i["element_id"],"question":i["a3_handoff"],
               "source_refs":deepcopy(i["evidence_refs"]),"stop_condition":"CURRENT_SERVER_READBACK_OR_TYPED_BLOCKER",
               "priority":"HIGH" if i["applicability"]=="CONDITIONAL_REQUIRED" else "NORMAL"}
              for i in elements if i["applicability"]!="REQUIRED"]
    # Fixed requirements still need evidence; the producer never claims SATISFIED.
    lineage=[{"signal_key":key,"declared_value":deepcopy(s[key]),
              "source_refs":deepcopy(signal_bundle["evidence_refs"]),
              "producer_verified":False,"currentness_verified":False} for key in SIGNALS]
    counts=dict(Counter(x["applicability"] for x in elements))
    return {
        "schema_version":SCHEMA,"status":"CANDIDATE_UNATTESTED", "business":biz,
        "catalog_sha256":CATALOG_SHA256,"canonical_a2_contract_blob":CANONICAL_A2_BLOB,
        "classification":deepcopy(classification),"signal_lineage":lineage,
        "dimensions":dimensions,"elements":elements,"a3_requests":requests,
        "coverage":{"dimensions":len(dimensions),"elements":len(elements),
                    "always_required":counts.get("REQUIRED",0),
                    "conditional_required":counts.get("CONDITIONAL_REQUIRED",0),
                    "conditional_unresolved":counts.get("UNRESOLVED_TRIGGER",0),
                    "not_applicable":0,"satisfied":0,"conditionals_total":len(COND_IDS)},
        "blocking_codes":["GOLDEN_NATIVE_SOURCE_AND_JUDGE_PENDING"],
        "catalog_source_attested":False,"a1_source_attested":False,
        "independent_judge_verified":False,"execution_run_verified":False,
        "a3_allowed":False,"next_step":None,"no_write_performed":True,
    }
