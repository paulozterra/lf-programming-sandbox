"""T24.1 end-to-end CP3.6 sweep wiring and authenticated historical attempts."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator.chain_contract import ChainBlocked, verified_failures
from pilot.orchestrator.test_t24_integration_replay import worker, failure
from pilot.orchestrator.native_integration_replay import WORKER, INTEGRATION

HEAD = "a" * 40
REPO = "paulozterra/lf-programming-sandbox"
TASK = "req186contrato1"
ROUTE_DEFECT = 43783407265
ATTEMPT_ONE = 43797178945
PASS = 43797847761
FAILED_CP35 = 43797998417
LEGACY_PACK = "b" * 64
CURRENT_PACK = "c" * 64


def _proof(run_id: int, attempt: int, pack: str) -> dict:
    return {"task_id": TASK, "run_id": run_id, "attempt": attempt,
            "task_pack_sha256": pack}


def _run(run_id: int, conclusion: str) -> dict:
    return {"id": run_id, "status": "completed", "conclusion": conclusion,
            "head_branch": "main", "run_attempt": 1, "event": "workflow_run"}


def test_historical_route_defect_then_real_one_and_pass_two_are_valid():
    rows = [_run(ROUTE_DEFECT, "failure"), _run(ATTEMPT_ONE, "failure"),
            _run(PASS, "success")]
    proofs = {ROUTE_DEFECT: _proof(ROUTE_DEFECT, 1, LEGACY_PACK),
              ATTEMPT_ONE: _proof(ATTEMPT_ONE, 1, CURRENT_PACK),
              PASS: _proof(PASS, 2, CURRENT_PACK)}
    # Before T24.1, the two authenticated attempt-one proofs conflicted.
    with pytest.raises(ChainBlocked, match="ATTEMPT_DUPLICATE"):
        verified_failures(TASK, rows, proofs)
    assert verified_failures(TASK, rows, proofs, route_defects={
        ROUTE_DEFECT: LEGACY_PACK}) == [ATTEMPT_ONE]
    # PASS is attempt two; its success must never become a second failure.
    assert proofs[PASS]["attempt"] == 2
    assert [proofs[ATTEMPT_ONE]["attempt"], proofs[PASS]["attempt"]] == [1, 2]



def test_actual_main_t23_migration_binds_historical_route_defect():
    from pilot.worker_v08.native_route_defect import verified_migration
    root = Path(__file__).resolve().parents[2]
    path = root / "pilot/worker_v08/native_tasks/req186contrato1.json"
    registration = json.loads(path.read_text("utf-8"))
    migration = verified_migration(root, TASK, registration)
    assert migration is not None, "T23_ROUTE_MIGRATION_UNVERIFIED"
    assert migration["source_run_id"] == ROUTE_DEFECT
    assert migration["proposal_commit_sha"] == (
        "23517ffc11bb6f763f1771a022d88c348ceeff10")
    assert migration["legacy_task_pack_sha256"] == (
        "aad35e83a04c1ae6d8676cd0b7b61dacef09ac9239ee8f5a3d78ff60e136e08b")
    rows = [_run(ROUTE_DEFECT, "failure"), _run(ATTEMPT_ONE, "failure"),
            _run(PASS, "success")]
    proofs = {
        ROUTE_DEFECT: _proof(ROUTE_DEFECT, 1, migration["legacy_task_pack_sha256"]),
        ATTEMPT_ONE: _proof(ATTEMPT_ONE, 1, migration["corrected_task_pack_sha256"]),
        PASS: _proof(PASS, 2, migration["corrected_task_pack_sha256"]),
    }
    assert verified_failures(TASK, rows, proofs,
        route_defects={migration["source_run_id"]:
                       migration["legacy_task_pack_sha256"]}) == [ATTEMPT_ONE]


def test_route_defect_exemption_cannot_mask_changed_proof():
    rows = [_run(ROUTE_DEFECT, "failure"), _run(ATTEMPT_ONE, "failure")]
    proofs = {ROUTE_DEFECT: _proof(ROUTE_DEFECT, 1, "d" * 64),
              ATTEMPT_ONE: _proof(ATTEMPT_ONE, 1, CURRENT_PACK)}
    with pytest.raises(ChainBlocked, match="ROUTE_DEFECT_PROOF_MISMATCH"):
        verified_failures(TASK, rows, proofs, route_defects={
            ROUTE_DEFECT: LEGACY_PACK})
    assert verified_failures(TASK, rows, {ROUTE_DEFECT: None,
                                           ATTEMPT_ONE: proofs[ATTEMPT_ONE]}) == [ATTEMPT_ONE]


def test_failed_lots_reads_exact_verified_t23_migration_and_keeps_one_real_attempt(tmp_path):
    registry = tmp_path / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"task_spec": {"base_head_sha": HEAD}}))
    rows = [_run(ROUTE_DEFECT, "failure"), _run(ATTEMPT_ONE, "failure"),
            _run(PASS, "success")]
    rows[0]["display_title"] = "route-defect"
    rows[1]["display_title"] = "real-attempt-one"
    rows[2]["display_title"] = "real-pass-two"
    proofs = {ROUTE_DEFECT: _proof(ROUTE_DEFECT, 1, LEGACY_PACK),
              ATTEMPT_ONE: _proof(ATTEMPT_ONE, 1, CURRENT_PACK)}
    seen = []
    def api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        assert path.startswith("actions/workflows/worker-native.yml/runs?")
        return {"total_count": len(rows), "workflow_runs": rows}
    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "api", side_effect=api), \
         patch.dict("os.environ", {"GH_TOKEN": "synthetic"}, clear=False), \
         patch("native_run_history._recognized_run", side_effect=lambda row, name: name == TASK), \
         patch("native_run_history._artifact_json", side_effect=lambda _r, _t, ident: proofs.get(ident)), \
         patch("pilot.worker_v08.native_route_defect.verified_migration",
               return_value={"source_run_id": ROUTE_DEFECT,
                             "legacy_task_pack_sha256": LEGACY_PACK}) as migration:
        result = chain_lots.failed_lots({"SOL-001": {"task_name": TASK}})
    assert result == {"SOL-001": [ATTEMPT_ONE]}
    migration.assert_called_once()


def test_full_sweep_dispatches_immutable_pass_and_continues_other_request(tmp_path):
    registry = tmp_path / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"task_spec": {
        "base_head_sha": HEAD,
        "write_path_patterns": ["contracts/sbx-rem-list.openapi.yaml"]}}))
    plan = [
        ("req-186", {"lots": [{"id": "SOL-001", "area": "CONTRATO", "depends_on": []}]}, {"stage": "LOTS_PLANNED"},
         {"SOL-001": {"task_name": TASK}}),
        ("req-901", {"lots": [{"id": "SOL-002", "area": "BACKEND", "depends_on": []}]}, {"stage": "LOTS_PLANNED"},
         {"SOL-002": {"task_name": "othertask"}}),
    ]
    worker_row = worker(created_at="2026-11-16T03:00:00Z")
    cp35_row = failure()
    dispatched = []
    failed_ledger_reads = []
    def api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path in ("issues/186", "issues/901"):
            return {"number": int(path.split("/")[-1]), "state": "open"}
        if path == f"actions/workflows/{INTEGRATION}/runs?per_page=100":
            return {"total_count": 1, "workflow_runs": [cp35_row]}
        # Synthetic merge metadata only: the historical PASS is before the
        # format feature, so recovery must not download a format artifact.
        if path == "pulls/816":
            return {"number":816,"merged":True,"merge_commit_sha":"f"*40,
                    "merged_at":"2026-11-26T20:00:00Z","base":{"ref":"main"}}
        if path in (f"actions/workflows/{WORKER}/runs?per_page=100",
                    f"actions/workflows/{WORKER}/runs?per_page=100&page=1"):
            return {"total_count": 1, "workflow_runs": [worker_row]}
        if path == f"actions/runs/{FAILED_CP35}/jobs?per_page=100":
            return {"total_count": 1, "jobs": [{
                "name": "integrate", "conclusion": "failure",
                "steps": [{"name": "Integrate PASS artifact into a draft PR with C9 and head-specific CI",
                           "conclusion": "failure"}]}]}
        raise AssertionError(path)
    def run(*args, **kwargs):
        if args[:3] == ("git", "ls-remote", "origin"):
            return ""
        if args[:3] == ("gh", "run", "view"):
            return "integrate 2026-11-16T03:24:37Z CP35_TASK_SCOPE_UNSAFE"
        if args[:3] == ("gh", "workflow", "run"):
            dispatched.append(args)
            return ""
        raise AssertionError(args)
    def read_failed_lots(bindings):
        task = next(iter(bindings.values()))["task_name"]
        failed_ledger_reads.append(task)
        return {next(iter(bindings)): [ATTEMPT_ONE] if task == TASK else []}
    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "plans", return_value=plan), \
         patch.object(chain_lots, "route_request_metadata", return_value=True), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "retry_failed_bot_prs", return_value=[]), \
         patch.multiple(chain_lots,
                         retry_native_infra=lambda *a, **kw: [],
                         recover_pending_worker=lambda *a, **kw: [],
                         recover_unstarted_integration=lambda *a, **kw: [],
                         sync_implemented_registry=lambda *a, **kw: {"status": "REGISTRY_CURRENT"}), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
         patch.object(chain_lots, "publish_missing_registered_pack", return_value=None), \
         patch.object(chain_lots, "publish_legacy_submission_contract", return_value=None), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "sweep_request_enabled", return_value=True), \
         patch.object(chain_lots, "complete_registered_exam_requests", return_value=[]), \
         patch.object(chain_lots, "request_all_lot_exams", return_value=[]), \
         patch.object(chain_lots, "completed_lots", return_value={}), \
         patch.object(chain_lots, "failed_lots", side_effect=read_failed_lots), \
         patch.object(chain_lots, "progress", return_value={
             "stage": "CHAIN_READY", "ready_lot_ids": []}), \
         patch.object(chain_lots, "api", side_effect=api), \
         patch.object(chain_lots, "run", side_effect=run):
        results = chain_lots.process(sweep=True, base_sha=HEAD)
    assert failed_ledger_reads == [TASK, "othertask"]
    assert len(dispatched) == 1
    assert dispatched[0][:4] == ("gh", "workflow", "run", INTEGRATION)
    assert "source_run_id=" + str(PASS) in dispatched[0]
    assert any(row.get("request") == "req-186"
               and row.get("status") == "NATIVE_INTEGRATION_REPLAY_DISPATCHED"
               and row.get("source_run_id") == PASS for row in results)
    assert not any(row.get("request") == "req-901"
                   and row.get("status") == "NATIVE_INTEGRATION_REPLAY_DISPATCHED"
                   for row in results)
    assert not any("worker-native.yml" in str(command) for command in dispatched)


def test_every_recover_or_sweep_import_in_chain_lots_is_called():
    source = (Path(__file__).with_name("chain_lots.py")).read_text("utf-8")
    syntax = ast.parse(source)
    recovery_names = {
        alias.asname or alias.name
        for stmt in ast.walk(syntax) if isinstance(stmt, ast.ImportFrom)
        for alias in stmt.names if (
            alias.name.startswith(("recover", "sweep", "retry_"))
            or (alias.asname or "").startswith(("recover", "replay_", "retry_")))
    }
    actual_calls = {
        node.func.id for node in ast.walk(syntax)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert recovery_names, "expected trusted recovery functions"
    assert not recovery_names - actual_calls, (
        "SWEEP_RECOVERY_IMPORT_NOT_CALLED:" + ",".join(sorted(recovery_names - actual_calls)))
    assert "replay_native_integration" in actual_calls
    assert "recover_route_defects" in actual_calls
    assert "recover_native_feedback" in actual_calls
