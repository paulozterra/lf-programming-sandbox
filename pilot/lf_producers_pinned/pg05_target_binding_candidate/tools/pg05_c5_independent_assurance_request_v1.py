"""PG-05_C5: source-only request preflight for existing INDEPENDENT_ASSURANCE.

Bundles C1-C4 candidate artifacts under exact hashes. Never executes a reviewer,
invents a ledger receipt, verifies currentness or authorizes a writer.
"""
from copy import deepcopy
import hashlib
import json
import re

class PG05AssuranceBlocked(ValueError):
    pass

SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")

def _fail(code):
    raise PG05AssuranceBlocked(code)

def _hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _frozen(obj,schema,code):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema:
        _fail(code)
    digest=obj.get("candidate_sha256")
    if not isinstance(digest,str) or not SHA256.fullmatch(digest) or digest!=_hash({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        _fail(code)
    return digest

def _ids(values):
    return isinstance(values,list) and bool(values) and all(isinstance(x,str) and bool(x.strip()) for x in values) and len(values)==len(set(values))

def prepare_pg05_assurance_request(*,pg04_exit,pg05_c1,pg05_c2,pg05_c3,pg05_c4,source_manifest,producer_execution_id):
    exit_sha=_frozen(pg04_exit,"PG04_TO_PG05_EXIT_CANDIDATE_V1","PG05_C5_EXIT_DIGEST_INVALID")
    c1_sha=_frozen(pg05_c1,"PG05_C1_TARGET_BINDING_PREFLIGHT_CANDIDATE_V1","PG05_C5_C1_DIGEST_INVALID")
    c2_sha=_frozen(pg05_c2,"PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1","PG05_C5_C2_DIGEST_INVALID")
    c3_sha=_frozen(pg05_c3,"PG05_C3_CONFLICT_LOCK_PLAN_CANDIDATE_V1","PG05_C5_C3_DIGEST_INVALID")
    c4_sha=_frozen(pg05_c4,"PG05_C4_WRITE_BOUNDARY_DIAGNOSTIC_CANDIDATE_V1","PG05_C5_C4_DIGEST_INVALID")

    expected_links=((pg05_c1,"source_pg04_exit_sha256",exit_sha),
                    (pg05_c2,"source_pg04_exit_sha256",exit_sha),
                    (pg05_c2,"source_pg05_c1_sha256",c1_sha),
                    (pg05_c3,"source_pg04_exit_sha256",exit_sha),
                    (pg05_c3,"source_pg05_c2_sha256",c2_sha),
                    (pg05_c4,"source_pg04_exit_sha256",exit_sha),
                    (pg05_c4,"source_pg05_c2_sha256",c2_sha),
                    (pg05_c4,"source_pg05_c3_sha256",c3_sha))
    if any(o.get(k)!=v for o,k,v in expected_links):
        _fail("PG05_C5_SOURCE_CHAIN_DRIFT")
    if (pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg04_exit.get("pg04_admitted") is not False
        or pg04_exit.get("pg05_admission_allowed") is not False
        or pg04_exit.get("handoff_allowed") is not False
        or pg04_exit.get("production_authority") is not False
        or pg05_c1.get("status") not in ("BLOCKED","CANDIDATE_NOT_ADMITTED")
        or pg05_c1.get("branch_created") is not False
        or pg05_c1.get("pg05_admitted") is not False
        or pg05_c2.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_c2.get("write_scope_authorized") is not False
        or pg05_c2.get("writer_lock_acquired") is not False
        or pg05_c3.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_c3.get("locks_acquired") is not False
        or pg05_c3.get("writer_dispatch_allowed") is not False
        or pg05_c4.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_c4.get("write_allowed") is not False
        or pg05_c4.get("real_diff_verified") is not False):
        _fail("PG05_C5_CANDIDATE_AUTHORITY_INVALID")
    for part in (pg05_c1,pg05_c2,pg05_c3,pg05_c4):
        if part.get("production_authority") is not False or part.get("handoff_allowed") is not False:
            _fail("PG05_C5_RUNTIME_AUTHORITY_FORBIDDEN")

    solutions=pg04_exit.get("solutions")
    scopes=pg05_c2.get("solution_scopes")
    locks=pg05_c3.get("lock_requests")
    reports=pg05_c4.get("solution_reports")
    if not isinstance(solutions,list) or not isinstance(scopes,list) or not isinstance(locks,list) or not isinstance(reports,list):
        _fail("PG05_C5_SOLUTIONS_MISSING")
    def collect(rows,key):
        ids=[x.get(key) if isinstance(x,dict) else None for x in rows]
        if not _ids(ids):
            _fail("PG05_C5_SOLUTION_ID_INVALID")
        return set(ids)
    expected=collect(solutions,"solution_id")
    if (expected!=collect(scopes,"solution_id") or
        expected!=collect(locks,"solution_id") or
        expected!=collect(reports,"solution_id") or
        expected!=set(pg05_c1.get("solution_ids",[]))):
        _fail("PG05_C5_SOLUTION_COVERAGE_DRIFT")

    if not isinstance(source_manifest,dict) or set(source_manifest)!={"source_head_sha","pg04_exit","pg05_c1","pg05_c2","pg05_c3","pg05_c4"}:
        _fail("PG05_C5_SOURCE_MANIFEST_INVALID")
    source_head=source_manifest["source_head_sha"]
    if not isinstance(source_head,str) or not GIT_SHA.fullmatch(source_head):
        _fail("PG05_C5_SOURCE_HEAD_INVALID")
    for key,sha in (("pg04_exit",exit_sha),("pg05_c1",c1_sha),("pg05_c2",c2_sha),
                    ("pg05_c3",c3_sha),("pg05_c4",c4_sha)):
        source=source_manifest[key]
        if (not isinstance(source,dict) or set(source)!={"ref","sha256"}
            or not isinstance(source["ref"],str) or not source["ref"].strip()
            or source["sha256"]!=sha):
            _fail("PG05_C5_MANIFEST_DIGEST_DRIFT")
    if not isinstance(producer_execution_id,str) or not producer_execution_id.strip():
        _fail("PG05_C5_PRODUCER_EXECUTION_REQUIRED")
    checks=[
        "EXACT_REPO_BASE_SHA_BINDING_AND_CURRENTNESS",
        "PG04_ADMITTED_PARTITION_AND_SOURCE_CHAIN",
        "L3_WRITE_SCOPE_EVIDENCE_AND_REPOSITORY_PATH_ADMISSION",
        "SHARED_CONTRACT_READ_ONLY_AND_DB_OBJECT_SAFETY",
        "WRITER_COLLISION_DEPENDENCIES_AND_LOCK_AUTHORITY",
        "NEGATIVE_OUT_OF_SCOPE_WRITE_BLOCK_PER_SOLUTION",
        "CHANGESET_GOVERNANCE_NO_SCOPE_ESCALATION",
        "REVIEWER_INDEPENDENCE_AND_LEDGER_VERIFIED_SUBJECT",
    ]
    blocked=[r["solution_id"] for r in reports if r.get("diagnostic_status")=="BLOCKED_SCOPE_VIOLATION"]
    clean=[r["solution_id"] for r in reports if r.get("diagnostic_status")=="NO_SCOPE_VIOLATION_VISIBLE"]
    if set(blocked)|set(clean)!=expected or set(blocked)&set(clean):
        _fail("PG05_C5_DIAGNOSTIC_REPORT_INVALID")
    if any(r.get("write_allowed") is not False or r.get("writer_dispatch_allowed") is not False for r in reports):
        _fail("PG05_C5_DIAGNOSTIC_AUTHORITY_FORBIDDEN")
    subject={
        "schema_version":"PG05_C5_ASSURANCE_SUBJECT_CANDIDATE_V1",
        "pg04_exit_sha256":exit_sha,
        "pg05_c1_sha256":c1_sha,
        "pg05_c2_sha256":c2_sha,
        "pg05_c3_sha256":c3_sha,
        "pg05_c4_sha256":c4_sha,
        "source_manifest_sha256":_hash(source_manifest),
        "solution_ids":sorted(expected),
        "blocked_solution_ids":sorted(blocked),
        "unaffected_solution_ids_not_admitted":sorted(clean),
        "no_write_authority":True,
    }
    subject_sha=_hash(subject)
    request={
        "schema_version":"PG05_C5_INDEPENDENT_REVIEW_REQUEST_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "subject_type":"PG05_WRITE_SCOPE_GOVERNANCE_CANDIDATE",
        "subject_ref":"PG05_WRITE_SCOPE_GOVERNANCE_CANDIDATE/"+subject_sha,
        "subject_sha256":subject_sha,
        "subject":subject,
        "source_head_sha":source_head,
        "source_manifest":deepcopy(source_manifest),
        "source_manifest_sha256":_hash(source_manifest),
        "producer_execution_id":producer_execution_id,
        "reviewer_execution_id":None,
        "subject_receipt_id":None,
        "independent_review_capability":"INDEPENDENT_ASSURANCE",
        "intended_review_operation":"REVISION_INDEPENDIENTE_ESTRATEGIA_LF",
        "required_assertions":checks,
        "required_runtime_binding":[
            "PG04_ADMITTED_AND_CURRENT_SOURCE_READBACK",
            "EVIDENCE_LEDGER_VERIFIED_EXACT_PG05_SUBJECT",
            "INDEPENDENT_REVIEWER_DISTINCT_FROM_PRODUCER",
            "GOVERNED_OPERATION_RESERVATION_AND_DISPATCH",
            "CURRENT_TARGET_REPOSITORY_AND_BASE_HEAD_READBACK",
            "CURRENT_CHANGESET_GOVERNANCE_PATH_ADMISSION",
            "REAL_WRITER_LOCKS_AND_NEGATIVE_TEST_RECEIPTS"
        ],
        "first_runtime_blocker":"PG05_VERIFIED_SUBJECT_RECEIPT_MISSING",
        "source_readback_verified":False,
        "ledger_subject_receipt_verified":False,
        "independent_review_executed":False,
        "reviewer_independence_attested":False,
        "review_execution_allowed":False,
        "pg05_admitted":False,
        "branch_creation_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False
    }
    request["request_sha256"]=_hash(request)
    return request
