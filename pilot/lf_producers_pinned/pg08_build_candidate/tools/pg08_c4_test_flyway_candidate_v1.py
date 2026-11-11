"""PG-08_C4 candidate: focal unit/smoke and local Flyway evidence envelope.

Source-only. Does not execute tests, start PostgreSQL, or invoke Flyway.
Every observation is caller supplied and UNAUTHENTICATED. No PASS authority.
"""
import hashlib
import json
import re
from copy import deepcopy

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KIND = {"UNIT_FOCAL", "SMOKE", "FLYWAY_APPLY", "FLYWAY_ROLLBACK", "FLYWAY_REAPPLY"}
_RESULT = {"PASS", "FAIL", "BLOCKED"}
_SEQUENCE = ["FLYWAY_APPLY", "FLYWAY_ROLLBACK", "FLYWAY_REAPPLY"]


class PG08C4Blocked(ValueError):
    pass


def _fail(reason):
    raise PG08C4Blocked(reason)


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _ref(value):
    return isinstance(value, str) and bool(value.strip())


def _source(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        _fail("PG08_C4_SOURCE_SCHEMA_INVALID")
    sha = value.get("candidate_sha256")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha) or sha != _digest(
        {k: v for k, v in value.items() if k != "candidate_sha256"}
    ):
        _fail("PG08_C4_SOURCE_DIGEST_INVALID")
    if (value.get("status") != "SOURCE_ONLY_NOT_ADMITTED" or
        value.get("handoff_allowed") is not False or
        value.get("production_authority") is not False):
        _fail("PG08_C4_SOURCE_PREMATURE_AUTHORITY")
    return sha


def _index(rows):
    if not isinstance(rows, list) or not rows:
        _fail("PG08_C4_SOLUTION_SET_MISSING")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _ref(row.get("solution_id")) or row["solution_id"] in result:
            _fail("PG08_C4_SOLUTION_SET_INVALID")
        result[row["solution_id"]] = row
    return result


