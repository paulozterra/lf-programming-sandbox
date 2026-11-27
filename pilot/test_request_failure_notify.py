"""T9.1 offline notification, association, duplicate suppression, and doubled intake."""
import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("request_failure_notify", HERE / "request_failure_notify.py")
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class Fake:
    def __init__(self):
        self.writes = []
        self.comments = []
        self.labels = [{"name": "lf-request"}]

    def api(self, method, path, body=None):

        from pilot.orchestrator.lifecycle_test_support import content, CONTROL

        if method == "GET" and path == f"/contents/{CONTROL}?ref=main":

            return content({})
        if method == "GET" and path == "/issues/160":
            return {"number": 160, "state": "open", "labels": self.labels}
        if method == "POST":
            self.writes.append((path, body))
            if path.endswith("/labels"):
                self.labels.append({"name": "lf-request-blocked"})
            if path.endswith("/comments"):
                self.comments.append({"user": {"login": "github-actions[bot]"}, "body": body["body"]})
            return {}
        raise AssertionError((method, path))

    def pages(self, path):
        self_ref = self
        return self_ref.comments


class Tests(unittest.TestCase):
    def run_obj(self, title="T9 intake req-160", conclusion="failure"):
        return {"id": 123, "name": "T9 issue request intake",
                "repository": {"full_name": notify.REPO},
                "display_title": title, "conclusion": conclusion,
                "html_url": f"https://github.com/{notify.REPO}/actions/runs/123"}

    def test_error_and_url_and_label_are_emitted_once(self):
        api = Fake()
        run = self.run_obj()
        self.assertEqual(notify.emit(api, run, []), "RUTA_NOTIFIED")
        self.assertEqual(notify.emit(api, run, []), "RUTA_ALREADY_NOTIFIED")
        self.assertEqual([p for p, _ in api.writes],
                         ["/issues/160/labels", "/issues/160/comments"])
        body = api.comments[0]["body"]
        self.assertIn("PEDIDO_INTAKE_FALLIDO", body)
        self.assertIn("/actions/runs/123", body)

    def test_nonterminal_and_wrong_issue_not_notified(self):
        api = Fake()
        self.assertEqual(notify.emit(api, self.run_obj(conclusion="success"), []),
                         "RUTA_NO_ISSUE_ASSOCIATION")
        self.assertEqual(notify.emit(api, self.run_obj(title="unknown"), []),
                         "RUTA_NO_ISSUE_ASSOCIATION")
        self.assertEqual(api.writes, [])

    def test_non_bot_request_branch_cannot_notify(self):
        class Untrusted(Fake):
            def api(self, method, path, body=None):
                from pilot.orchestrator.lifecycle_test_support import content, CONTROL
                if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                    return content({})
                if method == "GET" and path.startswith("/pulls?state=all"):
                    return [{"user": {"login": "human"},
                             "head": {"ref": "lf/request/req-160"}}]
                return super().api(method, path, body)
        api = Untrusted()
        run = self.run_obj(title="untrusted")
        run["name"] = "ci"
        run["head_branch"] = "lf/request/req-160"
        self.assertEqual(notify.emit(api, run, []), "RUTA_PR_ORIGEN_NO_CONFIABLE")
        self.assertEqual(api.writes, [])

    def test_untrusted_ci_title_cannot_claim_another_issue(self):
        run = self.run_obj(title="PR malicious req-160")
        run["name"] = "ci"
        run["head_branch"] = "feature/unrelated"
        self.assertIsNone(notify.resolve_issue(run))
        run["head_branch"] = "lf/request/req-161"
        self.assertEqual(notify.resolve_issue(run), 161)

    def test_conflicting_issue_numbers_fail_closed(self):
        run = self.run_obj(title="T9 intake req-160")
        run["head_branch"] = "lf/request/req-161"
        self.assertIsNone(notify.resolve_issue(run))

    def test_missing_ci_dispatched_is_reported_but_existing_ci_is_not(self):
        class Survey(Fake):
            existing_ci = False
            def api(self, method, path, body=None):
                from pilot.orchestrator.lifecycle_test_support import content, CONTROL
                if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                    return content({})
                if method == "GET" and path.startswith("/issues?state=open"):
                    return [{"number": 160, "state": "open",
                             "created_at": "2026-11-14T15:00:00Z"}]
                if method == "GET" and path.startswith("/pulls?state=all"):
                    return [{"number": 161, "user": {"login": "github-actions[bot]"},
                             "head": {"ref": "lf/request/req-160"}}]
                if method == "GET" and path.startswith("/actions/workflows/ci.yml/runs"):
                    return {"workflow_runs": [{"id": 7}] if self.existing_ci else []}
                return super().api(method, path, body)
        api = Survey()
        now = datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc)
        intake = self.run_obj(conclusion="success")
        self.assertEqual(notify.audit_undispatched_requests(api, [intake], now),
                         ["160:RUTA_NOTIFIED"])
        self.assertIn("PEDIDO_CI_NO_DISPARADO", api.comments[0]["body"])
        api.existing_ci = True
        self.assertEqual(notify.audit_undispatched_requests(api, [intake], now), [])

    def test_stalled_workflow_is_notified_only_after_timeout(self):
        api = Fake()
        run = self.run_obj()
        run["status"] = "in_progress"
        run["conclusion"] = None
        run["created_at"] = "2026-11-14T15:00:00Z"
        early = datetime(2026, 11, 14, 15, 10, tzinfo=timezone.utc)
        late = datetime(2026, 11, 14, 15, 30, tzinfo=timezone.utc)
        self.assertIsNone(notify.stalled_run(run, early))
        stalled = notify.stalled_run(run, late)
        self.assertEqual(stalled["failure_code"], "PEDIDO_WORKFLOW_SIN_AVANCE")
        self.assertEqual(notify.emit(api, stalled, []), "RUTA_NOTIFIED")
        self.assertIn("PEDIDO_WORKFLOW_SIN_AVANCE", api.comments[0]["body"])

    def test_suspended_watchdog_does_not_mutate_issue(self):
        from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL
        paused = fake_api({"req-160": {"state": "SUSPENDING", "authorization_pr": 77}})
        class Suspended(Fake):
            def api(self, method, path, body=None):
                if method == "GET" and path != "/issues/160":
                    return paused(path[1:])
                return super().api(method, path, body)
        api = Suspended()
        self.assertEqual(notify.emit(api, self.run_obj(), []), "REQUEST_SUSPENDED")
        self.assertEqual(api.writes, [])

    def test_timeout_code(self):
        run = self.run_obj()
        self.assertEqual(notify.error_code(run, [{"conclusion": "timed_out"}]),
                         "PEDIDO_WORKFLOW_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
