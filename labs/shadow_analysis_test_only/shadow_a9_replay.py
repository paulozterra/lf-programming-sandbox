#!/usr/bin/env python3
"""LF shadow A9 diagnostic. No source modification, inference of authority, or PG admission."""
import argparse
import copy
import hashlib
import json

def inspect(raw):
    original = copy.deepcopy(raw.get("context_payload",raw))
    snapshot = original.get("extensions",{}).get("programming_context_snapshot")
    if not isinstance(snapshot,dict):
        raise ValueError("A9_SNAPSHOT_MISSING")
    scopes = snapshot.get("scope_readiness",[])
    coverage = snapshot.get("material_front_coverage",{})
    fronts = coverage.get("fronts",[]) if isinstance(coverage,dict) else []
    if not isinstance(scopes,list) or not isinstance(fronts,list):
        raise ValueError("A9_SCOPE_OR_FRONT_INVALID")
    by_id = {f["id"]:f for f in fronts if isinstance(f,dict) and isinstance(f.get("id"),str)}
    original_matrix = snapshot.get("scope_front_matrix",[])
    derived=[]; missing=[]
    for scope in scopes:
        sid=scope["scope_id"]
        for fid in scope.get("material_front_refs",[]):
            if fid not in by_id:
                missing.append({"scope_id":sid,"front_id":fid,"reason":"FRONT_REFERENCE_MISSING"})
                continue
            if any(isinstance(x,dict) and x.get("scope_id")==sid and x.get("front_id")==fid for x in original_matrix):
                continue
            f=by_id[fid]
            derived.append({"scope_id":sid,"front_id":fid,
                "front_status":f.get("status"),"front_closure":f.get("closure"),
                "evidence_from":["scope_readiness.material_front_refs","material_front_coverage.fronts"],
                "provenance":"DERIVED_CANDIDATE_NOT_SOURCE_A9"})
    a6=snapshot.get("implementability_schema")
    typed_a6=isinstance(a6,dict) and isinstance(a6.get("requirements"),list) and isinstance(a6.get("bindings"),list)
    blockers=["CURRENTNESS_NOT_VERIFIED","HANDOFF_RECEIPT_NOT_VERIFIED","INDEPENDENT_JUDGE_NOT_EXECUTED"]
    if not typed_a6: blockers.append("A6_TYPED_IMPLEMENTABILITY_MISSING")
    if not isinstance(snapshot.get("obligations"),list) or not isinstance(snapshot.get("outcome_registry"),list):
        blockers.append("PG04_ATOMS_OR_OUTCOMES_NOT_AVAILABLE")
    if missing: blockers.append("BROKEN_FRONT_REFERENCE")
    return {"schema_version":"LF_SHADOW_ANALYSIS_TEST_ONLY_V1","simulation_only":True,
        "analysis_producer_executed":False,"production_authority":False,
        "pg01_admitted":False,"handoff_allowed":False,"is_original_a9_modified":False,
        "source_snapshot_version":snapshot.get("schema_version"),
        "source_scope_count":len(scopes),"source_matrix_rows":len(original_matrix),
        "suggested_matrix_rows":derived,"unmatched_refs":missing,
        "blockers":blockers,"result_code":"DIAGNOSTIC_ONLY_DERIVED_SCOPE_FRONT_LINKS"}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("snapshot");p.add_argument("--output",default="shadow_result.json")
    args=p.parse_args()
    with open(args.snapshot,encoding="utf-8") as f: data=json.load(f)
    r=inspect(data)
    with open(args.output,"w",encoding="utf-8") as f:json.dump(r,f,indent=2,ensure_ascii=False)
    print(json.dumps({"result_code":r["result_code"],"suggested_matrix_rows":len(r["suggested_matrix_rows"]),"blockers":r["blockers"]}))
