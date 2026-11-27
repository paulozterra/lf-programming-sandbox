"""T9 deterministic offline tests: accepted issue, outsider, altered PR, provenance."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class T9(unittest.TestCase):
    def setUp(self):
        self.mod = load("issue_intake_t9", "issue_intake.py")
        self.issue = {
            "number": 159, "state": "open",
            "user": {"login": "paulozterra"},
            "created_at": "2026-11-14T15:00:00Z",
            "body": "### Pedido\n\nImplementa SBX-REM-LIST\nCon filtro q.\n",
        }

    def test_literal_bytes_and_metadata(self):
        files = self.mod.expected_files(self.issue)
        self.assertEqual(files["pilot/runs/req-159/request.md"],
                         b"Implementa SBX-REM-LIST\nCon filtro q.\n")
        self.assertEqual(json.loads(files["pilot/runs/req-159/request_meta.json"]),
                         {"issue": 159, "author": "paulozterra",
                          "date": "2026-11-14T15:00:00Z"})

    def test_external_author_is_rejected_and_commented(self):
        class API:
            def issue(self, number):
                return self_data
            def call(self, method, path, payload=None):
                from pilot.orchestrator.lifecycle_test_support import fake_api
                return fake_api({})(path[1:])
            def permission(self, author):
                return "none"
            def comment(self, number, body):
                comments.append((number, body))
        self_data = dict(self.issue)
        self_data["user"] = {"login": "external"}
        comments = []
        self.assertEqual(self.mod.intake(API(), {"issue": self_data}),
                         "PEDIDO_AUTOR_NO_AUTORIZADO")
        self.assertEqual(comments,
                         [(159, "PEDIDO_AUTOR_NO_AUTORIZADO")])

    def test_valid_issue_produces_exact_bot_branch_and_pr(self):
        calls = []
        files = self.mod.expected_files(self.issue)
        class API:
            def issue(self, number):
                return self_data
            def permission(self, author):
                return "write"
            def call(self, method, path, payload=None):
                from pilot.orchestrator.lifecycle_test_support import content, CONTROL
                if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                    return content({})
                calls.append((method, path, payload))
                if method == "GET":
                    return []
                return {"html_url": "https://github.com/paulozterra/lf-programming-sandbox/pull/170"}
            def comment(self, number, body):
                calls.append(("COMMENT", number, body))
        self_data = self.issue
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(self.mod, "git") as fake_git, \
             patch("pilot.orchestrator.generated_branch_standards.synchronize") as sync:
            from os import chdir, getcwd
            old = getcwd()
            try:
                chdir(tmp)
                self.assertIn("/pull/170", self.mod.intake(API(), {"issue": self.issue}))
                self.assertEqual(Path("pilot/runs/req-159/request.md").read_bytes(),
                                 files["pilot/runs/req-159/request.md"])
            finally:
                chdir(old)
        sync.assert_called_once()
        self.assertEqual(sync.call_args.args[1], "request")
        self.assertIn(("switch", "-c", "lf/request/req-159", "origin/main"),
                      [call.args for call in fake_git.call_args_list])
        self.assertTrue(any(x[0] == "POST" and x[1] == "/pulls" and
                            x[2]["draft"] is False for x in calls))

    def test_tampered_request_is_blocked(self):
        class API:
            def issue(self, number):
                return self_data
            def permission(self, author):
                return "write"
            def content_bytes(self, path, sha):
                return b"altered" if path.endswith("/request.md") else expected[path]
        self_data = self.issue
        expected = self.mod.expected_files(self.issue)
        with self.assertRaisesRegex(self.mod.Blocked, "PEDIDO_CONTENIDO_MODIFICADO"):
            self.mod.verify(API(), 159, "a" * 40, list(expected))

    def test_suspended_intake_never_publishes(self):
        from pilot.orchestrator.lifecycle_test_support import fake_api
        api = fake_api({"req-159": {"state": "SUSPENDING", "authorization_pr": 77}})
        issue = self.issue
        class SuspendedAPI:
            def issue(self, number):
                return issue
            def call(self, method, path, payload=None):
                assert method == "GET"
                return api(path[1:])
        with patch.object(self.mod, "git") as git:
            self.assertEqual(self.mod.intake(SuspendedAPI(), {"issue": issue}),
                             "REQUEST_SUSPENDED")
            git.assert_not_called()

    def test_form_is_not_arbitrary_issue_body(self):
        with self.assertRaisesRegex(self.mod.Blocked, "PEDIDO_FORMULARIO_INVALIDO"):
            self.mod.request_text("raw forged body")


if __name__ == "__main__":
    unittest.main()
