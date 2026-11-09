#!/usr/bin/env python3
"""S2 manual native runner. The vendor executes every visible and hidden gate.

No hidden-oracle result, command, receipt, or output is included in feedback.
Task ex6 is intentionally NOT registered here; Claude registers it after S2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

from programming_agent_runner.hashutil import canonical_json_bytes, source_snapshot_sha256, strict_json_loads
from programming_agent_runner.worker_spec import parse_worker_task
from programming_agent_runner.worker_oracle import load_hidden_oracle, assert_hidden_oracle_external
from programming_agent_runner.worker_receipt import validate_worker_receipt
from programming_agent_runner.worker_patch import parse_patch_proposal, inspect_patch
from programming_agent_runner.verified_worker import run_verified_worker, validate_verified_worker_receipt
import programming_agent_runner.verified_worker as verified_module
from native_proposal_client import NativeProposalClient, read_proposal_envelope

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_PROPOSAL_PATH = Path("pilot/native_proposals/ex6.json")


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(canonical_json_bytes(value) + b"\n")


def load_registration(control: Path, task: str) -> tuple[dict, str]:
    if task != "ex6":
        raise ValueError("NATIVE_TASK_UNREGISTERED")
    path = control / "pilot/worker_v08/native_tasks/ex6.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("NATIVE_EX6_REGISTRATION_PENDING_CLAUDE")
    obj = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or set(obj) != {"task_spec", "holdout_sha256"}:
        raise ValueError("NATIVE_TASK_REGISTRATION_INVALID")
    sha = obj["holdout_sha256"]
    if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
        raise ValueError("NATIVE_HOLDOUT_PIN_INVALID")
    spec = parse_worker_task(obj["task_spec"])
    if spec.max_attempts != 1 or not _SHA40.fullmatch(spec.base_head_sha):
        raise ValueError("NATIVE_TASK_SPEC_INVALID")
    return obj["task_spec"], sha


def preflight(control: Path, task: str, output: Path) -> None:
    obj, expected = load_registration(control, task)
    spec = parse_worker_task(obj)
    # Do not publish the hidden oracle hash in a model-visible task pack.
    with output.open("a", encoding="utf-8") as f:
        f.write(f"base_sha={spec.base_head_sha}\n")
        f.write(f"holdout_sha256={expected}\n")


def _visible_feedback(visible: dict | None, attempt: int) -> dict:
    commands = []
    if isinstance(visible, dict):
        for row in visible.get("attempts", []):
            for item in row.get("acceptance", []):
                # Intentionally only visible acceptance, never hidden oracle.
                commands.append({
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "reason": item.get("reason"),
                    "returncode": item.get("returncode"),
                    "stdout_excerpt": item.get("stdout_excerpt"),
                    "stderr_excerpt": item.get("stderr_excerpt"),
                })
    return {"schema_version": "LF_NATIVE_VISIBLE_FEEDBACK_V1",
            "attempt": attempt, "kind": "VISIBLE_ACCEPTANCE_ONLY",
            "commands": commands}


def _proof(proposal: dict, task: str, attempt: int, run_id: int) -> dict:
    return {"task_id": task, "attempt": attempt,
            "task_pack_sha256": proposal["task_pack_sha256"], "run_id": run_id}


def execute(control: Path, source: Path, proposal_checkout: Path,
            private: Path, task: str, attempt: int, run_id: int) -> bool:
    public = private / "public"
    public.mkdir(parents=True, exist_ok=True)
    raw_task, expected_sha = load_registration(control, task)
    spec = replace(parse_worker_task(raw_task), max_attempts=1)
    proposal_path = proposal_checkout / _PROPOSAL_PATH
    # Read only this fixed proposal path from the untrusted checkout.
    submitted = read_proposal_envelope(proposal_path)
    _write(public / "cost.json", {
        "schema_version": "LF_NATIVE_INCREMENTAL_API_COST_V1",
        "cost_scope": "incremental_api",
        "real_api_usage": False, "api_calls": 0, "total_usd": 0,
        "subscription_cost": "NOT_EVALUATED",
        "tokens": "NOT_REPORTED",
    })
    _write(public / "feedback.json", _visible_feedback(None, attempt))
    if source.resolve() == control.resolve() or private.resolve().is_relative_to(source.resolve()):
        raise ValueError("NATIVE_WORKSPACE_BOUNDARY_INVALID")
    if (spec.base_head_sha != _git_head(source) or
        spec.source_snapshot_sha256 != source_snapshot_sha256(source)):
        raise ValueError("NATIVE_BASE_OR_SOURCE_SNAPSHOT_DRIFT")
    oracle_path = private / "holdout.oracle.json"
    if oracle_path.is_symlink() or not oracle_path.is_file():
        raise ValueError("NATIVE_HOLDOUT_NOT_LOADED")
    oracle = load_hidden_oracle(oracle_path, expected_sha)
    assert_hidden_oracle_external(source, oracle)
    # Check the proposal using the vendored schema/scope before consuming an attempt.
    proposal = parse_patch_proposal(submitted["proposal"], spec)
    inspect_patch(proposal, spec)
    # No preflight, missing oracle, invalid proposal, or scope failure is charged.
    # A later Worker failure does consume this attempt.
    _write(public / "attempt-proof.json", _proof(submitted, task, attempt, run_id))
    client = NativeProposalClient(proposal_path)
    seen = []
    original = verified_module.run_worker

    def collect(*args, **kwargs):
        result = original(*args, **kwargs)
        if validate_worker_receipt(result.receipt, result.patch):
            raise ValueError("NATIVE_VISIBLE_RECEIPT_INVALID")
        seen.append(result.receipt)
        return result

    with patch.object(verified_module, "run_worker", side_effect=collect):
        outcome = run_verified_worker(source, spec, client, oracle, work_parent=private)
    if validate_verified_worker_receipt(outcome.receipt, outcome.patch):
        raise ValueError("NATIVE_VERIFIED_RECEIPT_INVALID")
    visible = seen[0] if seen else None
    (public / "feedback.json").unlink()
    feedback = _visible_feedback(visible, attempt)
    _write(public / "feedback.json", feedback)
    feedback_sha256 = hashlib.sha256(canonical_json_bytes(feedback)).hexdigest()
    _write(public / "status.json", {
        "feedback_sha256": feedback_sha256,
        "schema_version": "LF_NATIVE_RESULT_SUMMARY_V1",
        "task_id": task, "attempt": attempt,
        "proposal_sha256": submitted["proposal_sha256"],
        "task_pack_sha256": submitted["task_pack_sha256"],
        "status": outcome.receipt["status"],
        "authority": "REAL_SANDBOX_UNAUTHENTICATED",
        "production_authority": False,
        "receipt_authenticated": False,
    })
    if outcome.receipt["status"] != "PASS":
        return False
    if not outcome.patch:
        raise ValueError("NATIVE_EMPTY_PASS_PATCH")
    with (public / "worker.patch").open("xb") as target:
        target.write(outcome.patch.encode("utf-8"))
    return True


def _git_head(source: Path) -> str:
    import subprocess
    return subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                   text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("preflight", "execute"))
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--private", type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--github-output", type=Path)
    a = parser.parse_args()
    try:
        if a.phase == "preflight":
            preflight(a.control, a.task, a.github_output)
        else:
            if not execute(a.control, a.source, a.proposal, a.private,
                           a.task, a.attempt, a.run_id):
                raise ValueError("NATIVE_VERIFIED_NONPASS")
    except Exception:
        # No exception messages: they may contain untrusted stdout or secrets.
        print("NATIVE_RUN_BLOCKED_OR_FAILED", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
