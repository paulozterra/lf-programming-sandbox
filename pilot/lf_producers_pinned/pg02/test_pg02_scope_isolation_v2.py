pg01_binding={"source":"PG01_C4","architecture_repo":"fixture://repo","architecture_commit":"f"*40,"manifest_digest_sha256":"a"*64,"architecture_profile":{"active_layers":["FRONTEND"]},"context_binding":{"context_id":"fixture-context","context_sha256":"b"*64,"receipt_ref":"fixture://pg01-receipt"}}
import copy
from pg02_scope_isolation_v2 import classify_scopes
from pg02_classifier_v1 import PG02Blocked
def front(fid,sid,status="REQUIRED",closure="CLOSED",kind="UI_VISUAL"):
 return {"front_id":fid,"front_kind":kind,"status":status,"closure":closure,"scope_refs":[sid]}
def row(fid,sid,status="REQUIRED",closure="CLOSED",effect="PRESERVE"):
 return {"front_id":fid,"scope_id":sid,"front_status":status,"front_closure":closure,"effect_on_scope":effect}
s={"schema_version":"PROGRAMMING_CONTEXT_SNAPSHOT_V1","target_granularity":{"level":"SCREEN","target_ref":"B2B-AUTH-001"},
"scope_readiness":[{"scope_id":"S1","status":"READY","material_front_refs":["F1"]},{"scope_id":"S2","status":"BLOCKED","material_front_refs":["F2"]}],
"material_front_coverage":{"all_material_fronts_accounted":True,"unmapped_material_signals":[],
"material_fronts":[front("F1","S1"),front("F2","S2",closure="BLOCKED")]},
"scope_front_matrix":[row("F1","S1"),row("F2","S2",closure="BLOCKED",effect="BLOCKS")]}
m={"state":"SOURCE_ONLY_CANDIDATE","front_kind_domains":{"UI_VISUAL":["STD-FE"],"API_CONTRACT":["STD-API"]},"domain_stack_layers":{"STD-FE":["FRONTEND"],"STD-API":["BACKEND"]}}
o=classify_scopes(s,m,pg01_binding=pg01_binding)
assert [r["state"] for r in o["scopes"]]==["READY_FOR_CLASSIFICATION","BLOCKED"]
assert o==classify_scopes(copy.deepcopy(s),copy.deepcopy(m),pg01_binding=pg01_binding)
n=copy.deepcopy(s)
n["material_front_coverage"]["material_fronts"][0]=front("F1","S1",status="NOT_APPLICABLE")
n["scope_front_matrix"][0]=row("F1","S1",status="NOT_APPLICABLE",effect="NOT_APPLICABLE")
assert classify_scopes(n,m,pg01_binding=pg01_binding)["scopes"][0]["candidate_domains"]==[]
def reject(obj,code):
 try: classify_scopes(obj,m,pg01_binding=pg01_binding)
 except PG02Blocked as e: assert str(e)==code,(str(e),code)
 else: raise AssertionError(code)
for fn,code in [
 (lambda x:x["material_front_coverage"].update(all_material_fronts_accounted=False),"CONTRADICTION:A7_UNACCOUNTED_MATERIAL_SIGNAL"),
 (lambda x:x["material_front_coverage"].update(unmapped_material_signals=["unknown"]),"CONTRADICTION:A7_UNACCOUNTED_MATERIAL_SIGNAL"),
 (lambda x:x["scope_readiness"][0].update(material_front_refs=[]),"CONTRADICTION:BIDIRECTIONAL_MAPPING"),
 (lambda x:x["material_front_coverage"]["material_fronts"][0].update(status="OPTIONAL"),"CONTRADICTION:A7_ENUM"),
 (lambda x:x["scope_front_matrix"][0].update(front_status="OPTIONAL"),"CONTRADICTION:A7_PARITY"),
]:
 b=copy.deepcopy(s);fn(b);reject(b,code)
print("PG02_A7_REMEDIATION_PASS: partial_ready=PASS not_applicable=PASS no_spurious_domains=PASS negatives=5 determinism=PASS")
