"""PG-03 C5: selective type-A rule projection, no omission or privilege escalation."""
import copy
from pg03_domain_judges_v1 import project_rules_with_analysis,deterministic_judge_complete,DomainJudgeBlocked
strategy={"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,"active_domains":["STD-BE","STD-FE"]}
catalog={"rules":[{"id":"BE","domain":"STD-BE","status":"APROBADO","text":"backend"},{"id":"FE","domain":"STD-FE","status":"APROBADO","text":"frontend"},{"id":"G","domain":"GLOBAL","status":"APROBADO","text":"global"}]}
rules=[{"id":"A1","domains":["STD-BE"],"text":"backend business invariant","source_ref":"fixture://A1"},
       {"id":"A2","domains":["STD-FE"],"text":"frontend business invariant","source_ref":"fixture://A2"}]
inv=[{"id":"INV1","domains":["GLOBAL"],"text":"cross cutting invariant","source_ref":"fixture://INV1"}]
args=dict(strategy=strategy,catalog=catalog,requested_domains=["STD-BE"],analysis_rules=rules,analysis_invariants=inv)
p=project_rules_with_analysis(**args)
assert [r["id"] for r in p["rules"]]==["BE","G"]
assert [r["id"] for r in p["analysis_rules"]]==["A1","INV1"]
assert p==project_rules_with_analysis(**copy.deepcopy(args))
assert deterministic_judge_complete(projection=p)["status"]=="PASS_CANDIDATE_ONLY"
bad=copy.deepcopy(p);bad["required_rule_ids"].remove("A1")
assert deterministic_judge_complete(projection=bad)["code"]=="REQUIRED_RULE_OMITTED"
bad=copy.deepcopy(p);bad["analysis_rules"][0]["source_ref"]=""
assert deterministic_judge_complete(projection=bad)["code"]=="ANALYSIS_PROVENANCE_MISSING"
def negative(field,val,reason):
    kw=copy.deepcopy(args);kw[field]=val
    try: project_rules_with_analysis(**kw)
    except DomainJudgeBlocked as exc: assert str(exc)==reason,(str(exc),reason)
    else:raise AssertionError(reason)
negative("analysis_rules",None,"ANALYSIS_RULES_MISSING")
negative("analysis_rules",[dict(rules[0],pending_decision=True)],"REQUIRES_DECISION_PENDING_ANALYSIS_RULE")
negative("analysis_rules",[dict(rules[0],source_ref="")],"ANALYSIS_PROVENANCE_MISSING")
negative("analysis_rules",[dict(rules[0],domains=["UNKNOWN"])],"UNCLASSIFIED_ANALYSIS_DOMAIN")
negative("analysis_rules",[dict(rules[0],id="BE")],"ANALYSIS_RULE_INVALID")
print("PG03_C5_ANALYSIS_PROJECTION_PASS backend_only=1 global=1 analysis=2 frontend_excluded=2 negative=7 authority=0")
