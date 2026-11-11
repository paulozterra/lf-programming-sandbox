"""PG13_C1: intent to freeze one exact programming candidate, without a lock."""
import hashlib,json,re
from copy import deepcopy
SHA=re.compile(r"^[0-9a-f]{64}$")
OID=re.compile(r"^[0-9a-f]{40,64}$")
class Blocked(ValueError):pass
def hashobj(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def valid(x):return isinstance(x,str) and bool(x.strip()) and x==x.strip()
def prepare_pg13_c1(*,pg12_c4,candidate_commit_sha,candidate_tree_sha,freeze_policy_ref,freeze_request_ref):
 if not isinstance(pg12_c4,dict) or pg12_c4.get("schema_version")!="PG12_C4_PERSISTENCE_READBACK_REQUEST_CANDIDATE_V2":raise Blocked("C1_UPSTREAM_SCHEMA")
 if hashobj({k:v for k,v in pg12_c4.items() if k!="candidate_sha256"})!=pg12_c4.get("candidate_sha256"):raise Blocked("C1_UPSTREAM_DIGEST")
 if pg12_c4.get("status")!="CANDIDATE_NOT_ADMITTED" or any(pg12_c4.get(k) is not False for k in ("pg12_c4_pass","pg12_c4_admitted","handoff_allowed","production_authority","persisted","readback_matched")):raise Blocked("C1_UPSTREAM_AUTHORITY")
 if not (isinstance(candidate_commit_sha,str) and OID.fullmatch(candidate_commit_sha) and isinstance(candidate_tree_sha,str) and OID.fullmatch(candidate_tree_sha)):raise Blocked("C1_INVALID_GIT_OBJECTS")
 if not valid(freeze_policy_ref) or not valid(freeze_request_ref):raise Blocked("C1_FREEZE_REFS")
 result={"schema_version":"PG13_C1_FREEZE_INTENT_CANDIDATE_V2","status":"CANDIDATE_NOT_ADMITTED","source_pg12_c4_sha256":pg12_c4["candidate_sha256"],"source_pg12_c1_sha256":pg12_c4["source_pg12_c1_sha256"],"candidate_commit_sha_reported":candidate_commit_sha,"candidate_tree_sha_reported":candidate_tree_sha,"freeze_policy_ref_reported":freeze_policy_ref,"freeze_request_ref_reported":freeze_request_ref,"git_objects_verified":False,"immutable_ref_created":False,"freeze_enforced":False,"pg13_c1_pass":False,"handoff_allowed":False,"production_authority":False,"next_gate":"EXACT_GIT_OBJECT_AND_FREEZE_LOCK_VERIFICATION"}
 result["candidate_sha256"]=hashobj(result)
 return deepcopy(result)
