"""PG-03_C2 candidate L3 type B source-bound isolated qualification."""
import copy
import hashlib
import json
from pg03_c2_l3_type_b_binding_v1 import bind_l3_manifest, MANIFEST

binding={"target_repo":"fixture/product","target_head_sha":"a"*40}
manifest={
    "schema_version":MANIFEST,
    "repo_full_name":binding["target_repo"],
    "commit_sha":binding["target_head_sha"],
    "project_schema":"product_app",
    "source_ref":"fixture://project/technical-rules.json",
    "rules":[
        {"type":"B","id":"B-API-01","domain":"STD-API","text":"Respect contract X","source_ref":"fixture://b1"},
        {"type":"B","id":"B-FE-01","domain":"STD-FE","text":"Respect frontend Y","source_ref":"fixture://b2"},
        {"type":"B","id":"B-GLOBAL-01","domain":"GLOBAL","text":"Use project glossary","source_ref":"fixture://b3"},
    ],
}
def raw(m):
    return json.dumps(m,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def arguments(m=manifest):
    blob=raw(m)
    sha=hashlib.sha256(blob).hexdigest()
    return dict(manifest_bytes=blob,target_binding=copy.deepcopy(binding),
        pg01_c4_evidence={"source_digest_sha256":sha,**binding},
        expected_manifest_sha256=sha,active_domains=["STD-API"])

args=arguments()
result=bind_l3_manifest(**args)
assert result["status"]=="CANDIDATE_NOT_ADMITTED" and result["l3_type_b_verified"] is False
assert result["project_schema"]=="product_app" and result["authority"] is False
assert [r["id"] for r in result["selected_rules"]]==["B-API-01","B-GLOBAL-01"]
assert bind_l3_manifest(**copy.deepcopy(args))==result
assert result["source_contract_approved"] is False and result["source_currentness_verified"] is False
before=copy.deepcopy(manifest)
assert bind_l3_manifest(**arguments())==result and manifest==before

cases=[]
def negative(label, code, modify):
    a=arguments()
    modify(a)
    out=bind_l3_manifest(**a)
    assert out["status"]=="BLOCKED" and out["code"]==code,(label,out)
    assert out["authority"] is False and out["handoff_allowed"] is False
    cases.append(label)
    print("PG03_C2_L3_NEGATIVE_PASS="+label)

def patch(mutate):
    m=copy.deepcopy(manifest)
    mutate(m)
    return arguments(m)
def replace(a, mutate):
    a.update(patch(mutate))
negative("digest_drift","L3_MANIFEST_DIGEST_DRIFT",lambda a:a.update(expected_manifest_sha256="0"*64))
negative("c4_source_mismatch","PG01_C4_L3_BINDING_DRIFT",lambda a:a["pg01_c4_evidence"].update(source_digest_sha256="f"*64))
negative("c4_head_mismatch","PG01_C4_L3_BINDING_DRIFT",lambda a:a["pg01_c4_evidence"].update(target_head_sha="f"*40))
negative("manifest_repo_mismatch","L3_MANIFEST_TARGET_DRIFT",lambda a:replace(a,lambda m:m.update(repo_full_name="other/repo")))
negative("manifest_head_mismatch","L3_MANIFEST_TARGET_DRIFT",lambda a:replace(a,lambda m:m.update(commit_sha="f"*40)))
negative("unapproved_schema","L3_MANIFEST_SCHEMA_NOT_GOVERNED",lambda a:replace(a,lambda m:m.update(schema_version="INVENTED")))
negative("lf_ops_default","PROJECT_SCHEMA_NOT_BOUND",lambda a:replace(a,lambda m:m.update(project_schema="lf_ops")))
negative("missing_schema","PROJECT_SCHEMA_NOT_BOUND",lambda a:replace(a,lambda m:m.pop("project_schema")))
negative("missing_source_ref","L3_SOURCE_REF_MISSING",lambda a:replace(a,lambda m:m.update(source_ref="")))
negative("type_a_injected","L3_TYPE_B_RULE_INVALID",lambda a:replace(a,lambda m:m["rules"][0].update(type="A")))
negative("duplicate_rules","L3_TYPE_B_RULE_INVALID",lambda a:replace(a,lambda m:m["rules"][1].update(id="B-API-01")))
negative("missing_rule_provenance","L3_TYPE_B_RULE_INVALID",lambda a:replace(a,lambda m:m["rules"][0].update(source_ref="")))
negative("pending_decision","L3_PENDING_DECISION",lambda a:replace(a,lambda m:m["rules"][0].update(pending_decision=True)))
negative("l1_override","L3_CANNOT_OVERRIDE_L1_WITHOUT_GOVERNED_WAIVER",lambda a:replace(a,lambda m:m["rules"][0].update(modifies_l1=True)))
negative("unapproved_waiver","L3_CANNOT_OVERRIDE_L1_WITHOUT_GOVERNED_WAIVER",lambda a:replace(a,lambda m:m["rules"][0].update(waives_standard=True)))
negative("invalid_domains","ACTIVE_DOMAINS_INVALID",lambda a:a.update(active_domains=["STD-API","STD-API"]))
assert len(cases)==16
print("PASS_PG03_C2_L3_TYPE_B_BINDING positive=1 negative=16 exact_target=true "
      "no_lf_ops_fallback=true type_a_rejected=true l1_waiver_blocked=true "
      "l3_type_b_verified=false source_contract_approved=false "
      "authority=NONE runtime_verified=false")
