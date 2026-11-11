"""Qualification-only PG03 C9 exact candidate subject binding.

Reuse existing preflight_pg03_subject and generic INDEPENDENT_ASSURANCE.
No semantic judge, receipt ledger writer, model dispatch, or source authenticator.
"""
import hashlib
import json
import re
from pg03_assurance_envelope_v1 import preflight_pg03_subject

HEX64=re.compile(r"^[0-9a-f]{64}$")
HEX40=re.compile(r"^[0-9a-f]{40}$")

def _deny(code):
    return {"status":"BLOCKED","code":code,"authority":False,
            "review_execution_allowed":False,"handoff_allowed":False}

def qualify_subject(*, strategy, envelope, upstream, expected_run_id):
    if not isinstance(strategy,dict) or strategy.get("schema_version")!="PG03_STRATEGY_CANDIDATE_V1" or strategy.get("status")!="CANDIDATE_NOT_ADMITTED" or strategy.get("dispatch_allowed") is not False or strategy.get("production_authority") is not False or strategy.get("handoff_allowed") is not False:
        return _deny("PG03_STRATEGY_CANDIDATE_REQUIRED")
    stored_digest=strategy.get("candidate_sha256")
    if not isinstance(stored_digest,str) or not HEX64.fullmatch(stored_digest):
        return _deny("PG03_CANDIDATE_DIGEST_INVALID")
    unsigned={k:v for k,v in strategy.items() if k!="candidate_sha256"}
    recomputed=hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if recomputed!=stored_digest:
        return _deny("PG03_STRATEGY_TAMPERED")
    if not isinstance(envelope,dict):
        return _deny("PG03_SUBJECT_ENVELOPE_INVALID")
    checked=preflight_pg03_subject(envelope)
    if checked.get("status")!="CANDIDATE_NOT_ADMITTED" or checked.get("runtime_call_permitted") is not False:
        return _deny("PG03_EXISTING_PREFLIGHT_DENIED")
    serialized_sha=hashlib.sha256(json.dumps(strategy,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if envelope.get("subject_sha256")!=serialized_sha:
        return _deny("PG03_SUBJECT_DIGEST_DRIFT")
    if envelope.get("source_head_sha")!=strategy.get("stack_commit_sha") or not HEX40.fullmatch(str(strategy.get("stack_commit_sha",""))):
        return _deny("PG03_SUBJECT_STACK_HEAD_DRIFT")
    if not isinstance(upstream,dict) or not isinstance(expected_run_id,str) or not expected_run_id:
        return _deny("PG03_UPSTREAM_RECEIPTS_MISSING")
    required=("PG-01_C6","PG-02_C5","PG-03_C2","PG-03_C3")
    if set(upstream)!=set(required) or any(upstream[k]!=expected_run_id for k in required):
        return _deny("PG03_UPSTREAM_RUN_DRIFT")
    if envelope.get("producer_execution_id")==envelope.get("reviewer_execution_id"):
        return _deny("PG03_REVIEWER_NOT_INDEPENDENT")
    # Matching synthetically supplied run ids, SHA and UUIDs does not prove
    # ledger existence/currentness, provider origin or reviewer qualification.
    return {"status":"CANDIDATE_NOT_ADMITTED",
            "code":"PG03_C9_EXACT_SUBJECT_BOUND_LEDGER_READBACK_REQUIRED",
            "operation_code":checked["operation_code"],
            "capability_code":checked["capability_code"],
            "subject_sha256":serialized_sha,
            "authority":False,"review_execution_allowed":False,
            "handoff_allowed":False,"ledger_readback_verified":False,
            "reviewer_independence_attested":False,
            "semantic_judge_executed":False}
