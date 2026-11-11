"""PG13_C3: negative mutation scenario inventory, not an enforcement gate."""
import hashlib,json
from copy import deepcopy
class Blocked(ValueError):pass
def digest(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def ref(x):return isinstance(x,str) and bool(x.strip()) and x==x.strip()
SCENARIOS={"REWRITE_FROZEN_BRANCH","FORCE_PUSH","MODIFY_WORKTREE","REPLACE_ARTIFACT","CHANGED_TREE_SAME_LABEL"}
def prepare_pg13_c3(*,pg13_c2,mutation_scenarios,policy_ref):
 if not isinstance(pg13_c2,dict) or pg13_c2.get("schema_version")!="PG13_C2_REBUILD_COMPARISON_CANDIDATE_V1":raise Blocked("C3_SCHEMA")
 if digest({k:v for k,v in pg13_c2.items() if k!="candidate_sha256"})!=pg13_c2.get("candidate_sha256"):raise Blocked("C3_DIGEST")
 if pg13_c2.get("status")!="CANDIDATE_NOT_ADMITTED" or any(pg13_c2.get(k) is not False for k in ("pg13_c2_pass","handoff_allowed","production_authority","rebuild_reproducibility_verified")):raise Blocked("C3_AUTHORITY")
 if not ref(policy_ref) or not isinstance(mutation_scenarios,list) or len(mutation_scenarios)!=len(SCENARIOS):raise Blocked("C3_COVERAGE")
 seen=set();rows=[]
 for s in mutation_scenarios:
  if not isinstance(s,dict) or set(s)!={"scenario_code","attempt_ref","expected_verdict","evidence_ref"}:raise Blocked("C3_SHAPE")
  code=s["scenario_code"]
  if code not in SCENARIOS or code in seen or s["expected_verdict"]!="BLOCK" or not ref(s["attempt_ref"]) or not ref(s["evidence_ref"]):raise Blocked("C3_EXPECTED_BLOCK_INVALID")
  seen.add(code)
  rows.append({**deepcopy(s),"mutating_operation_attempted":False,"actual_block_verified":False})
 if seen!=SCENARIOS:raise Blocked("C3_SCENARIO_GAP")
 result={"schema_version":"PG13_C3_MUTATION_BLOCK_CANDIDATE_V1","status":"CANDIDATE_NOT_ADMITTED","source_pg13_c2_sha256":pg13_c2["candidate_sha256"],"source_pg12_c1_sha256":pg13_c2["source_pg12_c1_sha256"],"candidate_commit_sha_reported":pg13_c2["frozen_commit_sha_reported"],"policy_ref_reported":policy_ref,"negative_scenarios":sorted(rows,key=lambda x:x["scenario_code"]),"executed_negative_tests":0,"mutation_blocks_verified":False,"freeze_verified":False,"pg13_c3_pass":False,"handoff_allowed":False,"production_authority":False,"next_gate":"EXECUTE_ADVERSARIAL_MUTATION_BLOCK_TESTS_ON_FROZEN_REF"}
 result["candidate_sha256"]=digest(result)
 return deepcopy(result)
