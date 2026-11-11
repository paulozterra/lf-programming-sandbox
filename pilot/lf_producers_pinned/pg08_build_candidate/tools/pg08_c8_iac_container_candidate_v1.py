"""PG-08_C8 source-only D14 infrastructure/container validation envelope.

No subprocesses, Terraform, Docker, Floci, remote endpoints, or cloud writes.
All observations are untrusted reports. Outputs can NEVER grant PASS.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA40 = re.compile(r"^[a-f0-9]{40}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
KINDS = ("TERRAFORM_FMT", "TERRAFORM_VALIDATE", "IAC_LINT",
         "FLOCI_PLAN", "FLOCI_APPLY", "CONTAINER_BUILD",
         "DOCKER_COMPOSE_UP", "CONTAINER_HEALTHCHECK")
RESULTS = {"PASS", "FAIL", "BLOCKED"}
MODES = {"GPT_NATIVE", "CLAUDE_NATIVE", "WORKER_API"}
DANGEROUS_TARGETS = {"CLOUD", "REMOTE", "PRODUCTION", "PUBLIC", "UNKNOWN"}

class PG08C8Blocked(ValueError):
    pass

def fail(code):
    raise PG08C8Blocked(code)

def digest(v):
    return hashlib.sha256(json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")).hexdigest()

def nonempty(v):
    return isinstance(v, str) and bool(v.strip())

def frozen(v, schema):
    if not isinstance(v, dict) or v.get("schema_version") != schema:
        fail("PG08_C8_SOURCE_SCHEMA_INVALID")
    sha = v.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {k: x for k, x in v.items() if k != "candidate_sha256"}
    ):
        fail("PG08_C8_SOURCE_DIGEST_INVALID")
    if (v.get("status") != "SOURCE_ONLY_NOT_ADMITTED"
        or v.get("handoff_allowed") is not False
        or v.get("production_authority") is not False):
        fail("PG08_C8_PREMATURE_AUTHORITY")
    return sha

def indexed(items):
    if not isinstance(items, list) or not items:
        fail("PG08_C8_SOLUTION_SET_EMPTY")
    out = {}
    for item in items:
        if not isinstance(item, dict) or not nonempty(item.get("solution_id")) or item["solution_id"] in out:
            fail("PG08_C8_SOLUTION_ID_INVALID")
        out[item["solution_id"]] = item
    return out

def prepare_pg08_c8(*, pg08_c1, pg08_c7, infrastructure_observations):
    """Assemble eight explicit IaC/container applicability decisions per solution.

    Every check is REQUIRED or NOT_APPLICABLE. REQUIRED includes command,
    version, hashes, outcome, execution and isolation references. FLOCI_APPLY,
    FLOCI_PLAN and Docker/health checks require a declared isolated target.
    Such a declaration does not authenticate network isolation: independent
    runtime sandboxing/allowlists are still mandatory.
    """
    c1sha = frozen(pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1")
    c7sha = frozen(pg08_c7, "PG08_C7_ARCH_BOUNDARY_CANDIDATE_V1")
    if (pg08_c7.get("source_pg08_c1_sha256") != c1sha
        or pg08_c7.get("target_repo") != pg08_c1.get("target_repo")
        or pg08_c7.get("base_head_sha") != pg08_c1.get("base_head_sha")
        or any(pg08_c1.get(k) is not False for k in ("pg08_c1_pass", "pg08_c1_admitted"))
        or any(pg08_c7.get(k) is not False for k in (
            "pg08_c7_pass", "pg08_c7_admitted", "receipts_authenticated"))):
        fail("PG08_C8_UPSTREAM_CHAIN_INVALID")
    repo, base = pg08_c1.get("target_repo"), pg08_c1.get("base_head_sha")
    if not nonempty(repo) or not isinstance(base, str) or not SHA40.fullmatch(base):
        fail("PG08_C8_TARGET_INVALID")
    c1, c7, observations = (
        indexed(pg08_c1.get("solutions")),
        indexed(pg08_c7.get("solutions")),
        indexed(infrastructure_observations),
    )
    if set(c1) != set(c7) or set(c1) != set(observations):
        fail("PG08_C8_COVERAGE_DRIFT")
    output = []
    for sid in sorted(c1):
        b, a, obs = c1[sid], c7[sid], observations[sid]
        if set(obs) != {
            "solution_id", "executor_mode", "target_repo", "base_head_sha",
            "candidate_head_sha", "diff_sha256", "iac_profile_ref",
            "isolation_policy_ref", "checks"
        }:
            fail("PG08_C8_OBSERVATION_SHAPE_INVALID")
        head, diff, mode = (b.get("candidate_head_sha_reported"),
                            b.get("diff_sha256_reported"), b.get("executor_mode_reported"))
        if (obs["target_repo"] != repo or obs["base_head_sha"] != base
            or obs["candidate_head_sha"] != head or obs["diff_sha256"] != diff
            or obs["executor_mode"] != mode or mode not in MODES
            or a.get("candidate_head_sha_reported") != head
            or a.get("diff_sha256_reported") != diff
            or a.get("executor_mode_reported") != mode
            or not isinstance(head, str) or not SHA40.fullmatch(head)
            or not isinstance(diff, str) or not SHA256.fullmatch(diff)
            or not nonempty(obs["iac_profile_ref"])
            or not nonempty(obs["isolation_policy_ref"])):
            fail("PG08_C8_TARGET_DIFF_OR_EXECUTOR_DRIFT")
        checks = obs["checks"]
        if not isinstance(checks, list) or len(checks) != len(KINDS):
            fail("PG08_C8_CHECK_COVERAGE_INVALID")
        seen = set()
        cmd_ids = set()
        reported = []
        issues = []
        for check in checks:
            if not isinstance(check, dict) or set(check) != {
                "kind", "applicability", "applicability_ref", "command_id",
                "command_ref", "tool_name", "tool_version",
                "config_sha256", "stdout_sha256", "stderr_sha256",
                "execution_receipt_ref", "result", "exit_code",
                "execution_target_type", "execution_target_ref", "finding_refs"
            }:
                fail("PG08_C8_CHECK_SHAPE_INVALID")
            kind = check["kind"]
            if kind not in KINDS or kind in seen or not nonempty(check["applicability_ref"]):
                fail("PG08_C8_CHECK_IDENTITY_INVALID")
            seen.add(kind)
            if check["applicability"] == "NOT_APPLICABLE":
                if (any(check[k] is not None for k in (
                    "command_id", "command_ref", "tool_name", "tool_version",
                    "config_sha256", "stdout_sha256", "stderr_sha256",
                    "execution_receipt_ref", "result", "exit_code",
                    "execution_target_type", "execution_target_ref"))
                    or check["finding_refs"] != []):
                    fail("PG08_C8_NA_FAKE_EXECUTION")
                reported.append({"kind": kind, "applicability_reported": "NOT_APPLICABLE",
                    "applicability_ref_reported": check["applicability_ref"],
                    "reported_result": "NOT_RUN", "receipt_authenticated": False})
                issues.append({"kind": kind, "reason": "APPLICABILITY_NOT_VERIFIED"})
                continue
            if check["applicability"] != "REQUIRED":
                fail("PG08_C8_APPLICABILITY_INVALID")
            if (not all(nonempty(check.get(k)) for k in (
                "command_id", "command_ref", "tool_name", "tool_version",
                "execution_receipt_ref", "execution_target_ref"))
                or check["command_id"] in cmd_ids):
                fail("PG08_C8_COMMAND_IDENTITY_INVALID")
            cmd_ids.add(check["command_id"])
            if any(not isinstance(check.get(k), str) or not SHA256.fullmatch(check[k])
                   for k in ("config_sha256", "stdout_sha256", "stderr_sha256")):
                fail("PG08_C8_CHECK_DIGEST_INVALID")
            # No real or remote targets may be proposed, even as a report.
            if (check["execution_target_type"] in DANGEROUS_TARGETS
                or check["execution_target_type"] not in {"LOCAL_ISOLATED", "FLOCI_EMULATOR"}):
                fail("PG08_C8_REMOTE_TARGET_FORBIDDEN")
            if kind in {"FLOCI_PLAN", "FLOCI_APPLY"} and check["execution_target_type"] != "FLOCI_EMULATOR":
                fail("PG08_C8_FLOCI_TARGET_REQUIRED")
            if kind not in {"FLOCI_PLAN", "FLOCI_APPLY"} and check["execution_target_type"] != "LOCAL_ISOLATED":
                fail("PG08_C8_LOCAL_TARGET_REQUIRED")
            status, code = check["result"], check["exit_code"]
            if (status not in RESULTS
                or (status == "PASS" and (type(code) is not int or code != 0))
                or (status == "FAIL" and (type(code) is not int or code == 0))
                or (status == "BLOCKED" and code is not None)):
                fail("PG08_C8_RESULT_EXIT_CONTRADICTION")
            findings = check["finding_refs"]
            if (not isinstance(findings, list)
                or any(not nonempty(x) for x in findings)
                or len(findings) != len(set(findings))
                or (status == "PASS" and findings)):
                fail("PG08_C8_FINDINGS_INVALID")
            reported.append({"kind": kind, "applicability_reported": "REQUIRED",
                "applicability_ref_reported": check["applicability_ref"],
                "reported_result": status,
                "command_id_reported": check["command_id"],
                "command_ref_reported": check["command_ref"],
                "tool_name_reported": check["tool_name"],
                "tool_version_reported": check["tool_version"],
                "config_sha256_reported": check["config_sha256"],
                "stdout_sha256_reported": check["stdout_sha256"],
                "stderr_sha256_reported": check["stderr_sha256"],
                "execution_receipt_ref_reported": check["execution_receipt_ref"],
                "execution_target_type_reported": check["execution_target_type"],
                "execution_target_ref_reported": check["execution_target_ref"],
                "exit_code_reported": code,
                "finding_refs_reported": deepcopy(findings),
                "receipt_authenticated": False,
                "isolation_verified": False})
            if status != "PASS":
                issues.append({"kind": kind, "reason": "REPORTED_" + status})
        if seen != set(KINDS):
            fail("PG08_C8_CHECK_KINDS_MISSING")
        reported_by_kind = {x["kind"]: x for x in reported}
        # Fail closed for a declared APPLY without a declared PLAN, or for
        # different Floci instances. This is only structural consistency.
        apply_check = reported_by_kind["FLOCI_APPLY"]
        plan_check = reported_by_kind["FLOCI_PLAN"]
        if apply_check["applicability_reported"] == "REQUIRED":
            if (plan_check["applicability_reported"] != "REQUIRED"
                or apply_check["execution_target_ref_reported"] !=
                   plan_check["execution_target_ref_reported"]
                or plan_check["reported_result"] != "PASS"):
                fail("PG08_C8_FLOCI_APPLY_WITHOUT_VALID_PLAN")
        if reported_by_kind["CONTAINER_HEALTHCHECK"]["applicability_reported"] == "REQUIRED":
            compose = reported_by_kind["DOCKER_COMPOSE_UP"]
            if compose["applicability_reported"] != "REQUIRED":
                fail("PG08_C8_HEALTHCHECK_WITHOUT_COMPOSE")
            if (reported_by_kind["CONTAINER_HEALTHCHECK"]["reported_result"] == "PASS"
                and compose["reported_result"] != "PASS"):
                fail("PG08_C8_HEALTHCHECK_PASS_WITHOUT_COMPOSE_PASS")
        if (reported_by_kind["DOCKER_COMPOSE_UP"]["applicability_reported"] == "REQUIRED"
            and reported_by_kind["DOCKER_COMPOSE_UP"]["reported_result"] == "PASS"
            and reported_by_kind["CONTAINER_BUILD"]["applicability_reported"] == "REQUIRED"
            and reported_by_kind["CONTAINER_BUILD"]["reported_result"] != "PASS"):
            fail("PG08_C8_COMPOSE_PASS_WITH_FAILED_BUILD")
        output.append({"solution_id": sid,
            "executor_mode_reported": mode,
            "candidate_head_sha_reported": head,
            "diff_sha256_reported": diff,
            "iac_profile_ref_reported": obs["iac_profile_ref"],
            "isolation_policy_ref_reported": obs["isolation_policy_ref"],
            "checks_reported": sorted(reported, key=lambda x: x["kind"]),
            "reported_issues": sorted(issues, key=lambda x: (x["kind"], x["reason"])),
            "reported_diagnostic": ("REPORTED_INCOMPLETE_OR_FAILED"
                if issues else "REPORTED_ALL_PASS_UNVERIFIED"),
            "runtime_isolation_verified": False,
            "no_cloud_calls_verified": False,
            "healthchecks_verified": False,
            "receipts_authenticated": False})
    result = {
        "schema_version": "PG08_C8_IAC_CONTAINER_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_pg08_c1_sha256": c1sha,
        "source_pg08_c7_sha256": c7sha,
        "target_repo": repo, "base_head_sha": base,
        "observations_sha256": digest(infrastructure_observations),
        "solutions": output,
        "iac_containers_executed_by_this_component": False,
        "target_isolation_verified": False,
        "cloud_access_prevented_by_runtime": False,
        "exact_head_readback_verified": False,
        "receipts_authenticated": False,
        "pg08_c8_pass": False,
        "pg08_c8_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_HEAD_OFFLINE_IAC_FLOCI_COMPOSE_HEALTHCHECK_REAL_RECEIPTS"
    }
    result["candidate_sha256"] = digest(result)
    return result
