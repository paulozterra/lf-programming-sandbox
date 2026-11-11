"""PG-08_C6: assemble declared check receipts as feedback, never verdict.

Reuses PG-08_C1..C5 source envelopes. No tool invocation, no authenticity,
no exact-HEAD readback, no PASS. Missing receipt fields remain missing.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")

class PG08C6Blocked(ValueError):
    pass

def fail(reason):
    raise PG08C6Blocked(reason)

def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()

def nonempty(v):
    return isinstance(v, str) and bool(v.strip())

def frozen(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        fail("PG08_C6_SOURCE_SCHEMA_INVALID")
    sha = value.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {k: v for k, v in value.items() if k != "candidate_sha256"}
    ):
        fail("PG08_C6_SOURCE_DIGEST_INVALID")
    if (value.get("status") != "SOURCE_ONLY_NOT_ADMITTED" or
        value.get("handoff_allowed") is not False or
        value.get("production_authority") is not False):
        fail("PG08_C6_SOURCE_AUTHORITY_INVALID")
    return sha

def index(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG08_C6_SOLUTION_SET_EMPTY")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not nonempty(row.get("solution_id")) or row["solution_id"] in out:
            fail("PG08_C6_SOLUTION_IDS_INVALID")
        out[row["solution_id"]] = row
    return out

def prepare_pg08_c6(*, pg08_c1, pg08_c2, pg08_c3, pg08_c4, pg08_c5):
    """Collect one unverified feedback entry per reported check.

    The source-only PG-08_C2 envelope omits stdout/stderr hashes and
    command_ref, and PG-08_C5 may report NOT_APPLICABLE. Those remain
    explicit gaps. This never synthesizes missing values or produces PASS.
    """
    sources = {
        "c1": (pg08_c1, "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1"),
        "c2": (pg08_c2, "PG08_C2_FORMAT_LINT_DELTA_CANDIDATE_V1"),
        "c3": (pg08_c3, "PG08_C3_TYPECHECK_CANDIDATE_V1"),
        "c4": (pg08_c4, "PG08_C4_TEST_AND_LOCAL_FLYWAY_CANDIDATE_V1"),
        "c5": (pg08_c5, "PG08_C5_CONTRACT_LINT_CANDIDATE_V1"),
    }
    sha = {name: frozen(obj, schema) for name, (obj, schema) in sources.items()}
    chain = [
        (pg08_c2, "source_pg08_c1_sha256", "c1"),
        (pg08_c3, "source_pg08_c1_sha256", "c1"),
        (pg08_c3, "source_pg08_c2_sha256", "c2"),
        (pg08_c4, "source_pg08_c1_sha256", "c1"),
        (pg08_c4, "source_pg08_c3_sha256", "c3"),
        (pg08_c5, "source_pg08_c1_sha256", "c1"),
        (pg08_c5, "source_pg08_c4_sha256", "c4"),
    ]
    if any(obj.get(field) != sha[key] for obj, field, key in chain):
        fail("PG08_C6_SOURCE_CHAIN_DRIFT")
    for key, (source, _) in sources.items():
        if (source.get("pg08_" + key + "_pass") is not False or
            source.get("pg08_" + key + "_admitted") is not False):
            fail("PG08_C6_PREMATURE_PASS")
    repo, base = pg08_c1.get("target_repo"), pg08_c1.get("base_head_sha")
    if not nonempty(repo) or not isinstance(base, str) or not SHA40.fullmatch(base):
        fail("PG08_C6_TARGET_INVALID")
    if any(obj.get("target_repo") != repo or obj.get("base_head_sha") != base
           for obj, _ in sources.values()):
        fail("PG08_C6_TARGET_DRIFT")
    indexed = {k: index(obj["solutions"]) for k, (obj, _) in sources.items()}
    ids = set(indexed["c1"])
    if any(set(rows) != ids for rows in indexed.values()):
        fail("PG08_C6_SOLUTION_SET_DRIFT")

    assembled = []
    diagnostics = []
    for sid in sorted(ids):
        reference = indexed["c1"][sid]
        head = reference.get("candidate_head_sha_reported")
        diff = reference.get("diff_sha256_reported")
        mode = reference.get("executor_mode_reported")
        if (not isinstance(head, str) or not SHA40.fullmatch(head) or
            not isinstance(diff, str) or not SHA256.fullmatch(diff) or
            mode not in ("GPT_NATIVE", "CLAUDE_NATIVE", "WORKER_API")):
            fail("PG08_C6_CANDIDATE_IDENTITY_INVALID")
        for key, rows in indexed.items():
            r = rows[sid]
            if (r.get("candidate_head_sha_reported") != head or
                r.get("diff_sha256_reported") != diff or
                r.get("executor_mode_reported") != mode):
                fail("PG08_C6_CANDIDATE_OR_EXECUTOR_DRIFT")
        checks = []
        seen = set()
        for lane in ("c1", "c2", "c3", "c4", "c5"):
            for item in indexed[lane][sid].get("commands_reported" if lane == "c1" else "checks_reported", []):
                if not isinstance(item, dict):
                    fail("PG08_C6_CHECK_INVALID")
                kind = item.get("kind", item.get("profile", "BUILD" if lane == "c1" else None))
                if not nonempty(kind):
                    fail("PG08_C6_CHECK_KIND_MISSING")
                key = lane + ":" + kind + ":" + str(item.get("command_id", item.get("command_id_reported", "")))
                if key in seen:
                    fail("PG08_C6_DUPLICATE_CHECK")
                seen.add(key)
                status = item.get("reported_result", item.get("result"))
                if status not in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
                    fail("PG08_C6_CHECK_RESULT_INVALID")
                # C2/C5 rename several fields. Deliberately retain null
                # when a source did not preserve evidence data.
                def field(name):
                    return item.get(name, item.get(name + "_reported"))
                tool = field("tool_name")
                version = field("tool_version")
                config = field("config_sha256")
                receipt = field("execution_receipt_ref")
                stdout = field("stdout_sha256")
                stderr = field("stderr_sha256")
                command_id = field("command_id")
                command_ref = field("command_ref")
                missing = []
                if status != "NOT_RUN":
                    for name, value in (
                        ("tool_name", tool), ("tool_version", version),
                        ("config_sha256", config), ("execution_receipt_ref", receipt),
                        ("stdout_sha256", stdout), ("stderr_sha256", stderr),
                        ("command_id", command_id), ("command_ref", command_ref)
                    ):
                        if not nonempty(value):
                            missing.append(name)
                    for name, value in (("config_sha256", config),
                                        ("stdout_sha256", stdout),
                                        ("stderr_sha256", stderr)):
                        if value is not None and (
                            not isinstance(value, str) or not SHA256.fullmatch(value)
                        ):
                            fail("PG08_C6_REPORTED_CHECK_DIGEST_INVALID")
                    if status == "PASS" and (missing or item.get("exit_code", item.get("exit_code_reported")) not in (0,)):
                        missing.append("verified_exit_code_or_fields")
                else:
                    missing.append("verified_non_applicability")
                if missing:
                    diagnostics.append({"solution_id": sid, "check_id": key,
                                        "missing_or_unverified": sorted(set(missing))})
                checks.append({
                    "check_id": key,
                    "checkpoint": "PG-08_C" + lane[-1],
                    "kind": kind,
                    "reported_result": status,
                    "command_id_reported": command_id,
                    "command_ref_reported": command_ref,
                    "tool_name_reported": tool,
                    "tool_version_reported": version,
                    "config_sha256_reported": config,
                    "stdout_sha256_reported": stdout,
                    "stderr_sha256_reported": stderr,
                    "execution_receipt_ref_reported": receipt,
                    "source_check_sha256": digest(item),
                    "missing_source_fields": sorted(set(missing)),
                    "receipt_authenticated": False,
                    "tool_execution_verified": False,
                    "feedback_only": True
                })
        if not checks or not any(x["checkpoint"] == "PG-08_C1" for x in checks):
            fail("PG08_C6_BUILD_CHECKS_MISSING")
        assembled.append({
            "solution_id": sid,
            "executor_mode_reported": mode,
            "candidate_head_sha_reported": head,
            "diff_sha256_reported": diff,
            "checks": sorted(checks, key=lambda row: row["check_id"]),
            "check_count": len(checks),
            "receipt_set_complete": False,
            "final_verdict_issued": False
        })
    output = {
        "schema_version": "PG08_C6_CHECK_RECEIPT_FEEDBACK_CANDIDATE_V1",
        "status": "SOURCE_ONLY_NOT_ADMITTED",
        "source_digests": sha,
        "target_repo": repo,
        "base_head_sha": base,
        "solutions": assembled,
        "source_gaps": diagnostics,
        "feedback_only": True,
        "receipt_completeness_verified": False,
        "tool_execution_verified": False,
        "exact_head_readback_verified": False,
        "receipts_authenticated": False,
        "pg08_c6_pass": False,
        "pg08_c6_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "AUTHENTICATED_EXACT_HEAD_CI_RECEIPTS_AND_INDEPENDENT_VERDICT"
    }
    output["candidate_sha256"] = digest(output)
    return output
