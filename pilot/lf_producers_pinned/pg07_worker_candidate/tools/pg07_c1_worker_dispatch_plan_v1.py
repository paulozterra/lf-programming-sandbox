"""PG-07_C1 non-executable Worker v0.8 binding and token-accounting plan.

References existing fn_agent_task_worker_spec and existing lane executor.
No invocation, dispatch, branch creation, token usage fabrication, receipt
attestation or new worker runtime. Actual usage is recorded by the executor,
never by this plan.
"""
import hashlib
import json
import re
from copy import deepcopy

class PG07WorkerPlanBlocked(ValueError):
    pass

SHA256=re.compile(r"^[0-9a-f]{64}$")
GITSHA=re.compile(r"^[0-9a-f]{40}$")
MONEY=re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,9})?$")

def _fail(code):raise PG07WorkerPlanBlocked(code)
def _hash(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _ref(x):return isinstance(x,str) and bool(x.strip())
def _frozen(obj,schema,digest_key="candidate_sha256"):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema:_fail("PG07_C1_SCHEMA_DRIFT")
    sig=obj.get(digest_key)
    if not isinstance(sig,str) or not SHA256.fullmatch(sig) or sig!=_hash({k:v for k,v in obj.items() if k!=digest_key}):
        _fail("PG07_C1_DIGEST_DRIFT")
    return sig

def _ids(rows):
    if not isinstance(rows,list) or not rows:_fail("PG07_C1_SOLUTIONS_MISSING")
    ids=[r.get("solution_id") if isinstance(r,dict) else None for r in rows]
    if any(not _ref(x) for x in ids) or len(set(ids))!=len(ids):_fail("PG07_C1_SOLUTION_IDS_INVALID")
    return ids

def prepare_pg07_c1(*,pg05_exit,pg06_c5,run_binding,worker_task_bindings):
    """Build a source-only binding proposal, not an executable task or PASS."""
    pg05_sha=_frozen(pg05_exit,"PG05_TO_PG06_EXIT_CANDIDATE_V1")
    pg06_sha=_frozen(pg06_c5,"PG06_C5_INDEPENDENT_REVIEW_REQUEST_CANDIDATE_V1","request_sha256")
    if (pg05_exit.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg05_exit.get("pg05_admitted") is not False or
        pg05_exit.get("pg06_admitted") is not False or
        pg05_exit.get("write_allowed") is not False or
        pg05_exit.get("handoff_allowed") is not False or
        pg05_exit.get("production_authority") is not False or
        pg06_c5.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg06_c5.get("pg06_admitted") is not False or
        pg06_c5.get("pg07_dispatch_allowed") is not False or
        pg06_c5.get("worker_invoked") is not False or
        pg06_c5.get("review_execution_allowed") is not False or
        pg06_c5.get("ledger_subject_receipt_verified") is not False or
        pg06_c5.get("subject_receipt_id") is not None or
        pg06_c5.get("production_authority") is not False or
        pg06_c5.get("handoff_allowed") is not False):
        _fail("PG07_C1_UPSTREAM_NOT_UNTRUSTED_CANDIDATE")
    subject=pg06_c5.get("subject")
    if (not isinstance(subject,dict) or
        pg06_c5.get("subject_sha256")!=_hash(subject) or
        subject.get("upstream_digests",{}).get("pg05_exit")!=pg05_sha):
        _fail("PG07_C1_PG06_SUBJECT_DRIFT")
    ids=sorted(_ids(pg05_exit.get("solutions")))
    if subject.get("solution_ids")!=ids:
        _fail("PG07_C1_SOLUTION_ID_DRIFT")
    if not isinstance(run_binding,dict) or set(run_binding)!={
        "run_ref","provider","model_id","model_profile_ref",
        "pricing_ref","pricing_currency","input_price_per_million",
        "output_price_per_million","cached_input_price_per_million",
        "lane_executor_ref","worker_contract_ref","worker_version"}:
        _fail("PG07_C1_RUN_BINDING_INVALID")
    binding=run_binding
    for k in ("run_ref","provider","model_id","model_profile_ref","pricing_ref","pricing_currency","lane_executor_ref","worker_contract_ref"):
        if not _ref(binding[k]):_fail("PG07_C1_RUN_IDENTITY_MISSING")
    if binding["worker_version"]!="0.8":_fail("PG07_C1_WORKER_VERSION_DRIFT")
    for k in ("input_price_per_million","output_price_per_million","cached_input_price_per_million"):
        if not isinstance(binding[k],str) or not MONEY.fullmatch(binding[k]):
            _fail("PG07_C1_PRICING_VALUE_INVALID")
    if not isinstance(worker_task_bindings,list) or len(worker_task_bindings)!=len(ids):
        _fail("PG07_C1_TASK_BINDING_COVERAGE_INCOMPLETE")
    tasks={}
    for row in worker_task_bindings:
        if not isinstance(row,dict) or set(row)!={
            "solution_id","agent_task_id","task_binding_ref","base_head_sha",
            "source_snapshot_sha256","worker_spec_ref","task_execution_authority_ref"}:
            _fail("PG07_C1_TASK_BINDING_SCHEMA_INVALID")
        sid=row["solution_id"]
        if sid not in ids or sid in tasks or not isinstance(row["agent_task_id"],int) or isinstance(row["agent_task_id"],bool) or row["agent_task_id"]<=0:
            _fail("PG07_C1_TASK_ID_INVALID")
        if any(not _ref(row[k]) for k in ("task_binding_ref","worker_spec_ref","task_execution_authority_ref")):
            _fail("PG07_C1_TASK_REFERENCES_MISSING")
        if (not isinstance(row["base_head_sha"],str) or not GITSHA.fullmatch(row["base_head_sha"])
            or not isinstance(row["source_snapshot_sha256"],str)
            or not SHA256.fullmatch(row["source_snapshot_sha256"])):
            _fail("PG07_C1_TASK_SOURCE_IDENTITY_INVALID")
        target=pg05_exit.get("target_binding")
        if (not isinstance(target,dict) or
            not isinstance(target.get("base_head_sha"),str) or
            row["base_head_sha"]!=target["base_head_sha"] or
            not _ref(target.get("repo_full_name"))):
            _fail("PG07_C1_TARGET_BINDING_UNRESOLVED")
        tasks[sid]=row
    result={
        "schema_version":"PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg05_exit_sha256":pg05_sha,
        "source_pg06_review_request_sha256":pg06_sha,
        "pg06_assurance_subject_sha256":pg06_c5["subject_sha256"],
        "target_binding":deepcopy(pg05_exit["target_binding"]),
        "run_binding":deepcopy(binding),
        "worker_spec_entrypoint":"programacion.fn_agent_task_worker_spec(bigint,text,text)",
        "existing_execution_bundle_entrypoint":"programacion.fn_agent_task_execution_bundle(bigint,text,text)",
        "worker_spec_oracle_isolation_required":True,
        "worker_spec_readback_verified":False,
        "worker_version_source_verified":False,
        "lane_executor_integration_verified":False,
        "model_provider_identity_verified":False,
        "pricing_snapshot_verified":False,
        "task_bindings":[{
            "solution_id":sid,
            "agent_task_id":tasks[sid]["agent_task_id"],
            "task_binding_ref":tasks[sid]["task_binding_ref"],
            "worker_spec_ref":tasks[sid]["worker_spec_ref"],
            "source_snapshot_sha256":tasks[sid]["source_snapshot_sha256"],
            "task_execution_authority_ref":tasks[sid]["task_execution_authority_ref"],
            "worker_spec_executed":False,
            "worker_invoked":False
        } for sid in ids],
        "usage_receipt_schema":{
            "per_call_required_fields":[
                "run_ref","solution_id","agent_task_id","worker_call_ref",
                "provider","model_id","model_profile_ref","pricing_ref",
                "input_tokens","output_tokens","cached_input_tokens",
                "reported_cost","pricing_currency","usage_source_ref",
                "call_execution_receipt_ref"
            ],
            "token_counter_source":"RUNTIME_PROVIDER_USAGE_NOT_INFERRED",
            "cost_accounting":"RUNTIME_PRICE_SNAPSHOT_TIMES_PROVIDER_USAGE",
            "input_tokens_include_cached":"PROVIDER_CONTRACT_DEPENDENT_MUST_BE_EXPLICIT",
            "usage_observation_recorded":False,
            "cost_calculated":False,
            "usage_receipts_verified":False
        },
        "parallelism_policy":"REUSE_EXISTING_LANE_EXECUTOR_AND_PG05_LOCKS",
        "writer_locks_acquired":False,
        "pg06_admitted":False,
        "pg07_admitted":False,
        "worker_invoked":False,
        "dispatch_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "first_blocker":"PG06_ADMISSION_AND_REAL_WORKER_RUNTIME_BINDINGS_MISSING"
    }
    result["candidate_sha256"]=_hash(result)
    return result
