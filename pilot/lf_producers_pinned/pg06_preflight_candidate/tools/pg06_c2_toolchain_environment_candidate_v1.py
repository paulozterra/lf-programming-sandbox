"""PG-06_C2 candidate catalog-to-environment reconciliation, no tool execution.

No built-in version assumptions. Catalog selection, currentness and observed
environment are caller-supplied, unverified. Missing/mismatched tools fail
closed; even matching reported versions cannot grant PG-06 execution.
"""
import hashlib
import json
import re

class ToolchainBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")
_NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_.+-]*$")

def _fail(reason):raise ToolchainBlocked(reason)

def _sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _text(value):
    return isinstance(value,str) and bool(value.strip())

def _ids(value):
    return isinstance(value,list) and bool(value) and all(_text(x) for x in value) and len(value)==len(set(value))

def _frozen(value,schema,code):
    if not isinstance(value,dict) or value.get("schema_version")!=schema:
        _fail(code)
    digest=value.get("candidate_sha256")
    if not isinstance(digest,str) or not _SHA.fullmatch(digest) or digest!=_sha({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _fail(code)
    return digest

def prepare_pg06_c2(*,pg05_exit,pg06_c1,toolchain_catalog,environment_observations):
    exit_sha=_frozen(pg05_exit,"PG05_TO_PG06_EXIT_CANDIDATE_V1","PG06_C2_EXIT_INVALID")
    c1_sha=_frozen(pg06_c1,"PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1","PG06_C2_C1_INVALID")
    if (pg05_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_exit.get("pg05_admitted") is not False
        or pg05_exit.get("pg06_admitted") is not False
        or pg05_exit.get("toolchain_verified") is not False
        or pg05_exit.get("write_allowed") is not False
        or pg05_exit.get("production_authority") is not False
        or pg05_exit.get("handoff_allowed") is not False
        or pg06_c1.get("source_pg05_exit_sha256")!=exit_sha
        or pg06_c1.get("pg06_ready") is not False
        or pg06_c1.get("execution_allowed") is not False
        or pg06_c1.get("production_authority") is not False
        or pg06_c1.get("handoff_allowed") is not False):
        _fail("PG06_C2_UPSTREAM_AUTHORITY_INVALID")
    sols=pg05_exit.get("solutions")
    if not isinstance(sols,list) or not sols:
        _fail("PG06_C2_SOLUTIONS_MISSING")
    sol_ids=[s.get("solution_id") if isinstance(s,dict) else None for s in sols]
    if not _ids(sol_ids):_fail("PG06_C2_SOLUTION_IDS_INVALID")
    if not isinstance(toolchain_catalog,dict) or set(toolchain_catalog)!={
        "schema_version","catalog_ref","catalog_sha256","profile_ref","target_repo",
        "target_base_head_sha","requirements"} or toolchain_catalog["schema_version"]!="PG06_TOOLCHAIN_CATALOG_SELECTION_CANDIDATE_V1":
        _fail("PG06_C2_CATALOG_SHAPE_INVALID")
    cat=toolchain_catalog
    if (not _text(cat["catalog_ref"]) or not _text(cat["profile_ref"])
        or not isinstance(cat["catalog_sha256"],str) or not _SHA.fullmatch(cat["catalog_sha256"])):
        _fail("PG06_C2_CATALOG_SOURCE_INVALID")
    bind=pg05_exit.get("target_binding")
    if (not isinstance(bind,dict)
        or not _text(bind.get("repo_full_name"))
        or not isinstance(bind.get("base_head_sha"),str)
        or not re.fullmatch(r"[0-9a-f]{40}",bind["base_head_sha"])):
        _fail("PG06_C2_TARGET_BINDING_MISSING")
    if cat["target_repo"]!=bind["repo_full_name"] or cat["target_base_head_sha"]!=bind["base_head_sha"]:
        _fail("PG06_C2_TARGET_BINDING_DRIFT")
    required=cat["requirements"]
    if not isinstance(required,list) or not required:
        _fail("PG06_C2_REQUIREMENTS_MISSING")
    req_map={}
    for item in required:
        if not isinstance(item,dict) or set(item)!={
            "tool_id","component","version_exact","source_ref","applies_to_solution_ids"}:
            _fail("PG06_C2_REQUIREMENT_INVALID")
        code=item["tool_id"]
        if (not _text(code) or code in req_map or not _text(item["component"])
            or not _text(item["version_exact"]) or not _text(item["source_ref"])
            or not _ids(item["applies_to_solution_ids"])
            or not set(item["applies_to_solution_ids"]).issubset(sol_ids)):
            _fail("PG06_C2_REQUIREMENT_BINDING_INVALID")
        req_map[code]=item
    covered=set(sid for row in required for sid in row["applies_to_solution_ids"])
    if covered!=set(sol_ids):
        _fail("PG06_C2_SOLUTION_TOOLCHAIN_UNRESOLVED")
    if not isinstance(environment_observations,dict) or set(environment_observations)!={
        "schema_version","environment_ref","observed_target_repo","observed_base_head_sha",
        "observations"} or environment_observations["schema_version"]!="PG06_TOOLCHAIN_ENVIRONMENT_OBSERVATION_CANDIDATE_V1":
        _fail("PG06_C2_OBSERVATION_SHAPE_INVALID")
    env=environment_observations
    if (not _text(env["environment_ref"]) or env["observed_target_repo"]!=cat["target_repo"]
        or env["observed_base_head_sha"]!=cat["target_base_head_sha"]):
        _fail("PG06_C2_ENVIRONMENT_TARGET_DRIFT")
    observations=env["observations"]
    if not isinstance(observations,list):
        _fail("PG06_C2_OBSERVATIONS_INVALID")
    seen={}
    for item in observations:
        if not isinstance(item,dict) or set(item)!={"tool_id","reported_version","availability","evidence_ref"}:
            _fail("PG06_C2_OBSERVATION_INVALID")
        code=item["tool_id"]
        if (not _text(code) or code in seen or code not in req_map
            or item["availability"] not in ("AVAILABLE","UNAVAILABLE","UNKNOWN")
            or not _text(item["evidence_ref"])
            or not isinstance(item["reported_version"],(str,type(None)))):
            _fail("PG06_C2_OBSERVATION_BINDING_INVALID")
        if item["availability"]=="AVAILABLE" and not _text(item["reported_version"]):
            _fail("PG06_C2_AVAILABLE_WITHOUT_VERSION")
        if item["availability"]!="AVAILABLE" and item["reported_version"] is not None:
            _fail("PG06_C2_UNAVAILABLE_VERSION_CONTRADICTION")
        seen[code]=item
    rows=[]
    blocking=[]
    for code in sorted(req_map):
        required=req_map[code]
        observation=seen.get(code)
        if observation is None:
            verdict="BLOCKED_TOOL_UNAVAILABLE"
            reason="MISSING_OBSERVATION"
        elif observation["availability"]!="AVAILABLE":
            verdict="BLOCKED_TOOL_UNAVAILABLE"
            reason="TOOL_"+observation["availability"]
        elif observation["reported_version"]!=required["version_exact"]:
            verdict="BLOCKED_TOOL_UNAVAILABLE"
            reason="EXACT_VERSION_MISMATCH"
        else:
            verdict="MATCH_REPORTED_UNVERIFIED"
            reason="CALLER_SUPPLIED_VERSION_EQUALITY"
        row={
            "tool_id":code,
            "component":required["component"],
            "expected_version":required["version_exact"],
            "reported_version":observation["reported_version"] if observation else None,
            "applies_to_solution_ids":sorted(required["applies_to_solution_ids"]),
            "diagnostic_status":verdict,
            "reason":reason,
            "tool_executed":False,
            "evidence_authenticity_verified":False}
        rows.append(row)
        if verdict=="BLOCKED_TOOL_UNAVAILABLE":
            blocking.append(code)
    solution_rows=[]
    for sid in sorted(sol_ids):
        relevant=[x for x in rows if sid in x["applies_to_solution_ids"]]
        blocked=[x["tool_id"] for x in relevant if x["diagnostic_status"]=="BLOCKED_TOOL_UNAVAILABLE"]
        solution_rows.append({
            "solution_id":sid,
            "required_tool_ids":[x["tool_id"] for x in relevant],
            "blocking_tool_ids":blocked,
            "diagnostic_status":"BLOCKED_TOOL_UNAVAILABLE" if blocked else "MATCH_REPORTED_UNVERIFIED",
            "execution_allowed":False})
    result={
        "schema_version":"PG06_C2_TOOLCHAIN_PREFLIGHT_CANDIDATE_V1",
        "status":"BLOCKED_TOOL_UNAVAILABLE" if blocking else "CANDIDATE_NOT_ADMITTED",
        "source_pg05_exit_sha256":exit_sha,
        "source_pg06_c1_sha256":c1_sha,
        "catalog_selection_sha256":_sha(cat),
        "environment_observation_sha256":_sha(env),
        "catalog_ref":cat["catalog_ref"],
        "profile_ref":cat["profile_ref"],
        "environment_ref":env["environment_ref"],
        "target_binding":{"repo_full_name":cat["target_repo"],
                          "base_head_sha":cat["target_base_head_sha"]},
        "required_toolchains":rows,
        "solutions":solution_rows,
        "blocking_tool_ids":sorted(blocking),
        "catalog_currentness_verified":False,
        "environment_currentness_verified":False,
        "toolchain_execution_verified":False,
        "toolchain_available_attested":False,
        "requirements_auto_inferred":False,
        "pg06_ready":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"CURRENT_TOOLCHAIN_CATALOG_AND_ENVIRONMENT_TOOL_EXECUTION_READBACK"
    }
    result["candidate_sha256"]=_sha(result)
    return result
