"""PG-08_C3 source-only typecheck observation projection (never invokes tools)."""
import hashlib
import json
import re
from copy import deepcopy

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PROFILES = {"TSC_STRICT", "JAVAC", "MYPY"}
RESULTS = {"PASS", "FAIL", "BLOCKED"}

class PG08C3Blocked(ValueError):
    pass

def fail(reason):
    raise PG08C3Blocked(reason)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()

def text_value(value):
    return isinstance(value, str) and bool(value.strip())

def source_sha(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        fail("PG08_C3_SOURCE_SCHEMA_INVALID")
    actual = value.get("candidate_sha256")
    if not isinstance(actual, str) or not SHA256.fullmatch(actual) or actual != digest(
        {key: val for key, val in value.items() if key != "candidate_sha256"}
    ):
        fail("PG08_C3_SOURCE_DIGEST_INVALID")
    if (value.get("status") != "SOURCE_ONLY_NOT_ADMITTED"
        or value.get("production_authority") is not False
        or value.get("handoff_allowed") is not False):
        fail("PG08_C3_PREMATURE_AUTHORITY")
    return actual

def indexed(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG08_C3_SOLUTIONS_MISSING")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not text_value(row.get("solution_id")) or row["solution_id"] in result:
            fail("PG08_C3_SOLUTION_INVALID")
        result[row["solution_id"]] = row
    return result

def prepare_pg08_c3(*, pg08_c1, pg08_c2, typecheck_observations):
    """Produce unverified typecheck report, with one check per selected profile.

    A caller supplies required_profiles (TSC_STRICT, JAVAC, MYPY) based on
    target tooling; selection is NOT trusted or executed by this function.
    """
    c1sha = source_sha(pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1")
    c2sha = source_sha(pg08_c2, "PG08_C2_FORMAT_LINT_DELTA_CANDIDATE_V1")
    if (pg08_c2.get("source_pg08_c1_sha256") != c1sha
        or pg08_c1.get("target_repo") != pg08_c2.get("target_repo")
        or pg08_c1.get("base_head_sha") != pg08_c2.get("base_head_sha")
        or any(pg08_c1.get(x) is not False for x in ("pg08_c1_pass","pg08_c1_admitted","diff_readback_verified"))
        or any(pg08_c2.get(x) is not False for x in ("pg08_c2_pass","pg08_c2_admitted","ci_configuration_verified"))):
        fail("PG08_C3_UPSTREAM_CHAIN_INVALID")
    repo, base = pg08_c1.get("target_repo"), pg08_c1.get("base_head_sha")
    if not text_value(repo) or not isinstance(base,str) or not SHA40.fullmatch(base):
        fail("PG08_C3_TARGET_INVALID")
    c1, c2, obs = indexed(pg08_c1.get("solutions")), indexed(pg08_c2.get("solutions")), indexed(typecheck_observations)
    if set(c1) != set(c2) or set(c1) != set(obs):
        fail("PG08_C3_SOLUTION_COVERAGE_INVALID")
    output = []
    for sid in sorted(c1):
        row, build, lint = obs[sid], c1[sid], c2[sid]
        if set(row) != {"solution_id","executor_mode","target_repo","base_head_sha",
                        "candidate_head_sha","diff_sha256","required_profiles","checks"}:
            fail("PG08_C3_OBSERVATION_SHAPE_INVALID")
        if (row["executor_mode"] != build.get("executor_mode_reported")
            or row["executor_mode"] != lint.get("executor_mode_reported")
            or row["target_repo"] != repo or row["base_head_sha"] != base
            or row["candidate_head_sha"] != build.get("candidate_head_sha_reported")
            or row["candidate_head_sha"] != lint.get("candidate_head_sha_reported")
            or row["diff_sha256"] != build.get("diff_sha256_reported")
            or row["diff_sha256"] != lint.get("diff_sha256_reported")
            or not isinstance(row["candidate_head_sha"],str) or not SHA40.fullmatch(row["candidate_head_sha"])
            or not isinstance(row["diff_sha256"],str) or not SHA256.fullmatch(row["diff_sha256"])):
            fail("PG08_C3_CANDIDATE_OR_EXECUTOR_DRIFT")
        selected = row["required_profiles"]
        if not isinstance(selected,list) or not selected or any(x not in PROFILES for x in selected) or len(set(selected)) != len(selected):
            fail("PG08_C3_PROFILE_SELECTION_INVALID")
        checks = row["checks"]
        if not isinstance(checks,list) or len(checks) != len(selected):
            fail("PG08_C3_CHECK_COVERAGE_INVALID")
        used, command_ids, checked = set(),set(),[]
        for check in checks:
            if not isinstance(check,dict) or set(check) != {"profile","command_id","command_ref","tool_name","tool_version",
                "config_sha256","execution_receipt_ref","stdout_sha256","stderr_sha256","result","exit_code","diagnostic_refs"}:
                fail("PG08_C3_CHECK_SHAPE_INVALID")
            profile = check["profile"]
            if (profile not in selected or profile in used or check["command_id"] in command_ids
                or not all(text_value(check.get(k)) for k in ("command_id","command_ref","tool_name","tool_version","execution_receipt_ref"))):
                fail("PG08_C3_CHECK_IDENTITY_INVALID")
            used.add(profile)
            command_ids.add(check["command_id"])
            if any(not isinstance(check.get(k),str) or not SHA256.fullmatch(check[k]) for k in ("config_sha256","stdout_sha256","stderr_sha256")):
                fail("PG08_C3_CHECK_DIGEST_INVALID")
            state, code = check["result"],check["exit_code"]
            if (state not in RESULTS
                or (state=="PASS" and (type(code) is not int or code!=0))
                or (state=="FAIL" and (type(code) is not int or code==0))
                or (state=="BLOCKED" and code is not None)):
                fail("PG08_C3_EXIT_CODE_INVALID")
            diags = check["diagnostic_refs"]
            if (not isinstance(diags,list) or any(not text_value(d) for d in diags)
                or len(diags)!=len(set(diags)) or (state=="PASS" and diags)):
                fail("PG08_C3_DIAGNOSTICS_INVALID")
            checked.append(deepcopy(check))
        if used != set(selected):
            fail("PG08_C3_PROFILE_COVERAGE_DRIFT")
        states = [x["result"] for x in checked]
        output.append({"solution_id":sid, "executor_mode_reported":row["executor_mode"],
            "candidate_head_sha_reported":row["candidate_head_sha"],
            "diff_sha256_reported":row["diff_sha256"],
            "required_profiles_reported":sorted(selected),
            "checks_reported":sorted(checked,key=lambda x:x["profile"]),
            "reported_diagnostic": "REPORTED_TYPECHECK_FAILED" if "FAIL" in states
                else "REPORTED_TYPECHECK_BLOCKED" if "BLOCKED" in states
                else "REPORTED_TYPECHECK_PASS_UNVERIFIED",
            "profile_selection_verified":False,"tool_execution_authenticated":False,
            "configuration_verified":False,"receipt_authenticated":False})
    result={"schema_version":"PG08_C3_TYPECHECK_CANDIDATE_V1","status":"SOURCE_ONLY_NOT_ADMITTED",
        "source_pg08_c1_sha256":c1sha,"source_pg08_c2_sha256":c2sha,
        "target_repo":repo,"base_head_sha":base,"observations_sha256":digest(typecheck_observations),
        "solutions":output,"typecheck_executed_by_this_component":False,
        "toolchain_selection_verified":False,"diff_readback_verified":False,
        "configuration_verified":False,"receipts_authenticated":False,
        "pg08_c3_pass":False,"pg08_c3_admitted":False,
        "handoff_allowed":False,"production_authority":False,
        "next_gate":"EXACT_CANDIDATE_TYPECHECK_AND_ATTESTED_RECEIPT_READBACK"}
    result["candidate_sha256"]=digest(result)
    return result
