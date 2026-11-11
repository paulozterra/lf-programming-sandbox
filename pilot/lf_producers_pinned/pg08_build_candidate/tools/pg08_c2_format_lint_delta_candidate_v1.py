"""PG-08_C2: untrusted format/lint observation projection against PG-06_C4 baseline.

No formatters, linters or Git operations are executed. A matching violation_ref
is *reported* as preexisting, never cryptographically proved to be the same
finding. PASS/authority are never granted by this component.
"""
import hashlib
import json
import re
from copy import deepcopy

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_KINDS = {"FORMAT", "LINT"}
_RESULTS = {"PASS", "FAIL", "BLOCKED"}
_SEVERITIES = {"BLOCK", "WARN", "INFO"}

class PG08C2Blocked(ValueError):
    pass

def _fail(code):
    raise PG08C2Blocked(code)

def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()

def _text(value):
    return isinstance(value, str) and bool(value.strip())

def _frozen(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        _fail("PG08_C2_SOURCE_SCHEMA_INVALID")
    sha = value.get("candidate_sha256")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha) or sha != _hash(
        {k: v for k, v in value.items() if k != "candidate_sha256"}
    ):
        _fail("PG08_C2_SOURCE_DIGEST_INVALID")
    return sha

def _indexed(rows, code):
    if not isinstance(rows, list) or not rows:
        _fail(code)
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("solution_id")) or row["solution_id"] in result:
            _fail(code)
        result[row["solution_id"]] = row
    return result

