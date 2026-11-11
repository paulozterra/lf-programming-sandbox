"""Real sandbox EX5C evidence admission (non-authenticating, source-only).

This adapter never invokes Worker/Testing, never writes to LF/Supabase, and
does not modify PG08..PG14 producers. Accepts a fixed SHA256 fixture only.
Missing bundle or SHA -> BLOCK, never a synthetic PASS.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

COMMIT = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
BASE = "28de535acd4a76be038013cc6241c59a08102155"
TREE = "922f74a8ffaab9b8233625c804b8c92a17d8b8a3"
SUBTREE = "4ba97b68310e913795d7ae1ac35d5912e2fe6551"
PATCH_SHA = "bfba0329bcac92dbde06a1319a16acd535acd718f224df6121dae3c70fe307c6"
CONTEXT_SHA = "23e4c00d387ae34a111b98994f00d9965eefd7886f5b945e892f9451d59b1cc4"
REQUIREMENTS = {f"REM-C{i}" for i in range(1, 8)}
AUTHORITY_KEYS = {"production_authority", "tool_execution_verified",
                  "receipt_authenticated", "worker_invoked", "handoff_allowed",
                  "pg12_admitted", "testing_real_invoked", "write_allowed",
                  "dispatch_allowed", "receipt_sealed"}


class RealEvidenceBlocked(ValueError):
    pass


def block(code: str):
    raise RealEvidenceBlocked(code)


def require(condition: bool, code: str):
    if not condition:
        block(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def oid(kind: str, data: bytes) -> str:
    header = f"{kind} {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def decode(value: str) -> bytes:
    if not isinstance(value, str):
        block("EVIDENCE_BASE64_TYPE_BLOCK")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error):
        block("EVIDENCE_BASE64_BLOCK")


def check_authority(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in AUTHORITY_KEYS and v is not False:
                block("EVIDENCE_AUTHORITY_INJECTION_BLOCK")
            check_authority(v)
    elif isinstance(value, list):
        for item in value:
            check_authority(item)


def rebuild_subtree(rows: list[dict]) -> str:
    require(len(rows) == 18 and sum(x["bytes"] for x in rows) == 29347,
            "PG12_FILE_COUNT_OR_BYTES_BLOCK")
    root: dict = {}
    seen = set()
    for row in rows:
        name = row["path"]
        require(isinstance(name, str) and name.startswith("apps/time-service/") and
                ".." not in name.split("/") and name not in seen and
                row["mode"] == "100644", "PG12_FILE_SCOPE_BLOCK")
        seen.add(name)
        data = decode(row["content_base64"])
        require(len(data) == row["bytes"] and oid("blob", data) == row["oid"],
                "PG12_BLOB_OID_BLOCK")
        names = name.removeprefix("apps/time-service/").split("/")
        target = root
        for part in names[:-1]:
            target = target.setdefault(part, {})
        require(names[-1] not in target, "PG12_DUPLICATE_BLOB_BLOCK")
        target[names[-1]] = (row["mode"], row["oid"])

    def tree_oid(node):
        entries = []
        for name, child in node.items():
            if isinstance(child, dict):
                mode, sha = "40000", tree_oid(child)
            else:
                mode, sha = child
            entries.append((name, mode, sha))
        entries.sort(key=lambda x: (x[0] + ("/" if x[1] == "40000" else "")).encode())
        raw_tree = b"".join(mode.encode() + b" " + name.encode() + b"\0" +
                            bytes.fromhex(sha) for name, mode, sha in entries)
        return oid("tree", raw_tree)
    result = tree_oid(root)
    require(result == SUBTREE, "PG12_SUBTREE_OID_BLOCK")
    return result


def check_bytes_record(record: dict, *, code: str) -> bytes:
    raw = decode(record["base64"])
    require(record.get("bytes") == len(raw) and record.get("sha256") == digest(raw),
            code)
    return raw


def check_worker(bundle: dict) -> tuple[dict, dict, dict]:
    worker = bundle["worker"]
    require(worker["run_id"] == 42284754122 and
            worker["evidence_kind"] == "REAL_SANDBOX_UNAUTHENTICATED",
            "REAL_WORKER_RUN_BINDING_BLOCK")
    receipts = {}
    for name in ("verified-worker-receipt.json", "visible-worker-receipt.json",
                 "cost.json", "derived-context.json"):
        record = worker["files"][name]
        raw = check_bytes_record({"base64": record["content_base64"],
                                  "bytes": record["bytes"], "sha256": record["sha256"]},
                                 code="WORKER_RECEIPT_BYTES_BLOCK")
        receipts[name] = json.loads(raw)
    v = receipts["verified-worker-receipt.json"]
    w = receipts["visible-worker-receipt.json"]
    c = receipts["cost.json"]
    context = receipts["derived-context.json"]
    require(v.get("status") == "PASS" and v.get("visible_status") == "PASS" and
            v.get("task_id") == "LF-WORKER-PILOT-REAL-005C" and
            v.get("base_head_sha") ==
                "5b5f860f2c142c9741a4dfad93f25bf4914c710d",
            "WORKER_PUBLIC_VERDICT_BLOCK")
    require(w.get("status") == "PASS" and w.get("receipt_sha256") == v.get("visible_receipt_sha256") and
            v.get("resolved_model") == w.get("resolved_model") ==
            worker.get("resolved_model") == "claude-sonnet-5-5",
            "WORKER_MODEL_OR_RECEIPT_BINDING_BLOCK")
    require(worker["files"]["derived-context.json"]["sha256"] == CONTEXT_SHA and
            context.get("sha256") == "9cc719ef41a3b9e70d21b94780e0b17a6887fb57b4683eeaaf3157c2a1cb676d" and
            context.get("bytes") == 18254 and len(context.get("files", [])) == 10,
            "WORKER_CONTEXT_SHA_BLOCK")
    require(c.get("schema_version") == "LF_WORKER_COST_V1" and
            c.get("model") == "claude-sonnet-5-5" and
            c.get("receipt_sha256") == w.get("receipt_sha256") and
            c.get("real_api_usage") is True and
            c.get("total_input_tokens") == 10421 and
            c.get("total_output_tokens") == 4918,
            "PG09_USAGE_BINDING_BLOCK")
    return v, w, c


def check_patch(bundle: dict) -> list:
    p = bundle["patch"]
    diff = decode(p["text_base64"])
    require(digest(diff) == p["sha256"] == p["worker_patch_sha256"] == PATCH_SHA and
            p["bytes"] == len(diff), "PG11_PATCH_SHA_BLOCK")
    headers = []
    current_file = None
    current = []
    chunks = []

    def complete():
        if current:
            hunk = b"".join(current)
            chunks.append((current_file, hunk.split(b"\n", 1)[0].decode(), hunk))
    for line in diff.splitlines(keepends=True):
        if line.startswith(b"diff --git "):
            complete()
            current = []
            current_file = line.decode().strip().split(" b/", 1)[1]
        elif line.startswith(b"@@ "):
            complete()
            current = [line]
        elif current:
            current.append(line)
    complete()
    require(len(chunks) == 6 and len(p["hunks"]) == 6,
            "PG11_HUNK_COUNT_BLOCK")
    reqs = set()
    for declared, (path, header, raw) in zip(p["hunks"], chunks):
        require(declared["path"] == path and declared["header"] == header and
                declared["sha256"] == digest(raw) and
                declared["bytes"] == len(raw) and
                decode(declared["content_base64"]) == raw,
                "PG11_HUNK_SHA_BLOCK")
        attached = declared.get("requirements")
        require(isinstance(attached, list) and bool(attached) and
                set(attached) <= REQUIREMENTS, "PG11_HUNK_REQUIREMENT_BLOCK")
        reqs.update(attached)
    require(reqs == REQUIREMENTS, "PG11_REQUIREMENT_COVERAGE_BLOCK")
    return p["hunks"]


def check_execution(bundle: dict) -> dict:
    execution = bundle["execution"]
    maven = execution["maven"]
    require(maven.get("argv") == ["mvn", "-B", "-f",
            "apps/time-service/pom.xml", "verify"], "PG08_TOOL_ARGV_BLOCK")
    for key in ("stdout", "stderr"):
        check_bytes_record(maven[key], code="PG08_" + key.upper() + "_SHA_BLOCK")
    require(type(maven.get("exit_code")) is int and maven["exit_code"] == 0 and
            maven.get("result") == "PASS", "PG08_EXIT_CODE_RESULT_BLOCK")
    smoke = execution["smoke"]
    for key in ("stdout", "stderr"):
        check_bytes_record(smoke[key], code="PG08_SMOKE_" + key.upper() + "_SHA_BLOCK")
    require(len(smoke["steps"]) == 5, "PG08_HEALTHCHECK_STEPS_BLOCK")
    want = [("healthcheck", 200), ("create", 201), ("search", 200),
            ("delete", 204), ("get_after_delete", 404)]
    for row, (name, status) in zip(smoke["steps"], want):
        raw = decode(row["body_base64"])
        require(row["step"] == name and row["status"] == status and
                digest(raw) == row["body_sha256"] and len(raw) == row["body_bytes"],
                "PG08_SMOKE_BODY_OR_STATUS_BLOCK")
    return execution


def cost_verdict(cost: str, cap: str = "0.35") -> str:
    try:
        actual = Decimal(cost)
        ceiling = Decimal(cap)
    except (InvalidOperation, TypeError, ValueError):
        block("PG09_COST_FORMAT_BLOCK")
    require(actual.is_finite() and ceiling == Decimal("0.35") and actual >= 0,
            "PG09_COST_INVALID_BLOCK")
    if actual > ceiling:
        block("PG09_COST_OVER_CAP_BLOCK")
    if actual == ceiling:
        return "REQUIRES_DECISION"
    if actual >= Decimal("0.28"):
        return "WARN"
    return "REPORTED_WITHIN_BUDGET_UNVERIFIED"


def load_real_bundle(path: Path, fixed_sha256: str) -> dict:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", fixed_sha256 or "")),
            "REAL_BUNDLE_SHA_NOT_PINNED")
    require(path.is_file() and not path.is_symlink(), "REAL_BUNDLE_FIXTURE_MISSING")
    raw = path.read_bytes()
    require(digest(raw) == fixed_sha256, "REAL_BUNDLE_SHA_CHANGED_BLOCK")
    bundle = json.loads(raw)
    require(bundle.get("schema_version") == "LF_EX5C_REAL_EVIDENCE_BUNDLE_V1" and
            bundle.get("evidence_kind") == "REAL_SANDBOX_UNAUTHENTICATED",
            "REAL_BUNDLE_SCHEMA_BLOCK")
    check_authority(bundle)
    git = bundle["git"]
    commit = decode(git["raw_commit_base64"])
    require(oid("commit", commit) == git["commit"] == COMMIT and
            digest(commit) == git["raw_commit_sha256"] and
            git["tree"] == TREE and git["subtree_oid"] == SUBTREE and
            git["base_commit"] == BASE and
            git["base_subtree_oid"] == "91ac08b61d4fbb20d47dacc698778def71f2c805",
            "PG12_GIT_COMMIT_OID_BLOCK")
    raw_lines = commit.decode("utf-8", errors="replace").splitlines()
    require(("tree " + TREE) in raw_lines and
            git["parents"] == [line[7:] for line in raw_lines if line.startswith("parent ")],
            "PG12_COMMIT_TREE_OR_PARENTS_BLOCK")
    rebuild_subtree(bundle["files"])
    check_patch(bundle)
    check_execution(bundle)
    _, _, cost = check_worker(bundle)
    cost_verdict(str(cost["total_estimated_usd"]))
    return bundle


def pg08_c1_observations(bundle: dict, *, solution_id: str = "EX5C") -> list[dict]:
    """Exact input shape for *existing* PG08_C1 source-only producer."""
    m = bundle["execution"]["maven"]
    return [{
        "solution_id": solution_id,
        "executor_mode": "WORKER_API",
        "executor_result_ref": "sandbox:run:42284754122",
        "candidate_head_sha": COMMIT,
        "diff_sha256": PATCH_SHA,
        "target_repo": "paulozterra/lf-programming-sandbox",
        "base_head_sha": BASE,
        "commands": [{
            "command_id": "ex5c-maven-verify",
            "command_ref": "evidence:ex5c:maven",
            "tool_name": "mvn", "tool_version": "JDK21-Maven",
            "config_sha256": digest(decode(next(x["content_base64"] for x in bundle["files"]
                if x["path"] == "apps/time-service/pom.xml"))),
            "execution_receipt_ref": "REAL_SANDBOX_UNAUTHENTICATED:ex5c",
            "stdout_sha256": m["stdout"]["sha256"],
            "stderr_sha256": m["stderr"]["sha256"],
            "result": "PASS", "exit_code": m["exit_code"]
        }]
    }]


def pg09_usage(bundle: dict, *, solution_id: str = "EX5C") -> list[dict]:
    """Only reports verified public receipt reference; never authenticates billing."""
    c = json.loads(decode(bundle["worker"]["files"]["cost.json"]["content_base64"]))
    return [{
        "solution_id": solution_id, "executor_mode": "WORKER_API",
        "batch_id": "EX5C", "attempts_used": 1,
        "attempt_limit_source_ref": "sandbox:run:42284754122:one-attempt",
        "calls": [{
            "call_ref": "sandbox:run:42284754122:attempt1",
            "usage_receipt_ref": "sandbox:run:42284754122:cost.json",
            "usage_authentication_ref": None,
            "provider": "anthropic", "model_id": "claude-sonnet-5-5",
            "reported_cost": c["total_estimated_usd"], "currency": "USD",
            "input_tokens": c["total_input_tokens"],
            "output_tokens": c["total_output_tokens"], "cached_input_tokens": 0
        }]
    }]


def independent_review_label(author: str, reviewer: str = "reviewer:claude-opus-verifier") -> dict:
    """Independence of identities is checked; a real review is NOT authenticated."""
    require(author == "worker:claude-sonnet-5-5", "PG11_AUTHOR_MODEL_MISMATCH")
    require(reviewer != author and bool(reviewer), "SELF_REVIEW")
    return {"author_reported": author, "reviewer_reported": reviewer,
            "review_authenticated": False, "production_authority": False}


def pg07_c6_source_for_real_bundle(bundle: dict) -> dict:
    """Build the exact shape PG08_C1 consumes, from *checked* real C evidence.

    Not a PG07 producer output, execution attestation or a source of authority.
    This adapter-projected envelope is deliberately labeled and hashed.
    """
    check_authority(bundle)
    check_patch(bundle)
    check_execution(bundle)
    v, _, _ = check_worker(bundle)
    require(bundle["git"]["commit"] == COMMIT and
            bundle["git"]["base_commit"] == BASE, "PG07_REAL_GIT_BINDING_BLOCK")
    changed = sorted({h["path"] for h in bundle["patch"]["hunks"]})
    require(changed == sorted([
        "apps/time-service/src/main/java/lf/sandbox/time/reminder/" + n
        for n in ("ReminderRepository.java", "InMemoryReminderRepository.java",
                  "ReminderController.java")]), "PG07_REAL_CHANGED_SCOPE_BLOCK")
    worker_sha = bundle["worker"]["files"]["verified-worker-receipt.json"]["sha256"]
    cost_sha = bundle["worker"]["files"]["cost.json"]["sha256"]
    context_sha = bundle["worker"]["files"]["derived-context.json"]["sha256"]
    source = {
        "schema_version": "PG07_C6_BATCH_EVIDENCE_MANIFEST_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "source_adapter_ref": "pg07_real_worker_evidence_adapter_v1",
        "upstream_source_digests": {},
        "target_repo": "paulozterra/lf-programming-sandbox",
        "base_head_sha": BASE,
        "run_ref": "sandbox:worker-run:42284754122",
        "batches": [{
            "solution_id": "EX5C",
            "batch_id": "EX5C",
            "candidate_head_sha_reported": COMMIT,
            "diff_sha256_reported": PATCH_SHA,
            "changed_paths_reported": changed,
            "worker_receipt_ref_reported": "sandbox:run:42284754122:verified",
            "worker_receipt_sha256_reported": worker_sha,
            "provider_usage_receipt_refs_reported": [cost_sha],
            "context_pack_ref": "sha256:" + context_sha,
            "blocking_diagnostics": ["REAL_SANDBOX_UNAUTHENTICATED",
                                     "PG06_C4_REAL_BASELINE_NOT_PROVIDED"],
            "diff_readback_verified": False,
            "worker_receipt_verified": False,
            "usage_receipts_verified": False,
            "pg12_evidence_admitted": False
        }],
        "blocking_diagnostics": [{
            "solution_id": "EX5C",
            "reason": "PG06_C4_REAL_BASELINE_NOT_PROVIDED"
        }],
        "worker_batch_evidence_input_sha256": digest(
            bundle["worker"]["files"]["verified-worker-receipt.json"]["sha256"].encode()),
        "receipt_guard_authority_executed": False,
        "receipt_sealed": False, "receipt_digest_authenticated": False,
        "worker_invoked": False, "pg12_admitted": False,
        "dispatch_allowed": False, "write_allowed": False,
        "production_authority": False, "handoff_allowed": False
    }
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    source["candidate_sha256"] = digest(canonical)
    return source


def run_real_pg08_c1(bundle: dict) -> dict:
    """CALL the existing PG08_C1 producer, without altering its source."""
    import importlib.util
    path = (Path(__file__).resolve().parents[2] /
            "pg08_build_candidate/tools/pg08_c1_build_compilation_candidate_v1.py")
    require(path.is_file(), "PG08_C1_REAL_PRODUCER_MISSING")
    spec = importlib.util.spec_from_file_location("pg08_c1_real_ex5c", path)
    require(spec is not None and spec.loader is not None, "PG08_C1_IMPORT_BLOCK")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    upstream = pg07_c6_source_for_real_bundle(bundle)
    observations = pg08_c1_observations(bundle)
    result = module.prepare_pg08_c1(pg07_c6=upstream,
                                    build_observations=observations)
    require(result["source_pg07_c6_sha256"] == upstream["candidate_sha256"] and
            result["solutions"][0]["diff_sha256_reported"] == PATCH_SHA and
            result["solutions"][0]["reported_build_outcome"] ==
                "REPORTED_PASS_UNVERIFIED" and
            result["production_authority"] is False,
            "PG08_C1_REAL_PRODUCER_OUTPUT_BLOCK")
    return {"pg07_c6": upstream, "pg08_c1": result,
            "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
            "pg08_c2_admission_block": "PG06_C4_REAL_BASELINE_NOT_PROVIDED"}


def require_pg08_c2_real_source(bundle: dict) -> None:
    """Fail rather than silently substitute a PG06 synthetic fixture.

    The C bundle has no PG06 C4 baseline, nor separate formatter/linter receipts.
    Do not imply C2-C8 or PG09-PG14 completed until these inputs exist.
    """
    require("pg06_c4_real_baseline" in bundle and
            "real_format_lint_observations" in bundle,
            "PG08_C2_REAL_BASELINE_AND_LINT_EVIDENCE_MISSING_BLOCK")


def pg07_budget_sources_for_real_bundle(bundle: dict) -> tuple[dict, dict]:
    """Adapter-projected PG07C1/C5 envelopes; never claim true PG07 execution."""
    check_authority(bundle)
    _, _, cost = check_worker(bundle)
    base = {
        "schema_version": "PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "run_binding": {
            "run_ref": "sandbox:run:42284754122",
            "pricing_currency": "USD",
            "model_id": "claude-sonnet-5-5",
            "provider": "anthropic"
        },
        "worker_invoked": False,
        "dispatch_allowed": False,
        "production_authority": False,
        "handoff_allowed": False
    }
    guard = {
        "schema_version": "PG07_C5_ITERATION_GUARD_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "solutions": [{"solution_id": "EX5C", "iterations": []}],
        "iteration_applied": False, "pg10_routing_executed": False,
        "production_authority": False,
        "handoff_allowed": False
    }
    for source in (base, guard):
        payload = json.dumps(source, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode()
        source["candidate_sha256"] = digest(payload)
    return base, guard


def run_real_pg09_c1(bundle: dict) -> dict:
    """Call original PG09_C1, preserving real one-attempt Worker limit.

    The original producer treats one used attempt out of one allowed as an
    exhausted iteration limit, and therefore emits REQUIRES_DECISION even if
    reported cost 0.070022 < 0.35. Never override that outcome.
    """
    import importlib.util
    path = Path(__file__).resolve().parents[2] / (
        "pg09_iteration_candidate/tools/pg09_c1_iteration_cost_governor_candidate_v1.py")
    require(path.is_file(), "PG09_C1_REAL_PRODUCER_MISSING")
    spec = importlib.util.spec_from_file_location("pg09_c1_real_ex5c", path)
    require(spec is not None and spec.loader is not None, "PG09_C1_IMPORT_BLOCK")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    c1, c5 = pg07_budget_sources_for_real_bundle(bundle)
    policy = {
        "policy_ref": "sandbox:run:42284754122:cost-ceiling",
        "currency": "USD",
        "request_budget": "0.35",
        "batch_budget": "0.35",
        "max_attempts_per_solution": 1,
        "existing_worker_limit_ref": "sandbox:run:42284754122:max_attempts=1"
    }
    observation = pg09_usage(bundle)
    result = module.prepare_pg09_c1(
        pg07_c1=c1, pg07_c5=c5,
        budget_policy=policy, usage_observations=observation)
    require(result.get("reported_request_known_cost") == "0.070022" and
            result.get("request_diagnostic") == "REQUIRES_DECISION" and
            result.get("iteration_limit_reached_reported") is True and
            result.get("production_authority") is False,
            "PG09_C1_REAL_LIMIT_OR_COST_PROJECTION_BLOCK")
    return {"pg07_c1": c1, "pg07_c5": c5, "pg09_c1": result,
            "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
            "contract_mismatch":
                "PG09_C1_ATTEMPTS_EXHAUSTED_REQUIRES_DECISION_FOR_1_OF_1"}


def run_real_pg09_c1_to_c4(bundle: dict) -> dict:
    """Call unchanged PG09 C1,C2,C3,C4 using real cost, zero real iterations.

    PG07 C1/C5 envelopes are adapter projections; no runtime authority.
    C4 must retain the typed BUDGET_DECISION reason and return (not retry).
    """
    import importlib.util
    from pathlib import Path
    import sys
    tool_dir = Path(__file__).resolve().parents[2] / "pg09_iteration_candidate/tools"

    def get(name: str, fn: str):
        path = tool_dir / (name + ".py")
        require(path.is_file(), "PG09_PRODUCER_MISSING_BLOCK")
        spec = importlib.util.spec_from_file_location(name + "_EX5C", path)
        require(spec is not None and spec.loader is not None, "PG09_IMPORT_BLOCK")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, fn)

    source = run_real_pg09_c1(bundle)
    c1 = source["pg09_c1"]
    guard = source["pg07_c5"]
    c2 = get("pg09_c2_convergence_guard_candidate_v1", "prepare_pg09_c2")(
        pg07_c5=guard, pg09_c1=c1,
        iteration_observations=[{"solution_id": "EX5C", "iterations": []}])
    c3 = get("pg09_c3_quality_bypass_guard_candidate_v1", "prepare_pg09_c3")(
        pg07_c5=guard, pg09_c2=c2,
        quality_change_observations=[{"solution_id": "EX5C", "iterations": []}])
    local_tools = str(Path(__file__).resolve().parent)
    if local_tools not in sys.path:
        sys.path.insert(0, local_tools)
    from pg09_pg10_ex5c_owner_decision_bridge_v1 import (
        load_registered_owner_decision, bridge_pg09_c4_owner_decision_to_pg10)
    decision = load_registered_owner_decision()
    receipt_sha = bundle["worker"]["files"]["cost.json"]["sha256"]
    c4 = get("pg09_c4_typed_escalation_candidate_v1", "prepare_pg09_c4")(
        pg09_c1=c1, pg09_c2=c2, pg09_c3=c3,
        escalation_context=[{
            "solution_id": "EX5C",
            "run_ref": "sandbox:run:42284754122",
            "owner_decision_ref": decision["decision_ref"],
            "diagnostic_evidence_refs": ["sha256:" + receipt_sha]
        }])
    bridge = bridge_pg09_c4_owner_decision_to_pg10(pg09_c4=c4)
    require(c4["solutions"][0]["reason_codes"] == ["BUDGET_DECISION"] and
            c4["solutions"][0]["escalation_type"] == "RETURN" and
            c4["retry_authorized"] is False and
            c4["production_authority"] is False and
            bridge["production_authority"] is False,
            "PG09_C4_OWNER_DECISION_RETRY_BLOCK")
    return {"pg09_c1": c1, "pg09_c2": c2, "pg09_c3": c3,
            "pg09_c4": c4, "pg10_owner_decision_reference": bridge,
            "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
            "production_authority": False, "retry_authorized": False}
