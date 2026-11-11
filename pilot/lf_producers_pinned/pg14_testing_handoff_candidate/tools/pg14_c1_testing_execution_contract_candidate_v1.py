"""PG14_C1 candidate EXECUTION handoff under existing TESTING_ADMISSION_CONTRACT_V1.

This produces no request to Testing. The source contract is SOURCE_ONLY_CANDIDATE.
"""
import hashlib,json,re
from copy import deepcopy
SHA=re.compile(r"^[a-f0-9]{64}$")
class Blocked(ValueError):pass
def dig(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def ref(x):return isinstance(x,str) and bool(x.strip()) and x==x.strip()
REQUIRES={"analysis_package_ref","analysis_package_sha256","source_currentness_ref","frozen_candidate_ref","frozen_candidate_sha256"}
def prepare_pg14_c1(*,pg13_c3,admission_contract,analysis_package_ref,analysis_package_sha256,source_currentness_ref,frozen_candidate_ref,frozen_candidate_sha256):
 if not isinstance(pg13_c3,dict) or pg13_c3.get("schema_version")!="PG13_C3_MUTATION_BLOCK_CANDIDATE_V1":raise Blocked("C1_UPSTREAM_SCHEMA")
 if pg13_c3.get("candidate_sha256")!=dig({k:v for k,v in pg13_c3.items() if k!="candidate_sha256"}):raise Blocked("C1_UPSTREAM_DIGEST")
 if pg13_c3.get("status")!="CANDIDATE_NOT_ADMITTED" or any(pg13_c3.get(k) is not False for k in ("pg13_c3_pass","freeze_verified","handoff_allowed","production_authority")):raise Blocked("C1_UPSTREAM_AUTHORITY")
 if not isinstance(admission_contract,dict) or admission_contract.get("schema_version")!="TESTING_ADMISSION_CONTRACT_V1" or admission_contract.get("state")!="SOURCE_ONLY_CANDIDATE" or admission_contract.get("no_parallel_engine") is not True:raise Blocked("C1_TESTING_CONTRACT")
 mode=admission_contract.get("modes",{}).get("EXECUTION")
 if not isinstance(mode,dict) or set(mode.get("requires",[]))!=REQUIRES or mode.get("agent_task_required") is not False or mode.get("story_required") is not False:raise Blocked("C1_MODE_EXECUTION_CONTRACT_DRIFT")
 if not all(ref(x) for x in (analysis_package_ref,source_currentness_ref,frozen_candidate_ref)):raise Blocked("C1_INPUT_REFS")
 if not all(isinstance(x,str) and SHA.fullmatch(x) for x in (analysis_package_sha256,frozen_candidate_sha256)):raise Blocked("C1_HASHES")
 if frozen_candidate_sha256!=pg13_c3.get("source_pg12_c1_sha256"):raise Blocked("C1_FROZEN_IDENTITY_DRIFT")
 result={"schema_version":"PG14_C1_TESTING_EXECUTION_HANDOFF_CANDIDATE_V1","status":"CANDIDATE_NOT_ADMITTED","source_pg13_c3_sha256":pg13_c3["candidate_sha256"],"testing_admission_contract_sha256":dig(admission_contract),"testing_contract_schema":"TESTING_ADMISSION_CONTRACT_V1","mode":"EXECUTION","analysis_package_ref_reported":analysis_package_ref,"analysis_package_sha256_reported":analysis_package_sha256,"source_currentness_ref_reported":source_currentness_ref,"frozen_candidate_ref_reported":frozen_candidate_ref,"frozen_candidate_sha256_reported":frozen_candidate_sha256,"frozen_git_commit_reported":pg13_c3["candidate_commit_sha_reported"],"contract_source_authenticated":False,"frozen_candidate_verified":False,"testing_admission_invoked":False,"pg14_c1_pass":False,"handoff_allowed":False,"production_authority":False,"next_gate":"AUTHENTIC_EXECUTION_CONTRACT_AND_FROZEN_CANDIDATE_READBACK"}
 result["candidate_sha256"]=dig(result)
 return deepcopy(result)
