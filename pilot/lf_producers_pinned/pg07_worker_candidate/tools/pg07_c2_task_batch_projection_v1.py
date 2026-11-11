"""PG-07_C2: source-only worker task projection, no execution or oracle leak.

Consume the *visible* v2 worker spec from the existing PG function.
Opaque hidden-oracle references are retained solely in a verifier envelope.
No new worker, no SQL invocation, no runtime dispatch, no PASS authority.
"""
import hashlib
import json
import re
from copy import deepcopy

class TaskProjectionBlocked(ValueError):
    pass

SHA256=re.compile(r"^[0-9a-f]{64}$")
SHA40=re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN={"hidden_oracle_ref","hidden_oracle_sha256","oracle_envelope","readiness","hidden_oracle","oracle_payload"}

def _fail(code):raise TaskProjectionBlocked(code)
def _sha(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _nonempty(v):return isinstance(v,str) and bool(v.strip())
def _frozen(obj,schema):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema:_fail("PG07_C2_SOURCE_SCHEMA_INVALID")
    digest=obj.get("candidate_sha256")
    if not isinstance(digest,str) or not SHA256.fullmatch(digest) or digest!=_sha({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        _fail("PG07_C2_SOURCE_DIGEST_DRIFT")
    return digest

def _oracle_free(obj):
    if isinstance(obj,dict):
        return not any(k in FORBIDDEN or not _oracle_free(v) for k,v in obj.items())
    if isinstance(obj,list):return all(_oracle_free(x) for x in obj)
    return True

def _unique(v,allow_empty=False):
    return isinstance(v,list) and (allow_empty or bool(v)) and all(_nonempty(x) for x in v) and len(set(v))==len(v)

def prepare_pg07_c2(*,pg07_c1,worker_spec_projections,verifier_oracle_bindings):
    c1_sha=_frozen(pg07_c1,"PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1")
    if (pg07_c1.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg07_c1.get("worker_spec_entrypoint")!="programacion.fn_agent_task_worker_spec(bigint,text,text)"
        or pg07_c1.get("worker_spec_oracle_isolation_required") is not True
        or pg07_c1.get("dispatch_allowed") is not False or pg07_c1.get("worker_invoked") is not False
        or pg07_c1.get("pg07_admitted") is not False or pg07_c1.get("write_allowed") is not False
        or pg07_c1.get("production_authority") is not False or pg07_c1.get("handoff_allowed") is not False):
        _fail("PG07_C2_SOURCE_AUTHORITY_INVALID")
    inputs=pg07_c1.get("task_bindings")
    if not isinstance(inputs,list) or not inputs:_fail("PG07_C2_TASK_BINDINGS_MISSING")
    bound={}
    for item in inputs:
        if (not isinstance(item,dict) or not _nonempty(item.get("solution_id"))
            or item["solution_id"] in bound or not isinstance(item.get("agent_task_id"),int)
            or isinstance(item.get("agent_task_id"),bool) or item["agent_task_id"]<=0
            or item.get("worker_invoked") is not False or item.get("worker_spec_executed") is not False):
            _fail("PG07_C2_TASK_BINDINGS_INVALID")
        bound[item["solution_id"]]=item
    if not isinstance(worker_spec_projections,list) or len(worker_spec_projections)!=len(bound):
        _fail("PG07_C2_SPEC_PROJECTIONS_INCOMPLETE")
    if not isinstance(verifier_oracle_bindings,list) or len(verifier_oracle_bindings)!=len(bound):
        _fail("PG07_C2_ORACLE_BINDINGS_INCOMPLETE")
    by_solution={}
    for row in worker_spec_projections:
        if not isinstance(row,dict) or set(row)!={"solution_id","function_result_ref","worker_spec","source_snapshot_sha256"}:
            _fail("PG07_C2_SPEC_ENVELOPE_SHAPE_INVALID")
        sid=row["solution_id"]
        if sid not in bound or sid in by_solution or not _nonempty(row["function_result_ref"]):
            _fail("PG07_C2_SPEC_SOURCE_BINDING_INVALID")
        spec=row["worker_spec"]
        if not isinstance(spec,dict) or spec.get("schema_version")!=2 or not _oracle_free(spec):
            _fail("PG07_C2_ORACLE_BOUNDARY_VIOLATION")
        required=("task_id","objective","expected_change","human_story","functional_contract","scope",
                  "cases","dependency_resolution","dependency_task_ids","required_tests",
                  "required_evidence","blocked_if","base_head_sha","source_snapshot_sha256",
                  "context_path_patterns","write_path_patterns","protected_path_patterns",
                  "files_expected","platform_refs","interface_refs","acceptance_commands",
                  "max_attempts","max_patch_bytes","max_changed_files","max_context_bytes","allow_deletions")
        if any(k not in spec for k in required):_fail("PG07_C2_WORKER_SPEC_INCOMPLETE")
        if (not _nonempty(spec["task_id"]) or not _nonempty(spec["objective"])
            or not isinstance(spec["base_head_sha"],str) or not SHA40.fullmatch(spec["base_head_sha"])
            or not isinstance(spec["source_snapshot_sha256"],str)
            or not SHA256.fullmatch(spec["source_snapshot_sha256"])
            or spec["source_snapshot_sha256"]!=row["source_snapshot_sha256"]
            or spec["source_snapshot_sha256"]!=bound[sid]["source_snapshot_sha256"]):
            _fail("PG07_C2_SPEC_SOURCE_IDENTITY_DRIFT")
        target=pg07_c1.get("target_binding")
        if not isinstance(target,dict) or spec["base_head_sha"]!=target.get("base_head_sha"):
            _fail("PG07_C2_BASE_HEAD_DRIFT")
        if (not isinstance(spec["scope"],dict) or any(k not in spec["scope"] for k in ("in_scope","out_of_scope","must_not_change"))
            or not isinstance(spec["functional_contract"],dict)
            or not isinstance(spec["acceptance_commands"],list) or not spec["acceptance_commands"]
            or not isinstance(spec["write_path_patterns"],list)
            or not isinstance(spec["protected_path_patterns"],list)
            or not isinstance(spec["context_path_patterns"],list)
            or not isinstance(spec["required_tests"],(list,dict))):
            _fail("PG07_C2_SPEC_MATERIAL_FIELDS_INVALID")
        if not isinstance(spec["allow_deletions"],bool):
            _fail("PG07_C2_SPEC_DELETION_POLICY_INVALID")
        for k in ("max_attempts","max_patch_bytes","max_changed_files","max_context_bytes"):
            if not isinstance(spec[k],int) or isinstance(spec[k],bool) or spec[k]<=0:
                _fail("PG07_C2_SPEC_LIMIT_INVALID")
        by_solution[sid]=row
    oracle={}
    for row in verifier_oracle_bindings:
        if not isinstance(row,dict) or set(row)!={"solution_id","verifier_only_ref","oracle_subject_sha256","access_policy"}:
            _fail("PG07_C2_ORACLE_ENVELOPE_INVALID")
        sid=row["solution_id"]
        if (sid not in bound or sid in oracle or not _nonempty(row["verifier_only_ref"])
            or row["access_policy"]!="VERIFIER_ONLY"
            or not isinstance(row["oracle_subject_sha256"],str)
            or not SHA256.fullmatch(row["oracle_subject_sha256"])):
            _fail("PG07_C2_ORACLE_REFERENCE_INVALID")
        oracle[sid]=row
    result_rows=[]
    verifier_rows=[]
    for sid in sorted(bound):
        row=by_solution[sid]
        spec=row["worker_spec"]
        result_rows.append({
            "solution_id":sid,
            "agent_task_id":bound[sid]["agent_task_id"],
            "worker_task_spec_source_ref":row["function_result_ref"],
            "worker_task_spec_sha256":_sha(spec),
            "worker_visible_task_spec":deepcopy(spec),
            "worker_spec_executed_by_this_component":False,
            "worker_dispatch_allowed":False,
            "oracle_in_worker_payload":False,
            "spec_currentness_verified":False
        })
        verifier_rows.append({
            "solution_id":sid,
            "verifier_only_ref":oracle[sid]["verifier_only_ref"],
            "oracle_subject_sha256":oracle[sid]["oracle_subject_sha256"],
            "access_policy":"VERIFIER_ONLY",
            "oracle_read_by_worker":False,
            "oracle_subject_verified":False
        })
    result={
        "schema_version":"PG07_C2_WORKER_TASK_BATCH_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg07_c1_sha256":c1_sha,
        "source_pg05_exit_sha256":pg07_c1.get("source_pg05_exit_sha256"),
        "run_ref":pg07_c1.get("run_binding",{}).get("run_ref"),
        "worker_spec_entrypoint":"programacion.fn_agent_task_worker_spec(bigint,text,text)",
        "worker_payloads":result_rows,
        "verifier_only_oracle_envelopes":verifier_rows,
        "verifier_envelopes_worker_delivery_forbidden":True,
        "worker_spec_runtime_readback_verified":False,
        "oracle_access_control_verified":False,
        "acceptance_commands_executed":False,
        "worker_invoked":False,
        "pg07_admitted":False,
        "dispatch_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"PG07_C3_CONTEXT_BUDGET_PROJECTION_AND_GOVERNED_WORKER_SPEC_READBACK"
    }
    result["candidate_sha256"]=_sha(result)
    return result
