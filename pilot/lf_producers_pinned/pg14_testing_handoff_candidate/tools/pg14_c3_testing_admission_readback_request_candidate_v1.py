"""PG14_C3 candidate Testing admission/readback request, deliberately no action.

Actual ACCEPT or BLOCK belongs exclusively to the real Testing admission owner.
"""
import hashlib,json
from copy import deepcopy
class Blocked(ValueError):pass
def d(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def ref(x):return isinstance(x,str) and bool(x.strip()) and x==x.strip()
def prepare_pg14_c3(*,pg14_c2,testing_admission_endpoint_ref,readback_contract_ref,request_key_ref):
 if not isinstance(pg14_c2,dict) or pg14_c2.get("schema_version")!="PG14_C2_TESTING_SPEC_PAYLOAD_CANDIDATE_V1":raise Blocked("C3_SOURCE_SCHEMA")
 source=d({k:v for k,v in pg14_c2.items() if k!="candidate_sha256"})
 if source!=pg14_c2.get("candidate_sha256"):raise Blocked("C3_SOURCE_DIGEST")
 if pg14_c2.get("status")!="CANDIDATE_NOT_ADMITTED" or any(pg14_c2.get(k) is not False for k in ("pg14_c2_pass","handoff_allowed","production_authority","testing_invoked")):raise Blocked("C3_AUTHORITY")
 if not all(ref(x) for x in (testing_admission_endpoint_ref,readback_contract_ref,request_key_ref)):raise Blocked("C3_REQUEST_REFS")
 candidate=pg14_c2.get("frozen_candidate_sha256_reported")
 if not isinstance(candidate,str) or len(candidate)!=64 or any(c not in "0123456789abcdef" for c in candidate):raise Blocked("C3_FROZEN_CANDIDATE_ID")
 request={"source_pg14_c2_sha256":source,"frozen_candidate_sha256_reported":candidate,"request_key_ref_reported":request_key_ref,"mode":"EXECUTION","expected_decisions":["ACCEPT","BLOCK"]}
 result={"schema_version":"PG14_C3_TESTING_ADMISSION_READBACK_REQUEST_CANDIDATE_V1","status":"CANDIDATE_NOT_ADMITTED","source_pg14_c2_sha256":source,"testing_endpoint_ref_reported":testing_admission_endpoint_ref,"readback_contract_ref_reported":readback_contract_ref,"admission_request":request,"admission_request_sha256":d(request),"testing_request_sent":False,"testing_decision":None,"testing_receipt_ref":None,"testing_readback_executed":False,"testing_readback_verified":False,"frozen_candidate_consumed_verified":False,"pg14_c3_pass":False,"handoff_allowed":False,"production_authority":False,"next_gate":"REAL_TESTING_ACCEPT_OR_BLOCK_AND_INDEPENDENT_READBACK"}
 result["candidate_sha256"]=d(result)
 return deepcopy(result)
