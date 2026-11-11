"""Fail-closed completeness check for PG14 C2 as Testing intake input."""
import hashlib,json
class PG14C2CompletenessBlocked(ValueError):pass
def block(s):raise PG14C2CompletenessBlocked(s)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def validate_pg14_c2_completeness(candidate):
    if not isinstance(candidate,dict) or candidate.get("schema_version")!="PG14_C2_TESTING_SPEC_PAYLOAD_CANDIDATE_V2":
        block("PG14_C2_SCHEMA_INVALID")
    if candidate.get("candidate_sha256")!=digest({k:v for k,v in candidate.items() if k!="candidate_sha256"}):
        block("PG14_C2_DIGEST_INVALID")
    if candidate.get("production_authority") is not False or candidate.get("handoff_allowed") is not False:
        block("PG14_C2_PREMATURE_AUTHORITY")
    if not isinstance(candidate.get("catalog_version_ref_reported"),str) or not candidate["catalog_version_ref_reported"].strip():
        block("PG14_C2_CATALOG_MISSING")
    if candidate.get("blind_test_contract_ref_reported")!="fn_submit_blind_test_contract":
        block("PG14_C2_BLIND_TEST_CONTRACT_MISSING")
    obligations=candidate.get("test_obligations_reported")
    if not isinstance(obligations,list) or candidate.get("required_obligation_ref_reported") not in {
            row.get("obligation_ref") for row in obligations if isinstance(row,dict)}:
        block("PG14_C2_V2_OBLIGATION_MISSING")
    pending=candidate.get("pending_copy_texts_reported")
    if not isinstance(pending,list) or (not pending and not isinstance(candidate.get("copy_applicability_ref_reported"),str)) or any(
            not isinstance(row,dict) or row.get("status")!="PENDING_COPY" or
            not isinstance(row.get("text_ref"),str) or not row["text_ref"].strip()
            for row in pending):
        block("PG14_C2_PENDING_COPY_LIST_MISSING")
    return {"valid_declared_package":True,"canonical_sources_authenticated":False,
        "testing_invoked":False,"production_authority":False}
