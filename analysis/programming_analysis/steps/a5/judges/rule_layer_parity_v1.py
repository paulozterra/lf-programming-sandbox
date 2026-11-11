"""Independent mechanical consistency judge for A5 unique rule Front/Back profiles.

Checks original A3 rule identities, scope exclusions, A4 traceability,
source-bound layer proposals and no fabricated layer certainty. Does NOT
independently attest source currentness or semantic correctness.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GROUPS=("policy_scope_clear_rule_candidates","policy_deferred_rule_items","excluded_rule_items")
LAYER=("FRONTEND","BACKEND")


def digest(data: Any)->str:
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def judge(inputs: Any, out: Any, readback: Any = None)->dict:
    failures=[]
    if not isinstance(inputs,dict) or not isinstance(out,dict):
        return {"verdict":"FAIL","violations":["INPUT_INVALID"],
                "independent_semantic_review":False}
    a3=inputs.get("TARGETED_EVIDENCE_SET_V1")
    a4=inputs.get("SHARED_CHANGE_IMPACT_ANALYSIS")
    result=out.get("rule_profiles")
    if not isinstance(a3,dict) or not isinstance(a4,dict) or not isinstance(result,dict):
        return {"verdict":"FAIL","violations":["RULE_PROFILES_OR_INPUT_MISSING"],
                "independent_semantic_review":False}
    rules=result.get("rules")
    if not isinstance(rules,list):
        return {"verdict":"FAIL","violations":["RULE_ARRAY_MISSING"],
                "independent_semantic_review":False}
    by_code={}
    for rule in rules:
        if (not isinstance(rule,dict) or not isinstance(rule.get("rule_code"),str)
                or rule["rule_code"] in by_code):
            failures.append("RULE_CODE_DUPLICATE_OR_INVALID")
            continue
        by_code[rule["rule_code"]]=rule
    source_rows={}
    missing=[]
    for group in GROUPS:
        records=a3.get(group,[])
        if not isinstance(records,list):
            failures.append("A3_RULE_GROUP_INVALID:"+group)
            continue
        for i,row in enumerate(records):
            if not isinstance(row,dict):
                failures.append("A3_RULE_ROW_INVALID")
                continue
            code,ref=row.get("rule_code"),row.get("source_ref")
            if not isinstance(code,str) or not isinstance(ref,str) or not ref:
                if group=="policy_scope_clear_rule_candidates":
                    failures.append("APPROVED_RULE_IDENTITY_MISSING")
                else:
                    missing.append(f"A3:{group}:{i}")
                continue
            if code in source_rows:
                failures.append("DUPLICATE_CANONICAL_RULE:"+code)
            source_rows[code]=(ref,group,row,f"A3:{group}:{i}")
    if set(source_rows)!=set(by_code):
        failures.append("RULE_CARDINALITY_OR_IDENTITY_LOSS")
    unresolved=result.get("unresolved_rule_identities",[])
    if not isinstance(unresolved,list) or [x.get("source_item_id") for x in unresolved if isinstance(x,dict)]!=missing:
        failures.append("MISSING_RULE_IDENTITY_HIDDEN")
    output_items=out.get("decision_items",[])
    if not isinstance(output_items,list):
        failures.append("DECISION_ITEMS_MISSING")
        output_items=[]
    all_ids={x.get("decision_item_id") for x in output_items if isinstance(x,dict)}
    bindings=readback.get("rule_layer_bindings",[]) if isinstance(readback,dict) else []
    if not isinstance(bindings,list):
        failures.append("LAYER_BINDINGS_INVALID")
        bindings=[]
    by_binding={}
    for b in bindings:
        if isinstance(b,dict):
            key=(b.get("rule_code"),b.get("layer"))
            if key in by_binding:
                failures.append("DUPLICATE_LAYER_BINDING")
            by_binding[key]=b
    for code,rule in by_code.items():
        if code not in source_rows:continue
        ref,group,source,item_id=source_rows[code]
        if (rule.get("rule_source_ref")!=ref
                or rule.get("rule_source_row")!=source
                or item_id not in rule.get("material_item_ids",[])):
            failures.append("RULE_SOURCE_ROW_LOSS:"+code)
        if rule.get("scope_approved_source_candidate") is not (group==GROUPS[0]):
            failures.append("RULE_SCOPE_PROMOTION:"+code)
        if (not isinstance(rule.get("material_item_ids"),list)
                or any(x not in all_ids for x in rule.get("material_item_ids",[]))):
            failures.append("RULE_REFERENCES_UNBOUND_MATERIAL:"+code)
        layer_map=rule.get("layers")
        if not isinstance(layer_map,dict) or set(layer_map)!=set(LAYER):
            failures.append("LAYER_MAP_INVALID:"+code)
            continue
        statuses=[]
        for name in LAYER:
            observed=layer_map[name]
            b=by_binding.get((code,name))
            if not isinstance(observed,dict):
                failures.append("LAYER_ROW_INVALID:"+code+":"+name)
                continue
            app=observed.get("applicability")
            statuses.append(app)
            expected=b.get("applicability") if isinstance(b,dict) else "UNKNOWN"
            if app!=expected or observed.get("source_attested") is not False:
                failures.append("UNBOUND_OR_FALSE_LAYER_APPLICABILITY:"+code+":"+name)
            if isinstance(b,dict):
                if observed.get("responsibility")!=b.get("responsibility"):
                    failures.append("LAYER_RESPONSIBILITY_MUTATED:"+code+":"+name)
                if observed.get("evidence_refs")!=[ref]:
                    failures.append("LAYER_EVIDENCE_REF_DRIFT:"+code+":"+name)
            else:
                if observed.get("responsibility") is not None or observed.get("evidence_refs")!=[]:
                    failures.append("INVENTED_LAYER_BEHAVIOR:"+code+":"+name)
        if len(statuses)==2:
            f,b=statuses
            if "UNKNOWN" in statuses: expected="UNKNOWN"
            elif f=="APPLIES" and b=="APPLIES":expected="SHARED_CANDIDATE"
            elif f=="APPLIES":expected="FRONTEND_ONLY_CANDIDATE"
            elif b=="APPLIES":expected="BACKEND_ONLY_CANDIDATE"
            else:expected="NO_APPLICABLE_LAYER_CANDIDATE"
            if rule.get("layer_classification")!=expected:
                failures.append("FALSE_FRONT_BACK_CLASSIFICATION:"+code)
            gaps=[name for name,layer in layer_map.items()
                  if layer.get("applicability")=="UNKNOWN"]
            if rule.get("unresolved_layer_evidence")!=gaps:
                failures.append("HIDDEN_LAYER_UNCERTAINTY:"+code)
        if rule.get("code_destination") is not None:
            failures.append("INVENTED_TARGET_CODE_DESTINATION:"+code)
        raw=rule.copy();fp=raw.pop("rule_fingerprint_sha256",None)
        if fp!=digest(raw):
            failures.append("RULE_FINGERPRINT_DRIFT:"+code)
    for x in bindings:
        if not isinstance(x,dict) or x.get("rule_code") not in by_code:
            failures.append("UNBOUND_RULE_LAYER_SOURCE")
    raw=result.copy();fp=raw.pop("fingerprint_sha256",None)
    if fp!=digest(raw):
        failures.append("RULE_PROFILES_FINGERPRINT_DRIFT")
    if (out.get("source_attested") is not False
            or out.get("a6_allowed") is not False
            or result.get("applicability_source_attested") is not False
            or result.get("independent_semantic_review") is not False):
        failures.append("FALSE_RUNTIME_OR_SEMANTIC_ATTESTATION")
    return {
        "verdict":"FAIL" if failures else "PASS",
        "violations":failures,
        "rules_checked":len(by_code),
        "source_rule_rows_checked":len(source_rows),
        "independent_semantic_review":False,
        "source_attested":False,
        "judge_type":"DETERMINISTIC_RULE_LAYER_PARITY_ONLY",
    }
