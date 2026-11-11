"""Exact PG03 subject binding to existing independent-assurance preflight."""
import copy
import hashlib
import json
from pg03_strategy_v1 import prepare_strategy
from pg03_c9_subject_binding_v1 import qualify_subject

strategy=prepare_strategy(
    classification={"status":"CANDIDATE_NOT_ADMITTED","dispatch_allowed":False,
        "candidate":{"status":"CANDIDATE_NOT_ADMITTED","scopes":[
            {"scope_id":"S1","state":"READY_FOR_CLASSIFICATION","candidate_domains":["STD-BE"]}]}},
    stack_evidence={"status":"CANDIDATE_NOT_ADMITTED","authority":False,
        "commit_sha":"a"*40,"sources":[{"sha256":"b"*64}]},
    partition_contract={"schema_version":"PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1",
        "partition_policy":{"canonical_spec_count":1,"partition_unit":"SOLUTION",
                            "minimum_rule":"SMALLEST_COHERENT_VALID_CHANGE"},
        "coverage":{"material_requirement_coverage_required_percent":100,
                    "acceptance_obligation_coverage_required_percent":100}},
    requirement_ids=["R1"],acceptance_ids=["A1"],reuse_refs=["MODULE"],
    capability_selector="REUSE",alternatives=["EXTEND"],fallback="REQUIRES_DECISION",
)
def sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":")).encode()).hexdigest()
envelope={
    "subject_type":"PG03_TECHNICAL_STRATEGY","subject_ref":"fixture://pg03/S1",
    "subject_sha256":sha(strategy),"source_head_sha":"a"*40,
    "subject_receipt_id":"11111111-1111-4111-8111-111111111111",
    "dispatch_receipt_id":"22222222-2222-4222-8222-222222222222",
    "producer_execution_id":"PRODUCER-1","reviewer_execution_id":"REVIEWER-2",
    "review_required":True,"required_dimensions":["RULE_FIDELITY","REUSE_CORRECTNESS"],
    "request_sha256":"c"*64,"plan_digest":"fixture-plan",
    "capability_manifest_sha256":"d"*64,
}
upstream={k:"RUN-1" for k in ("PG-01_C6","PG-02_C5","PG-03_C2","PG-03_C3")}
kw=dict(strategy=strategy,envelope=envelope,upstream=upstream,expected_run_id="RUN-1")
ok=qualify_subject(**kw)
assert ok["status"]=="CANDIDATE_NOT_ADMITTED"
assert ok["operation_code"]=="REVISION_INDEPENDIENTE_ESTRATEGIA_LF"
assert ok["capability_code"]=="INDEPENDENT_ASSURANCE"
assert ok["ledger_readback_verified"] is False
assert ok["semantic_judge_executed"] is False
assert ok["review_execution_allowed"] is False
assert ok==qualify_subject(**copy.deepcopy(kw))

def reject(label,changes,reason):
    arg=copy.deepcopy(kw)
    changes(arg)
    result=qualify_subject(**arg)
    assert result["status"]=="BLOCKED" and result["code"]==reason,(label,result)
    assert result["authority"] is False and result["review_execution_allowed"] is False
    print("PG03_C9_BINDING_NEGATIVE_PASS="+label)

reject("strategy_tamper",lambda a:a["strategy"].update(requirement_ids=["R2"]), "PG03_STRATEGY_TAMPERED")
reject("fake_strategy_authority",lambda a:a["strategy"].update(dispatch_allowed=True),"PG03_STRATEGY_CANDIDATE_REQUIRED")
reject("wrong_subject_digest",lambda a:a["envelope"].update(subject_sha256="f"*64),"PG03_SUBJECT_DIGEST_DRIFT")
reject("wrong_stack_head",lambda a:a["envelope"].update(source_head_sha="e"*40),"PG03_SUBJECT_STACK_HEAD_DRIFT")
reject("self_review",lambda a:a["envelope"].update(reviewer_execution_id="PRODUCER-1"),"PG03_EXISTING_PREFLIGHT_DENIED")
reject("missing_receipt",lambda a:a["envelope"].update(subject_receipt_id=None),"PG03_EXISTING_PREFLIGHT_DENIED")
reject("upstream_missing",lambda a:a["upstream"].pop("PG-01_C6"),"PG03_UPSTREAM_RUN_DRIFT")
reject("upstream_wrong_run",lambda a:a["upstream"].update({"PG-02_C5":"OTHER"}),"PG03_UPSTREAM_RUN_DRIFT")
reject("false_review_required",lambda a:a["envelope"].update(review_required=False),"PG03_EXISTING_PREFLIGHT_DENIED")
reject("duplicate_dimensions",lambda a:a["envelope"].update(required_dimensions=["RULE_FIDELITY"]*2),"PG03_EXISTING_PREFLIGHT_DENIED")
print("PASS_PG03_C9_EXACT_SUBJECT_BINDING positive=1 negative=10 "
      "existing_assurance_reused=true candidate_digest_bound=true "
      "ledger_readback_verified=false semantic_judge_executed=false "
      "authority=NONE runtime_verified=false")
