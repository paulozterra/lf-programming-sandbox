"""PG-07_C6: candidate batch evidence manifest for PG-12, never a sealed Worker receipt.

Binds C1-C5, task inputs, diff and applied standards with caller-supplied
references. Existing programacion worker receipt guards remain the sole
runtime authority. No receipts are issued or verified here.
"""
import hashlib
import json
import re
from copy import deepcopy

class BatchEvidenceBlocked(ValueError):
    pass

_SHA256=re.compile(r"^[0-9a-f]{64}$")
_SHA40=re.compile(r"^[0-9a-f]{40}$")
def _fail(v):raise BatchEvidenceBlocked(v)
def _hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _ref(v):return isinstance(v,str) and bool(v.strip())
def _frozen(v,schema):
    if not isinstance(v,dict) or v.get("schema_version")!=schema:_fail("PG07_C6_SOURCE_SCHEMA_INVALID")
    digest=v.get("candidate_sha256")
    if not isinstance(digest,str) or not _SHA256.fullmatch(digest) or digest!=_hash({k:x for k,x in v.items() if k!="candidate_sha256"}):
        _fail("PG07_C6_SOURCE_DIGEST_INVALID")
    return digest

def _index(items,collection):
    if not isinstance(items,list) or not items:_fail("PG07_C6_"+collection+"_MISSING")
    result={}
    for item in items:
        if not isinstance(item,dict) or not _ref(item.get("solution_id")) or item["solution_id"] in result:
            _fail("PG07_C6_"+collection+"_SOLUTION_IDS_INVALID")
        result[item["solution_id"]]=item
    return result

