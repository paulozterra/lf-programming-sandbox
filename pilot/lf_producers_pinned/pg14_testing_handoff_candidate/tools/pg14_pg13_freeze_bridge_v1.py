"""PG13 C3 -> PG14 C1 freeze lineage, no production Testing dispatch."""
import hashlib,json,re
SHA=re.compile(r"^[0-9a-f]{64}$")
OID=re.compile(r"^[0-9a-f]{40}$")
class PG14BridgeBlocked(ValueError):pass
def block(e):raise PG14BridgeBlocked(e)
def h(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def frozen(obj,schema):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema or obj.get("status")!="CANDIDATE_NOT_ADMITTED":
        block("PG14_BRIDGE_SOURCE_SCHEMA_INVALID")
    s=obj.get("candidate_sha256")
    if not isinstance(s,str) or not SHA.fullmatch(s) or s!=h({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        block("PG14_BRIDGE_SOURCE_DIGEST_DRIFT")
    if obj.get("production_authority") is not False or obj.get("handoff_allowed") is not False:
        block("PG14_BRIDGE_PREMATURE_AUTHORITY")
    return s

def bridge_pg13_to_pg14(*,pg12_c1,pg13_bridge,pg13_c1,pg13_c2,pg13_c3,
                        pg14_c1,freeze_tag_ref,freeze_tag_oid,
                        analysis_package_observation):
    h12=frozen(pg12_c1,"PG12_C1_CANDIDATE_IDENTITY_V1")
    hb=frozen(pg13_bridge,"PG12_C4_TO_PG13_C1_FREEZE_BRIDGE_CANDIDATE_V1")
    h1=frozen(pg13_c1,"PG13_C1_FREEZE_INTENT_CANDIDATE_V1")
    h2=frozen(pg13_c2,"PG13_C2_REBUILD_COMPARISON_CANDIDATE_V1")
    h3=frozen(pg13_c3,"PG13_C3_MUTATION_BLOCK_CANDIDATE_V1")
    h14=frozen(pg14_c1,"PG14_C1_TESTING_EXECUTION_HANDOFF_CANDIDATE_V1")
    if (pg13_bridge.get("source_pg12_c1_sha256")!=h12
        or pg13_bridge.get("source_pg13_c1_sha256")!=h1
        or pg13_c1.get("source_pg12_c1_sha256")!=h12
        or pg13_c2.get("source_pg13_c1_sha256")!=h1
        or pg13_c3.get("source_pg13_c2_sha256")!=h2
        or pg13_c3.get("source_pg12_c1_sha256")!=h12
        or pg14_c1.get("source_pg13_c3_sha256")!=h3):
        block("PG14_BRIDGE_SOURCE_LINK_DRIFT")
    commit=pg12_c1.get("candidate_commit_sha_reported")
    tree=pg12_c1.get("candidate_tree_sha_reported")
    if (not isinstance(commit,str) or not OID.fullmatch(commit)
        or not isinstance(tree,str) or not OID.fullmatch(tree)
        or pg13_bridge.get("candidate_commit_sha")!=commit
        or pg13_bridge.get("candidate_tree_sha")!=tree
        or pg13_c3.get("candidate_commit_sha_reported")!=commit
        or pg14_c1.get("frozen_git_commit_reported")!=commit):
        block("PG14_BRIDGE_FROZEN_COMMIT_DRIFT")
    if (pg14_c1.get("frozen_candidate_sha256_reported")!=h12
        or pg14_c1.get("mode")!="EXECUTION"):
        block("PG14_BRIDGE_FROZEN_IDENTITY_DRIFT")
    if (freeze_tag_ref!="refs/tags/frozen/"+commit
        or not isinstance(freeze_tag_oid,str) or not OID.fullmatch(freeze_tag_oid)):
        block("PG14_BRIDGE_FROZEN_TAG_DRIFT")
    if (not isinstance(analysis_package_observation,dict)
        or set(analysis_package_observation)!={"package_ref","package_sha256","source_currentness_ref","ready_verified"}
        or analysis_package_observation["package_ref"]!=pg14_c1.get("analysis_package_ref_reported")
        or analysis_package_observation["package_sha256"]!=pg14_c1.get("analysis_package_sha256_reported")
        or analysis_package_observation["source_currentness_ref"]!=pg14_c1.get("source_currentness_ref_reported")
        or not isinstance(analysis_package_observation["package_sha256"],str)
        or not SHA.fullmatch(analysis_package_observation["package_sha256"])
        or analysis_package_observation["ready_verified"] is not False):
        block("PG14_BRIDGE_ANALYSIS_PACKAGE_DRIFT_OR_UNAUTHORIZED_READY")
    result={
        "schema_version":"PG13_C3_TO_PG14_C1_FROZEN_HANDOFF_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg12_c1_sha256":h12,"source_pg13_bridge_sha256":hb,
        "source_pg13_c3_sha256":h3,"source_pg14_c1_sha256":h14,
        "frozen_commit_sha":commit,"frozen_tree_sha":tree,
        "frozen_candidate_sha256":h12,
        "freeze_tag_ref_reported":freeze_tag_ref,
        "freeze_tag_oid_reported":freeze_tag_oid,
        "analysis_package_sha256_reported":analysis_package_observation["package_sha256"],
        "freeze_tag_authenticity_verified":False,
        "analysis_ready_verified":False,
        "testing_invoked":False,"handoff_allowed":False,"production_authority":False}
    result["candidate_sha256"]=h(result)
    return result
