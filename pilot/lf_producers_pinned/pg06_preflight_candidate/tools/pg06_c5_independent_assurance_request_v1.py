"""PG-06_C5 source-only independent assurance request, no review execution.

Freeze C1-C4 results, preserve blocking diagnostics and request existing
INDEPENDENT_ASSURANCE. Never fabricate verification receipts or grant PG07
writer dispatch.
"""
import hashlib
import json
import re
from copy import deepcopy

class PG06AssuranceBlocked(ValueError):
    pass

SHA256=re.compile(r"^[0-9a-f]{64}$")
GIT_SHA=re.compile(r"^[0-9a-f]{40}$")
SCHEMAS={
    "pg05_exit":"PG05_TO_PG06_EXIT_CANDIDATE_V1",
    "pg06_c1":"PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1",
    "pg06_c2":"PG06_C2_TOOLCHAIN_PREFLIGHT_CANDIDATE_V1",
    "pg06_c3":"PG06_C3_REVERSIBILITY_PLAN_CANDIDATE_V1",
    "pg06_c4":"PG06_C4_BASELINE_BUILD_LINT_CANDIDATE_V1",
}
def _fail(reason):
    raise PG06AssuranceBlocked(reason)

def _sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _frozen(obj,schema):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema:
        _fail("PG06_C5_SOURCE_SCHEMA_INVALID")
    digest=obj.get("candidate_sha256")
    if not isinstance(digest,str) or not SHA256.fullmatch(digest) or digest!=_sha({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        _fail("PG06_C5_SOURCE_DIGEST_INVALID")
    return digest

def _ids(rows):
    if not isinstance(rows,list) or not rows:
        _fail("PG06_C5_SOLUTIONS_MISSING")
    ids=[r.get("solution_id") if isinstance(r,dict) else None for r in rows]
    if any(not isinstance(s,str) or not s.strip() for s in ids) or len(set(ids))!=len(ids):
        _fail("PG06_C5_SOLUTION_IDS_INVALID")
    return set(ids)

def prepare_pg06_assurance_request(*,pg05_exit,pg06_c1,pg06_c2,pg06_c3,pg06_c4,source_manifest,producer_execution_id):
    source={"pg05_exit":pg05_exit,"pg06_c1":pg06_c1,"pg06_c2":pg06_c2,"pg06_c3":pg06_c3,"pg06_c4":pg06_c4}
    digests={k:_frozen(source[k],SCHEMAS[k]) for k in SCHEMAS}
    links=[
        ("pg06_c1","source_pg05_exit_sha256","pg05_exit"),
        ("pg06_c2","source_pg05_exit_sha256","pg05_exit"),
        ("pg06_c2","source_pg06_c1_sha256","pg06_c1"),
        ("pg06_c3","source_pg05_exit_sha256","pg05_exit"),
        ("pg06_c3","source_pg06_c1_sha256","pg06_c1"),
        ("pg06_c3","source_pg06_c2_sha256","pg06_c2"),
        ("pg06_c4","source_pg05_exit_sha256","pg05_exit"),
        ("pg06_c4","source_pg06_c1_sha256","pg06_c1"),
        ("pg06_c4","source_pg06_c2_sha256","pg06_c2"),
        ("pg06_c4","source_pg06_c3_sha256","pg06_c3"),
    ]
    if any(source[s].get(field)!=digests[target] for s,field,target in links):
        _fail("PG06_C5_UPSTREAM_DIGEST_DRIFT")
    for key,obj in source.items():
        if obj.get("production_authority") is not False or obj.get("handoff_allowed") is not False:
            _fail("PG06_C5_PREMATURE_AUTHORITY")
    if (pg05_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_exit.get("pg06_admitted") is not False
        or pg06_c1.get("pg06_ready") is not False
        or pg06_c2.get("pg06_ready") is not False
        or pg06_c3.get("pg06_admitted") is not False
        or pg06_c4.get("pg06_ready") is not False
        or pg06_c4.get("unchanged_target_verified") is not False
        or pg06_c4.get("receipts_authenticated") is not False
        or pg06_c4.get("build_lint_executed_by_this_component") is not False
        or pg06_c3.get("rollback_plan_verified") is not False
        or pg06_c2.get("toolchain_available_attested") is not False
        or pg06_c1.get("pg01_decision_readback_verified") is not False):
        _fail("PG06_C5_SOURCE_NOT_UNADMITTED")
    ids=_ids(pg05_exit.get("solutions"))
    if any(_ids(source[k].get("solutions"))!=ids for k in ("pg06_c2","pg06_c3","pg06_c4")):
        _fail("PG06_C5_SOLUTION_COVERAGE_DRIFT")
    if (not isinstance(source_manifest,dict)
        or set(source_manifest)!={"source_head_sha",*SCHEMAS.keys()}
        or not isinstance(source_manifest["source_head_sha"],str)
        or not GIT_SHA.fullmatch(source_manifest["source_head_sha"])):
        _fail("PG06_C5_MANIFEST_INVALID")
    for name,digest in digests.items():
        entry=source_manifest[name]
        if (not isinstance(entry,dict) or set(entry)!={"ref","sha256"}
            or not isinstance(entry["ref"],str) or not entry["ref"].strip()
            or entry["sha256"]!=digest):
            _fail("PG06_C5_MANIFEST_SOURCE_DRIFT")
    if not isinstance(producer_execution_id,str) or not producer_execution_id.strip():
        _fail("PG06_C5_PRODUCER_EXECUTION_REQUIRED")
    tool_blocked=sorted(x["solution_id"] for x in pg06_c2["solutions"] if x["diagnostic_status"]=="BLOCKED_TOOL_UNAVAILABLE")
    a7_blocked=sorted(x["solution_id"] for x in pg06_c3["solutions"] if x["diagnostic_status"]=="BLOCKED_A7_FRONT")
    baseline_failed=sorted(x["solution_id"] for x in pg06_c4["solutions"] if x["diagnostic_status"]=="REPORTED_BASELINE_FAILURE")
    subject={
        "schema_version":"PG06_C5_ASSURANCE_SUBJECT_CANDIDATE_V1",
        "upstream_digests":digests,
        "source_manifest_sha256":_sha(source_manifest),
        "solution_ids":sorted(ids),
        "blocked_toolchain_solution_ids":tool_blocked,
        "blocked_a7_solution_ids":a7_blocked,
        "reported_baseline_failure_solution_ids":baseline_failed,
        "no_pg07_dispatch_authority":True,
    }
    subject_sha=_sha(subject)
    request={
        "schema_version":"PG06_C5_INDEPENDENT_REVIEW_REQUEST_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "subject_type":"PG06_ENVIRONMENT_READINESS_CANDIDATE",
        "subject_ref":"PG06_ENVIRONMENT_READINESS_CANDIDATE/"+subject_sha,
        "subject_sha256":subject_sha,
        "subject":subject,
        "source_manifest":deepcopy(source_manifest),
        "source_head_sha":source_manifest["source_head_sha"],
        "producer_execution_id":producer_execution_id,
        "reviewer_execution_id":None,
        "subject_receipt_id":None,
        "independent_review_capability":"INDEPENDENT_ASSURANCE",
        "required_assertions":[
            "PG05_ADMISSION_AND_EXACT_TARGET_BINDING",
            "PG01_CURRENTNESS_DECISION_RECEIPT_AND_NO_MID_EXECUTION_REBIND",
            "CURRENT_TOOLCHAIN_CATALOG_EXACT_VERSIONS_AND_REAL_ENVIRONMENT_OBSERVATIONS",
            "A7_FRONT_COVERAGE_AND_TECHNICAL_REVERSIBILITY_VALIDITY",
            "UNCHANGED_TARGET_BUILD_LINT_BASELINE_AUTHENTIC_RECEIPTS",
            "PREEXISTING_VIOLATION_INVENTORY_NO_FALSE_REGRESSION",
            "PER_SOLUTION_BLOCK_ISOLATION_AND_NO_PREMATURE_WRITER",
            "CURRENT_LEDGER_RECEIPT_AND_REVIEWER_INDEPENDENCE"
        ],
        "first_runtime_blocker":"PG06_EXACT_VERIFIED_SUBJECT_RECEIPT_NOT_READ_BACK",
        "required_runtime_binding":[
            "PG05_ADMITTED_AND_CURRENT_READBACK",
            "EXACT_EVIDENCE_LEDGER_VERIFIED_SUBJECT_RECEIPT",
            "INDEPENDENT_REVIEWER_DISTINCT_FROM_PRODUCER",
            "GOVERNED_ORCHESTRATOR_DISPATCH",
            "CURRENT_TOOLCHAIN_AND_TARGET_BASELINE_RECEIPTS",
            "A7_REVERSIBILITY_VALIDATION"
        ],
        "source_readback_verified":False,
        "ledger_subject_receipt_verified":False,
        "reviewer_independence_attested":False,
        "independent_review_executed":False,
        "review_execution_allowed":False,
        "pg06_admitted":False,
        "pg07_dispatch_allowed":False,
        "worker_invoked":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False
    }
    request["request_sha256"]=_sha(request)
    return request