def prepare_pg08_c4(*, pg08_c1, pg08_c3, test_observations):
    """Project reported execution data, not verified proof.

    Each observation:
      solution_id, executor_mode, target_repo, base_head_sha,
      candidate_head_sha, diff_sha256, flyway_applicability,
      flyway_applicability_ref, local_pg_isolation_ref, checks.

    flyway_applicability: REQUIRED or NOT_APPLICABLE. For REQUIRED, checks
    must include FLYWAY_APPLY/ROLLBACK/REAPPLY in that exact order; all
    refer to the SAME local PostgreSQL isolation ref. For NOT_APPLICABLE,
    only UNIT_FOCAL and SMOKE are required, and applicability is unverified.

    Each check:
      kind, command_id, command_ref, tool_name, tool_version,
      config_sha256, execution_receipt_ref, stdout_sha256, stderr_sha256,
      result, exit_code, diagnostic_refs, runtime_target_ref.

    All values come from the caller. No real command or migration is run.
    """
    c1_sha = _source(pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1")
    c3_sha = _source(pg08_c3, "PG08_C3_TYPECHECK_CANDIDATE_V1")
    if pg08_c3.get("source_pg08_c1_sha256") != c1_sha:
        _fail("PG08_C4_SOURCE_CHAIN_DRIFT")
    for obj, fields in (
        (pg08_c1, ("pg08_c1_pass", "pg08_c1_admitted", "build_executed_by_this_component")),
        (pg08_c3, ("pg08_c3_pass", "pg08_c3_admitted", "typecheck_executed_by_this_component")),
    ):
        if any(obj.get(field) is not False for field in fields):
            _fail("PG08_C4_PREMATURE_PASS")
    repo, base = pg08_c1.get("target_repo"), pg08_c1.get("base_head_sha")
    if (not _ref(repo) or not isinstance(base, str) or not _SHA40.fullmatch(base)
        or pg08_c3.get("target_repo") != repo or pg08_c3.get("base_head_sha") != base):
        _fail("PG08_C4_TARGET_DRIFT")
    c1, c3, observations = (
        _index(pg08_c1.get("solutions")),
        _index(pg08_c3.get("solutions")),
        _index(test_observations),
    )
    if set(c1) != set(c3) or set(c1) != set(observations):
        _fail("PG08_C4_COVERAGE_DRIFT")
    results = []
    for sid in sorted(c1):
        b, t, row = c1[sid], c3[sid], observations[sid]
        if set(row) != {
            "solution_id", "executor_mode", "target_repo", "base_head_sha",
            "candidate_head_sha", "diff_sha256", "flyway_applicability",
            "flyway_applicability_ref", "local_pg_isolation_ref", "checks"
        }:
            _fail("PG08_C4_OBSERVATION_SHAPE_INVALID")
        if (row["executor_mode"] != b.get("executor_mode_reported") or
            row["executor_mode"] != t.get("executor_mode_reported") or
            row["target_repo"] != repo or row["base_head_sha"] != base or
            row["candidate_head_sha"] != b.get("candidate_head_sha_reported") or
            row["candidate_head_sha"] != t.get("candidate_head_sha_reported") or
            row["diff_sha256"] != b.get("diff_sha256_reported") or
            row["diff_sha256"] != t.get("diff_sha256_reported") or
            not isinstance(row["candidate_head_sha"], str) or
            not _SHA40.fullmatch(row["candidate_head_sha"]) or
            not isinstance(row["diff_sha256"], str) or
            not _SHA256.fullmatch(row["diff_sha256"])):
            _fail("PG08_C4_CANDIDATE_OR_EXECUTOR_DRIFT")
        applicability = row["flyway_applicability"]
        if applicability not in {"REQUIRED", "NOT_APPLICABLE"} or not _ref(row["flyway_applicability_ref"]):
            _fail("PG08_C4_FLYWAY_APPLICABILITY_INVALID")
        is_pg = applicability == "REQUIRED"
        if (is_pg and not _ref(row["local_pg_isolation_ref"])) or (
            not is_pg and row["local_pg_isolation_ref"] is not None
        ):
            _fail("PG08_C4_LOCAL_PG_ISOLATION_INVALID")
        checks = row["checks"]
        needed = {"UNIT_FOCAL", "SMOKE"} | (set(_SEQUENCE) if is_pg else set())
        if not isinstance(checks, list) or len(checks) != len(needed):
            _fail("PG08_C4_REQUIRED_CHECKS_MISSING")
        seen, command_ids, check_rows = set(), set(), []
        flyway_order = []
        for check in checks:
            if not isinstance(check, dict) or set(check) != {
                "kind", "command_id", "command_ref", "tool_name",
                "tool_version", "config_sha256", "execution_receipt_ref",
                "stdout_sha256", "stderr_sha256", "result", "exit_code",
                "diagnostic_refs", "runtime_target_ref"
            }:
                _fail("PG08_C4_CHECK_SHAPE_INVALID")
            kind = check["kind"]
            if (kind not in needed or kind in seen or
                not all(_ref(check.get(field)) for field in (
                    "command_id", "command_ref", "tool_name", "tool_version",
                    "execution_receipt_ref", "runtime_target_ref"
                )) or check["command_id"] in command_ids):
                _fail("PG08_C4_CHECK_IDENTITY_INVALID")
            seen.add(kind)
            command_ids.add(check["command_id"])
            if any(not isinstance(check.get(field), str) or
                   not _SHA256.fullmatch(check[field]) for field in (
                       "config_sha256", "stdout_sha256", "stderr_sha256")):
                _fail("PG08_C4_CHECK_DIGEST_INVALID")
            status, code = check["result"], check["exit_code"]
            if (status not in _RESULT or
                (status == "PASS" and (type(code) is not int or code != 0)) or
                (status == "FAIL" and (type(code) is not int or code == 0)) or
                (status == "BLOCKED" and code is not None)):
                _fail("PG08_C4_EXIT_STATUS_INVALID")
            diags = check["diagnostic_refs"]
            if (not isinstance(diags, list) or any(not _ref(x) for x in diags) or
                len(set(diags)) != len(diags) or (status == "PASS" and diags)):
                _fail("PG08_C4_DIAGNOSTICS_INVALID")
            if kind in _SEQUENCE:
                flyway_order.append(kind)
                if check["runtime_target_ref"] != row["local_pg_isolation_ref"]:
                    _fail("PG08_C4_FLYWAY_TARGET_NOT_LOCAL_BOUND")
            check_rows.append(deepcopy(check))
        if seen != needed or (is_pg and flyway_order != _SEQUENCE):
            _fail("PG08_C4_MISSING_OR_OUT_OF_ORDER_FLYWAY")
        # A declared PASS after an earlier FAIL/BLOCKED is not a valid
        # apply/rollback/reapply evidence chain, even as a candidate.
        if is_pg:
            stages = {c["kind"]: c["result"] for c in check_rows}
            for previous, later in zip(_SEQUENCE, _SEQUENCE[1:]):
                if stages[previous] != "PASS" and stages[later] == "PASS":
                    _fail("PG08_C4_FLYWAY_SEQUENCE_CONTRADICTION")
        statuses = [x["result"] for x in check_rows]
        results.append({
            "solution_id": sid,
            "executor_mode_reported": row["executor_mode"],
            "candidate_head_sha_reported": row["candidate_head_sha"],
            "diff_sha256_reported": row["diff_sha256"],
            "flyway_applicability_reported": applicability,
            "flyway_applicability_ref_reported": row["flyway_applicability_ref"],
            "local_pg_isolation_ref_reported": row["local_pg_isolation_ref"],
            "checks_reported": check_rows,
            "reported_diagnostic": (
                "REPORTED_TEST_FAILURE" if "FAIL" in statuses else
                "REPORTED_TEST_BLOCKED" if "BLOCKED" in statuses else
                "REPORTED_TEST_PASS_UNVERIFIED"
            ),
            "migration_applicability_verified": False,
            "local_postgresql_verified": False,
            "migration_order_verified_by_runtime": False,
            "receipts_authenticated": False
        })
    result = {
        "schema_version": "PG08_C4_TEST_AND_LOCAL_FLYWAY_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_pg08_c1_sha256": c1_sha,
        "source_pg08_c3_sha256": c3_sha,
        "target_repo": repo,
        "base_head_sha": base,
        "observations_sha256": _digest(test_observations),
        "solutions": results,
        "tests_executed_by_this_component": False,
        "flyway_executed_by_this_component": False,
        "local_postgresql_verified": False,
        "migration_applicability_verified": False,
        "diff_readback_verified": False,
        "receipts_authenticated": False,
        "pg08_c4_pass": False,
        "pg08_c4_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_HEAD_REAL_UNIT_SMOKE_LOCAL_FLYWAY_AND_RECEIPT_READBACK"
    }
    result["candidate_sha256"] = _digest(result)
    return result
