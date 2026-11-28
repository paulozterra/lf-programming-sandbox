"""T17.3: trusted-main CP3.6 sweep always wakes Policy C, including idle sweeps.

Static wiring plus a network-free regression for a bot registration that was
already green before the latest code was merged into main.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
import yaml

from pilot import auto_integrate as policy
from pilot.orchestrator.lifecycle_test_support import content, CONTROL

ROOT = Path(__file__).resolve().parents[1]
CHAIN = ROOT / ".github/workflows/chain-lots.yml"
INTEGRATE = ROOT / ".github/workflows/auto-integrate.yml"
SHA = "a" * 40


def actions(doc):
    return doc.get("on", doc.get(True, {}))


def assert_wake_contract(chain, integration):
    workflow = actions(chain)
    job = chain["jobs"]["chain"]
    permissions = job.get("permissions", chain.get("permissions", {}))
    if permissions.get("actions") != "write":
        raise AssertionError("POLICY_C_SWEEP_ACTIONS_WRITE_REQUIRED")
    if "workflow_dispatch" not in workflow:
        raise AssertionError("POLICY_C_SWEEP_DISPATCH_MISSING")
    if not workflow["workflow_dispatch"]["inputs"]["sweep"]["type"] == "boolean":
        raise AssertionError("POLICY_C_SWEEP_INPUT_INVALID")
    steps = job["steps"]
    reconcile = next(i for i, step in enumerate(steps)
                     if "pilot/orchestrator/chain_lots.py" in str(step.get("run", "")))
    wakes = [(i, step) for i, step in enumerate(steps)
             if "gh workflow run auto-integrate.yml" in str(step.get("run", ""))]
    if len(wakes) != 1 or wakes[0][0] <= reconcile:
        raise AssertionError("POLICY_C_SWEEP_WAKE_MISSING")
    step = wakes[0][1]
    condition = str(step.get("if", ""))
    required = ("always()", "github.event_name == 'workflow_dispatch'",
                "inputs.sweep == true", "github.ref == 'refs/heads/main'")
    if any(term not in condition for term in required):
        raise AssertionError("POLICY_C_SWEEP_WAKE_SCOPE_INVALID")
    if '--ref main' not in str(step.get("run", "")):
        raise AssertionError("POLICY_C_SWEEP_WRONG_REF")
    if "workflow_dispatch" not in actions(integration):
        raise AssertionError("POLICY_C_RECEIVER_MISSING")
    receiver = integration["jobs"]["evaluate"]
    if ("github.event_name == 'workflow_dispatch'"
            not in str(receiver.get("if", ""))):
        raise AssertionError("POLICY_C_RECEIVER_NOT_DISPATCHABLE")


class PreviouslyGreenBotAPI:
    def __init__(self, with_candidate=True):
        self.writes = []
        self.candidate = with_candidate
        self.train_dispatched = False
        self.item = {
            "number": 205, "state": "open", "draft": True,
            "changed_files": 2, "labels": [], "body": "registered task",
            "base": {"ref": "main", "repo": {"full_name": policy.REPOSITORY}},
            "head": {"ref": "lf/native-registration/req186contrato1-2f384485df66",
                     "sha": SHA, "repo": {"full_name": policy.REPOSITORY}},
            "user": {"login": policy.BOT},
        }

    def pages(self, path, field):
        if path == "/pulls?state=open":
            return [deepcopy(self.item)] if self.candidate else []
        if path == "/issues/205/events":
            return [{"event": "labeled", "label": {"name": policy.READY_LABEL},
                     "actor": {"login": policy.BOT},
                     "created_at": "2026-11-20T20:00:00Z"}] if self.train_dispatched else []
        if path == "/pulls/205/files":
            return [
                {"filename": "standards/changes/CHG-0123.json"},
                {"filename": "standards/CAMBIOS.md"},
            ]
        if path == f"/commits/{SHA}/check-runs":
            return [{"name": name, "id": index + 101,
                     "head_sha": SHA, "status": "completed",
                     "conclusion": "success", "app": {"slug": "github-actions"}}
                    for index, name in enumerate(policy.REQUIRED)]
        raise AssertionError("Unexpected read " + path)

    def request(self, method, path, data=None):
        if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
            return content({})
        if method == "GET" and path == "/pulls/205":
            return deepcopy(self.item)
        if method == "GET" and path.startswith("/actions/workflows/sandbox-train.yml/runs"):
            return {"workflow_runs": [{"id": 1001, "created_at": "2026-11-20T20:01:00Z",
                                      "display_title": "sandbox-train PR #205",
                                      "status": "queued", "conclusion": None}]}
        if method == "POST":
            self.writes.append((path, data))
            if path == "/actions/workflows/sandbox-train.yml/dispatches":
                self.train_dispatched = True
            if path == "/issues/205/labels":
                self.item["labels"].append({"name": policy.READY_LABEL})
            return {}
        if method == "GET":
            from pilot.orchestrator.lifecycle_test_support import fake_api
            return fake_api({})(path[1:])
        raise AssertionError("Unexpected request " + method + " " + path)


class T173(unittest.TestCase):
    def test_static_wakeup_after_sweep_and_actions_write(self):
        assert_wake_contract(yaml.safe_load(CHAIN.read_text()),
                             yaml.safe_load(INTEGRATE.read_text()))

    def test_missing_actions_write_fails_static_guard(self):
        chain = yaml.safe_load(CHAIN.read_text())
        chain["permissions"]["actions"] = "read"
        with self.assertRaisesRegex(AssertionError, "POLICY_C_SWEEP_ACTIONS_WRITE_REQUIRED"):
            assert_wake_contract(chain, yaml.safe_load(INTEGRATE.read_text()))

    def test_no_change_sweep_still_has_wakeup(self):
        chain = yaml.safe_load(CHAIN.read_text())
        wake = next(step for step in chain["jobs"]["chain"]["steps"]
                    if "gh workflow run auto-integrate.yml" in str(step.get("run", "")))
        self.assertNotIn("needs.*.result", str(wake.get("if", "")))
        self.assertNotIn("success()", str(wake.get("if", "")))
        self.assertIn("always()", str(wake.get("if", "")))

    def test_previously_green_registration_taken_by_policy_on_next_sweep(self):
        # The source CI belongs to an earlier HEAD. It is still GREEN on its
        # exact SHA when a subsequent main sweep dispatches policy C.
        api = PreviouslyGreenBotAPI()
        self.assertEqual(policy.run(api, None, scheduled=True), [
            {"pr": 205, "decision": "LABEL_AND_TRAIN_DISPATCHED"}])
        self.assertEqual(api.writes, [
            ("/issues/205/labels", {"labels": [policy.READY_LABEL]}),
            ("/actions/workflows/sandbox-train.yml/dispatches",
             {"ref": "main", "inputs": {"pr_number": "205"}})])
        # Retry of the same sweep is idempotent: no further writes.
        self.assertEqual(policy.run(api, None, scheduled=True),
                         [{"pr": 205, "decision": "ALREADY_LABELED"}])
        self.assertEqual(len(api.writes), 2)

    def test_no_candidate_sweep_is_noop(self):
        api = PreviouslyGreenBotAPI(with_candidate=False)
        self.assertEqual(policy.run(api, None, scheduled=True), [])
        self.assertFalse(api.writes)


if __name__ == "__main__":
    unittest.main()
