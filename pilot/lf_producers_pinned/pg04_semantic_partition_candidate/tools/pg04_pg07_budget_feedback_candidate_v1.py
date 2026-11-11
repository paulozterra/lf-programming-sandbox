"""PG-04_C6: receive PG-07 context budget feedback and prepare a governed repair edge.

No token estimator, no second budget engine, no automatic repartition,
no mutation of solution DAG, no activation or production authority.
"""
import hashlib
import json
import re

class BudgetFeedbackBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")
_TEXT=lambda value:isinstance(value,str) and bool(value.strip())

def _fail(code):
    raise BudgetFeedbackBlocked(code)

def _sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _id_list(value):
    return isinstance(value,list) and all(_TEXT(x) for x in value) and len(value)==len(set(value))

def prepare_pg07_budget_feedback(*,partition,budget_feedback):
    """Freeze a diagnostic PG07→PG04 edge; never decide that budget passed."""
    if (not isinstance(partition,dict) or
        partition.get("schema_version")!="PG04_SEMANTIC_PARTITION_CANDIDATE_V1" or
        partition.get("status")!="CANDIDATE_NOT_ADMITTED" or
        partition.get("production_authority") is not False or
        partition.get("handoff_allowed") is not False):
        _fail("PARTITION_NOT_CANDIDATE")
    partition_sha=partition.get("candidate_sha256")
    if not isinstance(partition_sha,str) or not _SHA.fullmatch(partition_sha) or _sha({
        key:value for key,value in partition.items() if key!="candidate_sha256"
    })!=partition_sha:
        _fail("PARTITION_SHA_DRIFT")
    if not isinstance(budget_feedback,dict):
        _fail("BUDGET_FEEDBACK_MISSING")
    required={"schema_version","source_capability","budget_evaluation_ref",
              "partition_sha256","solution_id","context_status","source_mode",
              "material_ref_ids","jit_candidate_ref_ids","model_profile_ref"}
    if set(budget_feedback)!=required:
        _fail("BUDGET_FEEDBACK_FIELDS_INVALID")
    if (budget_feedback["schema_version"]!="PG07_CONTEXT_BUDGET_FEEDBACK_CANDIDATE_V1" or
        budget_feedback["source_capability"]!="CONTEXT_BUDGET_GOVERNANCE" or
        budget_feedback["source_mode"]!="CALLER_SUPPLIED_UNVERIFIED"):
        _fail("BUDGET_SOURCE_UNVERIFIED_CONTRACT_INVALID")
    if (not _TEXT(budget_feedback["budget_evaluation_ref"]) or
        not _TEXT(budget_feedback["model_profile_ref"]) or
        budget_feedback["partition_sha256"]!=partition_sha):
        _fail("BUDGET_BINDING_DRIFT")
    if budget_feedback["context_status"] not in ("GREEN","YELLOW","RED"):
        _fail("BUDGET_STATUS_INVALID")
    if (not _id_list(budget_feedback["material_ref_ids"]) or
        not _id_list(budget_feedback["jit_candidate_ref_ids"])):
        _fail("BUDGET_REF_SET_INVALID")
    if set(budget_feedback["jit_candidate_ref_ids"])-set(budget_feedback["material_ref_ids"]):
        _fail("JIT_REFERENCES_NOT_MATERIAL")
    sols=partition.get("solutions")
    if not isinstance(sols,list) or not sols or any(not isinstance(x,dict) for x in sols):
        _fail("SOLUTIONS_INVALID")
    sol_by_id={x.get("id"):x for x in sols}
    sid=budget_feedback["solution_id"]
    if not _TEXT(sid) or sid not in sol_by_id or len(sol_by_id)!=len(sols):
        _fail("BUDGET_SOLUTION_UNKNOWN")
    sol=sol_by_id[sid]
    reqs=sol.get("requirement_ids")
    accs=sol.get("acceptance_ids")
    atom_ids=sol.get("atom_ids")
    depends=sol.get("depends_on")
    if any(not _id_list(v) for v in (reqs,accs,atom_ids,depends)) or not atom_ids or not (reqs or accs):
        _fail("BUDGET_SOLUTION_OBLIGATIONS_INVALID")
    if budget_feedback["context_status"]=="RED":
        action="ASSESS_JIT_OR_REPARTITION"
        repair_required=True
        reason="PG07_RED_FAIL_CLOSED_NO_MATERIAL_TRUNCATION"
    elif budget_feedback["context_status"]=="YELLOW":
        action="NO_EXTRA_PREFETCH_RETRIEVE_JIT_ONLY"
        repair_required=False
        reason="PG07_YELLOW_REDUCE_OPTIONAL_CONTEXT_LOADING"
    else:
        action="CONTINUE_CONDITIONALLY_ON_AUTHENTIC_READBACK"
        repair_required=False
        reason="PG07_GREEN_CALLER_SUPPLIED_NOT_ATTESTED"
    result={
        "schema_version":"PG04_C6_BUDGET_REPAIR_EDGE_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "partition_sha256":partition_sha,
        "solution_id":sid,
        "source_capability":"CONTEXT_BUDGET_GOVERNANCE",
        "budget_evaluation_ref":budget_feedback["budget_evaluation_ref"],
        "model_profile_ref":budget_feedback["model_profile_ref"],
        "pg07_reported_context_status":budget_feedback["context_status"],
        "budget_readback_attested":False,
        "budget_engine_invoked":False,
        "budget_limits_inferred":False,
        "candidate_action":action,
        "repair_required":repair_required,
        "repair_edge":{"from":"PG-07_C3","to":"PG-04_C6",
                       "kind":"CONTROL_RETURN_NOT_SOLUTION_DAG_EDGE"},
        "preserved_solution":{
            "id":sid,"atom_ids":sorted(atom_ids),
            "requirement_ids":sorted(reqs),
            "acceptance_ids":sorted(accs),
            "depends_on":sorted(depends)
        },
        "material_ref_ids":sorted(budget_feedback["material_ref_ids"]),
        "jit_candidate_ref_ids":sorted(budget_feedback["jit_candidate_ref_ids"]),
        "material_truncation_allowed":False,
        "auto_repartition_allowed":False,
        "repartition_proven":False,
        "semantic_judge_executed":False,
        "pg07_budget_pass_claim_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "reason":reason,
        "next_gate":"PG07_CURRENT_BUDGET_READBACK_AND_GOVERNED_REPARTITION_REVIEW"
    }
    result["candidate_sha256"]=_sha(result)
    return result