def prepare_pg07_c6(*,pg07_c1,pg07_c2,pg07_c3,pg07_c4,pg07_c5,worker_batch_evidence):
    sources={"pg07_c1":(pg07_c1,"PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1"),
             "pg07_c2":(pg07_c2,"PG07_C2_WORKER_TASK_BATCH_CANDIDATE_V1"),
             "pg07_c3":(pg07_c3,"PG07_C3_CONTEXT_PROJECTION_CANDIDATE_V1"),
             "pg07_c4":(pg07_c4,"PG07_C4_CONTRACT_FIRST_STANDARDS_CANDIDATE_V1"),
             "pg07_c5":(pg07_c5,"PG07_C5_ITERATION_GUARD_CANDIDATE_V1")}
    digest={key:_frozen(value,schema) for key,(value,schema) in sources.items()}
    expected=[("pg07_c2","source_pg07_c1_sha256","pg07_c1"),
              ("pg07_c3","source_pg07_c1_sha256","pg07_c1"),
              ("pg07_c3","source_pg07_c2_sha256","pg07_c2"),
              ("pg07_c4","source_pg07_c1_sha256","pg07_c1"),
              ("pg07_c4","source_pg07_c2_sha256","pg07_c2"),
              ("pg07_c4","source_pg07_c3_sha256","pg07_c3"),
              ("pg07_c5","source_pg07_c2_sha256","pg07_c2"),
              ("pg07_c5","source_pg07_c3_sha256","pg07_c3"),
              ("pg07_c5","source_pg07_c4_sha256","pg07_c4")]
    if any(sources[k][0].get(field)!=digest[up] for k,field,up in expected):
        _fail("PG07_C6_SOURCE_CHAIN_DRIFT")
    for obj,_ in sources.values():
        if (obj.get("production_authority") is not False or
            obj.get("handoff_allowed") is not False or
            obj.get("dispatch_allowed") is not False or
            obj.get("worker_invoked") is not False):
            _fail("PG07_C6_PREMATURE_WORKER_AUTHORITY")
    c2=_index(pg07_c2.get("worker_payloads"),"C2_TASKS")
    c4=_index(pg07_c4.get("solution_plans"),"C4_RULES")
    c5=_index(pg07_c5.get("solutions"),"C5_ITERATIONS")
    c3=_index(pg07_c3.get("solutions"),"C3_BUDGET")
    if not (set(c2)==set(c3)==set(c4)==set(c5)):
        _fail("PG07_C6_SOLUTION_SET_DRIFT")
    if not isinstance(worker_batch_evidence,list) or len(worker_batch_evidence)!=len(c2):
        _fail("PG07_C6_BATCH_EVIDENCE_INCOMPLETE")
    evidence=_index(worker_batch_evidence,"WORKER_EVIDENCE")
    if set(evidence)!=set(c2):_fail("PG07_C6_EVIDENCE_SOLUTION_DRIFT")
    target=pg07_c1.get("target_binding")
    run=pg07_c1.get("run_binding")
    if not isinstance(target,dict) or not isinstance(run,dict):_fail("PG07_C6_TARGET_RUN_MISSING")
    if not _ref(target.get("repo_full_name")) or not isinstance(target.get("base_head_sha"),str) or not _SHA40.fullmatch(target["base_head_sha"]):
        _fail("PG07_C6_TARGET_INVALID")
    entries=[]
    all_warnings=[]
    for sid in sorted(c2):
        row=evidence[sid]
        if set(row)!={"solution_id","batch_id","execution_ref","context_pack_ref",
                     "candidate_head_sha","diff_ref","diff_sha256","changed_paths",
                     "input_refs","applied_rule_ids","formatter_receipt_refs",
                     "worker_receipt_ref","worker_receipt_sha256","provider_usage_receipt_refs"}:
            _fail("PG07_C6_EVIDENCE_SHAPE_INVALID")
        if (not _ref(row["batch_id"]) or not _ref(row["execution_ref"]) or not _ref(row["context_pack_ref"])
            or not _ref(row["diff_ref"]) or not _ref(row["worker_receipt_ref"])
            or not isinstance(row["candidate_head_sha"],str) or not _SHA40.fullmatch(row["candidate_head_sha"])
            or any(not isinstance(row[k],str) or not _SHA256.fullmatch(row[k]) for k in ("diff_sha256","worker_receipt_sha256"))):
            _fail("PG07_C6_EVIDENCE_REFS_INVALID")
        for field in ("changed_paths","input_refs","applied_rule_ids","formatter_receipt_refs","provider_usage_receipt_refs"):
            seq=row[field]
            if not isinstance(seq,list) or any(not _ref(x) for x in seq) or len(seq)!=len(set(seq)):
                _fail("PG07_C6_"+field.upper()+"_INVALID")
        if not row["input_refs"] or not row["changed_paths"]:
            _fail("PG07_C6_EMPTY_INPUT_OR_DIFF")
        # The supplied list of applied STD/Skills must not claim rules outside
        # the candidate C4 catalog; runtime proof of actual application is absent.
        known={r["rule_id"] for r in c4[sid].get("required_rules",[]) if isinstance(r,dict) and _ref(r.get("rule_id"))}
        if not known or not set(row["applied_rule_ids"]).issubset(known):
            _fail("PG07_C6_APPLIED_RULES_OUTSIDE_CATALOG")
        task_sha=c2[sid].get("worker_task_spec_sha256")
        if not isinstance(task_sha,str) or not _SHA256.fullmatch(task_sha):
            _fail("PG07_C6_TASK_SPEC_DIGEST_MISSING")
        problems=[]
        if c3[sid].get("diagnostic_status")=="BLOCK_CONTEXT_BUDGET":
            problems.append("CONTEXT_BUDGET_BLOCKED")
        if c4[sid].get("diagnostic_status")=="BLOCK_CONTEXT_BUDGET":
            problems.append("POLICY_CONTEXT_BLOCKED")
        if c5[sid].get("diagnostic_status")=="BLOCK_ROUTE_PG10":
            problems.append("ITERATION_REQUIRES_PG10")
        if not row["formatter_receipt_refs"]:
            problems.append("FORMATTER_RECEIPTS_MISSING")
        if not row["provider_usage_receipt_refs"]:
            problems.append("PROVIDER_USAGE_RECEIPTS_MISSING")
        if not row["applied_rule_ids"]:
            problems.append("APPLIED_RULES_MISSING")
        all_warnings.extend({"solution_id":sid,"reason":reason} for reason in problems)
        entries.append({
            "solution_id":sid,
            "batch_id":row["batch_id"],
            "agent_task_id":c2[sid].get("agent_task_id"),
            "worker_task_spec_sha256":task_sha,
            "worker_spec_ref":c2[sid].get("worker_task_spec_source_ref"),
            "execution_ref":row["execution_ref"],
            "context_pack_ref":row["context_pack_ref"],
            "base_head_sha":target["base_head_sha"],
            "candidate_head_sha_reported":row["candidate_head_sha"],
            "diff_ref":row["diff_ref"],
            "diff_sha256_reported":row["diff_sha256"],
            "changed_paths_reported":sorted(row["changed_paths"]),
            "input_refs_reported":sorted(row["input_refs"]),
            "required_rule_ids":sorted(known),
            "applied_rule_ids_reported":sorted(row["applied_rule_ids"]),
            "formatter_receipt_refs_reported":sorted(row["formatter_receipt_refs"]),
            "worker_receipt_ref_reported":row["worker_receipt_ref"],
            "worker_receipt_sha256_reported":row["worker_receipt_sha256"],
            "provider_usage_receipt_refs_reported":sorted(row["provider_usage_receipt_refs"]),
            "blocking_diagnostics":problems,
            "diff_readback_verified":False,
            "worker_receipt_verified":False,
            "formatter_receipts_verified":False,
            "usage_receipts_verified":False,
            "pg12_evidence_admitted":False})
    result={
        "schema_version":"PG07_C6_BATCH_EVIDENCE_MANIFEST_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "upstream_source_digests":digest,
        "target_repo":target["repo_full_name"],
        "base_head_sha":target["base_head_sha"],
        "run_ref":run.get("run_ref"),
        "worker_batch_evidence_input_sha256":_hash(worker_batch_evidence),
        "batches":entries,
        "blocking_diagnostics":all_warnings,
        "existing_receipt_type":"VERIFIED_WORKER_RECEIPT",
        "existing_receipt_source_system":"PROGRAMMING_AGENT_WORKER",
        "receipt_guard_ref":"programacion.fn_guard_evidence()",
        "receipt_guard_authority_executed":False,
        "receipt_sealed":False,
        "receipt_digest_authenticated":False,
        "worker_invoked":False,
        "pg12_admitted":False,
        "dispatch_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"EXACT_WORKER_RECEIPT_GUARD_AND_PG12_MANIFEST_CURRENT_READBACK"
    }
    result["candidate_sha256"]=_hash(result)
    return result
