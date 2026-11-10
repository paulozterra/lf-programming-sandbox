"""Offline P0 policy gates: no network, token, database, or merge."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sandbox-train.yml"
CODE = ROOT / "pilot/sandbox_train.py"
spec = importlib.util.spec_from_file_location("sandbox_train", CODE)
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)


def sample_pr(draft=False, fork=False):
    return {"state": "open", "draft": draft,
            "base": {"ref": "main"},
            "head": {"ref": "feat/test", "sha": "a" * 40,
                     "repo": {"full_name": "foreign/repo" if fork else "paulozterra/lf-programming-sandbox"}},
            "labels": [{"name": "ready-to-merge"}], "mergeable": True}


class PolicyTests(unittest.TestCase):
    def test_no_target_no_custom_secrets_no_external_privileges(self):
        data = WORKFLOW.read_text()
        self.assertNotIn("pull_request_target", data)
        self.assertNotIn("secrets.", data)
        self.assertIn("actions: write", data)
        self.assertIn("contents: write", data)
        self.assertIn("pull-requests: write", data)
        self.assertIn("checks: read", data)
        self.assertIn("cancel-in-progress: false", data)
        self.assertIn("group: sandbox-train", data)
        self.assertIn("persist-credentials: false", data)
        self.assertIn("ref: main", data)
        self.assertIn("types: [labeled]", data)
        self.assertIn("workflow_dispatch:", data)

    def test_draft_and_fork_denied(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}):
            for pr in (sample_pr(draft=True), sample_pr(fork=True)):
                with self.assertRaises(train.TrainError):
                    train.check_pr(pr)

    def test_label_missing_denied(self):
        pr = sample_pr()
        pr["labels"] = []
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}):
            with self.assertRaisesRegex(train.TrainError, "LABEL_MISSING"):
                train.check_pr(pr)

    def test_merge_requires_exact_sha_and_merge_commit(self):
        source = CODE.read_text()
        self.assertIn('"sha": initial_head, "merge_method": "merge"', source)
        self.assertIn('len(commit["parents"]) != 2', source)
        self.assertNotIn('"merge_method": "squash"', source)
        self.assertNotIn('"merge_method": "rebase"', source)
        self.assertIn('"/pulls/{number}/update-branch"', source)
        self.assertIn('"expected_head_sha": initial_head', source)

    def test_checks_must_be_from_exact_head(self):
        self.assertIn('run["head_sha"] != sha', CODE.read_text())
        self.assertIn('run["app"]["slug"] != "github-actions"', CODE.read_text())
        self.assertIn('"CHECK_WAIT_TIMEOUT"', CODE.read_text())
        self.assertIn('"RESTART_LIMIT_EXCEEDED"', CODE.read_text())
        self.assertTrue(train.REQUIRED)
        self.assertLessEqual(train.MAX_RESTARTS, 3)


    def test_dispatch_after_update_only(self):
        """Simulate a stale PR: updated HEAD must trigger CI exactly once."""
        pr = sample_pr()
        updated = sample_pr()
        updated["head"]["sha"] = "b" * 40
        responses = {"pr": [pr, updated, updated, updated, updated]}
        calls = []
        def fake_pr(_):
            return responses["pr"].pop(0) if responses["pr"] else updated
        def fake_api(method, path, payload=None, expected=(200,)):
            calls.append((method, path, payload))
            if path.startswith("/compare/"):
                return {"behind_by": 1, "status": "diverged"} if len([c for c in calls if c[1].startswith("/compare/")]) == 1 else {"behind_by": 0, "status": "ahead"}
            if path.endswith("/update-branch"):
                return {}
            if path.endswith("/dispatches"):
                return {}
            if path.endswith("/merge"):
                return {"merged": True, "sha": "c" * 40}
            if path == "/commits/" + "c" * 40:
                return {"parents": [{"sha": "a" * 40}, {"sha": "b" * 40}]}
            raise AssertionError(path)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox", "TRAIN_RECEIPT": os.devnull}), \\
             patch.object(train, "api", side_effect=fake_api), \\
             patch.object(train, "pr_data", side_effect=fake_pr), \\
             patch.object(train, "main_sha", return_value="m" * 40), \\
             patch.object(train, "await_checks", return_value={"backend (Maven verify)": {"conclusion": "success"}}), \\
             patch.object(train.time, "sleep", return_value=None):
            train.run(77)
        dispatch = [c for c in calls if c[1] == "/actions/workflows/ci.yml/dispatches"]
        self.assertEqual(len(dispatch), 1)
        self.assertEqual(dispatch[0][2], {"ref": "feat/test"})
        self.assertEqual(len([c for c in calls if c[1].endswith("/update-branch")]), 1)

    def test_no_dispatch_if_branch_not_updated(self):
        pr = sample_pr()
        calls = []
        def fake_api(method, path, payload=None, expected=(200,)):
            calls.append((method, path, payload))
            if path.startswith("/compare/"):
                return {"behind_by": 0, "status": "ahead"}
            if path.endswith("/merge"):
                return {"merged": True, "sha": "c" * 40}
            if path == "/commits/" + "c" * 40:
                return {"parents": [{}, {}]}
            raise AssertionError(path)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox", "TRAIN_RECEIPT": os.devnull}), \\
             patch.object(train, "api", side_effect=fake_api), \\
             patch.object(train, "pr_data", return_value=pr), \\
             patch.object(train, "main_sha", return_value="m" * 40), \\
             patch.object(train, "await_checks", return_value={"backend (Maven verify)": {"conclusion": "success"}}):
            train.run(77)
        self.assertFalse(any(c[1] == "/actions/workflows/ci.yml/dispatches" for c in calls))

    def test_ci_dispatch_is_enabled_and_restricted_to_updated_head(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("  workflow_dispatch:", ci)
        source = CODE.read_text()
        self.assertIn('dispatch_updated_head_ci(updated["head"]["ref"], updated["head"]["sha"])', source)
        self.assertIn('expected=(204,)', source)

if __name__ == "__main__":
    unittest.main()
