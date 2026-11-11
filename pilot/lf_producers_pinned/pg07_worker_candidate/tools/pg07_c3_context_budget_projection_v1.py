"""PG-07_C3: bounded per-task context reference projection, source-only.

No document fetching, summarization, truncation, model invocation, or second
context enforcement engine. Runtime must recheck with CONTEXT_BUDGET_GOVERNANCE
using active model/profile limits and actual compiled context.
"""
import hashlib
import json
import re

class ContextProjectionBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")
_KINDS={"BACKEND_RULE","FRONTEND_RULE","DATABASE_RULE","STD","SKILL","CONTRACT",
        "REQUIREMENT","ACCEPTANCE","TARGET_FILE","OTHER_MATERIAL"}
_STABLE={"REGULATIONS","TECHNICAL_PROFILE","SOURCE_PACKAGE"}
def _fail(code):raise ContextProjectionBlocked(code)
def _hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _ref(v):return isinstance(v,str) and bool(v.strip())
def _frozen(v,schema):
    if not isinstance(v,dict) or v.get("schema_version")!=schema:_fail("PG07_C3_SOURCE_SCHEMA_INVALID")
    h=v.get("candidate_sha256")
    if not isinstance(h,str) or not _SHA.fullmatch(h) or h!=_hash({k:x for k,x in v.items() if k!="candidate_sha256"}):
        _fail("PG07_C3_SOURCE_DIGEST_DRIFT")
    return h

