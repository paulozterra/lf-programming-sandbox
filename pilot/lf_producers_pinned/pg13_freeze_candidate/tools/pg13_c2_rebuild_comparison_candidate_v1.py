"""PG13_C2: declared rebuild digest comparison, no rebuild performed."""
import hashlib,json,re
from copy import deepcopy
SHA=re.compile(r"^[0-9a-f]{64}$")
class Blocked(ValueError):pass
def d(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def ref(x):return isinstance(x,str) and bool(x.strip()) and x==x.strip()
def prepare_pg13_c2(*,pg13_c1,rebuild_observations,build_recipe_ref,environment_lock_ref):
 if not isinstance(pg13_c1,dict) or pg13_c1.get("schema_version")!="PG13_C1_FREEZE_INTENT_CANDIDATE_V1":raise Blocked("C2_SCHEMA")
 if d({k:v for k,v in pg13_c1.items() if k!="candidate_sha256"})!=pg13_c1.get("candidate_sha256"):raise Blocked("C2_DIGEST")
 if pg13_c1.get("status")!="CANDIDATE_NOT_ADMITTED" or any(pg13_c1.get(k) is not False for k in ("pg13_c1_pass","freeze_enforced","handoff_allowed","production_authority")):raise Blocked("C2_AUTHORITY")
 if not ref(build_recipe_ref) or not ref(environment_lock_ref) or not isinstance(rebuild_observations,list) or not rebuild_observations:raise Blocked("C2_REQUIRED_INPUTS")
 names=set();rows=[]
 for x in rebuild_observations:
  if not isinstance(x,dict) or set(x)!={"artifact_ref","baseline_digest_sha256","rebuild_digest_sha256","difference_ref"}:raise Blocked("C2_SHAPE")
  name=x["artifact_ref"]
  if not ref(name) or name in names:raise Blocked("C2_DUPLICATE")
  names.add(name)
  if not all(isinstance(x[k],str) and SHA.fullmatch(x[k]) for k in ("baseline_digest_sha256","rebuild_digest_sha256")):raise Blocked("C2_DIGEST_FORMAT")
  equal=x["baseline_digest_sha256"]==x["rebuild_digest_sha256"]
  if not equal and not ref(x["difference_ref"]):raise Blocked("C2_DIFFERENCE_UNDOCUMENTED")
  if equal and x["difference_ref"] is not None:raise Blocked("C2_SPURIOUS_DIFFERENCE")
  rows.append({**deepcopy(x),"digest_equal_reported":equal,"rebuild_execution_verified":False})
 result={"schema_version":"PG13_C2_REBUILD_COMPARISON_CANDIDATE_V1","status":"CANDIDATE_NOT_ADMITTED","source_pg13_c1_sha256":pg13_c1["candidate_sha256"],"source_pg12_c1_sha256":pg13_c1["source_pg12_c1_sha256"],"frozen_commit_sha_reported":pg13_c1["candidate_commit_sha_reported"],"build_recipe_ref_reported":build_recipe_ref,"environment_lock_ref_reported":environment_lock_ref,"observations":sorted(rows,key=lambda x:x["artifact_ref"]),"rebuild_performed_by_component":False,"rebuild_reproducibility_verified":False,"pg13_c2_pass":False,"handoff_allowed":False,"production_authority":False,"next_gate":"REBUILD_EXACT_SHA_WITH_CAPTURED_TOOLCHAIN"}
 result["candidate_sha256"]=d(result)
 return deepcopy(result)
