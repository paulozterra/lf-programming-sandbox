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
from lot_preflight import check_task, LotBlocked
from holdout_age import holdout_ref

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_TASK_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")

def proposal_path(task: str) -> Path:
    if not isinstance(task,str) or _TASK_ID.fullmatch(task) is None:
        raise ValueError("NATIVE_TASK_ID_INVALID")
    return Path("pilot/native_proposals") / (task + ".json")


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(canonical_json_bytes(value) + b"\n")


def load_registration(control: Path, task: str) -> tuple[dict, str]:
    proposal_path(task)
    path = control / "pilot/worker_v08/native_tasks" / (task + ".json")
    if not path.is_file() or path.is_symlink():
        raise ValueError("NATIVE_TASK_UNREGISTERED")
    obj = strict_json_loads(path.read_text(encoding="utf-8"))
    if (not isinstance(obj, dict) or
            set(obj) not in ({"task_spec", "holdout_sha256"},
                             {"task_spec", "holdout_sha256", "holdout_ref"})):
        raise ValueError("NATIVE_TASK_REGISTRATION_INVALID")
    if "holdout_ref" in obj:
        holdout_ref(task, obj["holdout_ref"])
    sha = obj["holdout_sha256"]
    if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
        raise ValueError("NATIVE_HOLDOUT_PIN_INVALID")
    spec = parse_worker_task(obj["task_spec"])
    if spec.max_attempts != 1 or not _SHA40.fullmatch(spec.base_head_sha):
        raise ValueError("NATIVE_TASK_SPEC_INVALID")
    return obj["task_spec"], sha


def registration_holdout_ref(control: Path, task: str) -> str | None:
    """Optional private locator; preserve legacy load_registration's two-tuple."""
    load_registration(control, task)
    file = control / "pilot/worker_v08/native_tasks" / (task + ".json")
    return strict_json_loads(file.read_text("utf-8")).get("holdout_ref")