def prepare_pg07_c3(*,pg07_c1,pg07_c2,model_context_profile,task_context_selections):
    c1_sha=_frozen(pg07_c1,"PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1")
    c2_sha=_frozen(pg07_c2,"PG07_C2_WORKER_TASK_BATCH_CANDIDATE_V1")
    if (pg07_c1.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg07_c2.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg07_c2.get("source_pg07_c1_sha256")!=c1_sha
        or pg07_c1.get("dispatch_allowed") is not False
        or pg07_c2.get("dispatch_allowed") is not False
        or pg07_c1.get("worker_invoked") is not False
        or pg07_c2.get("worker_invoked") is not False
        or pg07_c1.get("production_authority") is not False
        or pg07_c2.get("production_authority") is not False
        or pg07_c2.get("handoff_allowed") is not False):
        _fail("PG07_C3_SOURCE_AUTHORITY_INVALID")
    run=pg07_c1.get("run_binding")
    if not isinstance(run,dict):_fail("PG07_C3_RUN_MISSING")
    if not isinstance(model_context_profile,dict) or set(model_context_profile)!={
        "profile_ref","provider","model_id","context_window_tokens","reserved_output_tokens",
        "reserved_system_tokens","safety_margin_tokens","token_estimator_ref",
        "budget_policy_ref","budget_capability"}:
        _fail("PG07_C3_MODEL_PROFILE_INVALID")
    profile=model_context_profile
    if (profile["profile_ref"]!=run.get("model_profile_ref")
        or profile["provider"]!=run.get("provider")
        or profile["model_id"]!=run.get("model_id")
        or profile["budget_capability"]!="CONTEXT_BUDGET_GOVERNANCE"
        or not _ref(profile["token_estimator_ref"]) or not _ref(profile["budget_policy_ref"])):
        _fail("PG07_C3_MODEL_PROFILE_BINDING_DRIFT")
    for k in ("context_window_tokens","reserved_output_tokens","reserved_system_tokens","safety_margin_tokens"):
        if not isinstance(profile[k],int) or isinstance(profile[k],bool) or profile[k]<0:
            _fail("PG07_C3_MODEL_TOKEN_LIMIT_INVALID")
    if profile["context_window_tokens"]<=0 or profile["reserved_output_tokens"]<=0:
        _fail("PG07_C3_MODEL_TOKEN_LIMIT_INVALID")
    available=(profile["context_window_tokens"]-profile["reserved_output_tokens"]
               -profile["reserved_system_tokens"]-profile["safety_margin_tokens"])
    if available<=0:_fail("PG07_C3_CONTEXT_WINDOW_EXHAUSTED")
    payloads=pg07_c2.get("worker_payloads")
    if not isinstance(payloads,list) or not payloads:_fail("PG07_C3_WORKER_PAYLOADS_MISSING")
    specs={}
    for row in payloads:
        if not isinstance(row,dict) or not _ref(row.get("solution_id")) or row["solution_id"] in specs:
            _fail("PG07_C3_SOLUTION_BINDING_INVALID")
        spec=row.get("worker_visible_task_spec")
        if not isinstance(spec,dict) or not isinstance(spec.get("max_context_bytes"),int) or spec["max_context_bytes"]<=0:
            _fail("PG07_C3_SPEC_CONTEXT_LIMIT_INVALID")
        specs[row["solution_id"]]=spec
    if not isinstance(task_context_selections,list) or len(task_context_selections)!=len(specs):
        _fail("PG07_C3_SELECTION_SET_INCOMPLETE")
    selections={}
    for row in task_context_selections:
        if not isinstance(row,dict) or set(row)!={
            "solution_id","mandatory_ref_ids","reference_catalog","stable_cache_refs",
            "token_estimate_ref","estimated_static_tokens","estimated_dynamic_tokens",
            "estimated_jit_tokens","estimated_context_bytes"}:
            _fail("PG07_C3_SELECTION_SHAPE_INVALID")
        sid=row["solution_id"]
        if sid not in specs or sid in selections:_fail("PG07_C3_SELECTION_OWNER_INVALID")
        if (not isinstance(row["mandatory_ref_ids"],list) or not row["mandatory_ref_ids"]
            or any(not _ref(x) for x in row["mandatory_ref_ids"])
            or len(row["mandatory_ref_ids"])!=len(set(row["mandatory_ref_ids"]))):
            _fail("PG07_C3_MANDATORY_REFS_INVALID")
        if not _ref(row["token_estimate_ref"]):_fail("PG07_C3_TOKEN_ESTIMATE_REF_MISSING")
        for k in ("estimated_static_tokens","estimated_dynamic_tokens","estimated_jit_tokens","estimated_context_bytes"):
            if not isinstance(row[k],int) or isinstance(row[k],bool) or row[k]<0:
                _fail("PG07_C3_ESTIMATE_INVALID")
        if row["estimated_context_bytes"]>specs[sid]["max_context_bytes"]:
            # Do not attempt to shrink material or bypass worker-spec hard bounds.
            pass
        catalog=row["reference_catalog"]
        if not isinstance(catalog,list) or not catalog:_fail("PG07_C3_REFERENCE_CATALOG_MISSING")
        found={}
        for item in catalog:
            if not isinstance(item,dict) or set(item)!={
                "ref_id","source_ref","source_sha256","kind","material",
                "delivery","estimated_tokens","estimated_bytes","role"}:
                _fail("PG07_C3_REFERENCE_SHAPE_INVALID")
            rid=item["ref_id"]
            if rid in found or not _ref(rid) or not _ref(item["source_ref"]):
                _fail("PG07_C3_REFERENCE_DUPLICATE_OR_MISSING")
            if not isinstance(item["source_sha256"],str) or not _SHA.fullmatch(item["source_sha256"]):
                _fail("PG07_C3_REFERENCE_SOURCE_SHA_INVALID")
            if (item["kind"] not in _KINDS or not isinstance(item["material"],bool)
                or item["delivery"] not in ("EAGER","JIT")
                or item["role"] not in ("REQUIRED","OPTIONAL")
                or not isinstance(item["estimated_tokens"],int) or isinstance(item["estimated_tokens"],bool)
                or item["estimated_tokens"]<0 or not isinstance(item["estimated_bytes"],int)
                or isinstance(item["estimated_bytes"],bool) or item["estimated_bytes"]<0):
                _fail("PG07_C3_REFERENCE_CLASSIFICATION_INVALID")
            found[rid]=item
        mandatory=set(row["mandatory_ref_ids"])
        if not mandatory.issubset(found):_fail("PG07_C3_MANDATORY_REFERENCE_MISSING")
        if any(not found[r]["material"] or found[r]["role"]!="REQUIRED" for r in mandatory):
            _fail("PG07_C3_MANDATORY_REFERENCE_DOWNGRADED")
        if any(i["material"] and i["role"]=="REQUIRED" and rid not in mandatory for rid,i in found.items()):
            _fail("PG07_C3_REQUIRED_MATERIAL_OMITTED")
        cache=row["stable_cache_refs"]
        if not isinstance(cache,list) or len(cache)!=len(set(x.get("ref_id") for x in cache if isinstance(x,dict))):
            _fail("PG07_C3_CACHE_ENTRIES_INVALID")
        for item in cache:
            if not isinstance(item,dict) or set(item)!={"ref_id","stable_role","cache_key_ref"}:
                _fail("PG07_C3_CACHE_ENTRY_INVALID")
            if (item["ref_id"] not in found or item["stable_role"] not in _STABLE
                or found[item["ref_id"]]["delivery"]!="EAGER" or not _ref(item["cache_key_ref"])):
                _fail("PG07_C3_CACHE_BINDING_INVALID")
        eager=sum(x["estimated_tokens"] for x in found.values() if x["delivery"]=="EAGER")
        jit=sum(x["estimated_tokens"] for x in found.values() if x["delivery"]=="JIT")
        if (jit!=row["estimated_jit_tokens"]
            or eager!=row["estimated_static_tokens"]+row["estimated_dynamic_tokens"]):
            _fail("PG07_C3_TOKEN_PROJECTION_INCONSISTENT")
        selections[sid]=row
    outputs=[]
    for sid in sorted(specs):
        row=selections[sid]
        spec=specs[sid]
        eager=row["estimated_static_tokens"]+row["estimated_dynamic_tokens"]
        total=eager+row["estimated_jit_tokens"]
        estimated_bytes=row["estimated_context_bytes"]
        exceeds_model=total>available
        exceeds_task=estimated_bytes>spec["max_context_bytes"]
        blocked=exceeds_model or exceeds_task
        plan={
            "solution_id":sid,
            "required_ref_ids":sorted(row["mandatory_ref_ids"]),
            "eager_ref_ids":sorted(x["ref_id"] for x in row["reference_catalog"] if x["delivery"]=="EAGER"),
            "jit_ref_ids":sorted(x["ref_id"] for x in row["reference_catalog"] if x["delivery"]=="JIT"),
            "stable_cache_refs":row["stable_cache_refs"],
            "estimated_eager_tokens":eager,
            "estimated_jit_tokens":row["estimated_jit_tokens"],
            "estimated_worst_case_tokens":total,
            "available_model_input_tokens":available,
            "estimated_context_bytes":estimated_bytes,
            "max_worker_context_bytes":spec["max_context_bytes"],
            "diagnostic_status":"BLOCK_CONTEXT_BUDGET" if blocked else "ESTIMATE_WITHIN_DECLARED_BOUNDS_UNVERIFIED",
            "blocking_reasons":(["MODEL_PROFILE_WINDOW_EXCEEDED"] if exceeds_model else [])
                             +(["WORKER_SPEC_CONTEXT_BYTES_EXCEEDED"] if exceeds_task else []),
            "recommended_action":("RETURN_TO_PG04_FOR_REPARTITION_OR_EXACT_JIT_FETCH"
                                   if blocked else "GOVERNED_CONTEXT_ADMISSION_READBACK_REQUIRED"),
            "no_material_truncation":True,
            "model_context_admitted":False,
            "dispatch_allowed":False
        }
        outputs.append(plan)
    result={
        "schema_version":"PG07_C3_CONTEXT_PROJECTION_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg07_c1_sha256":c1_sha,
        "source_pg07_c2_sha256":c2_sha,
        "model_profile_sha256":_hash(profile),
        "model_profile_ref":profile["profile_ref"],
        "token_estimator_ref":profile["token_estimator_ref"],
        "budget_policy_ref":profile["budget_policy_ref"],
        "budget_capability":"CONTEXT_BUDGET_GOVERNANCE",
        "model_input_token_budget":available,
        "solutions":outputs,
        "reference_sources_verified":False,
        "token_estimates_authenticity_verified":False,
        "active_policy_readback_verified":False,
        "router_context_admission_executed":False,
        "context_budget_ledger_receipts_verified":False,
        "full_repo_prefetch_allowed":False,
        "full_spec_prefetch_allowed":False,
        "material_truncation_allowed":False,
        "worker_invoked":False,
        "pg07_admitted":False,
        "dispatch_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"ACTIVE_CONTEXT_BUDGET_GOVERNANCE_POLICY_COMPILATION_AND_RECEIPT_READBACK"
    }
    result["candidate_sha256"]=_hash(result)
    return result
