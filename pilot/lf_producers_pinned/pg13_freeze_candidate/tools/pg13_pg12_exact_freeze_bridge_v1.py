"""Exact PG12 C1/C4 -> PG13 C1 freeze intent lineage, non-authoritative."""
import hashlib
import json
import re

SHA256=re.compile(r"^[0-9a-f]{64}$")
GIT40=re.compile(r"^[0-9a-f]{40}$")
class PG13BridgeBlocked(ValueError):pass
def block(code):raise PG13BridgeBlocked(code)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def freeze(obj,schema):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema or obj.get("status")!="CANDIDATE_NOT_ADMITTED":
        block("PG13_BRIDGE_SCHEMA_INVALID")
    h=obj.get("candidate_sha256")
    if not isinstance(h,str) or not SHA256.fullmatch(h) or h!=digest({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        block("PG13_BRIDGE_DIGEST_MISMATCH")
    if obj.get("production_authority") is not False or obj.get("handoff_allowed") is not False:
        block("PG13_BRIDGE_AUTHORITY_FORBIDDEN")
    return h

def bridge_pg12_c4_to_pg13_c1(*,pg12_c1,pg12_c4,pg13_c1):
    h1=freeze(pg12_c1,"PG12_C1_CANDIDATE_IDENTITY_V1")
    h4=freeze(pg12_c4,"PG12_C4_PERSISTENCE_READBACK_REQUEST_CANDIDATE_V1")
    hf=freeze(pg13_c1,"PG13_C1_FREEZE_INTENT_CANDIDATE_V1")
    commit=pg12_c1.get("candidate_commit_sha_reported")
    tree=pg12_c1.get("candidate_tree_sha_reported")
    if (not isinstance(commit,str) or not GIT40.fullmatch(commit)
        or not isinstance(tree,str) or not GIT40.fullmatch(tree)):
        block("PG13_BRIDGE_GIT_OID_INVALID")
    if (pg12_c4.get("source_pg12_c1_sha256")!=h1
        or pg13_c1.get("source_pg12_c4_sha256")!=h4
        or pg13_c1.get("source_pg12_c1_sha256")!=h1):
        block("PG13_BRIDGE_UPSTREAM_CHAIN_DRIFT")
    if (pg13_c1.get("candidate_commit_sha_reported")!=commit
        or pg13_c1.get("candidate_tree_sha_reported")!=tree):
        block("PG13_BRIDGE_EXACT_COMMIT_TREE_DRIFT")
    request_payload=pg12_c4.get("payload_candidate")
    expected_digest=pg12_c4.get("payload_candidate_sha256")
    if (not isinstance(expected_digest,str) or expected_digest!=digest(request_payload)
        or pg12_c4.get("persisted") is not False
        or pg12_c4.get("readback_matched") is not False
        or pg13_c1.get("freeze_enforced") is not False):
        block("PG13_BRIDGE_PREMATURE_READBACK_OR_FREEZE")
    result={"schema_version":"PG12_C4_TO_PG13_C1_FREEZE_BRIDGE_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg12_c1_sha256":h1,"source_pg12_c4_sha256":h4,
        "source_pg13_c1_sha256":hf,
        "pg12_c4_payload_sha256":expected_digest,
        "candidate_commit_sha":commit,"candidate_tree_sha":tree,
        "payload_digest_checked_against_declaration":True,
        "pg12_postgres_readback_authenticated_by_this_component":False,
        "git_object_readback_authenticated":False,
        "freeze_enforced":False,"production_authority":False,"handoff_allowed":False}
    result["candidate_sha256"]=digest(result)
    return result
