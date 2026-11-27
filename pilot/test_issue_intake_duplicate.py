"""T9.1 verifies opened+labeled only produce one PR and a single CI dispatch."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("issue_intake_dup", HERE / "orchestrator/issue_intake.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)


class Fake:
    def __init__(self, issue):
        self.issue_data = issue
        self.pr = None
        self.created = 0
        self.comments = []

    def issue(self, n):
        return self.issue_data

    def permission(self, who):
        return "write"

    def call(self, method, path, payload=None):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
            return content({})
        if method == "GET" and path.startswith("/pulls?state=all"):
            return [self.pr] if self.pr is not None else []
        if method == "GET" and path.startswith("/issues?state=open&labels=lf-request&"):
            return []  # no competing open request in this legacy single-issue case
        if method == "POST" and path == "/pulls":
            self.created += 1
            self.pr = {"html_url": "https://github.com/paulozterra/lf-programming-sandbox/pull/170"}
            return self.pr
        raise AssertionError((method, path))

    def comment(self, n, body):
        self.comments.append((n, body))


class DuplicateTests(unittest.TestCase):
    def test_opened_then_labeled_single_pr_single_dispatch(self):
        issue = {"number": 160, "state": "open", "user": {"login": "paulozterra"},
                 "created_at": "2026-11-14T16:00:00Z",
                 "body": "### Pedido\n\nImplementa SBX-REM-LIST\n"}
        api = Fake(issue)
        with tempfile.TemporaryDirectory() as tmp, patch.object(intake, "git"), \
             patch("pilot.orchestrator.generated_branch_standards.synchronize") as sync:
            old = Path.cwd()
            try:
                os.chdir(tmp)
                first = intake.intake(api, {"issue": issue, "action": "opened"})
                second = intake.intake(api, {"issue": issue, "action": "labeled"})
            finally:
                os.chdir(old)
        sync.assert_called_once()
        self.assertEqual(sync.call_args.args[1], "request")
        self.assertIn("/pull/170", first)
        self.assertEqual(second, "PEDIDO_YA_REGISTRADO")
        self.assertEqual(api.created, 1)
        self.assertEqual(len(api.comments), 1)
        workflow = yaml.safe_load((HERE.parent / ".github/workflows/request-intake.yml")
                                  .read_text(encoding="utf-8"))
        steps = workflow["jobs"]["intake"]["steps"]
        step = next(x for x in steps if x.get("name") == "Run CI for bot-created request PR")
        self.assertIn("steps.intake.outputs.created == 'true'", step["if"])
        self.assertIn("gh workflow run ci.yml", step["run"])
        creation = next(x for x in steps if x.get("id") == "intake")
        self.assertIn('created=false', creation["run"])
        self.assertIn('PEDIDO_YA_REGISTRADO', creation["run"])
        self.assertIn('created=true', creation["run"])


if __name__ == "__main__":
    unittest.main()
