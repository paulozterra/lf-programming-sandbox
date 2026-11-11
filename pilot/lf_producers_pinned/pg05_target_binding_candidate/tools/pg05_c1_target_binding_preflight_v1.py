"""PG-05_C1 source-only target binding and branch-plan preflight.

Consumes frozen PG04 exit candidate. Never discovers a repository, resolves a
Git ref, creates a branch, reserves a lock, or claims an admitted writer.
"""
import hashlib
import json
import re

class PG05BindingBlocked(ValueError):
    pass

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
WORK = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def _fail(code):
    raise PG05BindingBlocked(code)

def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _freeze(value):
    if not isinstance(value,dict):
        _fail("PG04_EXIT_MISSING")
    digest=value.get("candidate_sha256")
    if not isinstance(digest,str) or digest!=_hash({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _fail("PG04_EXIT_DIGEST_DRIFT")
    return digest

def prepare_pg05_c1(*,pg04_exit,work_code,slug):
    """Plan the canonical branch name; do not create it or authorize anything."""
    exit_sha=_freeze(pg04_exit)
    if (pg04_exit.get("schema_version")!="PG04_TO_PG05_EXIT_CANDIDATE_V1"
        or pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg04_exit.get("pg04_admitted") is not False
        or pg04_exit.get("pg05_admission_allowed") is not False
        or pg04_exit.get("pg05_branch_creation_allowed") is not False
        or pg04_exit.get("pg05_write_allowed") is not False
        or pg04_exit.get("handoff_allowed") is not False
        or pg04_exit.get("production_authority") is not False
        or pg04_exit.get("target_binding_inferred") is not False
        or pg04_exit.get("target_branch_created") is not False):
        _fail("PG04_EXIT_NOT_UNTRUSTED_CANDIDATE")
    if not isinstance(work_code,str) or not WORK.fullmatch(work_code):
        _fail("PG05_WORK_CODE_INVALID")
    if not isinstance(slug,str) or not SLUG.fullmatch(slug) or len(slug)>80:
        _fail("PG05_BRANCH_SLUG_INVALID")
    binding=pg04_exit.get("target_binding")
    if not isinstance(binding,dict) or set(binding)!={"repo_full_name","base_head_sha","target_binding_ref","source_attested"} or binding.get("source_attested") is not False:
        _fail("PG05_BINDING_AUTHORITY_INVALID")
    repo=binding["repo_full_name"]
    head=binding["base_head_sha"]
    ref=binding["target_binding_ref"]
    if repo is None and head is None and ref is None:
        status="BLOCKED"
        reason="PG05_TARGET_BINDING_MISSING"
        proposed_branch=None
    elif (isinstance(repo,str) and REPO.fullmatch(repo) and
          repo.split("/")[0] not in (".","..") and repo.split("/")[1] not in (".","..") and
          isinstance(head,str) and SHA40.fullmatch(head) and
          isinstance(ref,str) and bool(ref.strip())):
        status="CANDIDATE_NOT_ADMITTED"
        reason="PG05_TARGET_BINDING_UNATTESTED_AND_PG04_UNADMITTED"
        proposed_branch=f"lf/prog-{work_code}/{slug}"
    else:
        _fail("PG05_TARGET_BINDING_INVALID")
    solutions=pg04_exit.get("solutions")
    if not isinstance(solutions,list) or not solutions:
        _fail("PG05_SOLUTIONS_MISSING")
    ids=[]
    for item in solutions:
        if not isinstance(item,dict) or not isinstance(item.get("solution_id"),str) or not item["solution_id"].strip() or item["solution_id"] in ids:
            _fail("PG05_SOLUTION_IDS_INVALID")
        ids.append(item["solution_id"])
        if (item.get("pg05_write_scope_authorized") is not False
            or item.get("pg05_parallel_writer_lock_acquired") is not False
            or item.get("execution_allowed") is not False
            or item.get("shared_contract_access_default")!="READ_ONLY"):
            _fail("PG05_WRITER_AUTHORITY_IN_CANDIDATE")
        scopes=item.get("write_scope_candidates")
        if not isinstance(scopes,list) or not scopes or not all(isinstance(x,str) and x.strip() for x in scopes) or len(scopes)!=len(set(scopes)):
            _fail("PG05_WRITE_SCOPE_CANDIDATES_INVALID")
    result={
        "schema_version":"PG05_C1_TARGET_BINDING_PREFLIGHT_CANDIDATE_V1",
        "status":status,
        "first_blocker":reason,
        "source_pg04_exit_sha256":exit_sha,
        "source_partition_sha256":pg04_exit.get("partition_sha256"),
        "work_code":work_code,
        "target_binding":{"repo_full_name":repo,"base_head_sha":head,
                          "target_binding_ref":ref,
                          "source_attested":False},
        "branch_name_candidate":proposed_branch,
        "branch_naming_rule":"lf/prog-<work_code>/<slug>",
        "solution_ids":sorted(ids),
        "target_binding_currentness_verified":False,
        "base_head_repository_readback_verified":False,
        "branch_collision_checked":False,
        "branch_created":False,
        "writer_lock_acquired":False,
        "write_scope_authorized":False,
        "pg04_independent_assurance_verified":False,
        "pg05_admitted":False,
        "branch_creation_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"AUTHORIZED_TARGET_BINDING_CURRENT_READBACK_AND_PG04_ADMISSION"
    }
    result["candidate_sha256"]=_hash(result)
    return result
