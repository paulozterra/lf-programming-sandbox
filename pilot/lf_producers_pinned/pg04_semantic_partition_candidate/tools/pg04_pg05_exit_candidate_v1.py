"""PG-04 candidate exit package for PG-05: source-only composition, no handoff authority.

Never infers target repo/base, acquires locks, creates branches, grants write scope,
or promotes an unreviewed partition. A missing target binding stays missing.
"""
import copy
import hashlib
import json
import re

class ExitPackageBlocked(ValueError):
    pass

_GIT_SHA=re.compile(r"^[0-9a-f]{40}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")

def _fail(reason):
    raise ExitPackageBlocked(reason)

def _hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _ids(value,empty=False):
    return isinstance(value,list) and (empty or bool(value)) and all(isinstance(x,str) and bool(x.strip()) for x in value) and len(value)==len(set(value))

def _frozen(obj,digest_key,code):
    if not isinstance(obj,dict):
        _fail(code)
    digest=obj.get(digest_key)
    if not isinstance(digest,str) or not _SHA.fullmatch(digest) or digest!=_hash({k:v for k,v in obj.items() if k!=digest_key}):
        _fail(code)
    return digest

def assemble_pg04_exit_candidate(*,partition,dod,coverage_dossier,review_request,target_binding=None):
    """Assemble artifacts already produced by PG-04 into an explicitly nonadmitted PG-05 preview."""
    psha=_frozen(partition,"candidate_sha256","PARTITION_DIGEST_INVALID")
    if (partition.get("schema_version")!="PG04_SEMANTIC_PARTITION_CANDIDATE_V1"
        or partition.get("status")!="CANDIDATE_NOT_ADMITTED"
        or partition.get("production_authority") is not False
        or partition.get("handoff_allowed") is not False):
        _fail("PARTITION_NOT_CANDIDATE")
    dsha=_frozen(dod,"candidate_sha256","DOD_DIGEST_INVALID")
    if (dod.get("schema_version")!="PG04_SOLUTION_DOD_CANDIDATE_V1"
        or dod.get("partition_sha256")!=psha or dod.get("status")!="CANDIDATE_NOT_ADMITTED"
        or dod.get("checks_executed") is not False or dod.get("receipts_verified") is not False
        or dod.get("production_authority") is not False or dod.get("handoff_allowed") is not False):
        _fail("DOD_NOT_MATCHING_CANDIDATE")
    csha=_frozen(coverage_dossier,"candidate_sha256","COVERAGE_DOSSIER_DIGEST_INVALID")
    if (coverage_dossier.get("schema_version")!="PG04_C7_DETERMINISTIC_COVERAGE_DOSSIER_V1"
        or coverage_dossier.get("partition_sha256")!=psha
        or coverage_dossier.get("status")!="CANDIDATE_NOT_ADMITTED"
        or coverage_dossier.get("coverage_deterministic_check")!="PASS_SOURCE_ONLY"
        or coverage_dossier.get("semantic_fidelity_judged") is not False
        or coverage_dossier.get("independent_review_executed") is not False
        or coverage_dossier.get("production_authority") is not False):
        _fail("COVERAGE_DOSSIER_NOT_MATCHING")
    rsha=_frozen(review_request,"request_sha256","REVIEW_REQUEST_DIGEST_INVALID")
    if (review_request.get("schema_version")!="PG04_C7_PARTITION_REVIEW_REQUEST_CANDIDATE_V1"
        or review_request.get("candidate_sha256")!=psha
        or review_request.get("deterministic_coverage_dossier_sha256")!=csha
        or review_request.get("status")!="CANDIDATE_NOT_ADMITTED"
        or review_request.get("subject_receipt_id") is not None
        or review_request.get("review_execution_allowed") is not False
        or review_request.get("semantic_judge_executed") is not False
        or review_request.get("production_authority") is not False
        or review_request.get("handoff_allowed") is not False):
        _fail("REVIEW_REQUEST_NOT_MATCHING")
    solutions=partition.get("solutions")
    plans=dod.get("solutions")
    coverage_rows=coverage_dossier.get("solutions")
    if not isinstance(solutions,list) or not solutions or not isinstance(plans,list) or not isinstance(coverage_rows,list):
        _fail("EXIT_SOLUTIONS_MISSING")
    ids=[s.get("id") if isinstance(s,dict) else None for s in solutions]
    dids=[p.get("solution_id") if isinstance(p,dict) else None for p in plans]
    cids=[c.get("solution_id") if isinstance(c,dict) else None for c in coverage_rows]
    if (not _ids(ids) or not _ids(dids) or not _ids(cids)
        or set(ids)!=set(dids) or set(ids)!=set(cids)
        or review_request.get("solution_ids")!=sorted(ids)):
        _fail("EXIT_SOLUTIONS_MISMATCH")
    plan_by_id={p["solution_id"]:p for p in plans}
    cover_by_id={c["solution_id"]:c for c in coverage_rows}
    entries=[]
    for sol in solutions:
        sid=sol["id"]
        plan=plan_by_id[sid]
        cov=cover_by_id[sid]
        if (plan.get("partition_sha256")!=psha or plan.get("status")!="PLANNED_NOT_EXECUTED"
            or plan.get("done") is not False or plan.get("receipts_verified") is not False
            or not _ids(sol.get("write_scope")) or not _ids(sol.get("depends_on"),True)
            or not _ids(sol.get("shared_contract_refs"),True)):
            _fail("EXIT_SOLUTION_STATE_INVALID")
        for key,source_key in (("atom_ids","atom_ids"),("requirement_ids","requirement_ids"),
                               ("acceptance_ids","acceptance_ids"),("depends_on","depends_on")):
            if not _ids(sol.get(source_key),True) or sorted(sol[source_key])!=cov.get(key):
                _fail("EXIT_SOLUTION_COVERAGE_DRIFT")
        checks=plan.get("checks")
        if not isinstance(checks,list) or len(checks)!=plan.get("check_count") or not checks or any(
            not isinstance(ch,dict) or ch.get("status")!="NOT_EXECUTED"
            or ch.get("receipt_id") is not None or ch.get("pass_claim_allowed") is not False
            for ch in checks
        ):
            _fail("EXIT_DOD_CHECKS_INVALID")
        entries.append({
            "solution_id":sid,
            "business_outcome":sol.get("business_outcome"),
            "atom_ids":sorted(sol["atom_ids"]),
            "requirement_ids":sorted(sol["requirement_ids"]),
            "acceptance_ids":sorted(sol["acceptance_ids"]),
            "depends_on":sorted(sol["depends_on"]),
            "write_scope_candidates":sorted(sol["write_scope"]),
            "shared_contract_refs":sorted(sol["shared_contract_refs"]),
            "shared_contract_access_default":"READ_ONLY",
            "implementation_state":sol.get("implementation_state"),
            "source_bindings":copy.deepcopy(sol.get("source_bindings")),
            "dod":copy.deepcopy(plan),
            "pg05_write_scope_authorized":False,
            "pg05_parallel_writer_lock_acquired":False,
            "execution_allowed":False
        })
    if target_binding is None:
        binding={"repo_full_name":None,"base_head_sha":None,"target_binding_ref":None,
                 "source_attested":False}
        blocked="PG05_TARGET_BINDING_MISSING"
    else:
        if (not isinstance(target_binding,dict) or
            set(target_binding)!={"repo_full_name","base_head_sha","target_binding_ref"} or
            any(not isinstance(target_binding.get(k),str) or not target_binding[k].strip()
                for k in target_binding) or
            not _GIT_SHA.fullmatch(target_binding["base_head_sha"]) or
            "/" not in target_binding["repo_full_name"]):
            _fail("PG05_TARGET_BINDING_INVALID")
        binding=dict(copy.deepcopy(target_binding),source_attested=False)
        blocked="PG04_INDEPENDENT_REVIEW_NOT_EXECUTED"
    output={
        "schema_version":"PG04_TO_PG05_EXIT_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "partition_sha256":psha,
        "dod_sha256":dsha,
        "coverage_dossier_sha256":csha,
        "review_request_sha256":rsha,
        "target_binding":binding,
        "target_binding_inferred":False,
        "target_branch_created":False,
        "solutions":sorted(entries,key=lambda x:x["solution_id"]),
        "coverage":copy.deepcopy(coverage_dossier.get("coverage")),
        "review_required":True,
        "review_execution_allowed":False,
        "independent_review_executed":False,
        "ledger_subject_receipt_verified":False,
        "pg04_admitted":False,
        "pg05_admission_allowed":False,
        "pg05_branch_creation_allowed":False,
        "pg05_write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "first_pg05_blocker":blocked
    }
    output["candidate_sha256"]=_hash(output)
    return output
