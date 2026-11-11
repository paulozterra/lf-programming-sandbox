"""PG-03_C2 L3 type-B source binding candidate; no project rule discovery.

Verifies bytes, target identity, schema and C4 evidence parity. The proposed
manifest shape is a qualification fixture, NOT a published L3 source contract.
Independent Git/Supabase readback, currentness and precedence authorization
remain outside this function; it never grants admission.
"""
import hashlib
import json
import re

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST = "PG03_L3_TYPE_B_MANIFEST_CANDIDATE_V1"

def block(code):
    return {"status":"BLOCKED","code":code,"authority":False,
            "handoff_allowed":False,"l3_type_b_verified":False}

def bind_l3_manifest(*, manifest_bytes, target_binding, pg01_c4_evidence,
                     expected_manifest_sha256, active_domains):
    if not isinstance(target_binding,dict) or not isinstance(target_binding.get("target_repo"),str) or "/" not in target_binding["target_repo"] or not SHA40.fullmatch(str(target_binding.get("target_head_sha",""))):
        return block("TARGET_BINDING_INVALID")
    if not isinstance(manifest_bytes,bytes) or not manifest_bytes or not SHA64.fullmatch(str(expected_manifest_sha256)):
        return block("MANIFEST_SOURCE_INVALID")
    sha=hashlib.sha256(manifest_bytes).hexdigest()
    if sha != expected_manifest_sha256:
        return block("L3_MANIFEST_DIGEST_DRIFT")
    if not isinstance(pg01_c4_evidence,dict):
        return block("PG01_C4_L3_EVIDENCE_MISSING")
    if (pg01_c4_evidence.get("source_digest_sha256")!=sha or
        pg01_c4_evidence.get("target_repo")!=target_binding["target_repo"] or
        pg01_c4_evidence.get("target_head_sha")!=target_binding["target_head_sha"]):
        return block("PG01_C4_L3_BINDING_DRIFT")
    if not isinstance(active_domains,list) or not active_domains or len(set(map(str,active_domains)))!=len(active_domains) or any(not isinstance(x,str) or not x.strip() for x in active_domains):
        return block("ACTIVE_DOMAINS_INVALID")
    try:
        manifest=json.loads(manifest_bytes)
    except (ValueError,UnicodeDecodeError):
        return block("L3_MANIFEST_JSON_INVALID")
    if not isinstance(manifest,dict) or manifest.get("schema_version")!=MANIFEST:
        return block("L3_MANIFEST_SCHEMA_NOT_GOVERNED")
    if (manifest.get("repo_full_name")!=target_binding["target_repo"] or
        manifest.get("commit_sha")!=target_binding["target_head_sha"]):
        return block("L3_MANIFEST_TARGET_DRIFT")
    project_schema=manifest.get("project_schema")
    if not isinstance(project_schema,str) or not re.fullmatch(r"[a-z][a-z0-9_]*",project_schema) or project_schema in ("lf_ops","public","private","programacion","transversal"):
        return block("PROJECT_SCHEMA_NOT_BOUND")
    if not isinstance(manifest.get("source_ref"),str) or not manifest["source_ref"].strip():
        return block("L3_SOURCE_REF_MISSING")
    if not isinstance(manifest.get("rules"),list):
        return block("L3_RULES_INVALID")
    projected=[]
    ids=set()
    for row in manifest["rules"]:
        if not isinstance(row,dict) or row.get("type")!="B" or not isinstance(row.get("id"),str) or not row["id"] or row["id"] in ids:
            return block("L3_TYPE_B_RULE_INVALID")
        ids.add(row["id"])
        if (not isinstance(row.get("domain"),str) or not row["domain"] or
            not isinstance(row.get("text"),str) or not row["text"].strip() or
            not isinstance(row.get("source_ref"),str) or not row["source_ref"].strip()):
            return block("L3_TYPE_B_RULE_INVALID")
        if row.get("pending_decision") is True:
            return block("L3_PENDING_DECISION")
        if row.get("modifies_l1") is True or row.get("waives_standard") is True:
            return block("L3_CANNOT_OVERRIDE_L1_WITHOUT_GOVERNED_WAIVER")
        if row["domain"] in active_domains or row["domain"]=="GLOBAL":
            projected.append({k:row[k] for k in ("id","domain","text","source_ref")})
    return {
        "status":"CANDIDATE_NOT_ADMITTED",
        "code":"L3_TYPE_B_SHAPE_BOUND_TRUSTED_READBACK_REQUIRED",
        "authority":False,"handoff_allowed":False,
        "l3_type_b_verified":False,"source_contract_approved":False,
        "source_currentness_verified":False,"precedence_verified":False,
        "target_repo":target_binding["target_repo"],
        "target_head_sha":target_binding["target_head_sha"],
        "project_schema":project_schema,"manifest_sha256":sha,
        "selected_rules":sorted(projected,key=lambda x:x["id"]),
    }
