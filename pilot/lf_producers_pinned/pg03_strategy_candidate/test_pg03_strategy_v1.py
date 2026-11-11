"""PG-03 C3 candidate strategy decision: reused policy, no authority."""
import copy
import json
from pathlib import Path
from pg03_strategy_v1 import prepare_strategy,StrategyBlocked

# Strictly synthetic fixtures; real coverage and stack provenance remain outside scope.
contract={"schema_version":"PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1",
          "partition_policy":{"canonical_spec_count":1,"partition_unit":"SOLUTION",
                              "minimum_rule":"SMALLEST_COHERENT_VALID_CHANGE"},
          "coverage":{"material_requirement_coverage_required_percent":100,
                      "acceptance_obligation_coverage_required_percent":100}}
c={"status":"CANDIDATE_NOT_ADMITTED","dispatch_allowed":False,
   "candidate":{"status":"CANDIDATE_NOT_ADMITTED","scopes":[
       {"scope_id":"S1","state":"READY_FOR_CLASSIFICATION","candidate_domains":["STD-BE"]}]}}
s={"status":"CANDIDATE_NOT_ADMITTED","authority":False,"commit_sha":"a"*40,
   "sources":[{"sha256":"b"*64}]}
kw=dict(classification=c,stack_evidence=s,partition_contract=contract,
        requirement_ids=["R1"],acceptance_ids=["A1"],reuse_refs=["existing-module"],
        capability_selector="REUSE_COMPONENT",alternatives=["NEW_COMPONENT"],fallback="REQUIRES_DECISION")
o=prepare_strategy(**kw)
assert o["status"]=="CANDIDATE_NOT_ADMITTED" and not o["handoff_allowed"] and not o["production_authority"]
assert o==prepare_strategy(**copy.deepcopy(kw))
def negative(field,value,reason):
    args=copy.deepcopy(kw);args[field]=value
    try:prepare_strategy(**args)
    except StrategyBlocked as e: assert str(e)==reason,(str(e),reason)
    else:raise AssertionError(reason)
negative("classification",{"status":"PASS"},"PG02_CANDIDATE_REQUIRED")
bad=copy.deepcopy(c);bad["candidate"]["scopes"][0]["state"]="BLOCKED"
negative("classification",bad,"NON_READY_SCOPE")
bad=copy.deepcopy(s);bad["authority"]=True
negative("stack_evidence",bad,"STACK_EVIDENCE_INVALID")
bad=copy.deepcopy(contract);bad["partition_policy"]["partition_unit"]="FILE"
negative("partition_contract",bad,"PARTITION_POLICY_DRIFT")
negative("requirement_ids",[],"COVERAGE_NOT_ESTABLISHED")
negative("alternatives",[],"STRATEGY_DECISION_MISSING")
print("PG03_C3_STRATEGY_CANDIDATE_PASS positive=1 deterministic=1 negatives=6 authority=0")