def prepare_pg08_c2(*, pg06_c4, pg08_c1, lint_observations):
    """Produce per-solution reported new-blocker deltas; never an official PASS.

    lint_observations is a list with one row per solution. Fields:
      solution_id, executor_mode, candidate_head_sha, diff_sha256, target_repo,
      base_head_sha, checks.
    Each check: kind (FORMAT/LINT), command_id, command_ref, tool_name,
      tool_version, config_sha256, execution_receipt_ref, stdout_sha256,
      stderr_sha256, result, exit_code, findings.
    Each finding: violation_ref, severity, rule_id, path, line (positive int or
      null), and scope (DIFF or REPOSITORY). Stable violation_ref values must
      be based on identical rule/path/location semantics across both runs.
    """
    c4_sha = _frozen(pg06_c4, "PG06_C4_BASELINE_BUILD_LINT_CANDIDATE_V1")
    c1_sha = _frozen(pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1")
    if (pg06_c4.get("status") != "CANDIDATE_NOT_ADMITTED" or
        pg08_c1.get("status") != "SOURCE_ONLY_NOT_ADMITTED" or
        any(pg06_c4.get(k) is not False for k in (
            "unchanged_target_verified", "receipts_authenticated", "pg06_ready",
            "write_allowed", "production_authority", "handoff_allowed")) or
        any(pg08_c1.get(k) is not False for k in (
            "pg08_c1_pass", "build_executed_by_this_component", "pg08_c1_admitted",
            "diff_readback_verified", "executor_provenance_verified",
            "handoff_allowed", "production_authority"))):
        _fail("PG08_C2_PREMATURE_AUTHORITY")
    target = pg06_c4.get("target_binding")
    if (not isinstance(target, dict) or not _text(target.get("repo_full_name")) or
        not isinstance(target.get("base_head_sha"), str) or
        not _SHA40.fullmatch(target["base_head_sha"]) or
        pg08_c1.get("target_repo") != target["repo_full_name"] or
        pg08_c1.get("base_head_sha") != target["base_head_sha"]):
        _fail("PG08_C2_TARGET_BINDING_DRIFT")
    c1_sol = _indexed(pg08_c1.get("solutions"), "PG08_C2_C1_SOLUTIONS_INVALID")
    c4_sol = _indexed(pg06_c4.get("solutions"), "PG08_C2_C4_SOLUTIONS_INVALID")
    if set(c1_sol) != set(c4_sol):
        _fail("PG08_C2_BASELINE_SOLUTION_DRIFT")
    baseline = {}
    for item in pg06_c4.get("command_reports", []):
        if not isinstance(item, dict) or item.get("solution_id") not in c1_sol:
            _fail("PG08_C2_BASELINE_REPORT_INVALID")
        if item.get("kind") != "LINT":
            continue
        sid = item["solution_id"]
        if sid in baseline:
            _fail("PG08_C2_BASELINE_LINT_DUPLICATE")
        violations = item.get("preexisting_violation_refs")
        if (not isinstance(violations, list) or
            any(not _text(v) for v in violations) or
            len(violations) != len(set(violations))):
            _fail("PG08_C2_BASELINE_VIOLATIONS_INVALID")
        baseline[sid] = set(violations)
    if set(baseline) != set(c1_sol):
        _fail("PG08_C2_BASELINE_LINT_INCOMPLETE")
    rows = _indexed(lint_observations, "PG08_C2_OBSERVATIONS_INVALID")
    if set(rows) != set(c1_sol):
        _fail("PG08_C2_OBSERVATION_COVERAGE_DRIFT")
    result_rows = []
    for sid in sorted(c1_sol):
        row, build = rows[sid], c1_sol[sid]
        if not isinstance(row, dict) or set(row) != {
            "solution_id", "executor_mode", "candidate_head_sha", "diff_sha256",
            "target_repo", "base_head_sha", "checks"
        }:
            _fail("PG08_C2_OBSERVATION_SHAPE_INVALID")
        if (row["executor_mode"] != build.get("executor_mode_reported") or
            row["candidate_head_sha"] != build.get("candidate_head_sha_reported") or
            row["diff_sha256"] != build.get("diff_sha256_reported") or
            row["target_repo"] != target["repo_full_name"] or
            row["base_head_sha"] != target["base_head_sha"] or
            not isinstance(row["candidate_head_sha"], str) or
            not _SHA40.fullmatch(row["candidate_head_sha"]) or
            not isinstance(row["diff_sha256"], str) or
            not _SHA256.fullmatch(row["diff_sha256"])):
            _fail("PG08_C2_CANDIDATE_IDENTITY_DRIFT")
        checks = row["checks"]
        if not isinstance(checks, list) or len(checks) != 2:
            _fail("PG08_C2_FORMAT_LINT_COVERAGE_INVALID")
        kinds, cmd_ids, all_findings, reported_results = set(), set(), [], []
        for cmd in checks:
            if not isinstance(cmd, dict) or set(cmd) != {
                "kind", "command_id", "command_ref", "tool_name", "tool_version",
                "config_sha256", "execution_receipt_ref", "stdout_sha256",
                "stderr_sha256", "result", "exit_code", "findings"
            }:
                _fail("PG08_C2_COMMAND_SHAPE_INVALID")
            if (cmd["kind"] not in _KINDS or cmd["kind"] in kinds or
                not all(_text(cmd.get(k)) for k in (
                    "command_id", "command_ref", "tool_name", "tool_version",
                    "execution_receipt_ref")) or cmd["command_id"] in cmd_ids or
                any(not isinstance(cmd.get(k), str) or not _SHA256.fullmatch(cmd[k])
                    for k in ("config_sha256", "stdout_sha256", "stderr_sha256"))):
                _fail("PG08_C2_COMMAND_IDENTITY_INVALID")
            kinds.add(cmd["kind"])
            cmd_ids.add(cmd["command_id"])
            code = cmd["exit_code"]
            if (cmd["result"] not in _RESULTS or
                (cmd["result"] == "PASS" and (type(code) is not int or code != 0)) or
                (cmd["result"] == "FAIL" and (type(code) is not int or code == 0)) or
                (cmd["result"] == "BLOCKED" and code is not None)):
                _fail("PG08_C2_COMMAND_RESULT_INVALID")
            findings = cmd["findings"]
            if not isinstance(findings, list):
                _fail("PG08_C2_FINDINGS_INVALID")
            refs = set()
            for finding in findings:
                if not isinstance(finding, dict) or set(finding) != {
                    "violation_ref", "severity", "rule_id", "path", "line", "scope"
                }:
                    _fail("PG08_C2_FINDING_SHAPE_INVALID")
                if (not all(_text(finding.get(k)) for k in
                            ("violation_ref", "rule_id", "path")) or
                    finding["severity"] not in _SEVERITIES or
                    finding["scope"] not in {"DIFF", "REPOSITORY"} or
                    (finding["line"] is not None and
                     (type(finding["line"]) is not int or finding["line"] <= 0)) or
                    finding["violation_ref"] in refs or
                    finding["path"].startswith("/") or
                    ".." in finding["path"].split("/") or
                    "\\" in finding["path"]):
                    _fail("PG08_C2_FINDING_IDENTITY_INVALID")
                refs.add(finding["violation_ref"])
                classification = ("REPORTED_PREEXISTING" if
                                  finding["violation_ref"] in baseline[sid]
                                  else "REPORTED_NEW")
                all_findings.append({**deepcopy(finding),
                                     "reported_classification": classification,
                                     "check_kind": cmd["kind"]})
            if cmd["result"] == "PASS" and any(x["severity"] == "BLOCK" for x in findings):
                _fail("PG08_C2_PASS_WITH_BLOCK_FINDINGS")
            reported_results.append({"kind": cmd["kind"],
                                     "result": cmd["result"],
                                     "exit_code": code,
                                     "tool_name": cmd["tool_name"],
                                     "tool_version": cmd["tool_version"],
                                     "config_sha256": cmd["config_sha256"],
                                     "execution_receipt_ref": cmd["execution_receipt_ref"],
                                     "command_id": cmd["command_id"],
                                     "command_ref": cmd["command_ref"],
                                     "stdout_sha256": cmd["stdout_sha256"],
                                     "stderr_sha256": cmd["stderr_sha256"]})
        if kinds != _KINDS:
            _fail("PG08_C2_FORMAT_LINT_COVERAGE_INVALID")
        new_block = sorted({
            f["violation_ref"] for f in all_findings
            if f["reported_classification"] == "REPORTED_NEW" and f["severity"] == "BLOCK"
        })
        result_rows.append({
            "solution_id": sid,
            "executor_mode_reported": row["executor_mode"],
            "candidate_head_sha_reported": row["candidate_head_sha"],
            "diff_sha256_reported": row["diff_sha256"],
            "baseline_lint_violation_refs_reported": sorted(baseline[sid]),
            "findings_reported": sorted(all_findings,
                                        key=lambda f:(f["check_kind"], f["violation_ref"])),
            "checks_reported": sorted(reported_results,key=lambda x:x["kind"]),
            "reported_new_blockers": new_block,
            "reported_diagnostic": "REPORTED_NEW_BLOCKERS" if new_block
              else "REPORTED_CHECK_NOT_PASS" if any(c["result"] != "PASS" for c in checks)
              else "REPORTED_NO_NEW_BLOCKERS_UNVERIFIED",
            "baseline_currentness_verified": False,
            "finding_equivalence_verified": False,
            "ci_configuration_verified": False,
            "diff_scoped_execution_verified": False,
            "receipts_authenticated": False
        })
    result = {
        "schema_version": "PG08_C2_FORMAT_LINT_DELTA_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_pg06_c4_sha256": c4_sha,
        "source_pg08_c1_sha256": c1_sha,
        "target_repo": target["repo_full_name"],
        "base_head_sha": target["base_head_sha"],
        "observations_sha256": _hash(lint_observations),
        "solutions": result_rows,
        "pg08_c2_pass": False,
        "format_lint_executed_by_this_component": False,
        "baseline_currentness_verified": False,
        "diff_readback_verified": False,
        "ci_configuration_verified": False,
        "receipts_authenticated": False,
        "pg08_c2_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "REAL_CI_FORMAT_LINT_EXACT_DIFF_BASELINE_AND_RECEIPT_READBACK"
    }
    result["candidate_sha256"] = _hash(result)
    return result
