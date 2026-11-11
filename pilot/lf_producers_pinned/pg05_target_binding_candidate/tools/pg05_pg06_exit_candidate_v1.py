"""PG05 -> PG06 candidate boundary manifest; never an admitted handoff.

The document freezes C1-C5 source artifacts, preserves per-solution blocks
and exposes PG06 prerequisites. Does not reuse PG01 currentness as verified,
create branches, execute toolchains, inspect baseline, or reserve writers.
"""
import hashlib
import json
import re
from copy import deepcopy

class PG05ExitBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")

def _block(code):raise PG05ExitBlocked(code)

def _hash(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _frozen(x,schema):
    if not isinstance(x,dict) or x.get("schema_version")!=schema:
        _block("PG05_EXIT_SOURCE_SCHEMA_INVALID")
    sha=x.get("candidate_sha256")
    if not isinstance(sha,str) or not _SHA.fullmatch(sha) or sha!=_hash({k:v for k,v in x.items() if k!="candidate_sha256"}):
        _block("PG05_EXIT_SOURCE_HASH_DRIFT")
    return sha

def _ids(v):
    return isinstance(v,list) and bool(v) and all(isinstance(z,str) and bool(z.strip()) for z in v) and len(v)==len(set(v))

def assemble_pg05_pg06_candidate(*,pg04_exit,pg05_c1,pg05_c2,pg05_c3,pg05_c4,pg05_c5):
    sources={
        "pg04_exit":(pg04_exit,"PG04_TO_PG05_EXIT_CANDIDATE_V1"),
        "pg05_c1":(pg05_c1,"PG05_C1_TARGET_BINDING_PREFLIGHT_CANDIDATE_V1"),
        "pg05_c2":(pg05_c2,"PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1"),
        "pg05_c3":(pg05_c3,"PG05_C3_CONFLICT_LOCK_PLAN_CANDIDATE_V1"),
        "pg05_c4":(pg05_c4,"PG05_C4_WRITE_BOUNDARY_DIAGNOSTIC_CANDIDATE_V1")
    }
    digests={k:_frozen(obj,schema) for k,(obj,schema) in sources.items()}
    if not isinstance(pg05_c5,dict) or pg05_c5.get("schema_version")!="PG05_C5_INDEPENDENT_REVIEW_REQUEST_CANDIDATE_V1":
        _block("PG05_EXIT_C5_SCHEMA_INVALID")
    c5sha=pg05_c5.get("request_sha256")
    if not isinstance(c5sha,str) or not _SHA.fullmatch(c5sha) or c5sha!=_hash({k:v for k,v in pg05_c5.items() if k!="request_sha256"}):
        _block("PG05_EXIT_C5_HASH_DRIFT")
    expected={
        ("pg05_c1","source_pg04_exit_sha256"):digests["pg04_exit"],
        ("pg05_c2","source_pg04_exit_sha256"):digests["pg04_exit"],
        ("pg05_c2","source_pg05_c1_sha256"):digests["pg05_c1"],
        ("pg05_c3","source_pg04_exit_sha256"):digests["pg04_exit"],
        ("pg05_c3","source_pg05_c2_sha256"):digests["pg05_c2"],
        ("pg05_c4","source_pg04_exit_sha256"):digests["pg04_exit"],
        ("pg05_c4","source_pg05_c2_sha256"):digests["pg05_c2"],
        ("pg05_c4","source_pg05_c3_sha256"):digests["pg05_c3"]
    }
    if any(sources[name][0].get(field)!=expected_sha for (name,field),expected_sha in expected.items()):
        _block("PG05_EXIT_UPSTREAM_CHAIN_DRIFT")
    subject=pg05_c5.get("subject")
    if not isinstance(subject,dict) or subject.get("schema_version")!="PG05_C5_ASSURANCE_SUBJECT_CANDIDATE_V1":
        _block("PG05_EXIT_ASSURANCE_SUBJECT_INVALID")
    if pg05_c5.get("subject_sha256")!=_hash(subject):
        _block("PG05_EXIT_ASSURANCE_SUBJECT_DIGEST_DRIFT")
    if any(subject.get(k+"_sha256")!=v for k,v in digests.items()):
        _block("PG05_EXIT_ASSURANCE_CHAIN_DRIFT")
    if (pg05_c5.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_c5.get("subject_receipt_id") is not None
        or pg05_c5.get("reviewer_execution_id") is not None
        or pg05_c5.get("independent_review_executed") is not False
        or pg05_c5.get("ledger_subject_receipt_verified") is not False
        or pg05_c5.get("production_authority") is not False
        or pg05_c5.get("handoff_allowed") is not False):
        _block("PG05_EXIT_C5_NOT_UNTRUSTED")
    for k,(obj,_) in sources.items():
        if obj.get("production_authority") is not False or obj.get("handoff_allowed") is not False:
            _block("PG05_EXIT_UPSTREAM_AUTHORITY_INVALID")
    if (pg04_exit.get("pg04_admitted") is not False
        or pg05_c1.get("branch_created") is not False
        or pg05_c2.get("write_scope_authorized") is not False
        or pg05_c3.get("locks_acquired") is not False
        or pg05_c4.get("write_allowed") is not False):
        _block("PG05_EXIT_PREMATURE_AUTHORITY")
    original=pg04_exit.get("solutions")
    scopes=pg05_c2.get("solution_scopes")
    locks=pg05_c3.get("lock_requests")
    reports=pg05_c4.get("solution_reports")
    if not all(isinstance(x,list) for x in (original,scopes,locks,reports)):
        _block("PG05_EXIT_SOLUTIONS_INVALID")
    def index(rows):
        ids=[r.get("solution_id") if isinstance(r,dict) else None for r in rows]
        if not _ids(ids):_block("PG05_EXIT_SOLUTION_IDS_INVALID")
        return {r["solution_id"]:r for r in rows}
    om,sm,lm,rm=[index(x) for x in (original,scopes,locks,reports)]
    if any(set(m)!=set(om) for m in (sm,lm,rm)) or set(pg05_c1.get("solution_ids",[]))!=set(om):
        _block("PG05_EXIT_SOLUTION_SET_DRIFT")
    if set(subject.get("solution_ids",[]))!=set(om) or not _ids(subject.get("solution_ids")):
        _block("PG05_EXIT_SUBJECT_SOLUTIONS_DRIFT")
    entries=[]
    for sid in sorted(om):
        report=rm[sid]
        findings=report.get("blocking_findings")
        if (not isinstance(findings,list)
            or report.get("diagnostic_status") not in ("BLOCKED_SCOPE_VIOLATION","NO_SCOPE_VIOLATION_VISIBLE")
            or (bool(findings)) != (report.get("diagnostic_status")=="BLOCKED_SCOPE_VIOLATION")
            or report.get("write_allowed") is not False
            or sm[sid].get("write_authorized") is not False
            or lm[sid].get("lock_acquired") is not False):
            _block("PG05_EXIT_DIAGNOSTIC_OR_LOCK_DRIFT")
        entries.append({
            "solution_id":sid,
            "depends_on":deepcopy(om[sid].get("depends_on")),
            "write_resources":deepcopy(sm[sid].get("write_resource_keys")),
            "shared_read_refs":deepcopy(sm[sid].get("shared_read_refs")),
            "requested_lock_resources":deepcopy(lm[sid].get("requested_resources")),
            "write_boundary_diagnostic":report["diagnostic_status"],
            "blocking_findings":deepcopy(findings),
            "write_allowed":False,
            "pg06_execution_ready":False
        })
    blocked=sorted(x["solution_id"] for x in entries if x["blocking_findings"])
    clean=sorted(x["solution_id"] for x in entries if not x["blocking_findings"])
    if (subject.get("blocked_solution_ids")!=blocked
        or subject.get("unaffected_solution_ids_not_admitted")!=clean):
        _block("PG05_EXIT_SUBJECT_CLASSIFICATION_DRIFT")
    result={
        "schema_version":"PG05_TO_PG06_EXIT_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_hashes":dict(digests,pg05_c5=c5sha),
        "source_pg05_assurance_subject_sha256":pg05_c5["subject_sha256"],
        "target_binding":deepcopy(pg05_c1.get("target_binding")),
        "target_branch_candidate":pg05_c1.get("branch_name_candidate"),
        "solutions":entries,
        "affected_solutions":blocked,
        "unaffected_solutions_not_promoted":clean,
        "pg06_required_gates":{
            "PG-06_C1":"PG01_CURRENTNESS_DECISION_REUSE_OR_TYPED_SOURCE_DRIFT_STALE_RECHECK",
            "PG-06_C2":"CURRENT_TOOLCHAIN_CATALOG_AND_ENVIRONMENT_READBACK",
            "PG-06_C3":"A7_REVERSIBILITY_FRONTS_AND_TECHNICAL_ROLLBACK_PLAN",
            "PG-06_C4":"UNCHANGED_TARGET_BUILD_LINT_BASELINE_RECEIPTS",
            "PG-06_C5":"INDEPENDENT_ASSURANCE_REVIEW"
        },
        "pg01_currentness_decision_verified":False,
        "target_binding_verified":False,
        "toolchain_verified":False,
        "rollback_plan_verified":False,
        "baseline_build_lint_executed":False,
        "pg05_independent_review_executed":False,
        "pg05_admitted":False,
        "pg06_admitted":False,
        "branch_created":False,
        "locks_acquired":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"PG05_GOVERNED_ASSURANCE_AND_PG06_CURRENTNESS_TOOLCHAIN_BASELINE_ADMISSION"
    }
    result["candidate_sha256"]=_hash(result)
    return result
