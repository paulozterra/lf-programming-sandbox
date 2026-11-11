"""Simulated Testing receiver only. NEVER invokes Testing / changes status.

Requires a valid PG14 C3 request, catalog/obligations/copy intact, Analysis
explicitly NOT READY and a source-only PG13-to-PG14 bridge. ACCEPT means
the local fixture has intact shape; not Testing production admission.
"""
import hashlib,json
from pg14_c2_completeness_guard_v1 import validate_pg14_c2_completeness,PG14C2CompletenessBlocked

class PG14LocalReceiverBlocked(ValueError):pass
def block(s):raise PG14LocalReceiverBlocked(s)
def h(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def valid(obj,schema):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema or obj.get("status")!="CANDIDATE_NOT_ADMITTED":
        block("PG14_RECEIVER_SCHEMA")
    if obj.get("candidate_sha256")!=h({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        block("PG14_RECEIVER_HASH_MISMATCH")
    if obj.get("production_authority") is not False or obj.get("handoff_allowed") is not False:
        block("PG14_RECEIVER_UNAUTHORIZED")
    return obj["candidate_sha256"]

def simulate_testing_receiver(*,pg14_bridge,pg14_c1,pg14_c2,pg14_c3,request_payload):
    try:
        hb=valid(pg14_bridge,"PG13_C3_TO_PG14_C1_FROZEN_HANDOFF_CANDIDATE_V1")
        h1=valid(pg14_c1,"PG14_C1_TESTING_EXECUTION_HANDOFF_CANDIDATE_V1")
        h2=valid(pg14_c2,"PG14_C2_TESTING_SPEC_PAYLOAD_CANDIDATE_V1")
        h3=valid(pg14_c3,"PG14_C3_TESTING_ADMISSION_READBACK_REQUEST_CANDIDATE_V1")
        validate_pg14_c2_completeness(pg14_c2)
        if (pg14_bridge.get("source_pg14_c1_sha256")!=h1
            or pg14_c2.get("source_pg14_c1_sha256")!=h1
            or pg14_c3.get("source_pg14_c2_sha256")!=h2
            or pg14_bridge.get("frozen_candidate_sha256")!=pg14_c1.get("frozen_candidate_sha256_reported")
            or pg14_c2.get("frozen_candidate_sha256_reported")!=pg14_c1.get("frozen_candidate_sha256_reported")):
            block("PG14_RECEIVER_LINEAGE_DRIFT")
        if pg14_c1.get("mode")!="EXECUTION" or pg14_c1.get("testing_contract_schema")!="TESTING_ADMISSION_CONTRACT_V1":
            block("PG14_RECEIVER_WRONG_CONTRACT")
        if (not isinstance(pg14_c2.get("catalog_version_ref_reported"),str)
            or not pg14_c2["catalog_version_ref_reported"].strip()
            or pg14_c2.get("blind_test_contract_ref_reported")!="fn_submit_blind_test_contract"):
            block("PG14_RECEIVER_MISSING_CATALOG_OR_BLIND_TEST")
        obligations=pg14_c2.get("test_obligations_reported")
        if not isinstance(obligations,list) or "B2B-RULE-TEST-001" not in {
            o.get("obligation_ref") for o in obligations if isinstance(o,dict)}:
            block("PG14_RECEIVER_MISSING_B2B_TEST_OBLIGATION")
        pending=pg14_c2.get("pending_copy_texts_reported")
        if not isinstance(pending,list) or not pending:
            block("PG14_RECEIVER_MISSING_COPY_LIST")
        if (pg14_c1.get("testing_admission_invoked") is not False or
            pg14_c2.get("testing_invoked") is not False or
            pg14_c3.get("testing_request_sent") is not False or
            pg14_c3.get("testing_decision") is not None or
            pg14_bridge.get("analysis_ready_verified") is not False):
            block("PG14_RECEIVER_REAL_TESTING_OR_READY_FORBIDDEN")
        if (not isinstance(request_payload,dict)
            or request_payload!=pg14_c3.get("admission_request")
            or h(request_payload)!=pg14_c3.get("admission_request_sha256")
            or request_payload.get("mode")!="EXECUTION"
            or request_payload.get("frozen_candidate_sha256_reported")!=pg14_bridge.get("frozen_candidate_sha256")):
            block("PG14_RECEIVER_TAMPERED_REQUEST")
        verdict="ACCEPT"
        reason="LOCAL_FIXTURE_SHAPE_ACCEPTED_ONLY"
    except (PG14LocalReceiverBlocked,PG14C2CompletenessBlocked) as exc:
        verdict="BLOCK"
        reason=str(exc)
    result={
        "schema_version":"PG14_LOCAL_TESTING_RECEIVER_RESPONSE_V1",
        "mode":"EXECUTION","verdict":verdict,"reason":reason,
        "request_digest_reported":h(request_payload),
        "local_fixture_only":True,"testing_real_invoked":False,
        "analysis_ready_authenticated":False,"production_authority":False}
    result["response_sha256"]=h(result)
    return result
