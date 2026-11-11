"""Independent mechanical A5 parity judge for *source-only* candidate output.

Does NOT replace GPT-native semantic evaluation or the governed independent
review. Validate literal A3/A4 row preservation, scope, no invented owner
decisions and no false readiness. No source access or network.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

A3_LISTS = (
    "policy_scope_clear_rule_candidates", "policy_deferred_rule_items",
    "excluded_rule_items", "policy_link_items", "evidence_items")
A4_LISTS = (
    "direct_impacts", "indirect_impacts", "consumers", "dependency_paths",
    "excluded_pending_obligations", "unresolved_material_impacts")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def judge(inputs: Any, out: Any, readback: Any = None) -> dict:
    failures = []
    if not isinstance(inputs, dict) or not isinstance(out, dict):
        return {"verdict":"FAIL","violations":["A5_JUDGE_INPUT_INVALID"],
                "independent_semantic_review":False}
    a3, a4 = inputs.get("TARGETED_EVIDENCE_SET_V1"), inputs.get("SHARED_CHANGE_IMPACT_ANALYSIS")
    ledger, result_items = out.get("material_ledger"), out.get("decision_items")
    if not isinstance(a3, dict) or not isinstance(a4, dict):
        failures.append("CANONICAL_SOURCES_MISSING")
    if not isinstance(ledger, dict) or not isinstance(result_items, list):
        failures.append("MATERIAL_LEDGER_OR_ITEM_OUTPUT_MISSING")
    if failures:
        return {"verdict":"FAIL","violations":failures,"independent_semantic_review":False}
    if ledger.get("source_digest_sha256") != _sha({"a3":a3,"a4":a4}):
        failures.append("SOURCE_DIGEST_NOT_PARITY")
    if ledger.get("upstream_contract_snapshot") != {"A3":a3,"A4":a4}:
        failures.append("UPSTREAM_CONTRACT_SNAPSHOT_LOSS")
    actual = ledger.get("items")
    if not isinstance(actual, list) or len(result_items) != len(actual):
        failures.append("MATERIAL_ITEM_COUNT_NOT_PARITY")
        actual = []
    by_id = {x.get("decision_item_id"):x for x in result_items if isinstance(x, dict)}
    if len(by_id) != len(result_items) or any(not isinstance(x, dict) for x in result_items):
        failures.append("DUPLICATE_OR_INVALID_ITEM_ID")
    expected_counts = {}
    for stage, source, cols in (("A3",a3,A3_LISTS),("A4",a4,A4_LISTS)):
        for col in cols:
            if col in source:
                rows = source[col]
                if not isinstance(rows, list):
                    failures.append("SOURCE_COLLECTION_NOT_LIST:"+stage+"."+col)
                    continue
                expected_counts[stage+"."+col] = len(rows)
                for i, datum in enumerate(rows):
                    item_id = f"{stage}:{col}:{i}"
                    projected = by_id.get(item_id)
                    if not isinstance(projected, dict):
                        failures.append("MISSING_MATERIAL_ITEM:"+item_id)
                        continue
                    if projected.get("source_payload") != datum or projected.get("source_payload_sha256") != _sha(datum):
                        failures.append("LOSSY_MATERIAL_PAYLOAD:"+item_id)
    mat=a3.get("material_contract_readback")
    if mat is not None:
        if not isinstance(mat, dict) or not isinstance(mat.get("status_items"), list):
            failures.append("MATERIAL_CONTRACT_SHAPE_INVALID")
        else:
            vals=mat["status_items"]
            expected_counts["A3.material_contract_readback.status_items"]=len(vals)
            for i,datum in enumerate(vals):
                item_id=f"A3:material_contract_readback.status_items:{i}"
                projected=by_id.get(item_id)
                if not isinstance(projected,dict):
                    failures.append("MISSING_MATERIAL_ITEM:"+item_id)
                elif projected.get("source_payload")!=datum or projected.get("source_payload_sha256")!=_sha(datum):
                    failures.append("LOSSY_MATERIAL_PAYLOAD:"+item_id)
    if ledger.get("source_collection_counts")!=expected_counts:
        failures.append("SOURCE_COLLECTION_COUNTS_DRIFT")
    if ledger.get("source_detail",{}).get("a3_policy_resolution")!=a3.get("policy_resolution"):
        failures.append("POLICY_RESOLUTION_LOST")
    if ledger.get("source_detail",{}).get("a3_material_contract")!=mat:
        failures.append("MATERIAL_CONTRACT_DETAILS_LOST")
    missing=[]
    for c in A3_LISTS:
        if c not in a3:missing.append("A3."+c)
    for c in A4_LISTS:
        if c not in a4:missing.append("A4."+c)
    if mat is None:missing.append("A3.material_contract_readback.status_items")
    if ledger.get("missing_collections")!=missing:
        failures.append("MISSING_COLLECTIONS_HIDDEN")
    coverage=out.get("material_coverage")
    expected_sum=sum(expected_counts.values())
    if (not isinstance(coverage,dict) or
            coverage.get("input_item_count")!=expected_sum or
            coverage.get("output_item_count")!=len(result_items) or
            coverage.get("omitted_material_item_count")!=expected_sum-len(result_items)):
        failures.append("COVERAGE_FALSE_ACCOUNTING")
    for projected in result_items:
        if not isinstance(projected,dict):continue
        if projected.get("decision_classification") in (
                "EXCLUDED_FROM_APPROVED_SCOPE","TARGETED_EVIDENCE_REQUIRED"):
            if projected.get("owner_decision_required") is not False:
                failures.append("FALSE_OWNER_DECISION:"+str(projected.get("decision_item_id")))
        if projected.get("source_attested") is not False:
            failures.append("FALSE_ATTESTATION")
    listed=out.get("pending_owner_decisions",[])
    candidates=readback.get("material_decisions",[]) if isinstance(readback,dict) else []
    if not isinstance(listed,list) or not isinstance(candidates,list) or len(listed)!=len(candidates):
        failures.append("OWNER_DECISION_CARDINALITY_MISMATCH")
    else:
        for expected,found in zip(candidates,listed):
            if (not isinstance(expected,dict) or not isinstance(found,dict)
                    or found.get("source_item_id")!=expected.get("source_item_id")
                    or found.get("question")!=expected.get("material_question")
                    or found.get("selected_option_ref") is not None):
                failures.append("OWNER_DECISION_UNGROUNDED")
    if (out.get("a6_allowed") is not False or
            out.get("source_attested") is not False or
            out.get("independent_judge_verified") is not False):
        failures.append("FALSE_RUNTIME_ADMISSION")
    dc=out.get("decision_context")
    decisions=out.get("decisions")
    if isinstance(dc,dict) and isinstance(decisions,list) and decisions:
        if dc!=decisions[0]:
            failures.append("SUMMARY_DECISION_DUPLICATE_DRIFT")
        d=dict(dc); f=d.pop("decision_fingerprint_sha256",None)
        if f!=_sha(d):
            failures.append("DECISION_FINGERPRINT_DRIFT")
    else:failures.append("DECISION_CONTEXT_MISSING")
    return {
        "verdict":"FAIL" if failures else "PASS",
        "violations":failures,
        "input_item_count":expected_sum,
        "output_item_count":len(result_items),
        "independent_semantic_review":False,
        "source_attested":False,
        "judge_type":"DETERMINISTIC_MATERIAL_PARITY_ONLY",
    }
