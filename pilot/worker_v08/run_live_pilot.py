#!/usr/bin/env python3
"""Manual Worker v0.8 pilot, source copied BYTE-IDENTICAL from pinned commit.

QUALITY_CLI_NOT_USED=true: calls ORIGINAL run_verified_worker, not hardened
quality-v7 CLI. No baseline is synthesized. Never creates a PR or modifies
the original Worker source. Every paid attempt is independently costed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch

PIN_WORKER = "298307e2f9cac72abfde2b181f3554b0e28bad24"
PIN_ADAPTER = "5c981dfc77f8ffee1aa3cd66ab08a3b4d0051e2e"
PIN_HOLDOUT = "979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821"
MAX_COST_BY_MODEL = {"claude-haiku-5-5": Decimal("0.03"),
                     "claude-sonnet-5-5": Decimal("0.20")}
MAX_ATTEMPTS = 3
LIMITS = {
    "max_attempts": 3,
    "max_context_bytes": 60000,
    "max_patch_bytes": 20000,
    "max_changed_files": 3,
}
SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parents[2]
MANIFEST = SCRIPT.with_name("manifest.json")
VENDOR = REPO / "vendor/programming-agent"
ADAPTER = SCRIPT.parent / "cost_adapter"
QUALITY_CLI_NOT_USED = True


class PilotBlocked(RuntimeError):
    pass


def block(reason: str) -> None:
    raise PilotBlocked(reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        block("PILOT_JSON_OBJECT_REQUIRED")
    return value


def put(path: Path, value: dict) -> None:
    if path.exists():
        block("PILOT_OUTPUT_ALREADY_EXISTS:" + path.name)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                     allow_nan=False).encode("utf-8") + b"\n"
    with path.open("xb") as handle:
        handle.write(raw)
    path.chmod(0o600)


def git_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def verify_adapter_snapshot() -> None:
    proof = read(ADAPTER / "PROVENANCE.json")
    if (proof.get("schema_version") != "LF_PILOT_COST_ADAPTER_PIN_V1"
        or proof.get("source_commit") != PIN_ADAPTER
        or proof.get("source_repository") != "cristhianlujan/claude-persona-lf-patch"):
        block("COST_ADAPTER_PROVENANCE_INVALID")
    expected = proof.get("files")
    if not isinstance(expected, dict) or len(expected) != 3:
        block("COST_ADAPTER_FILE_LIST_INVALID")
    if not ADAPTER.is_dir() or ADAPTER.is_symlink():
        block("COST_ADAPTER_DIRECTORY_INVALID")
    observed = list(ADAPTER.iterdir())
    if any(p.is_symlink() or not p.is_file() for p in observed):
        block("COST_ADAPTER_UNAPPROVED_ENTRY")
    actual = {p.name for p in observed}
    if actual != set(expected) | {"PROVENANCE.json"}:
        block("COST_ADAPTER_FILES_DRIFT")
    for name, row in expected.items():
        if name not in {"pg07_to_worker_v1_adapter.py", "worker_cost_report_v1.py", "pricing_v1.json"}:
            block("COST_ADAPTER_NAME_INVALID")
        source = ADAPTER / name
        if source.is_symlink() or set(row) != {"source_git_blob_sha1"}:
            block("COST_ADAPTER_SOURCE_INVALID")
        raw = source.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if blob != row["source_git_blob_sha1"]:
            block("COST_ADAPTER_BYTES_DRIFT:" + name)


def selected_policy():
    model=os.environ.get("PILOT_MODEL")
    attempts=os.environ.get("PILOT_MAX_ATTEMPTS")
    if os.environ.get("PILOT_PROVIDER")!="anthropic" or model not in MAX_COST_BY_MODEL:
        block("PILOT_PROVIDER_MODEL_FORBIDDEN")
    if attempts not in ("1","2","3"):
        block("PILOT_ATTEMPTS_FORBIDDEN")
    from budget_gate import require, BudgetBlocked
    try:
        verified=require(model,int(attempts))
    except BudgetBlocked as exc:
        block(str(exc))
    return model,int(attempts),verified


def enforce_task_limits(task,attempts):
    if not isinstance(task,dict) or task.get("max_attempts")!=attempts:
        block("PILOT_TASK_ATTEMPTS_INVALID")
    for field in ("max_attempts","max_context_bytes","max_patch_bytes","max_changed_files"):
        value=task.get(field)
        if type(value) is not int or value<1 or value>LIMITS[field]:
            block("PILOT_TASK_LIMIT_EXCEEDED:"+field)
    if task.get("allow_deletions") is not False:
        block("PILOT_DELETIONS_FORBIDDEN")


def validate_common(private: Path) -> None:
    if REPO != REPO.resolve():
        block("PILOT_REPO_IS_SYMLINK")
    if not private.is_dir() or private.is_symlink():
        block("PILOT_PRIVATE_DIR_INVALID")
    if private.resolve() == REPO or private.resolve().is_relative_to(REPO):
        block("PILOT_PRIVATE_DIR_INSIDE_REPO")
    if subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                      capture_output=True, text=True, check=True).stdout.strip():
        block("PILOT_REPOSITORY_DIRTY")
    expected_head = os.environ.get("GITHUB_SHA")
    if expected_head and git_head(REPO) != expected_head:
        block("PILOT_CHECKOUT_HEAD_MISMATCH")
    from verify_vendor import verify
    verify(VENDOR)
    verify_adapter_snapshot()
    config = read(MANIFEST)
    selected_policy()
    from task_selector import select
    task = select(os.environ.get("PILOT_TASK"), require_holdout=True)
    # The manifest is the immutable legacy exercise-1 catalog. Never treat
    # its single target / holdout as a global authority for exercise-2.
    if (config.get("worker_commit") != PIN_WORKER
        or config.get("cost_adapter_source_commit") != PIN_ADAPTER
        or config.get("source_repo") != "paulozterra/lf-programming-sandbox"):
        block("PILOT_MANIFEST_SOURCE_DRIFT")
    if (config.get("limits") != {
            **LIMITS, "max_output_tokens": 8000, "allow_deletions": False,
        } or config.get("allowed_models") != list(MAX_COST_BY_MODEL)
        or config.get("attempts_options") != [1,2,3]):
        block("PILOT_MANIFEST_LIMIT_DRIFT")
    if os.environ["PILOT_TASK"] == "exercise-1":
        if (config.get("target_file") != task["write_path_patterns"][0]
            or config.get("external_holdout_sha256") != task["holdout_sha256"]
            or config.get("objective") != task["objective"]
            or config.get("visible_acceptance_command") != task["acceptance_commands"][0]):
            block("PILOT_EXERCISE1_LEGACY_CONTRACT_DRIFT")
    else:
        if (task["write_path_patterns"] != [
                "standards/tools/migrations.py", "standards/tools/checks.py"]
            or task["spec_sha256"] is None):
            block("PILOT_EXERCISE2_SCOPE_INVALID")
    holdout = private / "holdout.oracle.json"
    if (not holdout.is_file() or holdout.is_symlink()
        or digest(holdout.read_bytes()) != task["holdout_sha256"]):
        block("HIDDEN_HOLDOUT_SHA_MISMATCH")


def importer():
    sys.path.insert(0, str(ADAPTER))
    from worker_cost_report_v1 import price_receipt
    from pg07_to_worker_v1_adapter import check_limits
    from programming_agent_runner.worker_spec import parse_worker_task
    from programming_agent_runner.hashutil import source_snapshot_sha256
    from programming_agent_runner.worker_oracle import load_hidden_oracle, assert_hidden_oracle_external
    from programming_agent_runner.worker_receipt import validate_worker_receipt
    from programming_agent_runner.verified_worker import (
        run_verified_worker, validate_verified_worker_receipt,
    )
    return (price_receipt, check_limits, parse_worker_task, source_snapshot_sha256,
            load_hidden_oracle, assert_hidden_oracle_external,
            validate_worker_receipt, run_verified_worker, validate_verified_worker_receipt)


def prepare(private: Path) -> None:
    validate_common(private)
    from task_selector import select
    task_decl = select(os.environ.get("PILOT_TASK"), require_holdout=True)
    pre = task_decl["source_precondition"]
    path = REPO / pre["path"]
    if pre["kind"] == "EXACT_LINE_ONCE":
        if not path.is_file() or path.read_text(encoding="utf-8").count(pre["value"]) != 1:
            block("PILOT_TARGET_SOURCE_DRIFT")
    elif pre["kind"] == "NEW_FILE_ABSENT":
        if path.exists():
            block("PILOT_NEW_TARGET_ALREADY_EXISTS")
    else:
        block("PILOT_SOURCE_PRECONDITION_INVALID")
    (_, _legacy_check_limits, parse, snapshot, load_oracle, assert_external, *_) = importer()
    model,attempts,budget=selected_policy()
    task = {
        "schema_version": 1,
        "task_id": task_decl["task_id"],
        "objective": task_decl["objective"],
        "base_head_sha": git_head(REPO),
        "source_snapshot_sha256": snapshot(REPO),
        "context_path_patterns": task_decl["context_path_patterns"],
        "write_path_patterns": task_decl["write_path_patterns"],
        "protected_path_patterns": task_decl["protected_path_patterns"],
        "acceptance_commands": task_decl["acceptance_commands"],
        "max_attempts": attempts,
        "max_context_bytes": 60000,
        "max_patch_bytes": 20000,
        "max_changed_files": 3,
        "allow_deletions": False,
    }
    enforce_task_limits(task,attempts)
    spec = parse(task)
    oracle = load_oracle(private / "holdout.oracle.json", task_decl["holdout_sha256"])
    assert_external(REPO, oracle)
    put(private / "task.v1.json", task)
    put(private / "extra.envelope.json", {
        "schema_version": "LF_PILOT_UNADMITTED_ENVELOPE_V1",
        "task_id": spec.task_id,
        "task_sha256": spec.sha256,
        "pg07_admitted": False,
        "production_authority": False,
        "QUALITY_CLI_NOT_USED": True,
        "verified_worker_path": "run_verified_worker",
        "worker_commit": PIN_WORKER,
        "pilot_task": os.environ.get("PILOT_TASK"),
        "spec_sha256": task_decl["spec_sha256"],
        "holdout_sha256": task_decl["holdout_sha256"],
    })
    print("PILOT_PREPARED_QUALITY_CLI_NOT_USED=true_NO_MODEL model="+model+
          " attempts="+str(attempts)+" worst_usd="+budget["worst_case_usd"])


def execute(private: Path) -> None:
    validate_common(private)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        block("ANTHROPIC_API_KEY_MISSING")
    (price_receipt, _legacy_check_limits, parse, snapshot, load_oracle, assert_external,
     validate_visible, run_verified, validate_verified) = importer()
    model,attempts,_budget=selected_policy()
    from task_selector import select
    task_decl = select(os.environ.get("PILOT_TASK"), require_holdout=True)
    task = read(private / "task.v1.json")
    if (task.get("task_id")!=task_decl["task_id"]
        or task.get("objective")!=task_decl["objective"]
        or task.get("context_path_patterns")!=task_decl["context_path_patterns"]
        or task.get("write_path_patterns")!=task_decl["write_path_patterns"]
        or task.get("protected_path_patterns")!=task_decl["protected_path_patterns"]
        or task.get("acceptance_commands")!=task_decl["acceptance_commands"]):
        block("PILOT_TASK_SCOPE_DRIFT")
    enforce_task_limits(task,attempts)
    spec = parse(task)
    if spec.base_head_sha != git_head(REPO) or spec.source_snapshot_sha256 != snapshot(REPO):
        block("PILOT_SOURCE_CHANGED_AFTER_PREFLIGHT")
    oracle = load_oracle(private / "holdout.oracle.json", task_decl["holdout_sha256"])
    assert_external(REPO, oracle)
    from programming_agent_runner.anthropic_messages import AnthropicMessagesClient
    import programming_agent_runner.verified_worker as verified_module
    client = AnthropicMessagesClient(
        api_key=api_key, model=model, timeout_seconds=90,
        max_output_tokens=8000,
    )
    # Keep key out of persistent locals longer than necessary.
    del api_key
    seen = []
    original = verified_module.run_worker

    def collect(*args, **kwargs):
        response = original(*args, **kwargs)
        if validate_visible(response.receipt, response.patch):
            block("WORKER_VISIBLE_RECEIPT_INVALID")
        seen.append(response.receipt)
        return response

    # This instrumentation does not modify vendor code. It captures the
    # original sealed visible receipt because VerifiedWorker omits usage.
    with patch.object(verified_module, "run_worker", side_effect=collect):
        outcome = run_verified(REPO, spec, client, oracle, work_parent=private)
    if validate_verified(outcome.receipt, outcome.patch):
        block("VERIFIED_WORKER_RECEIPT_INVALID")
    put(private / "verified-worker-receipt.json", outcome.receipt)
    if seen:
        put(private / "visible-worker-receipt.json", seen[0])
    # Produce PUBLIC diagnostic projections before any non-PASS exception.
    # The ORIGINAL sealed receipts remain private; free-form reason text or
    # model response are never uploaded.
    from receipt_diagnostics import write_public_receipt
    if seen:
        write_public_receipt(private / "public", seen[0], "visible")
    model_category=next((
        a.get("proposal_reason") for a in (seen[0].get("attempts",[]) if seen else [])
        if isinstance(a,dict) and a.get("proposal_reason") in ("MODEL_ERROR","MODEL_REFUSAL")
    ),None)
    write_public_receipt(private / "public", outcome.receipt, "verified",model_category)
    if outcome.receipt["status"] == "PASS":
        raw = outcome.patch.encode("utf-8")
        if not raw or len(raw) > LIMITS["max_patch_bytes"]:
            block("PILOT_PATCH_INVALID")
        with (private / "worker.patch").open("xb") as file:
            file.write(raw)
        (private / "worker.patch").chmod(0o600)
    if outcome.receipt["status"] != "PASS":
        block("WORKER_NONPASS_" + outcome.receipt["status"])
    print("PILOT_VERIFIED_WORKER_PASS_QUALITY_CLI_NOT_USED=true")


def cost(private: Path) -> None:
    validate_common(private)
    path = private / "visible-worker-receipt.json"
    verified_path = private / "verified-worker-receipt.json"
    if not path.is_file() or not verified_path.is_file():
        block("WORKER_RECEIPT_OR_USAGE_MISSING")
    (price_receipt, *_) = importer()
    model,attempts,_budget=selected_policy()
    from task_selector import select
    task_decl=select(os.environ.get("PILOT_TASK"),require_holdout=True)
    visible = read(path)
    verified = read(verified_path)
    if visible.get("task_id")!=task_decl["task_id"]:
        block("PILOT_RECEIPT_TASK_DRIFT")
    if (visible.get("task_id") != verified.get("task_id")
        or visible.get("receipt_sha256") != verified.get("visible_receipt_sha256")
        or visible.get("model_provider") != "anthropic"
        or visible.get("requested_model") != model
        or verified.get("requested_model") != model):
        block("WORKER_VISIBLE_VERIFIED_RECEIPT_BINDING_INVALID")
    from receipt_diagnostics import write_usage_unavailable
    public=private/"public"
    # MODEL_ERROR / MODEL_REFUSAL may occur before a provider returns any
    # billable usage metadata. Preserve reason and explicitly UNKNOWN billing.
    usage_missing=any(
        a.get("proposal_reason") in ("MODEL_ERROR","MODEL_REFUSAL") and
        (not isinstance(a.get("usage"),dict) or
         type(a["usage"].get("input_tokens")) is not int or
         type(a["usage"].get("output_tokens")) is not int)
        for a in visible.get("attempts",[]) if isinstance(a,dict)
    )
    if usage_missing:
        if write_usage_unavailable(public,visible,verified):
            block("USAGE_UNAVAILABLE_CHECK_ANTHROPIC_CONSOLE")
    result = price_receipt(visible)
    if (result.get("model_provider") != "anthropic"
        or result.get("real_api_usage") is not True
        or not 1<=len(result.get("attempts", []))<=attempts
        or result.get("model") != model):
        block("PILOT_UNPRICED_OR_MULTIATTEMPT")
    try:
        usd = Decimal(result["total_estimated_usd"])
    except (InvalidOperation, KeyError, ValueError):
        block("PILOT_COST_INVALID")
    if not usd.is_finite() or usd < 0:
        block("PILOT_COST_INVALID")
    public = private / "public"
    public.mkdir(mode=0o700,exist_ok=True)
    # Sanitized diagnostic files were already generated by execute(), even
    # if it returned BLOCKED / FAIL. Never upload private sealed originals.
    from receipt_diagnostics import write_public_receipt
    if not (public/"visible-worker-receipt.json").is_file():
        write_public_receipt(public,visible,"visible")
    if not (public/"verified-worker-receipt.json").is_file():
        write_public_receipt(public,verified,"verified")
    put(public / "cost.json", result)
    # Preserve read-only receipts and cost even when over budget; NEVER expose
    # patch if this gate rejects the paid attempt.
    if usd > MAX_COST_BY_MODEL[model]:
        block("PILOT_COST_OVER_USD_0_10")
    if verified.get("status") == "PASS":
        if not (private / "worker.patch").is_file():
            block("PASS_PATCH_MISSING")
        shutil.copyfile(private / "worker.patch", public / "worker.patch")
    (public / "pilot-summary.log").write_text(
        "QUALITY_CLI_NOT_USED=true\n"
        "WORKER=run_verified_worker\n"
        "PG07_ADMITTED=false\n"
        "COST_ESTIMATE_USD=" + str(usd) + "\n"
        "COST_CEILING_USD=" + str(MAX_COST_BY_MODEL[model]) + "\n",
        encoding="utf-8",
    )
    print("PILOT_COST_GATE_PASS_USD_" + str(usd) + "_QUALITY_CLI_NOT_USED=true")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("prepare", "execute", "cost"))
    p.add_argument("--private", required=True, type=Path)
    args = p.parse_args()
    private = args.private.resolve(strict=True)
    {"prepare": prepare, "execute": execute, "cost": cost}[args.phase](private)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PILOT_BLOCKED:" + str(exc), file=sys.stderr)
        raise SystemExit(1)
