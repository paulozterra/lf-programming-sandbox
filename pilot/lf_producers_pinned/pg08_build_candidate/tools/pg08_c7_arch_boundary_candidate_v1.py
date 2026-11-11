"""PG-08_C7: source-only architectural boundary evidence, never a PASS.

Contracts: D15 public module APIs/events, Spring Modulith verify()/ArchUnit.
No Java tools, CI, repository checkout or model invocation occurs here.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
KINDS = {"SPRING_MODULITH_VERIFY", "ARCHUNIT"}
RESULTS = {"PASS", "FAIL", "BLOCKED"}
SEVERITIES = {"BLOCK", "WARN", "INFO"}


class PG08C7Blocked(ValueError):
    pass


def fail(code):
    raise PG08C7Blocked(code)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
        ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def ref(value):
    return isinstance(value, str) and bool(value.strip())


def frozen(obj, schema):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG08_C7_UPSTREAM_SCHEMA_INVALID")
    sha = obj.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {k: v for k, v in obj.items() if k != "candidate_sha256"}
    ):
        fail("PG08_C7_UPSTREAM_DIGEST_INVALID")
    if (obj.get("status") != "SOURCE_ONLY_NOT_ADMITTED" or
        obj.get("production_authority") is not False or
        obj.get("handoff_allowed") is not False):
        fail("PG08_C7_PREMATURE_AUTHORITY")
    return sha


def indexed(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG08_C7_SOLUTIONS_MISSING")
    output = {}
    for row in rows:
        if not isinstance(row, dict) or not ref(row.get("solution_id")) or row["solution_id"] in output:
            fail("PG08_C7_SOLUTION_ID_INVALID")
        output[row["solution_id"]] = row
    return output


def prepare_pg08_c7(*, pg08_c1, pg08_c6, architecture_observations):
    """Project reports per solution, leaving applicability and execution unverified.

    A report declares target identity, executor_mode and checks. Exactly two
    checks are mandatory to describe, each REQUIRED or NOT_APPLICABLE.
    The runtime must independently establish whether a Java module boundary
    test is applicable, and whether additional architecture suites are needed.
    """
    c1sha = frozen(pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1")
    c6sha = frozen(pg08_c6, "PG08_C6_CHECK_RECEIPT_FEEDBACK_CANDIDATE_V1")
    if (pg08_c6.get("source_digests", {}).get("c1") != c1sha or
        pg08_c1.get("target_repo") != pg08_c6.get("target_repo") or
        pg08_c1.get("base_head_sha") != pg08_c6.get("base_head_sha") or
        any(pg08_c1.get(k) is not False for k in ("pg08_c1_pass", "pg08_c1_admitted")) or
        any(pg08_c6.get(k) is not False for k in ("pg08_c6_pass", "pg08_c6_admitted",
            "tool_execution_verified", "receipts_authenticated")) or
        pg08_c6.get("feedback_only") is not True):
        fail("PG08_C7_SOURCE_CHAIN_OR_AUTHORITY_INVALID")
    repo, base = pg08_c1.get("target_repo"), pg08_c1.get("base_head_sha")
    if not ref(repo) or not isinstance(base, str) or not SHA40.fullmatch(base):
        fail("PG08_C7_TARGET_INVALID")
    source, receipts, observations = (
        indexed(pg08_c1.get("solutions")),
        indexed(pg08_c6.get("solutions")),
        indexed(architecture_observations),
    )
    if set(source) != set(receipts) or set(source) != set(observations):
        fail("PG08_C7_SOLUTION_COVERAGE_DRIFT")

    results = []
    for sid in sorted(source):
        build, receipt, obs = source[sid], receipts[sid], observations[sid]
        if set(obs) != {"solution_id", "executor_mode", "target_repo",
                        "base_head_sha", "candidate_head_sha", "diff_sha256",
                        "architecture_profile_ref", "checks"}:
            fail("PG08_C7_OBSERVATION_SHAPE_INVALID")
        head, diff, mode = (
            build.get("candidate_head_sha_reported"),
            build.get("diff_sha256_reported"),
            build.get("executor_mode_reported"),
        )
        if (obs["target_repo"] != repo or obs["base_head_sha"] != base or
            obs["candidate_head_sha"] != head or obs["diff_sha256"] != diff or
            obs["executor_mode"] != mode or
            receipt.get("candidate_head_sha_reported") != head or
            receipt.get("diff_sha256_reported") != diff or
            receipt.get("executor_mode_reported") != mode or
            not isinstance(head, str) or not SHA40.fullmatch(head) or
            not isinstance(diff, str) or not SHA256.fullmatch(diff) or
            mode not in ("GPT_NATIVE", "CLAUDE_NATIVE", "WORKER_API") or
            not ref(obs["architecture_profile_ref"])):
            fail("PG08_C7_CANDIDATE_IDENTITY_DRIFT")
        checks = obs["checks"]
        if not isinstance(checks, list) or len(checks) != 2:
            fail("PG08_C7_ARCH_CHECK_COVERAGE_INVALID")
        seen, ids, reported, blockers = set(), set(), [], []
        for check in checks:
            if not isinstance(check, dict) or set(check) != {
                "kind", "applicability", "applicability_ref", "command_id",
                "command_ref", "tool_name", "tool_version",
                "config_sha256", "execution_receipt_ref", "stdout_sha256",
                "stderr_sha256", "result", "exit_code", "findings",
            }:
                fail("PG08_C7_CHECK_SHAPE_INVALID")
            kind = check["kind"]
            if kind not in KINDS or kind in seen or not ref(check["applicability_ref"]):
                fail("PG08_C7_CHECK_IDENTITY_INVALID")
            seen.add(kind)
            if check["applicability"] == "NOT_APPLICABLE":
                if (any(check[k] is not None for k in (
                    "command_id", "command_ref", "tool_name", "tool_version",
                    "config_sha256", "execution_receipt_ref", "stdout_sha256",
                    "stderr_sha256", "result", "exit_code")) or
                    check["findings"] != []):
                    fail("PG08_C7_NA_FAKE_EXECUTION")
                reported.append({"kind": kind, "applicability_reported": "NOT_APPLICABLE",
                                 "applicability_ref_reported": check["applicability_ref"],
                                 "reported_result": "NOT_RUN",
                                 "receipt_authenticated": False})
                continue
            if check["applicability"] != "REQUIRED":
                fail("PG08_C7_APPLICABILITY_INVALID")
            if (not all(ref(check.get(k)) for k in (
                    "command_id", "command_ref", "tool_name", "tool_version",
                    "execution_receipt_ref")) or check["command_id"] in ids):
                fail("PG08_C7_COMMAND_INVALID")
            ids.add(check["command_id"])
            if any(not isinstance(check.get(k), str) or not SHA256.fullmatch(check[k])
                   for k in ("config_sha256", "stdout_sha256", "stderr_sha256")):
                fail("PG08_C7_HASH_INVALID")
            state, code = check["result"], check["exit_code"]
            if (state not in RESULTS or
                (state == "PASS" and (type(code) is not int or code != 0)) or
                (state == "FAIL" and (type(code) is not int or code == 0)) or
                (state == "BLOCKED" and code is not None)):
                fail("PG08_C7_EXIT_CODE_CONTRADICTION")
            findings = check["findings"]
            if not isinstance(findings, list):
                fail("PG08_C7_FINDINGS_INVALID")
            finding_refs = set()
            local_blockers = []
            for finding in findings:
                if not isinstance(finding, dict) or set(finding) != {
                    "finding_ref", "severity", "source_module", "target_module",
                    "boundary_rule_ref"}:
                    fail("PG08_C7_FINDING_SHAPE_INVALID")
                if (not all(ref(finding.get(k)) for k in (
                    "finding_ref", "source_module", "target_module", "boundary_rule_ref"))
                    or finding["severity"] not in SEVERITIES
                    or finding["finding_ref"] in finding_refs):
                    fail("PG08_C7_FINDING_INVALID")
                finding_refs.add(finding["finding_ref"])
                if finding["severity"] == "BLOCK":
                    blockers.append(finding["finding_ref"])
                    local_blockers.append(finding["finding_ref"])
            if state == "PASS" and local_blockers:
                fail("PG08_C7_PASS_WITH_BLOCKING_FINDINGS")
            reported.append({"kind": kind, "applicability_reported": "REQUIRED",
                "applicability_ref_reported": check["applicability_ref"],
                "reported_result": state,
                "command_id_reported": check["command_id"],
                "command_ref_reported": check["command_ref"],
                "tool_name_reported": check["tool_name"],
                "tool_version_reported": check["tool_version"],
                "config_sha256_reported": check["config_sha256"],
                "stdout_sha256_reported": check["stdout_sha256"],
                "stderr_sha256_reported": check["stderr_sha256"],
                "execution_receipt_ref_reported": check["execution_receipt_ref"],
                "exit_code_reported": code,
                "findings_reported": deepcopy(findings),
                "receipt_authenticated": False})
        if seen != KINDS:
            fail("PG08_C7_ARCH_KINDS_INCOMPLETE")
        states = [x["reported_result"] for x in reported]
        results.append({
            "solution_id": sid,
            "executor_mode_reported": mode,
            "candidate_head_sha_reported": head,
            "diff_sha256_reported": diff,
            "architecture_profile_ref_reported": obs["architecture_profile_ref"],
            "checks_reported": sorted(reported, key=lambda x: x["kind"]),
            "reported_blockers": sorted(set(blockers)),
            "reported_diagnostic": (
                "REPORTED_ARCH_BLOCKERS" if blockers else
                "REPORTED_ARCH_CHECK_FAILURE" if "FAIL" in states or "BLOCKED" in states else
                "REPORTED_ARCH_APPLICABILITY_UNVERIFIED" if "NOT_RUN" in states else
                "REPORTED_ARCH_PASS_UNVERIFIED"
            ),
            "architecture_profile_verified": False,
            "boundary_coverage_verified": False,
            "receipt_authenticated": False,
        })
    result = {
        "schema_version": "PG08_C7_ARCH_BOUNDARY_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_pg08_c1_sha256": c1sha,
        "source_pg08_c6_sha256": c6sha,
        "target_repo": repo,
        "base_head_sha": base,
        "observations_sha256": digest(architecture_observations),
        "solutions": results,
        "architecture_checks_executed_by_this_component": False,
        "architecture_profile_verified": False,
        "boundary_coverage_verified": False,
        "exact_head_readback_verified": False,
        "receipts_authenticated": False,
        "pg08_c7_pass": False,
        "pg08_c7_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_HEAD_REAL_ARCHUNIT_MODULITH_ARCHITECTURE_CHECK_RECEIPTS"
    }
    result["candidate_sha256"] = digest(result)
    return result
