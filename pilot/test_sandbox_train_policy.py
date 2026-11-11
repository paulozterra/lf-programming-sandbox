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

    def test_labeled_draft_transitions_then_normal_merge_flow(self):
        draft = sample_pr(draft=True)
        draft["node_id"] = "PR_eligible"
        ready = sample_pr(draft=False)
        ready["node_id"] = "PR_eligible"
        seen = []
        def fake_graphql(query, variables):
            seen.append((query, variables))
            return {"markPullRequestReadyForReview": {
                "pullRequest": {"id": "PR_eligible", "isDraft": False}}}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox",
                                     "TRAIN_RECEIPT": os.devnull}), \
             patch.object(train, "pr_data", side_effect=[draft, ready, ready, ready]) as read, \
             patch.object(train, "graphql", side_effect=fake_graphql), \
             patch.object(train, "main_sha", return_value="m" * 40), \
             patch.object(train, "await_checks", return_value={"backend": {"conclusion": "success"}}), \
             patch.object(train, "api") as api_mock:
            api_mock.side_effect = lambda method, path, payload=None, expected=(200,): (
                {"behind_by": 0, "status": "ahead"} if path.startswith("/compare/") else
                {"merged": True, "sha": "c" * 40} if path.endswith("/merge") else
                {"parents": [{}, {}]} if path == "/commits/" + "c" * 40 else
                (_ for _ in ()).throw(AssertionError(path)))
            train.run(101)
        self.assertEqual(len(seen), 1)
        self.assertIn("markPullRequestReadyForReview", seen[0][0])
        self.assertEqual(seen[0][1], {"id": "PR_eligible"})
        self.assertEqual(read.call_count, 3)
        self.assertTrue(any(c.args[0] == "PUT" and c.args[1] == "/pulls/101/merge"
                            for c in api_mock.call_args_list))

    def test_draft_without_label_denied_before_graphql(self):
        draft = sample_pr(draft=True)
        draft["labels"] = []
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft), \
             patch.object(train, "graphql") as mutation:
            with self.assertRaisesRegex(train.TrainError, "PR_CLOSED_OR_DRAFT"):
                train.run(101)
            mutation.assert_not_called()

    def test_forked_draft_denied_before_graphql(self):
        draft = sample_pr(draft=True, fork=True)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft), \
             patch.object(train, "graphql") as mutation:
            with self.assertRaisesRegex(train.TrainError, "FORK_REJECTED"):
                train.run(101)
            mutation.assert_not_called()

    def test_failed_mutation_blocks_without_followup(self):
        draft = sample_pr(draft=True)
        draft["node_id"] = "PR_eligible"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft) as read, \
             patch.object(train, "graphql", side_effect=train.TrainError("GRAPHQL_RESPONSE_INVALID")), \
             patch.object(train, "main_sha") as main, \
             patch.object(train, "api") as api_mock:
            with self.assertRaisesRegex(train.TrainError, "DRAFT_READY_FAILED"):
                train.run(101)
            self.assertEqual(read.call_count, 1)
            main.assert_not_called()
            api_mock.assert_not_called()

    def test_closed_pr_denied_even_with_label(self):
        draft = sample_pr(draft=True)
        draft["state"] = "closed"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft), \
             patch.object(train, "graphql") as mutation:
            with self.assertRaisesRegex(train.TrainError, "PR_CLOSED_OR_DRAFT"):
                train.run(101)
            mutation.assert_not_called()

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
        self.assertIn("update_branch_locally(", source)
        self.assertIn('"sha": initial_head, "merge_method": "merge"', source)

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
            if path.endswith("/dispatches"):
                return {}
            if path.endswith("/merge"):
                return {"merged": True, "sha": "c" * 40}
            if path == "/commits/" + "c" * 40:
                return {"parents": [{"sha": "a" * 40}, {"sha": "b" * 40}]}
            raise AssertionError(path)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox", "GH_TOKEN": "test-token", "TRAIN_RECEIPT": os.devnull}), \
             patch.object(train, "api", side_effect=fake_api), \
             patch.object(train, "pr_data", side_effect=fake_pr), \
             patch.object(train, "main_sha", return_value="m" * 40), \
             patch.object(train, "await_checks", return_value={"backend (Maven verify)": {"conclusion": "success"}}), \
             patch.object(train, "update_branch_locally", return_value="b" * 40) as local_update, \
             patch.object(train.time, "sleep", return_value=None):
            train.run(77)
        dispatch = [c for c in calls if c[1] == "/actions/workflows/ci.yml/dispatches"]
        self.assertEqual(len(dispatch), 1)
        self.assertEqual(dispatch[0][2], {"ref": "feat/test"})
        local_update.assert_called_once_with("feat/test", "a" * 40, "m" * 40, "test-token", "paulozterra/lf-programming-sandbox")

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
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox", "TRAIN_RECEIPT": os.devnull}), \
             patch.object(train, "api", side_effect=fake_api), \
             patch.object(train, "pr_data", return_value=pr), \
             patch.object(train, "main_sha", return_value="m" * 40), \
             patch.object(train, "await_checks", return_value={"backend (Maven verify)": {"conclusion": "success"}}), \
             patch.object(train, "update_branch_locally", side_effect=AssertionError("no update expected")):
            train.run(77)
        self.assertFalse(any(c[1] == "/actions/workflows/ci.yml/dispatches" for c in calls))

    def test_ci_dispatch_is_enabled_and_restricted_to_updated_head(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("  workflow_dispatch:", ci)
        source = CODE.read_text()
        self.assertIn('dispatch_updated_head_ci(updated["head"]["ref"], merged_head)', source)
        self.assertIn('expected=(204,)', source)


    def test_all_workflows_reject_runner_context_in_job_env(self):
        checker_path = ROOT / "pilot/check_workflow_job_env.py"
        checker_spec = importlib.util.spec_from_file_location("workflow_env_guard", checker_path)
        checker = importlib.util.module_from_spec(checker_spec)
        checker_spec.loader.exec_module(checker)
        self.assertEqual(checker.main(), 0)

    def test_workflow_env_guard_rejects_invalid_job_env(self):
        checker_path = ROOT / "pilot/check_workflow_job_env.py"
        checker_spec = importlib.util.spec_from_file_location("workflow_env_guard", checker_path)
        checker = importlib.util.module_from_spec(checker_spec)
        checker_spec.loader.exec_module(checker)
        invalid = """name: invalid
on: push
jobs:
  merge:
    runs-on: ubuntu-latest
    env:
      TRAIN_RECEIPT: ${{ runner.temp }}/receipt.json
    steps:
      - run: echo done
"""
        self.assertEqual(len(checker.violations(invalid, "invalid.yml")), 1)
        valid = invalid.replace("      TRAIN_RECEIPT: ${{ runner.temp }}/receipt.json", "      TRAIN_RECEIPT: sandbox-train-receipt.json")
        self.assertEqual(checker.violations(valid), [])
        # runner context is legal in a step-level env; only reject job-level.
        step_env = """jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Read artifact
        env:
          TRAIN_RECEIPT: ${{ runner.temp }}/receipt.json
        run: echo ok
"""
        self.assertEqual(checker.violations(step_env), [])

if __name__ == "__main__":
    unittest.main()