def preflight(control: Path, task: str, output: Path) -> None:
    obj, expected = load_registration(control, task)
    spec = parse_worker_task(obj)
    # Legacy ex6/ex7/ex8 registrations are byte-identical and predated CP1.3.
    # New tasks must satisfy their general lot size/handoff gate before they
    # can reach the Worker executor.
    if task not in {"ex6", "ex7", "ex8"}:
        try:
            check_task(control, {"task_spec": obj})
        except LotBlocked as exc:
            raise ValueError("NATIVE_LOT_PREFLIGHT_BLOCKED:" + str(exc)) from exc
    # Do not publish the hidden oracle hash in a model-visible task pack.
    with output.open("a", encoding="utf-8") as f:
        f.write(f"base_sha={spec.base_head_sha}\n")
        f.write(f"holdout_sha256={expected}\n")
        ref = registration_holdout_ref(control, task)
        if ref is not None:
            f.write(f"holdout_ref={ref}\n")


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
    proposal_file = proposal_checkout / proposal_path(task)
    # Read only this fixed proposal path from the untrusted checkout.
    submitted = read_proposal_envelope(proposal_file)
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
    # T7 duplicate detection is a trusted pre-acceptance gate, after the
    # attempt proof has been emitted: a rejection is a spent FAIL, never PASS.
    # Legacy registrations without a reuse assessment remain untouched.
    reports = [p for p in raw_task.get("context_path_patterns", [])
               if isinstance(p, str) and re.fullmatch(
                   r"pilot/runs/[a-z][a-z0-9_-]{0,63}/reuse_assessment[.]json", p)]
    if reports:
        from reuse_guard import check as check_reuse, DuplicateComponent
        try:
            if len(reports) != 1:
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            source_report = source / reports[0]
            if source_report.is_symlink() or not source_report.is_file():
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            document = strict_json_loads(source_report.read_text("utf-8"))
            if (document.get("schema_version") != "T7_REUSE_ASSESSMENT_V1"
                    or not isinstance(document.get("obligations"), list)):
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            reuse_context = []
            for row in document["obligations"]:
                if not isinstance(row, dict) or not isinstance(row.get("reuse_context"), list):
                    raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
                for ref in row["reuse_context"]:
                    if isinstance(ref, dict) and ref.get("path") in raw_task.get("context_path_patterns", []):
                        reuse_context.append(ref)
            check_reuse(source, proposal.patch, reuse_context)
        except (DuplicateComponent, OSError, ValueError, KeyError) as exc:
            code = str(exc).split(":", 1)[0]
            if code not in ("DUPLICA_COMPONENTE_EXISTENTE", "REUTILIZACION_INDETERMINADA"):
                code = "REUTILIZACION_INDETERMINADA"
            component = str(exc)[:500] if code == "DUPLICA_COMPONENTE_EXISTENTE" else code
            (public / "feedback.json").unlink()
            feedback = _visible_feedback({"attempts":[{"acceptance":[{
                "name":"reuse-component-guard", "status":"FAIL",
                "reason":component, "returncode":1,
                "stdout_excerpt":"", "stderr_excerpt":""}]}]}, attempt)
            _write(public / "feedback.json", feedback)
            _write(public / "status.json", {
                "feedback_sha256": hashlib.sha256(canonical_json_bytes(feedback)).hexdigest(),
                "schema_version":"LF_NATIVE_RESULT_SUMMARY_V1",
                "task_id":task, "attempt":attempt,
                "proposal_sha256":submitted["proposal_sha256"],
                "task_pack_sha256":submitted["task_pack_sha256"],
                "status":"FAIL", "authority":"REAL_SANDBOX_UNAUTHENTICATED",
                "production_authority":False,"receipt_authenticated":False,
            })
            return False
    # T8: a failed deterministic standard is a spent, visible FAIL. The
    # examiner's oracle is not inspected or reflected in this report.
    rule_receipts = [p for p in raw_task.get("context_path_patterns", [])
                     if p == f".lf/worker-context/{task}/lf_rules.receipt.json"]
    if rule_receipts:
        from lf_rule_gate import evaluate, coverage, RuleGateBlocked
        try:
            manifest_path = source / rule_receipts[0]
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise RuleGateBlocked("LF_RULE_CONTEXT_MISSING")
            manifest = strict_json_loads(manifest_path.read_text("utf-8"))
            if manifest.get("schema_version") not in (None, "T8_LF_RULE_CONTEXT_V1"):
                raise RuleGateBlocked("LF_RULE_CONTEXT_INVALID")
            gate = evaluate(proposal.patch, manifest["rule_ids"], root=control)
            table = coverage(gate)
        except (RuleGateBlocked, ValueError, KeyError, TypeError, OSError) as exc:
            gate = {"status":"FAIL", "violations":[{
                "rule_id":"LF_RULE_CONTEXT", "code":"LF_RULE_CONTEXT_INVALID",
                "path":"context"}]}
            table = []
        _write(public / "lf-rule-report.json", {
            "schema_version":"T8_RULE_REPORT_V1",
            "status":gate["status"], "rules":table,
            "violations":gate["violations"]})
        if gate["status"] != "PASS":
            (public / "feedback.json").unlink()
            visible = {"attempts":[{"acceptance":[{
                "name":v["rule_id"], "status":"FAIL", "reason":v["code"],
                "returncode":1, "stdout_excerpt":"", "stderr_excerpt":""}
                for v in gate["violations"]]}]}
            feedback = _visible_feedback(visible, attempt)
            _write(public / "feedback.json", feedback)
            _write(public / "status.json", {
                "schema_version":"LF_NATIVE_RESULT_SUMMARY_V1",
                "task_id":task, "attempt":attempt,
                "proposal_sha256":submitted["proposal_sha256"],
                "task_pack_sha256":submitted["task_pack_sha256"],
                "feedback_sha256":hashlib.sha256(canonical_json_bytes(feedback)).hexdigest(),
                "status":"FAIL", "authority":"REAL_SANDBOX_UNAUTHENTICATED",
                "production_authority":False, "receipt_authenticated":False})
            return False
    client = NativeProposalClient(proposal_file)
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
    if rule_receipts:
        from lf_rule_gate import verified_visible_commands
        report_file = public / "lf-rule-report.json"
        report = strict_json_loads(report_file.read_text("utf-8"))
        report["rules"] = verified_visible_commands(
            report["rules"], visible, raw_task["acceptance_commands"])
        report_file.write_bytes(canonical_json_bytes(report) + b"\n")
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
    parser.add_argument("phase", choices=("preflight", "execute", "dry-run-reuse", "dry-run-lf-rules"))
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--private", type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--reuse-context", type=Path)
    parser.add_argument("--rule-receipt", type=Path)
    a = parser.parse_args()
    if a.phase == "dry-run-lf-rules":
        # Same trusted gate, without model, hidden oracle or paid attempt.
        from lf_rule_gate import evaluate, coverage, RuleGateBlocked
        try:
            if not a.proposal or not a.rule_receipt:
                raise RuleGateBlocked("LF_RULE_CONTEXT_MISSING")
            proposal = strict_json_loads(a.proposal.read_text("utf-8"))
            receipt = strict_json_loads(a.rule_receipt.read_text("utf-8"))
            if (not isinstance(proposal, dict)
                    or set(proposal) != {"schema_version", "summary", "patch", "changed_paths"}
                    or proposal.get("schema_version") != 1
                    or not isinstance(proposal.get("patch"), str)):
                raise RuleGateBlocked("LF_PATCH_INVALID")
            result = evaluate(proposal["patch"], receipt["rule_ids"], root=a.control)
            print(json.dumps({"result": result, "coverage": coverage(result)},
                             sort_keys=True))
            if result["status"] != "PASS":
                print("NATIVE_LF_RULE_DRY_RUN_BLOCKED:" +
                      ",".join(sorted({v["code"] for v in result["violations"]})),
                      file=sys.stderr)
                raise SystemExit(1)
            return
        except (RuleGateBlocked, OSError, ValueError, KeyError, TypeError) as exc:
            print("NATIVE_LF_RULE_DRY_RUN_BLOCKED:LF_RULE_CONTEXT_INVALID",
                  file=sys.stderr)
            raise SystemExit(1)
    if a.phase == "dry-run-reuse":
        # Explicit offline rehearsal; no vendor invocation, no model, no
        # hidden oracle, no native PASS receipt and no attempt registration.
        from reuse_guard import check as check_reuse, DuplicateComponent
        try:
            if not a.source or not a.proposal or not a.reuse_context:
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            candidate = strict_json_loads(a.proposal.read_text("utf-8"))
            if (not isinstance(candidate, dict)
                    or set(candidate) != {"schema_version", "summary", "patch", "changed_paths"}
                    or candidate["schema_version"] != 1
                    or not isinstance(candidate["patch"], str)
                    or not isinstance(candidate["changed_paths"], list)):
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            context = strict_json_loads(a.reuse_context.read_text("utf-8"))
            check_reuse(a.source, candidate["patch"], context)
        except (DuplicateComponent, OSError, ValueError, KeyError) as exc:
            reason = str(exc)
            code = reason.split(":", 1)[0]
            if code not in ("DUPLICA_COMPONENTE_EXISTENTE", "REUTILIZACION_INDETERMINADA"):
                code = "REUTILIZACION_INDETERMINADA"
            print("NATIVE_REUSE_DRY_RUN_BLOCKED:" + (
                reason[:500] if code == "DUPLICA_COMPONENTE_EXISTENTE" else code),
                file=sys.stderr)
            raise SystemExit(1)
        print("NATIVE_REUSE_DRY_RUN_PASS_UNAUTHENTICATED")
        return
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
