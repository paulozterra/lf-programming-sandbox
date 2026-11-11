"""PG-03_C5 candidate projector: adversarial content integrity tests.
No governed catalog readback, model invocation or production authority.
"""
import copy
from pg03_domain_judges_v1 import project_rules_with_analysis, deterministic_judge_complete

strategy = {"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,
            "active_domains":["STD-BE"]}
catalog = {"rules":[
    {"id":"STD-GEN-01","domain":"GLOBAL","text":"preserve runtime safety","status":"APROBADO"},
    {"id":"STD-BE-01","domain":"STD-BE","text":"validate service inputs","status":"APROBADO"},
]}
a_rules = [{"id":"A1","domains":["STD-BE"],"text":"Never change existing auth",
            "source_ref":"fixture://A1"}]
p = project_rules_with_analysis(
    strategy=strategy,catalog=catalog,requested_domains=["STD-BE"],
    analysis_rules=a_rules,analysis_invariants=[])
assert deterministic_judge_complete(projection=p)["status"]=="PASS_CANDIDATE_ONLY"

negative = 0
def denied(label,mutate):
    global negative
    candidate=copy.deepcopy(p)
    mutate(candidate)
    result=deterministic_judge_complete(projection=candidate)
    assert result["status"]=="BLOCKED", (label,result)
    assert result["code"]=="PROJECTION_CONTENT_DIGEST_DRIFT", (label,result)
    negative+=1

# Historically these could be changed without affecting required_rule_ids parity.
denied("change_rule_text",lambda d:d["rules"][0].update(text="skip safety checks"))
denied("change_rule_domain",lambda d:d["rules"][0].update(domain="STD-FE"))
denied("change_analysis_text",lambda d:d["analysis_rules"][0].update(text="remove auth"))
denied("change_analysis_source",lambda d:d["analysis_rules"][0].update(source_ref="fixture://substituted"))
denied("change_catalog_sha",lambda d:d.update(source_catalog_sha256="0"*64))
denied("change_requested_domain",lambda d:d.update(requested_domains=["STD-FE"]))
denied("tamper_digest",lambda d:d.update(projection_sha256="f"*64))
denied("tamper_token_estimate",lambda d:d.update(estimated_tokens=0))

# Completeness by itself is insufficient if attacker drops a rule AND adjusts
# the self-declared expected IDs to match the truncated list.
def remove_and_hide(d):
    d["rules"]=d["rules"][1:]
    d["required_rule_ids"]=[x for x in d["required_rule_ids"] if x!="STD-BE-01"]
denied("remove_rule_and_required_id",remove_and_hide)

print(f"PASS_PG03_C5_PROJECTION_INTEGRITY positive=1 negatives={negative} "
      "local_digest_verified=true provider_attestation=false authority=NONE")
