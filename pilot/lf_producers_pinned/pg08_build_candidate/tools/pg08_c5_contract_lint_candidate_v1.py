"""PG-08_C5: source-only contract lint observations, not checks execution.

Spectral/OpenAPI, oasdiff breaking changes, and migrated DB catalog lint
are tracked separately. All claims are caller-supplied and unauthenticated.
"""
import hashlib
import json
import re
from copy import deepcopy

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_KINDS = {"SPECTRAL_OPENAPI", "OASDIFF_BREAKING", "MIGRATED_DB_CATALOG"}
_RESULTS = {"PASS", "FAIL", "BLOCKED"}
_SEVERITIES = {"BLOCK", "WARN", "INFO"}

class PG08C5Blocked(ValueError):
    pass

def _fail(reason):
    raise PG08C5Blocked(reason)

def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()

def _text(value):
    return isinstance(value, str) and bool(value.strip())

def _source(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        _fail("PG08_C5_SOURCE_SCHEMA_INVALID")
    sha = value.get("candidate_sha256")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha) or sha != _digest(
        {k: v for k, v in value.items() if k != "candidate_sha256"}
    ):
        _fail("PG08_C5_SOURCE_DIGEST_INVALID")
    if (value.get("status") != "SOURCE_ONLY_NOT_ADMITTED"
        or value.get("production_authority") is not False
        or value.get("handoff_allowed") is not False):
        _fail("PG08_C5_PREMATURE_SOURCE_AUTHORITY")
    return sha

def _index(rows):
    if not isinstance(rows, list) or not rows:
        _fail("PG08_C5_SOLUTIONS_MISSING")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("solution_id")) or row["solution_id"] in result:
            _fail("PG08_C5_SOLUTION_IDS_INVALID")
        result[row["solution_id"]] = row
    return result

