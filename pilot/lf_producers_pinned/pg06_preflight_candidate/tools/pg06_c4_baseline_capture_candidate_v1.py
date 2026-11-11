"""PG-06_C4: source-only baseline build/lint evidence manifest.

Requires explicit unchanged-target observations, captures pre-existing violations,
and prevents an observed success from becoming an authorized PASS. Does not
execute shell commands, inspect Git, authenticate receipts, or alter the target.
"""
import hashlib
import json
import re
from copy import deepcopy

class BaselineBlocked(ValueError):
    pass

_SHA256=re.compile(r"^[0-9a-f]{64}$")
_SHA40=re.compile(r"^[0-9a-f]{40}$")
_KINDS={"BUILD","LINT"}
_RESULTS={"PASS","FAIL"}

def _fail(code):
    raise BaselineBlocked(code)

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _text(value):
    return isinstance(value,str) and bool(value.strip())

def _frozen(value,schema,code):
    if not isinstance(value,dict) or value.get("schema_version")!=schema:
        _fail(code)
    digest=value.get("candidate_sha256")
    if not isinstance(digest,str) or not _SHA256.fullmatch(digest) or digest!=_digest({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _fail(code)
    return digest

def prepare_pg06_c4(*,pg05_exit,pg06_c1,pg06_c2,pg06_c3,baseline_observations):
    exit_sha=_frozen(pg05_exit,"PG05_TO_PG06_EXIT_CANDIDATE_V1","PG06_C4_EXIT_INVALID")
    c1_sha=_frozen(pg06_c1,"PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1","PG06_C4_C1_INVALID")
    c2_sha=_frozen(pg06_c2,"PG06_C2_TOOLCHAIN_PREFLIGHT_CANDIDATE_V1","PG06_C4_C2_INVALID")
    c3_sha=_frozen(pg06_c3,"PG06_C3_REVERSIBILITY_PLAN_CANDIDATE_V1","PG06_C4_C3_INVALID")
    if (pg05_exit.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg05_exit.get("production_authority") is not False or pg05_exit.get("handoff_allowed") is not False or
        pg06_c1.get("source_pg05_exit_sha256")!=exit_sha or
        pg06_c2.get("source_pg05_exit_sha256")!=exit_sha or pg06_c2.get("source_pg06_c1_sha256")!=c1_sha or
        pg06_c3.get("source_pg05_exit_sha256")!=exit_sha or
        pg06_c3.get("source_pg06_c1_sha256")!=c1_sha or pg06_c3.get("source_pg06_c2_sha256")!=c2_sha or
        pg06_c1.get("execution_allowed") is not False or pg06_c2.get("pg06_ready") is not False or
        pg06_c3.get("write_allowed") is not False or pg06_c3.get("pg06_admitted") is not False or
        any(x.get("production_authority") is not False or x.get("handoff_allowed") is not False for x in (pg06_c1,pg06_c2,pg06_c3))):
        _fail("PG06_C4_SOURCE_CHAIN_OR_AUTHORITY_INVALID")
    target=pg05_exit.get("target_binding")
    if (not isinstance(target,dict) or not _text(target.get("repo_full_name")) or
        not isinstance(target.get("base_head_sha"),str) or not _SHA40.fullmatch(target["base_head_sha"])):
        _fail("PG06_C4_TARGET_BINDING_MISSING")
    sols=pg05_exit.get("solutions")
    if not isinstance(sols,list) or not sols:
        _fail("PG06_C4_SOLUTIONS_MISSING")
    ids=[s.get("solution_id") if isinstance(s,dict) else None for s in sols]
    if any(not _text(sid) for sid in ids) or len(set(ids))!=len(ids):
        _fail("PG06_C4_SOLUTION_ID_INVALID")
    if not isinstance(baseline_observations,dict) or set(baseline_observations)!={
        "schema_version","target_repo","base_head_sha","observation_ref",
        "execution_environment_ref","unchanged_target_claim","command_results"}:
        _fail("PG06_C4_OBSERVATION_SCHEMA_INVALID")
    obs=baseline_observations
    if (obs["schema_version"]!="PG06_UNCHANGED_TARGET_BASELINE_OBSERVATION_CANDIDATE_V1" or
        obs["target_repo"]!=target["repo_full_name"] or obs["base_head_sha"]!=target["base_head_sha"] or
        not _text(obs["observation_ref"]) or not _text(obs["execution_environment_ref"]) or
        obs["unchanged_target_claim"] is not True):
        _fail("PG06_C4_TARGET_OR_UNCHANGED_CLAIM_INVALID")
    commands=obs["command_results"]
    if not isinstance(commands,list) or not commands:
        _fail("PG06_C4_COMMAND_RESULTS_REQUIRED")
    seen=set()
    per_solution={sid:{} for sid in ids}
    reports=[]
    for c in commands:
        if not isinstance(c,dict) or set(c)!={
            "command_id","solution_id","kind","command_ref","command_sha256","result",
            "exit_code","stdout_sha256","stderr_sha256","violation_refs","execution_receipt_ref"}:
            _fail("PG06_C4_COMMAND_RESULT_SCHEMA_INVALID")
        sid=c["solution_id"]
        kind=c["kind"]
        command_id=c["command_id"]
        if (sid not in per_solution or kind not in _KINDS or not _text(command_id) or command_id in seen
            or kind in per_solution[sid] or not _text(c["command_ref"]) or not _text(c["execution_receipt_ref"])
            or any(not isinstance(c[x],str) or not _SHA256.fullmatch(c[x]) for x in
                   ("command_sha256","stdout_sha256","stderr_sha256"))
            or c["result"] not in _RESULTS or not isinstance(c["exit_code"],int)
            or isinstance(c["exit_code"],bool)):
            _fail("PG06_C4_COMMAND_BINDING_INVALID")
        if ((c["result"]=="PASS" and (c["exit_code"]!=0 or c["violation_refs"]!=[])) or
            (c["result"]=="FAIL" and c["exit_code"]==0)):
            _fail("PG06_C4_COMMAND_RESULT_CONTRADICTION")
        violations=c["violation_refs"]
        if (not isinstance(violations,list) or
            any(not _text(v) for v in violations) or len(violations)!=len(set(violations))):
            _fail("PG06_C4_VIOLATION_REFS_INVALID")
        seen.add(command_id)
        per_solution[sid][kind]=c
        reports.append({
            "command_id":command_id,"solution_id":sid,"kind":kind,
            "command_ref":c["command_ref"],"command_sha256":c["command_sha256"],
            "reported_result":c["result"],"exit_code":c["exit_code"],
            "stdout_sha256":c["stdout_sha256"],"stderr_sha256":c["stderr_sha256"],
            "preexisting_violation_refs":sorted(violations),
            "execution_receipt_ref":c["execution_receipt_ref"],
            "execution_receipt_verified":False,
            "target_unchanged_verified":False,
            "source_currentness_verified":False,
            "actual_pass_attested":False})
    if any(set(v)!={"BUILD","LINT"} for v in per_solution.values()):
        _fail("PG06_C4_BUILD_LINT_COVERAGE_INCOMPLETE")
    solution_rows=[]
    for sid in sorted(ids):
        kinds=per_solution[sid]
        failures=[kind for kind in ("BUILD","LINT") if kinds[kind]["result"]=="FAIL"]
        solution_rows.append({
            "solution_id":sid,
            "reported_failed_kinds":failures,
            "reported_preexisting_violation_refs":sorted(set(
                v for kind in ("BUILD","LINT") for v in kinds[kind]["violation_refs"])),
            "diagnostic_status":"REPORTED_BASELINE_FAILURE" if failures else "REPORTED_BASELINE_PASS_UNVERIFIED",
            "baseline_verified":False,
            "execution_allowed":False})
    result={
        "schema_version":"PG06_C4_BASELINE_BUILD_LINT_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg05_exit_sha256":exit_sha,"source_pg06_c1_sha256":c1_sha,
        "source_pg06_c2_sha256":c2_sha,"source_pg06_c3_sha256":c3_sha,
        "target_binding":{"repo_full_name":target["repo_full_name"],"base_head_sha":target["base_head_sha"]},
        "observation_manifest_sha256":_digest(obs),
        "observation_ref":obs["observation_ref"],
        "execution_environment_ref":obs["execution_environment_ref"],
        "command_reports":sorted(reports,key=lambda x:(x["solution_id"],x["kind"])),
        "solutions":solution_rows,
        "unchanged_target_verified":False,
        "build_lint_executed_by_this_component":False,
        "receipts_authenticated":False,
        "baseline_digest_recorded":_digest(reports),
        "pg06_ready":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"EXACT_TARGET_CLEAN_TREE_AND_BUILD_LINT_EXECUTION_RECEIPT_READBACK"
    }
    result["candidate_sha256"]=_digest(result)
    return result
