"""CHG-0259: immutable per-sweep inventories and equivalent recovery decisions."""
import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path

import chain_lots as cl
from pilot.orchestrator import sweep_api_budget as budget
from pilot.orchestrator import native_infra_retry, native_route_recovery
from pilot.orchestrator.native_pending_recovery import recover as pending_recover
from pilot.worker_v08.native_feedback_delivery import recover_sweep as feedback_recover

WORKER = "actions/workflows/worker-native.yml/runs?per_page=100"
ARTIFACTS = "actions/runs/123/artifacts?per_page=100"


class BudgetTests(unittest.TestCase):
    @staticmethod
    def fake_process(log):
        def fake(args, **kwargs):
            argv = tuple(args)
            log.append(argv)
            if argv[:2] == ("gh", "api"):
                route = argv[2]
                if "worker-native.yml/runs" in route:
                    data = {"workflow_runs": [], "total_count": 0}
                elif "artifacts" in route:
                    data = {"artifacts": [], "total_count": 0}
                else:
                    raise AssertionError(argv)
                return subprocess.CompletedProcess(args, 0, json.dumps(data), "")
            if argv[:3] == ("gh", "pr", "list"):
                self_rows = [{
                    "number": 99, "headRefName": "lf/test-a",
                    "headRefOid": "a" * 40,
                    "author": {"login": "github-actions[bot]"},
                    "isDraft": True, "title": "test"}]
                return subprocess.CompletedProcess(args, 0, json.dumps(self_rows), "")
            if argv[:3] == ("gh", "pr", "close"):
                return subprocess.CompletedProcess(args, 0, "", "")
            raise AssertionError(argv)
        return fake

    def decisions(self):
        infra = native_infra_retry.retry_native_infra(
            "a" * 40, cl.run, cl.api, cl.REPO, Path("/tmp"))
        route = native_route_recovery.history(cl.api)
        feedback = feedback_recover(cl.run, cl.api, cl.REPO, Path("/tmp"))
        arts = (cl.api(ARTIFACTS), cl.api(ARTIFACTS))
        drafts = (cl.pending_draft("lf/native-registration/"),
                  cl.pending_draft("lf/chain-complete/"))
        return infra, route, feedback, arts, drafts

    def test_recovery_decisions_unchanged_and_synthetic_sweep_budget(self):
        raw_calls = []
        with patch.object(cl.subprocess, "run",
                          side_effect=self.fake_process(raw_calls)):
            original = self.decisions()
            without = len(raw_calls)
            raw_calls.clear()
            out = io.StringIO()
            with redirect_stdout(out):
                with budget.session() as tracked:
                    with budget.phase("T20_NATIVE_INFRA"):
                        cached = self.decisions()
                    # A shared open-PR snapshot also works in the later phase.
                    with budget.phase("CHAIN"):
                        self.assertFalse(cl.pending_draft("lf/evidence/"))
            self.assertEqual(original, cached)
            self.assertGreater(without, len(raw_calls))
            # Explicit N=3 for this simulated inventory/PR fixture.
            # Real production N can only be pinned after a sweep runs on main.
            self.assertLessEqual(sum(tracked.calls.values()), 3)
            self.assertEqual(sum(tracked.calls.values()), len(raw_calls))
            self.assertIn("API_CALLS:T20_NATIVE_INFRA:3", out.getvalue())
            self.assertIn("API_CALLS:TOTAL:3", out.getvalue())
            self.assertGreater(sum(tracked.hits.values()), 0)

    def test_no_pending_inspection_without_live_plan(self):
        calls = []
        refs = "\n".join([
            "a" * 40 + "\trefs/heads/lf/native-proposal/oldtask",
            "b" * 40 + "\trefs/heads/lf/native-proposal/completetask",
        ])
        def fake_run(*args, **kwargs):
            calls.append(args)
            if args[:3] == ("git", "ls-remote", "--heads"):
                return refs
            raise AssertionError("unexpected " + repr(args))
        result = pending_recover("f" * 40, fake_run,
                                 lambda path: self.fail("API should not be read"),
                                 cl.REPO, Path("/tmp"),
                                 allowed_task=lambda task: False)
        self.assertEqual(result, [])
        self.assertEqual(len(calls), 1)

    def test_cache_is_scoped_to_session_and_returns_copies(self):
        calls = []
        with patch.object(cl.subprocess, "run",
                          side_effect=self.fake_process(calls)):
            with budget.session():
                first = cl.api(WORKER)
                first["total_count"] = 99
                self.assertEqual(cl.api(WORKER)["total_count"], 0)
            with budget.session():
                self.assertEqual(cl.api(WORKER)["total_count"], 0)
        self.assertEqual(len(calls), 2)

    def test_pr_list_snapshot_invalidates_after_write(self):
        calls = []
        with patch.object(cl.subprocess, "run",
                          side_effect=self.fake_process(calls)):
            with budget.session():
                self.assertFalse(cl.pending_draft("lf/chain-complete/"))
                self.assertFalse(cl.pending_draft("lf/evidence/"))
                cl.run("gh", "pr", "close", "99", "--repo", cl.REPO)
                self.assertFalse(cl.pending_draft("lf/chain-complete/"))
        self.assertEqual([c[:3] for c in calls],
                         [("gh", "pr", "list"), ("gh", "pr", "close"),
                          ("gh", "pr", "list")])


if __name__ == "__main__":
    unittest.main()
