"""One governed-source candidate per unique LF rule with Front/Back applicability.

Uses only A3/A4 *already supplied* contract rows plus optional explicitly
source-bound layer readback. No keyword guesses, code destination, new
applicability resolver, database query, semantic judge or source attestation.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

RULE_GROUPS=(
    ("policy_scope_clear_rule_candidates","APPROVED_SCOPE"),
    ("policy_deferred_rule_items","POLICY_DEFERRED"),
    ("excluded_rule_items","EXCLUDED_PENDING"),
)
LAYER_NAMES=("FRONTEND","BACKEND")
LAYER_STATES=("APPLIES","NOT_APPLICABLE")


def _sha(value: Any)->str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,
        sort_keys=True,allow_nan=False,separators=(",",":")).encode("utf-8")).hexdigest()


def _failure(code: str)->None:
    raise ValueError(code)


def _layer_unknown(name: str)->dict:
    return {
        "layer":name,"applicability":"UNKNOWN",
        "responsibility":None,"evidence_refs":[],
        "source_readback_state":"NOT_SUPPLIED",
        "source_attested":False,"semantic_review_verified":False,
    }


def consolidate(a3: Any, a4: Any, decision_items: Any,
                readback: Any = None)->dict:
    if (not isinstance(a3,dict) or not isinstance(a4,dict)
            or a3.get("target_ref") != a4.get("target_ref")
            or not isinstance(decision_items,list)):
        _failure("A5_RULE_LAYER_CANONICAL_INPUT_INVALID")
    if not isinstance(a3.get("source_refs"),list):
        _failure("A5_RULE_LAYER_SOURCE_REFS_REQUIRED")
    all_items={}
    for item in decision_items:
        if (not isinstance(item,dict)
                or not isinstance(item.get("decision_item_id"),str)
                or item["decision_item_id"] in all_items):
            _failure("A5_RULE_LAYER_DECISION_ITEM_IDENTITY_INVALID")
        all_items[item["decision_item_id"]]=item
    rules, code_by_ref={},{}
    unresolved_rule_identities=[]
    for section, disposition in RULE_GROUPS:
        records=a3.get(section)
        if records is None:
            continue  # Ledger records the missing source collection explicitly.
        if not isinstance(records,list):
            _failure("A5_RULE_LAYER_SOURCE_COLLECTION_INVALID")
        for i,row in enumerate(records):
            if not isinstance(row,dict):
                _failure("A5_RULE_LAYER_ROW_INVALID")
            code, ref=row.get("rule_code"),row.get("source_ref")
            if (not isinstance(code,str) or not code
                    or not isinstance(ref,str) or not ref):
                if disposition=="APPROVED_SCOPE":
                    _failure("A5_RULE_LAYER_RULE_IDENTITY_NOT_BOUND")
                unresolved_rule_identities.append({
                    "source_item_id":f"A3:{section}:{i}",
                    "rule_code":code if isinstance(code,str) else None,
                    "rule_source_ref":ref if isinstance(ref,str) else None,
                    "scope":disposition,
                    "reason":"UNRESOLVED_RULE_IDENTITY_NOT_IMPLEMENTABLE",
                    "source_row":deepcopy(row),
                })
                continue
            if ref not in a3["source_refs"] and section=="policy_scope_clear_rule_candidates":
                _failure("A5_RULE_LAYER_RULE_IDENTITY_NOT_BOUND")
            if code in rules or (ref in code_by_ref and code_by_ref[ref] != code):
                _failure("A5_RULE_LAYER_DUPLICATE_OR_CONFLICTING_RULE")
            code_by_ref[ref]=code
            if disposition=="APPROVED_SCOPE":
                if (row.get("rule_status")!="VIGENTE"
                        or row.get("pending_decision") is not False
                        or row.get("policy_dependency_disposition") not in (
                            None,"NO_KNOWN_POLICY_DEPENDENCY_BLOCKER")):
                    _failure("A5_RULE_LAYER_APPROVED_RULE_STATE_CONFLICT")
            item_id=f"A3:{section}:{i}"
            if item_id not in all_items:
                _failure("A5_RULE_LAYER_RULE_ITEM_PARITY_MISSING")
            rules[code]={
                "rule_code":code,"rule_source_ref":ref,
                "title":row.get("title"),"description":row.get("description"),
                "rule_status":row.get("rule_status"),
                "pending_decision":row.get("pending_decision"),
                "implementation_scope":disposition,
                "scope_approved_source_candidate":disposition=="APPROVED_SCOPE",
                "inheritance":{
                    "evidence_kind":row.get("evidence_kind"),
                    "binding_source":row.get("binding_source"),
                    "association_ref":row.get("association_ref"),
                    "source_attested":False,
                },
                "policy_dependencies":[],
                "policy_objects":[],
                "material_item_ids":[item_id],
                "implementation_impacts":[],
                "layers":{name:_layer_unknown(name) for name in LAYER_NAMES},
                "layer_classification":"UNKNOWN",
                "layer_verification_state":"NOT_ESTABLISHED",
                "unresolved_layer_evidence":[*LAYER_NAMES],
                "rule_source_row":deepcopy(row),
                "source_attested":False,
                "independent_semantic_review":False,
                "code_destination":None,
            }
    # Evidence items may duplicate an *identity*, never create a second rule.
    evidence=a3.get("evidence_items",[])
    if not isinstance(evidence,list):
        _failure("A5_RULE_LAYER_EVIDENCE_ITEMS_INVALID")
    for i,row in enumerate(evidence):
        if not isinstance(row,dict):
            _failure("A5_RULE_LAYER_EVIDENCE_ROW_INVALID")
        code=row.get("rule_code")
        if not isinstance(code,str) or code not in rules:
            # Other evidence items have no proven rule identity and remain in
            # the lossless global ledger, not forced onto an unrelated rule.
            continue
        if row.get("source_ref")!=rules[code]["rule_source_ref"]:
            _failure("A5_RULE_LAYER_EVIDENCE_REF_CONFLICT")
        item_id=f"A3:evidence_items:{i}"
        if item_id not in all_items:
            _failure("A5_RULE_LAYER_RULE_ITEM_PARITY_MISSING")
        rules[code]["material_item_ids"].append(item_id)
    policy=a3.get("policy_resolution")
    if policy is not None:
        if not isinstance(policy,dict):
            _failure("A5_RULE_LAYER_POLICY_RESOLUTION_INVALID")
        dependencies=policy.get("rule_policy_dependencies",[])
        approved_objects=policy.get("approved_policy_objects",[])
        excluded_objects=policy.get("excluded_policy_objects",[])
        if any(not isinstance(x,list) for x in (
            dependencies,approved_objects,excluded_objects)):
            _failure("A5_RULE_LAYER_POLICY_DETAILS_INVALID")
        objects={}
        for obj in approved_objects+excluded_objects:
            if not isinstance(obj,dict):
                _failure("A5_RULE_LAYER_POLICY_OBJECT_INVALID")
            ref=obj.get("source_ref")
            if not isinstance(ref,str) or ref in objects:
                _failure("A5_RULE_LAYER_POLICY_OBJECT_DUPLICATE")
            objects[ref]=obj
        for item in dependencies:
            if not isinstance(item,dict):
                _failure("A5_RULE_LAYER_POLICY_DEPENDENCY_INVALID")
            code=item.get("rule_code")
            if not isinstance(code,str):
                _failure("A5_RULE_LAYER_POLICY_DEPENDENCY_RULE_INVALID")
            if code not in rules:
                continue
            rules[code]["policy_dependencies"].append(deepcopy(item))
            target=item.get("policy_target_ref")
            if isinstance(target,str) and target in objects:
                if all(x.get("source_ref")!=target for x in rules[code]["policy_objects"]):
                    rules[code]["policy_objects"].append(deepcopy(objects[target]))
    impacts=a4.get("direct_impacts",[])
    if not isinstance(impacts,list):
        _failure("A5_RULE_LAYER_IMPACTS_INVALID")
    unlinked=[]
    for i,impact in enumerate(impacts):
        if not isinstance(impact,dict):
            _failure("A5_RULE_LAYER_IMPACT_ROW_INVALID")
        code=impact.get("requirement_code")
        ref=impact.get("affected_ref")
        if isinstance(code,str) and code not in rules:
            unlinked.append(f"A4:direct_impacts:{i}")
            continue
        if not isinstance(code,str):
            code=code_by_ref.get(ref)
        if not isinstance(code,str) or code not in rules:
            continue  # Field/screen impacts stay in the global ledger.
        row=rules[code]
        if ref!=row["rule_source_ref"]:
            _failure("A5_RULE_LAYER_IMPACT_RULE_REF_MISMATCH")
        item_id=f"A4:direct_impacts:{i}"
        if item_id not in all_items:
            _failure("A5_RULE_LAYER_IMPACT_ITEM_PARITY_MISSING")
        row["material_item_ids"].append(item_id)
        row["implementation_impacts"].append({
            "decision_item_id":item_id,
            "action":impact.get("change_action"),
            "definition_action":impact.get("definition_action"),
            "impact_class":impact.get("impact_class"),
            "source_payload":deepcopy(impact),
        })
    # Layer assertions come from a distinct host readback and remain
    # UNATTESTED, even if all supplied refs look plausible. Absence is UNKNOWN.
    source_layers=(readback.get("rule_layer_bindings",[])
                   if isinstance(readback,dict) else [])
    if not isinstance(source_layers,list):
        _failure("A5_RULE_LAYER_BINDINGS_NOT_ARRAY")
    used=set()
    for entry in source_layers:
        if not isinstance(entry,dict):
            _failure("A5_RULE_LAYER_BINDING_ROW_INVALID")
        code,ref=entry.get("rule_code"),entry.get("rule_source_ref")
        layer,applies=entry.get("layer"),entry.get("applicability")
        evidence_ref=entry.get("evidence_ref")
        identity=(code,layer)
        if (not isinstance(code,str) or code not in rules
                or ref!=rules[code]["rule_source_ref"]
                or layer not in LAYER_NAMES or applies not in LAYER_STATES
                or identity in used or not isinstance(evidence_ref,str)
                or evidence_ref not in a3["source_refs"]
                or evidence_ref!=ref
                or entry.get("source_attested") is not False):
            _failure("A5_RULE_LAYER_BINDING_UNTRUSTED_OR_CONFLICTING")
        responsibility=entry.get("responsibility")
        if ((applies=="APPLIES" and (not isinstance(responsibility,str)
              or not responsibility.strip()))
              or (applies=="NOT_APPLICABLE" and responsibility not in (None,""))):
            _failure("A5_RULE_LAYER_BEHAVIOR_EVIDENCE_REQUIRED")
        used.add(identity)
        rules[code]["layers"][layer]={
            "layer":layer,"applicability":applies,
            "responsibility":responsibility or None,
            "evidence_refs":[evidence_ref],
            "source_readback_state":"SOURCE_CANDIDATE_UNATTESTED",
            "source_attested":False,
            "semantic_review_verified":False,
        }
    for rule in rules.values():
        front=rule["layers"]["FRONTEND"]["applicability"]
        back=rule["layers"]["BACKEND"]["applicability"]
        if "UNKNOWN" in (front,back):
            classification="UNKNOWN"
        elif front=="APPLIES" and back=="APPLIES":
            classification="SHARED_CANDIDATE"
        elif front=="APPLIES":
            classification="FRONTEND_ONLY_CANDIDATE"
        elif back=="APPLIES":
            classification="BACKEND_ONLY_CANDIDATE"
        else:
            classification="NO_APPLICABLE_LAYER_CANDIDATE"
        rule["layer_classification"]=classification
        rule["layer_verification_state"]=(
            "CANDIDATE_REQUIRES_SOURCE_ATTESTATION_AND_SEMANTIC_REVIEW"
            if classification!="UNKNOWN" else "EVIDENCE_MISSING"
        )
        rule["unresolved_layer_evidence"]=[
            name for name,layer in rule["layers"].items()
            if layer["applicability"]=="UNKNOWN"
        ]
        rule["material_item_ids"]=list(dict.fromkeys(rule["material_item_ids"]))
        rule["rule_fingerprint_sha256"]=_sha(rule)
    result={
        "schema_version":"A5_RULE_LAYER_CONSOLIDATION_V1",
        "target_ref":a3.get("target_ref"),
        "rules":[rules[key] for key in sorted(rules)],
        "rule_count":len(rules),
        "source_rule_occurrence_count":sum(
            len(a3.get(section,[])) for section,_ in RULE_GROUPS
            if isinstance(a3.get(section,[]),list)),
        "rule_layer_evidence_missing_count":sum(
            bool(x["unresolved_layer_evidence"]) for x in rules.values()),
        "unlinked_explicit_rule_impact_items":unlinked,
        "unresolved_rule_identities":unresolved_rule_identities,
        "applicability_source_attested":False,
        "independent_semantic_review":False,
        "a6_allowed":False,
        "no_write_performed":True,
    }
    result["fingerprint_sha256"]=_sha(result)
    return result