def prepare_pg08_c5(*, pg08_c1, pg08_c4, contract_observations):
    """Receive a strict, untrusted envelope for each solution.

    Each observation provides target identity, selected executor and three
    contract checks. Every check must be REQUIRED or NOT_APPLICABLE; the
    applicability decision carries a source ref but is NOT verified.

    REQUIRED checks: tool and version, command/config/receipt references,
    source baseline digest, candidate contract digest, stdout/stderr digests,
    result and exit code, and findings with severity BLOCK/WARN/INFO.

    NOT_APPLICABLE checks: no fake tool execution or receipt, but a nonempty
    applicability justification reference. The runtime must independently
    prove non-applicability before official checkpoint admission.
    """
    c1sha = _source(pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1")
    c4sha = _source(pg08_c4, "PG08_C4_TEST_AND_LOCAL_FLYWAY_CANDIDATE_V1")
    if (pg08_c4.get("source_pg08_c1_sha256") != c1sha
        or pg08_c1.get("target_repo") != pg08_c4.get("target_repo")
        or pg08_c1.get("base_head_sha") != pg08_c4.get("base_head_sha")
        or any(pg08_c1.get(k) is not False for k in
               ("pg08_c1_pass", "pg08_c1_admitted", "diff_readback_verified"))
        or any(pg08_c4.get(k) is not False for k in
               ("pg08_c4_pass", "pg08_c4_admitted", "receipts_authenticated"))):
        _fail("PG08_C5_SOURCE_CHAIN_DRIFT")
    repo, base = pg08_c1.get("target_repo"), pg08_c1.get("base_head_sha")
    if not _text(repo) or not isinstance(base, str) or not _SHA40.fullmatch(base):
        _fail("PG08_C5_TARGET_INVALID")
    c1 = _index(pg08_c1.get("solutions"))
    c4 = _index(pg08_c4.get("solutions"))
    obs = _index(contract_observations)
    if set(c1) != set(c4) or set(c1) != set(obs):
        _fail("PG08_C5_SOLUTION_COVERAGE_DRIFT")
    result_rows = []
    for sid in sorted(c1):
        row, build, tests = obs[sid], c1[sid], c4[sid]
        if set(row) != {"solution_id", "executor_mode", "target_repo",
                "base_head_sha", "candidate_head_sha", "diff_sha256", "checks"}:
            _fail("PG08_C5_OBSERVATION_SHAPE_INVALID")
        if (row["executor_mode"] != build.get("executor_mode_reported")
            or row["executor_mode"] != tests.get("executor_mode_reported")
            or row["target_repo"] != repo or row["base_head_sha"] != base
            or row["candidate_head_sha"] != build.get("candidate_head_sha_reported")
            or row["candidate_head_sha"] != tests.get("candidate_head_sha_reported")
            or row["diff_sha256"] != build.get("diff_sha256_reported")
            or row["diff_sha256"] != tests.get("diff_sha256_reported")
            or not isinstance(row["candidate_head_sha"], str)
            or not _SHA40.fullmatch(row["candidate_head_sha"])
            or not isinstance(row["diff_sha256"], str)
            or not _SHA256.fullmatch(row["diff_sha256"])):
            _fail("PG08_C5_TARGET_DIFF_OR_MODE_DRIFT")
        checks = row["checks"]
        if not isinstance(checks, list) or len(checks) != len(_KINDS):
            _fail("PG08_C5_REQUIRED_CHECK_COVERAGE_INVALID")
        seen, command_ids, summaries, findings = set(), set(), [], []
        for check in checks:
            if not isinstance(check, dict) or set(check) != {
                "kind", "applicability", "applicability_ref", "command_id",
                "command_ref", "tool_name", "tool_version", "config_sha256",
                "baseline_contract_sha256", "candidate_contract_sha256",
                "execution_receipt_ref", "stdout_sha256", "stderr_sha256",
                "result", "exit_code", "findings"
            }:
                _fail("PG08_C5_CHECK_SHAPE_INVALID")
            kind = check["kind"]
            if kind not in _KINDS or kind in seen or not _text(check["applicability_ref"]):
                _fail("PG08_C5_CHECK_IDENTITY_INVALID")
            seen.add(kind)
            if check["applicability"] == "NOT_APPLICABLE":
                if any(check[k] is not None for k in (
                    "command_id", "command_ref", "tool_name", "tool_version",
                    "config_sha256", "baseline_contract_sha256",
                    "candidate_contract_sha256", "execution_receipt_ref",
                    "stdout_sha256", "stderr_sha256", "result", "exit_code"
                )) or check["findings"] != []:
                    _fail("PG08_C5_NA_MUST_NOT_FABRICATE_EXECUTION")
                summaries.append({"kind": kind, "applicability_reported": "NOT_APPLICABLE",
                    "applicability_ref_reported": check["applicability_ref"],
                    "reported_result": "NOT_RUN",
                    "tool_receipt_authenticated": False})
                continue
            if check["applicability"] != "REQUIRED":
                _fail("PG08_C5_APPLICABILITY_INVALID")
            if (not all(_text(check.get(k)) for k in (
                "command_id", "command_ref", "tool_name", "tool_version",
                "execution_receipt_ref"
            )) or check["command_id"] in command_ids):
                _fail("PG08_C5_COMMAND_IDENTITY_INVALID")
            command_ids.add(check["command_id"])
            if any(not isinstance(check.get(k), str) or not _SHA256.fullmatch(check[k])
                   for k in ("config_sha256", "baseline_contract_sha256",
                              "candidate_contract_sha256", "stdout_sha256", "stderr_sha256")):
                _fail("PG08_C5_CHECK_DIGEST_INVALID")
            status, code = check["result"], check["exit_code"]
            if (status not in _RESULTS or
                (status == "PASS" and (type(code) is not int or code != 0)) or
                (status == "FAIL" and (type(code) is not int or code == 0)) or
                (status == "BLOCKED" and code is not None)):
                _fail("PG08_C5_RESULT_EXIT_INCONSISTENT")
            if not isinstance(check["findings"], list):
                _fail("PG08_C5_FINDINGS_INVALID")
            finding_ids = set()
            for finding in check["findings"]:
                if not isinstance(finding, dict) or set(finding) != {
                    "finding_ref", "severity", "rule_id", "subject_ref"
                }:
                    _fail("PG08_C5_FINDING_SHAPE_INVALID")
                if (not all(_text(finding.get(k)) for k in (
                    "finding_ref", "rule_id", "subject_ref"
                )) or finding["severity"] not in _SEVERITIES
                    or finding["finding_ref"] in finding_ids):
                    _fail("PG08_C5_FINDING_INVALID")
                finding_ids.add(finding["finding_ref"])
                findings.append({"check_kind": kind, **deepcopy(finding)})
            if status == "PASS" and any(f["severity"] == "BLOCK" for f in check["findings"]):
                _fail("PG08_C5_PASS_WITH_BLOCKING_FINDINGS")
            summaries.append({"kind": kind, "applicability_reported": "REQUIRED",
                "applicability_ref_reported": check["applicability_ref"],
                "reported_result": status, "tool_name_reported": check["tool_name"],
                "tool_version_reported": check["tool_version"],
                "command_id_reported": check["command_id"],
                "command_ref_reported": check["command_ref"],
                "config_sha256_reported": check["config_sha256"],
                "baseline_contract_sha256_reported": check["baseline_contract_sha256"],
                "candidate_contract_sha256_reported": check["candidate_contract_sha256"],
                "execution_receipt_ref_reported": check["execution_receipt_ref"],
                "stdout_sha256_reported": check["stdout_sha256"],
                "stderr_sha256_reported": check["stderr_sha256"],
                "exit_code_reported": code, "tool_receipt_authenticated": False})
        if seen != _KINDS:
            _fail("PG08_C5_CHECK_KINDS_MISSING")
        blockers = sorted({f["finding_ref"] for f in findings if f["severity"] == "BLOCK"})
        any_bad = any(c["reported_result"] in ("FAIL", "BLOCKED") for c in summaries)
        any_na = any(c["reported_result"] == "NOT_RUN" for c in summaries)
        diagnosis = ("REPORTED_CONTRACT_BLOCKERS" if blockers else
            "REPORTED_CHECK_FAILURE_OR_BLOCKED" if any_bad else
            "REPORTED_APPLICABILITY_UNVERIFIED" if any_na else
            "REPORTED_ZERO_BLOCK_UNVERIFIED")
        result_rows.append({
            "solution_id": sid,
            "executor_mode_reported": row["executor_mode"],
            "candidate_head_sha_reported": row["candidate_head_sha"],
            "diff_sha256_reported": row["diff_sha256"],
            "checks_reported": sorted(summaries, key=lambda c: c["kind"]),
            "findings_reported": sorted(findings, key=lambda f: (f["check_kind"], f["finding_ref"])),
            "reported_blocker_refs": blockers,
            "reported_diagnostic": diagnosis,
            "applicability_verified": False,
            "contract_baseline_verified": False,
            "migrated_db_catalog_verified": False,
            "ci_configuration_verified": False,
            "receipts_authenticated": False
        })
    result = {
        "schema_version": "PG08_C5_CONTRACT_LINT_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_pg08_c1_sha256": c1sha,
        "source_pg08_c4_sha256": c4sha,
        "target_repo": repo, "base_head_sha": base,
        "observations_sha256": _digest(contract_observations),
        "solutions": result_rows,
        "contract_checks_executed_by_this_component": False,
        "diff_readback_verified": False,
        "applicability_verified": False,
        "migrated_db_catalog_verified": False,
        "receipts_authenticated": False,
        "pg08_c5_pass": False,
        "pg08_c5_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_HEAD_SPECTRAL_OASDIFF_DB_CATALOG_REAL_CHECK_RECEIPTS"
    }
    result["candidate_sha256"] = _digest(result)
    return result
