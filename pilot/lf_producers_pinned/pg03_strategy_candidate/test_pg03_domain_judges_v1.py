from pg03_domain_judges_v1 import project_rules,deterministic_judge,semantic_judge_boundary,DomainJudgeBlocked
strategy={"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,"active_domains":["STD-BE","STD-FE"]}
catalog={"rules":[{"id":"G1","domain":"GLOBAL","status":"APROBADO","text":"global"},
                  {"id":"B1","domain":"STD-BE","status":"APROBADO","text":"backend rule"},
                  {"id":"F1","domain":"STD-FE","status":"APROBADO","text":"frontend rule"}]}
out=project_rules(strategy=strategy,catalog=catalog,requested_domains=["STD-BE"])
assert [r["id"] for r in out["rules"]]==["B1","G1"]
assert out==project_rules(strategy=strategy,catalog=catalog,requested_domains=["STD-BE"])
ok=deterministic_judge(projection=out,mandatory_ids=["B1","G1"])
assert ok["status"]=="PASS_CANDIDATE_ONLY"
assert deterministic_judge(projection=out,mandatory_ids=["F1"])["code"]=="REQUIRED_RULE_OMITTED"
assert semantic_judge_boundary(deterministic_result=ok,semantic_review=None)["status"]=="REQUIRES_REVIEW"
assert semantic_judge_boundary(deterministic_result=ok,semantic_review={"verdict":"PASS","independent_attestation":True})["status"]=="CANDIDATE_NOT_ADMITTED"
def block(strategy,catalog,domains,code):
    try:project_rules(strategy=strategy,catalog=catalog,requested_domains=domains)
    except DomainJudgeBlocked as exc:assert str(exc)==code,(str(exc),code)
    else:raise AssertionError(code)
block(strategy,catalog,["UNKNOWN"],"UNCLASSIFIED_DOMAIN_REQUEST")
block(strategy,{"rules":catalog["rules"]+[dict(catalog["rules"][1])]},["STD-BE"],"CATALOG_RULE_INVALID")
changed={"rules":[dict(r) for r in catalog["rules"]]}
changed["rules"][1]["pending_decision"]=True
block(strategy,changed,["STD-BE"],"REQUIRES_DECISION_PENDING_RULE")
print("PG03_C5_DOMAIN_JUDGES_PASS selected_backend_global=2 frontend_excluded=1 negatives=3 semantic_no_authority=1")
