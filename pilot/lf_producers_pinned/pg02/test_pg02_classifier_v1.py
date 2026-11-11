pg01_binding={"source":"PG01_C4","architecture_repo":"fixture://repo","architecture_commit":"f"*40,"manifest_digest_sha256":"a"*64,"architecture_profile":{"active_layers":["FRONTEND"]},"context_binding":{"context_id":"fixture-context","context_sha256":"b"*64,"receipt_ref":"fixture://pg01-receipt"}}
import copy
from pg02_classifier_v1 import classify, PG02Blocked, digest
s={"schema_version":"PROGRAMMING_CONTEXT_SNAPSHOT_V1",
   "target_granularity":{"level":"SCREEN","target_ref":"B2B-AUTH-001"},
   "scope_readiness":[{"scope_id":"B2B_COPY","status":"READY","material_front_refs":["F1"]}],
   "material_front_coverage":{"all_material_fronts_accounted":True,"unmapped_material_signals":[],
      "material_fronts":[{"front_id":"F1","front_kind":"UI_VISUAL","status":"REQUIRED",
                          "closure":"CLOSED","scope_refs":["B2B_COPY"]}]},
   "scope_front_matrix":[{"scope_id":"B2B_COPY","front_id":"F1","front_status":"REQUIRED",
                          "front_closure":"CLOSED","effect_on_scope":"PRESERVE"}]}
m={"state":"SOURCE_ONLY_CANDIDATE","source_ref":"fixture://PG02-C1",
   "version":"fixture-v1","front_kind_domains":{"UI_VISUAL":["STD-FE","NAV","MSG"]},"domain_stack_layers":{"STD-FE":["FRONTEND"],"NAV":["FRONTEND"],"MSG":["FRONTEND"]}}
before=copy.deepcopy(s)
result=classify(s,m,pg01_binding=pg01_binding)
assert result==classify(copy.deepcopy(s),copy.deepcopy(m),pg01_binding=pg01_binding)
assert s==before
assert result["status"]=="CANDIDATE_NOT_ADMITTED"
assert result["scopes"][0]["candidate_domains"]==["MSG","NAV","STD-FE"]
assert classify(s,m,pg01_binding=pg01_binding,expected_catalog_ref=m["source_ref"],expected_catalog_sha256=digest(m))==result

def reject(mut,expected):
    a,b=copy.deepcopy(s),copy.deepcopy(m)
    mut(a,b)
    try: classify(a,b,pg01_binding=pg01_binding)
    except PG02Blocked as exc: assert str(exc)==expected,(str(exc),expected)
    else: raise AssertionError(expected)
cases=[
 (lambda a,b:a.pop("target_granularity"),"CONTRADICTION:A2_MISSING"),
 (lambda a,b:a["scope_front_matrix"][0].update(front_status="OPTIONAL"),"CONTRADICTION:A7_PARITY"),
 (lambda a,b:a.update(scope_front_matrix=[]),"CONTRADICTION:MATRIX_MISMATCH"),
 (lambda a,b:a["material_front_coverage"]["material_fronts"][0].update(status="OPTIONAL"),"CONTRADICTION:A7_ENUM"),
 (lambda a,b:a["material_front_coverage"].update(all_material_fronts_accounted=False),"CONTRADICTION:A7_UNACCOUNTED_MATERIAL_SIGNAL"),
 (lambda a,b:a["scope_readiness"][0].update(material_front_refs=[]),"CONTRADICTION:BIDIRECTIONAL_MAPPING"),
 (lambda a,b:b.update(state="CURRENT_RELEASED"),"CATALOG_NOT_AUTHORIZED"),
]
for fn,code in cases: reject(fn,code)
for kwargs,code in [
 ({"expected_catalog_ref":"fixture://other"},"CATALOG_SOURCE_DRIFT"),
 ({"expected_catalog_sha256":"0"*64},"CATALOG_DIGEST_DRIFT"),
]:
 try:classify(s,m,pg01_binding=pg01_binding,**kwargs)
 except PG02Blocked as e:assert str(e)==code
 else:raise AssertionError(code)
print("PG02_PRIMARY_CONSOLIDATED_PASS positives=1 negatives=9 deterministic=PASS")
