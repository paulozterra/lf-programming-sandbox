"""T15 offline sweep and pre-green CI neutrality; no real issues or oracles."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "orchestrator"))
from pilot.orchestrator import chain_lots
from pilot.orchestrator.lifecycle_test_support import fake_api

HEAD = "a" * 40


def base_runs(*rows):
    return {"total_count": len(rows), "workflow_runs": list(rows)}


def ci_run(status, conclusion):
    return {"id": 123, "head_sha": HEAD, "head_branch": "main",
            "event": "workflow_dispatch", "run_attempt": 1,
            "path": chain_lots.CI, "repository": {"full_name": chain_lots.REPO},
            "created_at": "2026-11-15T06:00:00Z",
            "status": status, "conclusion": conclusion}


class SweepTests(unittest.TestCase):
    def setUp(self):
        # T15 isolates original orchestration: T20 bot-CI recovery is tested
        # with authenticated, independently mocked GitHub evidence in T20.
        retry = patch.object(chain_lots, "retry_failed_bot_prs", return_value=[])
        retry.start()
        self.addCleanup(retry.stop)
        native = patch.object(chain_lots, "retry_native_infra", return_value=[])
        native.start()
        self.addCleanup(native.stop)
        feedback = patch.object(chain_lots, "recover_native_feedback", return_value=[])
        feedback.start()
        self.addCleanup(feedback.stop)
        route = patch.object(chain_lots, "recover_route_defects", return_value=[])
        route.start()
        self.addCleanup(route.stop)
        integration = patch.object(chain_lots, "replay_native_integration", return_value=[])
        integration.start()
        self.addCleanup(integration.stop)
        ledger = patch.object(chain_lots, "sync_implemented_registry",
                              return_value={"status": "REGISTRY_CURRENT"})
        ledger.start()
        self.addCleanup(ledger.stop)
        r1_worker = patch.object(chain_lots, "recover_pending_worker", return_value=[])
        r1_worker.start()
        self.addCleanup(r1_worker.stop)
        r1_integration = patch.object(chain_lots, "recover_unstarted_integration", return_value=[])
        r1_integration.start()
        self.addCleanup(r1_integration.stop)

    def test_empty_sweep_is_noop_no_registry_write(self):
        with patch.object(chain_lots, "check_main", return_value=HEAD), \
             patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
             patch.object(chain_lots, "plans", return_value=[]), \
             patch.object(chain_lots, "first_parent_merges", return_value=[]), \
             patch.object(chain_lots, "sync_implemented_registry") as registry, \
             patch.object(chain_lots, "run", return_value="[]") as command:
            result = chain_lots.process(sweep=True, base_sha=HEAD)
        self.assertEqual(result, [{"status": "NO_OWNER_REGISTERED_CHAIN_PLANS"}])
        registry.assert_not_called()
        command.assert_called_once()
        self.assertEqual(command.call_args.args[:3], ("gh", "pr", "list"))

    def test_exam_on_main_registers_ready_task(self):
        lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
                "production_authority": False, "handoff_allowed": False,
                "worker_invoked": False,
                "lots": [{"id": "SOL-1", "depends_on": [], "area": "CONTRATO"}]}
        binding = {"SOL-1": {"task_name": "sample1", "lot_id": "SOL-1",
                             "template_path": "task.json",
                             "holdout_metadata_path": "sample1.json"}}
        state = {"stage": "LOTS_PLANNED"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            import shutil
            source_config = Path(__file__).resolve().parents[1] / "pilot/config"
            target_config = root / "pilot/config"
            (target_config / "projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_config / "active_project.json", target_config / "active_project.json")
            shutil.copy2(source_config / "projects/sandbox.json", target_config / "projects/sandbox.json")
            hidden = root / "pilot/holdouts/sample1.oracle.json.age"
            hidden.parent.mkdir(parents=True)
            hidden.write_bytes(b"opaque")
            with patch.object(chain_lots, "ROOT", root), \
                 patch.object(chain_lots, "check_main", return_value=HEAD), \
                 patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
                 patch.object(chain_lots, "plans", return_value=[("req-901", lots, state, binding)]), \
                 patch.object(chain_lots, "api", side_effect=fake_api({})), \
                 patch.object(chain_lots, "first_parent_merges", return_value=[]), \
                 patch.object(chain_lots, "completed_lots", return_value={}), \
                 patch.object(chain_lots, "failed_lots", return_value={}), \
                 patch.object(chain_lots, "pending_draft", return_value=False), \
                 patch.object(chain_lots, "run", return_value="[]") as github_commands, \
                 patch.object(chain_lots, "admit_registration", return_value=None), \
                 patch.object(chain_lots, "prepare_successor", return_value={"status": "DRAFT_PREPARED"}) as prepare:
                result = chain_lots.process(sweep=True, base_sha=HEAD)
        self.assertTrue(any(item.get("status") == "DRAFT_PREPARED" for item in result))
        prepare.assert_called_once()
        # The T17 sweep must share the same mocked GitHub boundary as CP3.6,
        # not run a real gh command from the offline T15 fixture.
        self.assertGreaterEqual(github_commands.call_count, 2)
        self.assertTrue(all(call.args[:3] == ("gh", "pr", "list")
                            for call in github_commands.call_args_list))

    def test_closed_discarded_request_ignored(self):
        rows = {"req-901": {"number": 901, "state": "closed", "state_reason": "not_planned"},
                "req-902": {"number": 902, "state": "closed", "state_reason": "duplicate"}}
        from pilot.orchestrator.lifecycle_test_support import fake_api
        with patch.object(chain_lots, "api", side_effect=lambda p: rows["req-" + p.split("/")[-1]] if p.startswith("issues/") else fake_api({})(p)):
            self.assertFalse(chain_lots.sweep_request_enabled("req-901"))
            self.assertFalse(chain_lots.sweep_request_enabled("req-902"))
        with patch.object(chain_lots, "check_main", return_value=HEAD), \
             patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
             patch.object(chain_lots, "plans", return_value=[
                 ("req-901", {}, {"stage": "LOTS_PLANNED"}, {}),
                 ("req-902", {}, {"stage": "LOTS_PLANNED"}, {})]), \
             patch.object(chain_lots, "first_parent_merges", return_value=[]), \
             patch.object(chain_lots, "api", side_effect=lambda p: rows["req-" + p.split("/")[-1]] if p.startswith("issues/") else fake_api({})(p)), \
             patch.object(chain_lots, "request_all_lot_exams") as request, \
             patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
             patch.object(chain_lots, "prepare_successor") as prepare:
            self.assertEqual(chain_lots.process(sweep=True, base_sha=HEAD),
                             [{"request": "req-901", "status": "SKIPPED_NOT_ROUTE_REQUEST"},
                               {"request": "req-902", "status": "SKIPPED_NOT_ROUTE_REQUEST"},
                               {"request": "req-901", "status": "REQUEST_CLOSED"},
                               {"request": "req-902", "status": "REQUEST_CLOSED"}])
            request.assert_not_called()
            prepare.assert_not_called()

    def test_before_main_ci_is_neutral_and_fails_only_on_red(self):
        for payload in (base_runs(), base_runs(ci_run("in_progress", None))):
            with patch.object(chain_lots, "api", return_value=payload):
                self.assertEqual(chain_lots.main_ci_decision(HEAD), "WAITING_MAIN_CI")
        with patch.object(chain_lots, "api", return_value=base_runs(
                ci_run("completed", "failure"))):
            with self.assertRaisesRegex(ValueError, "BASE_NO_VERDE"):
                chain_lots.main_ci_decision(HEAD)
        with patch.object(chain_lots, "check_main", return_value=HEAD), \
             patch.object(chain_lots, "event_kind", return_value="TRAIN"), \
             patch.object(chain_lots, "main_ci_decision", return_value="WAITING_MAIN_CI"), \
             patch.object(chain_lots, "sync_implemented_registry") as registry, \
             patch.object(chain_lots, "plans") as plans:
            self.assertEqual(chain_lots.process(event_run_id=777, require_ci=True),
                             [{"status": "WAITING_MAIN_CI", "head_sha": HEAD}])
            registry.assert_not_called()
            plans.assert_not_called()

    def test_sweep_rejects_wrong_commit_before_processing(self):
        with patch.object(chain_lots, "check_main", return_value=HEAD), \
             patch.object(chain_lots, "plans") as plans:
            with self.assertRaisesRegex(ValueError, "CHAIN_SWEEP_BASE_INVALID"):
                chain_lots.process(sweep=True, base_sha="b" * 40)
            plans.assert_not_called()


if __name__ == "__main__":
    unittest.main()
