"""PG-08_C1: source-only build/compilation evidence projection.

Never runs commands, accesses source trees or authenticates receipts. Both
GPT_NATIVE/CLAUDE_NATIVE and API Worker results follow the same checks,
but executor provenance remains a reported, unverified assertion.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MODES = {"GPT_NATIVE", "CLAUDE_NATIVE", "WORKER_API"}
ALLOWED_RESULTS = {"PASS", "FAIL", "BLOCKED"}

class PG08C1Blocked(ValueError):
    pass

def _block(reason):
    raise PG08C1Blocked(reason)

def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()

def _valid_ref(value):
    return isinstance(value, str) and bool(value.strip())

def _check_source(obj):
    if not isinstance(obj, dict) or obj.get("schema_version") != "PG07_C6_BATCH_EVIDENCE_MANIFEST_CANDIDATE_V1":
        _block("PG08_C1_PG07_C6_SCHEMA_INVALID")
    old = obj.get("candidate_sha256")
    if not isinstance(old, str) or not SHA256.fullmatch(old) or old != _digest(
        {key: value for key, value in obj.items() if key != "candidate_sha256"}
    ):
        _block("PG08_C1_PG07_C6_DIGEST_INVALID")
    if any(obj.get(key) is not False for key in (
        "worker_invoked", "receipt_sealed", "pg12_admitted",
        "dispatch_allowed", "write_allowed", "production_authority",
        "handoff_allowed"
    )):
        _block("PG08_C1_PREMATURE_SOURCE_AUTHORITY")
    if not _valid_ref(obj.get("target_repo")) or not isinstance(obj.get("base_head_sha"), str) or not SHA40.fullmatch(obj["base_head_sha"]):
        _block("PG08_C1_TARGET_BINDING_INVALID")
    batches = obj.get("batches")
    if not isinstance(batches, list) or not batches:
        _block("PG08_C1_NO_BATCHES")
    ids = [x.get("solution_id") for x in batches if isinstance(x, dict)]
    if len(ids) != len(batches) or any(not _valid_ref(x) for x in ids) or len(ids) != len(set(ids)):
        _block("PG08_C1_SOLUTION_SET_INVALID")
    return {x["solution_id"]: x for x in batches}

def prepare_pg08_c1(*, pg07_c6, build_observations):
    """Capture *reported* post-generation build evidence, never a CI PASS.

    build_observations is untrusted caller data. Each solution requires:
      solution_id, executor_mode, executor_result_ref, candidate_head_sha,
      diff_sha256, target_repo, base_head_sha, commands.
    commands is a nonempty list of BUILD/COMPILE observations with:
      command_id, command_ref, tool_name, tool_version, config_sha256,
      execution_receipt_ref, stdout_sha256, stderr_sha256, result, exit_code.
    """
    by_solution = _check_source(pg07_c6)
    if not isinstance(build_observations, list) or len(build_observations) != len(by_solution):
        _block("PG08_C1_BUILD_COVERAGE_INCOMPLETE")
    out = []
    observed = set()
    for row in build_observations:
        if not isinstance(row, dict) or set(row) != {
            "solution_id", "executor_mode", "executor_result_ref",
            "candidate_head_sha", "diff_sha256", "target_repo", "base_head_sha", "commands"
        }:
            _block("PG08_C1_OBSERVATION_SHAPE_INVALID")
        sid = row["solution_id"]
        if sid not in by_solution or sid in observed:
            _block("PG08_C1_OBSERVATION_SOLUTION_DRIFT")
        observed.add(sid)
        source = by_solution[sid]
        if row["executor_mode"] not in MODES or not _valid_ref(row["executor_result_ref"]):
            _block("PG08_C1_EXECUTOR_PROVENANCE_INVALID")
        if (row["target_repo"] != pg07_c6["target_repo"] or row["base_head_sha"] != pg07_c6["base_head_sha"] or
            row["candidate_head_sha"] != source.get("candidate_head_sha_reported") or
            row["diff_sha256"] != source.get("diff_sha256_reported")):
            _block("PG08_C1_PG07_TARGET_OR_DIFF_DRIFT")
        if not SHA40.fullmatch(row["candidate_head_sha"]) or not SHA256.fullmatch(row["diff_sha256"]):
            _block("PG08_C1_TARGET_SHA_INVALID")
        commands = row["commands"]
        if not isinstance(commands, list) or not commands:
            _block("PG08_C1_BUILD_COMMANDS_MISSING")
        seen_commands = set()
        outcomes = []
        for cmd in commands:
            if not isinstance(cmd, dict) or set(cmd) != {
                "command_id", "command_ref", "tool_name", "tool_version",
                "config_sha256", "execution_receipt_ref", "stdout_sha256",
                "stderr_sha256", "result", "exit_code"
            }:
                _block("PG08_C1_COMMAND_SHAPE_INVALID")
            if (not all(_valid_ref(cmd.get(k)) for k in (
                "command_id", "command_ref", "tool_name", "tool_version", "execution_receipt_ref"
            )) or cmd["command_id"] in seen_commands):
                _block("PG08_C1_COMMAND_IDENTITY_INVALID")
            seen_commands.add(cmd["command_id"])
            if any(not isinstance(cmd.get(k), str) or not SHA256.fullmatch(cmd[k]) for k in
                   ("config_sha256", "stdout_sha256", "stderr_sha256")):
                _block("PG08_C1_COMMAND_DIGEST_INVALID")
            if cmd["result"] not in ALLOWED_RESULTS:
                _block("PG08_C1_RESULT_INVALID")
            if (cmd["result"] == "PASS" and (type(cmd["exit_code"]) is not int or cmd["exit_code"] != 0) or
                cmd["result"] == "FAIL" and (type(cmd["exit_code"]) is not int or cmd["exit_code"] == 0) or
                cmd["result"] == "BLOCKED" and cmd["exit_code"] is not None):
                _block("PG08_C1_RESULT_EXIT_CODE_INCONSISTENT")
            outcomes.append(deepcopy(cmd))
        out.append({
            "solution_id": sid,
            "executor_mode_reported": row["executor_mode"],
            "executor_result_ref_reported": row["executor_result_ref"],
            "candidate_head_sha_reported": row["candidate_head_sha"],
            "diff_sha256_reported": row["diff_sha256"],
            "commands_reported": outcomes,
            "reported_build_outcome": "REPORTED_FAIL" if any(c["result"] == "FAIL" for c in outcomes)
               else "REPORTED_BLOCKED" if any(c["result"] == "BLOCKED" for c in outcomes)
               else "REPORTED_PASS_UNVERIFIED",
            "tool_execution_authenticated": False,
            "candidate_clean_tree_verified": False,
            "config_digest_authenticated": False,
            "receipt_authenticated": False
        })
    result = {
        "schema_version": "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_pg07_c6_sha256": pg07_c6["candidate_sha256"],
        "observations_sha256": _digest(build_observations),
        "target_repo": pg07_c6["target_repo"],
        "base_head_sha": pg07_c6["base_head_sha"],
        "solutions": sorted(out, key=lambda x: x["solution_id"]),
        "pg08_c1_pass": False,
        "build_executed_by_this_component": False,
        "tool_version_verified": False,
        "diff_readback_verified": False,
        "executor_provenance_verified": False,
        "pg08_c1_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_HEAD_CLEAN_WORKTREE_BUILD_WITH_SIGNED_OR_ATTESTED_TOOL_RECEIPTS"
    }
    result["candidate_sha256"] = _digest(result)
    return result
