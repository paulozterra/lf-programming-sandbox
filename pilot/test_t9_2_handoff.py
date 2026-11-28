"""T9.2 offline Train dispatch and unreachable trigger tests (no GitHub token)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


handoff = module("train_handoff")
trigger = module("test_workflow_triggers")
ROUTES = json.loads((HERE / "train_handoff_map_v1.json").read_text())
POLICY = json.loads((HERE / "workflow_trigger_policy_v1.json").read_text())
SHA = "a" * 40
PR = 777


class API:
    def __init__(self, branch):
        self.branch = branch
        self.writes = []

    def call(self, method, path, body=None):
        from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL
        if method == "GET" and (path == f"/contents/{CONTROL}?ref=main" or
                                (path.startswith("/issues/") and path[8:].isdigit())):
            return fake_api({})(path[1:])
        if method == "GET" and path == "/pulls/777":
            return {"number": 777, "merged": True, "merge_commit_sha": SHA,
                    "base": {"ref": "main", "repo": {"full_name": handoff.REPO}},
                    "head": {"ref": self.branch, "sha": "b" * 40,
                             "repo": {"full_name": handoff.REPO}}}
        if method == "GET" and path == "/commits/" + SHA:
            return {"sha": SHA, "parents": [{"sha": "c" * 40}, {"sha": "b" * 40}],
                    "commit": {"message": "Merge PR #777 via sandbox-train"}}
        if method == "POST":
            self.writes.append((path, body))
            return {}
        if method == "GET":
            return fake_api({})(path[1:])
        raise AssertionError((method, path, body))


class HandoffTests(unittest.TestCase):
    def dispatch(self, branch):
        api = API(branch)
        with patch.object(handoff, "git", return_value=SHA), \
             patch.object(handoff, "validate_train_run"), \
             patch.object(handoff, "validate_request_paths"), \
             patch.object(handoff, "ensure_main_ci", return_value={"status":"MAIN_CI_GREEN"}), \
             patch.object(handoff, "merged_request_slug", return_value="req-987"), \
             patch.object(handoff, "comment_analysis_report"), \
             patch("pilot.exam_issue_lifecycle.close_registered", return_value=None):
            result = handoff.dispatch(api, PR, SHA, 12345, ROUTES)
        return result, api.writes

    def test_request_chain_uses_exact_slug_and_merge(self):
        result, writes = self.dispatch("lf/request/req-987")
        self.assertEqual(result["workflow"], "t7-request.yml")
        self.assertEqual(writes, [("/actions/workflows/t7-request.yml/dispatches",
                                   {"ref": "main",
                                    "inputs": {"slug": "req-987", "merge_sha": SHA}}),
                                  ("/actions/workflows/chain-lots.yml/dispatches",
                                   {"ref": "main", "inputs": {"sweep": "true", "base_sha": SHA}})])

    def test_generated_chain_and_integration(self):
        generated, gw = self.dispatch("lf/generated-t7/" + "d" * 12)
        self.assertEqual(generated["workflow"], "chain-lots.yml")
        self.assertEqual(gw[0][1]["inputs"],
                         {"source_run_id": "12345", "merge_pr": "777",
                          "request_slug": "req-987", "base_sha": SHA,
                                                     "new_plan_request": "req-987"})
        self.assertEqual(gw[1][1]["inputs"], {"sweep": "true", "base_sha": SHA})
        integration, iw = self.dispatch("lf/native-integration/demo-run-123")
        self.assertEqual(integration["workflow"], "chain-lots.yml")
        self.assertEqual(iw[0][1]["inputs"], {"integration_pr": "777", "request_slug": "req-987",
                                                     "base_sha": SHA})
        self.assertEqual(iw[1][1]["inputs"], {"sweep": "true", "base_sha": SHA})

    def test_unmapped_feat_branch_still_sweeps(self):
        result, writes = self.dispatch("feat/manual")
        self.assertEqual(result["status"], "SWEEP_DISPATCHED")
        self.assertEqual(writes, [("/actions/workflows/chain-lots.yml/dispatches",
                                   {"ref": "main", "inputs": {"sweep": "true", "base_sha": SHA}})])

    def test_forged_merge_is_rejected(self):
        api = API("lf/request/req-987")
        pr = api.call("GET", "/pulls/777")
        commit = api.call("GET", "/commits/" + SHA)
        commit["commit"]["message"] = "Merge by human"
        with self.assertRaisesRegex(handoff.HandoffBlocked,
                                    "HANDOFF_MERGE_NOT_TRAIN"):
            handoff.verify_merge(pr, commit, PR, SHA, first_parent=False)
        pr["head"]["repo"]["full_name"] = "attacker/fork"
        with self.assertRaisesRegex(handoff.HandoffBlocked,
                                    "HANDOFF_MERGE_UNTRUSTED"):
            handoff.verify_merge(pr, commit, PR, SHA, first_parent=False)

    def test_push_only_bot_path_fails_offline(self):
        with tempfile.TemporaryDirectory() as td:
            workflow = Path(td) / "only-push.yml"
            workflow.write_text("""on:
  push:
    paths: ['pilot/runs/*/request.md']
jobs:
  entry:
    runs-on: ubuntu-latest
    steps:
      - run: echo unreachable
""")
            self.assertEqual(trigger.unreachable(workflow, POLICY),
                             ["WORKFLOW_DISPARO_INALCANZABLE:only-push.yml"])
            workflow.write_text("""on:
  push:
    paths: ['pilot/runs/*/request.md']
  workflow_dispatch:
jobs:
  entry:
    runs-on: ubuntu-latest
    steps:
      - run: echo reachable
""")
            self.assertEqual(trigger.unreachable(workflow, POLICY), [])

    def test_all_current_workflows_reachable(self):
        self.assertEqual(trigger.scan(HERE.parent, POLICY), [])

    def test_train_handoff_is_direct_not_relying_on_workflow_run(self):
        train = (HERE.parent / ".github/workflows/sandbox-train.yml").read_text()
        self.assertIn("gh workflow run train-handoff.yml", train)
        forward = (HERE.parent / ".github/workflows/train-handoff.yml").read_text()
        self.assertIn("workflow_dispatch:", forward)
        self.assertIn("pilot/train_handoff.py", forward)
        t7 = (HERE.parent / ".github/workflows/t7-request.yml").read_text()
        self.assertIn("workflow_dispatch:", t7)
        self.assertIn("push:", t7)


if __name__ == "__main__":
    unittest.main()
