"""PG12 binding to PG11 C5 and Git object proof from independently read bytes.

Source-only: the caller must retrieve Git object bytes from a trusted repo.
Object SHA1 is verified, commit->tree is parsed, but source authenticity
and Git diff readback remain unverified without a trusted Git checkout.
"""
import hashlib
import json
import re

OID=re.compile(r"^[0-9a-f]{40}$")
SHA256=re.compile(r"^[0-9a-f]{64}$")

class PG12IdentityBlocked(ValueError):pass
def block(code):raise PG12IdentityBlocked(code)
def sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def freeze(obj,schema,status="CANDIDATE_NOT_ADMITTED"):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema or obj.get("status")!=status:
        block("PG12_BRIDGE_SCHEMA_OR_STATUS_INVALID")
    s=obj.get("candidate_sha256")
    if not isinstance(s,str) or not SHA256.fullmatch(s) or s!=sha({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        block("PG12_BRIDGE_SHA_DRIFT")
    if obj.get("production_authority") is not False or obj.get("handoff_allowed") is not False:
        block("PG12_BRIDGE_PREMATURE_AUTHORITY")
    return s

def verify_git_object(*,object_kind,object_bytes,declared_oid):
    if object_kind not in ("commit","tree","blob") or not isinstance(object_bytes,bytes):
        block("PG12_GIT_OBJECT_FORMAT_INVALID")
    if not isinstance(declared_oid,str) or not OID.fullmatch(declared_oid):
        block("PG12_GIT_OID_SHAPE_INVALID")
    actual=hashlib.sha1((object_kind+" "+str(len(object_bytes))+"\0").encode()+object_bytes).hexdigest()
    if declared_oid!=actual:block("PG12_GIT_OBJECT_OID_MISMATCH")
    return actual

def bridge_pg11_to_pg12_identity(*,pg10_pg11_bridge,pg11_c5,pg12_c1,
                                repo_ref,base_commit_bytes=None,candidate_commit_bytes=None,
                                candidate_tree_bytes=None):
    h11=freeze(pg11_c5,"PG11_C5_INDEPENDENT_REVIEW_CANDIDATE_V1")
    h12=freeze(pg12_c1,"PG12_C1_CANDIDATE_IDENTITY_V1")
    hb=freeze(pg10_pg11_bridge,"PG10_C5_TO_PG11_C1_HANDOFF_CANDIDATE_V1")
    if pg12_c1.get("source_pg11_c5_sha256")!=h11:
        block("PG12_PG11_C5_LINK_DRIFT")
    if (pg11_c5.get("source_pg11_c4_sha256") is None or
        pg10_pg11_bridge.get("source_pg11_c1_sha256") is None):
        block("PG12_PG11_C1_C5_LINEAGE_MISSING")
    if (pg10_pg11_bridge.get("base_head_sha")!=pg12_c1.get("base_commit_sha_reported")
        or pg10_pg11_bridge.get("expected_head_sha")!=pg12_c1.get("candidate_commit_sha_reported")
        or pg10_pg11_bridge.get("target_repo")!=repo_ref
        or pg12_c1.get("repository_ref_reported")!=repo_ref):
        block("PG12_PG11_RUN_REPO_COMMIT_DRIFT")
    base=pg12_c1["base_commit_sha_reported"]
    head=pg12_c1["candidate_commit_sha_reported"]
    tree=pg12_c1["candidate_tree_sha_reported"]
    present=[v is not None for v in (
        base_commit_bytes,candidate_commit_bytes,candidate_tree_bytes)]
    if any(present) and not all(present):
        block("PG12_GIT_OBJECT_PROOF_INCOMPLETE")
    if all(present):
        verify_git_object(object_kind="commit",object_bytes=base_commit_bytes,declared_oid=base)
        verify_git_object(object_kind="commit",object_bytes=candidate_commit_bytes,declared_oid=head)
        verify_git_object(object_kind="tree",object_bytes=candidate_tree_bytes,declared_oid=tree)
        try:
            lines=candidate_commit_bytes.split(b"\n\n",1)[0].split(b"\n")
            tree_lines=[l for l in lines if l.startswith(b"tree ")]
            parsed=tree_lines[0].split(b" ",1)[1].decode("ascii")
        except (UnicodeDecodeError,IndexError):
            block("PG12_GIT_COMMIT_TREE_PARSE_INVALID")
        if len(tree_lines)!=1 or parsed!=tree:block("PG12_GIT_COMMIT_TREE_DRIFT")
    return {
        "schema_version":"PG11_C5_TO_PG12_C1_GIT_BOUND_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg10_pg11_bridge_sha256":hb,
        "source_pg11_c5_sha256":h11,"source_pg12_c1_sha256":h12,
        "run_ref":pg10_pg11_bridge.get("run_ref"),
        "target_repo":repo_ref,"base_commit_sha":base,
        "candidate_commit_sha":head,"candidate_tree_sha":tree,
        "git_object_sha1_recomputed_from_supplied_bytes":all(present),
        "git_object_source_authenticated":False,
        "diff_readback_verified":False,"independent_review_executed":False,
        "handoff_allowed":False,"production_authority":False}
