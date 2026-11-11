"""PG14_C2 candidate testing obligations package, no test execution or admission."""
import hashlib,json
from copy import deepcopy
class Blocked(ValueError):pass
def d(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def ref(x):return isinstance(x,str) and bool(x.strip()) and x==x.strip()
def prepare_pg14_c2(*,pg14_c1,catalog_version_ref,spec_test_obligations,blind_test_contract_ref,pending_copy_texts):
 if not isinstance(pg14_c1,dict) or pg14_c1.get("schema_version")!="PG14_C1_TESTING_EXECUTION_HANDOFF_CANDIDATE_V1":raise Blocked("C2_UPSTREAM_SCHEMA")
 if pg14_c1.get("candidate_sha256")!=d({k:v for k,v in pg14_c1.items() if k!="candidate_sha256"}):raise Blocked("C2_UPSTREAM_DIGEST")
 if pg14_c1.get("status")!="CANDIDATE_NOT_ADMITTED" or any(pg14_c1.get(k) is not False for k in ("pg14_c1_pass","handoff_allowed","production_authority","testing_admission_invoked")):raise Blocked("C2_PREMATURE_AUTHORITY")
 if pg14_c1.get("mode")!="EXECUTION" or not ref(catalog_version_ref) or blind_test_contract_ref!="fn_submit_blind_test_contract":raise Blocked("C2_REQUIRED_CONTRACT")
 if not isinstance(spec_test_obligations,list) or not spec_test_obligations:raise Blocked("C2_TEST_OBLIGATIONS_MISSING")
 seen=set();obligations=[]
 for row in spec_test_obligations:
  keys={"obligation_ref","spec_ref","test_case_ref","expected_oracle_ref"}
  if not isinstance(row,dict) or set(row)!=keys or not all(ref(row[k]) for k in keys) or row["obligation_ref"] in seen:raise Blocked("C2_OBLIGATION_SHAPE")
  seen.add(row["obligation_ref"]);obligations.append(deepcopy(row))
 if "B2B-RULE-TEST-001" not in seen:raise Blocked("C2_B2B_RULE_TEST_001_REQUIRED")
 if not isinstance(pending_copy_texts,list):raise Blocked("C2_COPY_LIST_INVALID")
 copyrefs=set();texts=[]
 for row in pending_copy_texts:
  if not isinstance(row,dict) or set(row)!={"text_ref","source_ref","status"} or not ref(row["text_ref"]) or not ref(row["source_ref"]) or row["status"]!="PENDING_COPY" or row["text_ref"] in copyrefs:raise Blocked("C2_PENDING_COPY_ENTRY_INVALID")
  copyrefs.add(row["text_ref"]);texts.append(deepcopy(row))
 result={"schema_version":"PG14_C2_TESTING_SPEC_PAYLOAD_CANDIDATE_V1","status":"CANDIDATE_NOT_ADMITTED","source_pg14_c1_sha256":pg14_c1["candidate_sha256"],"frozen_candidate_sha256_reported":pg14_c1["frozen_candidate_sha256_reported"],"catalog_version_ref_reported":catalog_version_ref,"test_obligations_reported":sorted(obligations,key=lambda x:x["obligation_ref"]),"blind_test_contract_ref_reported":blind_test_contract_ref,"pending_copy_texts_reported":sorted(texts,key=lambda x:x["text_ref"]),"catalog_version_authenticated":False,"spec_obligation_coverage_verified":False,"blind_test_contract_authenticated":False,"pending_copy_list_complete_verified":False,"testing_invoked":False,"pg14_c2_pass":False,"handoff_allowed":False,"production_authority":False,"next_gate":"VALIDATE_CANONICAL_SPEC_AND_BLIND_TEST_CONTRACT"}
 result["candidate_sha256"]=d(result)
 return deepcopy(result)
