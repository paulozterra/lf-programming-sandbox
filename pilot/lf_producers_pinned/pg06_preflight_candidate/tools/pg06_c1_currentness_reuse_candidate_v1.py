"""PG-06_C1 reuse the PG-01 currentness decision without re-evaluation.

Produces a bound decision reuse proposal or a typed recheck request. Does not
read or attest receipts, call CURRENTNESS_AUTHORITY, rebind mid execution or
promote an upstream candidate to READY.
"""
import hashlib
import json
import re

class PG06CurrentnessBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")

def _fail(code):
    raise PG06CurrentnessBlocked(code)

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _frozen(value):
    if not isinstance(value,dict) or value.get("schema_version")!="PG05_TO_PG06_EXIT_CANDIDATE_V1":
        _fail("PG06_C1_EXIT_SCHEMA_INVALID")
    sig=value.get("candidate_sha256")
    if not isinstance(sig,str) or not _SHA.fullmatch(sig) or sig!=_digest({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _fail("PG06_C1_EXIT_DIGEST_DRIFT")
    if (value.get("status")!="CANDIDATE_NOT_ADMITTED" or
        value.get("pg05_admitted") is not False or
        value.get("pg06_admitted") is not False or
        value.get("write_allowed") is not False or
        value.get("production_authority") is not False or
        value.get("handoff_allowed") is not False or
        value.get("pg01_currentness_decision_verified") is not False):
        _fail("PG06_C1_EXIT_NOT_UNTRUSTED_CANDIDATE")
    return sig

def _ref(value):
    return isinstance(value,str) and bool(value.strip())

def prepare_pg06_c1(*,pg05_exit,pg01_currentness_binding,change_signal=None,execution_started=False):
    """Source-only: preserve PG01 binding; typed change signal triggers recheck request."""
    exit_sha=_frozen(pg05_exit)
    if execution_started is not False:
        _fail("PG06_C1_MID_EXECUTION_REBIND_FORBIDDEN")
    if not isinstance(pg01_currentness_binding,dict) or set(pg01_currentness_binding)!={
        "pg01_decision_ref","pg01_decision_sha256","context_sha256",
        "snapshot_schema_digest_sha256","authority_fingerprint_sha256",
        "source_snapshot_sha256","decision","decision_source_capability"
    }:
        _fail("PG06_C1_PG01_DECISION_BINDING_INCOMPLETE")
    p=pg01_currentness_binding
    if (any(not _ref(p[k]) for k in ("pg01_decision_ref",))
        or any(not isinstance(p[k],str) or not _SHA.fullmatch(p[k]) for k in
               ("pg01_decision_sha256","context_sha256","snapshot_schema_digest_sha256",
                "authority_fingerprint_sha256","source_snapshot_sha256"))
        or p["decision_source_capability"]!="CURRENTNESS_AUTHORITY"
        or p["decision"] not in ("CURRENT","CURRENT_REBOUND","STALE_AFFECTED","UNKNOWN_FAIL_CLOSED")):
        _fail("PG06_C1_PG01_DECISION_BINDING_INVALID")
    if change_signal is None:
        mode="REUSE_PG01_DECISION_REFERENCE"
        typed_reason=None
        signal_ref=None
        affected=[]
        if p["decision"] in ("CURRENT","CURRENT_REBOUND"):
            state="CANDIDATE_NOT_ADMITTED"
            reason="PG01_REFERENCE_REUSE_REQUIRES_CURRENT_RECEIPT_READBACK"
        else:
            state="BLOCKED"
            reason="PG01_DECISION_NOT_CURRENT"
    else:
        if not isinstance(change_signal,dict) or set(change_signal)!={
            "reason","evidence_ref","affected_scope_ids","observed_source_snapshot_sha256"
        }:
            _fail("PG06_C1_CHANGE_SIGNAL_INVALID")
        typed_reason=change_signal["reason"]
        signal_ref=change_signal["evidence_ref"]
        affected=change_signal["affected_scope_ids"]
        if typed_reason not in ("SOURCE_DRIFT","STALE") or not _ref(signal_ref):
            _fail("PG06_C1_RECHECK_REASON_NOT_TYPED")
        if (not isinstance(affected,list) or not affected or
            any(not _ref(x) for x in affected) or len(set(affected))!=len(affected)):
            _fail("PG06_C1_AFFECTED_SCOPE_IDS_INVALID")
        observed=change_signal["observed_source_snapshot_sha256"]
        if not isinstance(observed,str) or not _SHA.fullmatch(observed):
            _fail("PG06_C1_SOURCE_OBSERVATION_INVALID")
        if typed_reason=="SOURCE_DRIFT" and observed==p["source_snapshot_sha256"]:
            _fail("PG06_C1_SOURCE_DRIFT_NOT_EVIDENCED_BY_HASH")
        mode="REQUEST_GOVERNED_RECHECK"
        state="BLOCKED"
        reason="CURRENTNESS_AUTHORITY_TYPED_RECHECK_REQUIRED"
    result={
        "schema_version":"PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1",
        "status":state,
        "first_blocker":reason,
        "source_pg05_exit_sha256":exit_sha,
        "mode":mode,
        "source_pg01_binding":dict(p),
        "change_signal_ref":signal_ref,
        "typed_recheck_reason":typed_reason,
        "affected_scope_ids":sorted(affected),
        "currentness_decision_value_from_caller":p["decision"],
        "pg01_decision_readback_verified":False,
        "pg01_receipt_currentness_verified":False,
        "pg01_binding_fingerprint_verified":False,
        "source_snapshot_currentness_verified":False,
        "change_signal_authenticity_verified":False,
        "currentness_authority_invoked":False,
        "recheck_executed":False,
        "mid_execution_rebind_permitted":False,
        "pg01_receipt_mutated":False,
        "pg06_ready":False,
        "execution_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":("PG01_EXACT_CURRENTNESS_RECEIPT_READBACK"
                     if change_signal is None
                     else "GOVERNED_CURRENTNESS_AUTHORITY_RECHECK_ON_AFFECTED_SCOPES")
    }
    result["candidate_sha256"]=_digest(result)
    return result
