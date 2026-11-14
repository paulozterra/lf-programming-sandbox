"""T9.1 offline notification, association, duplicate suppression, and doubled intake."""
import importlib.util
from pathlib import Path
import unittest

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

    def test_conflicting_issue_numbers_fail_closed(self):
        run = self.run_obj(title="T9 intake req-160")
        run["head_branch"] = "lf/request/req-161"
        self.assertIsNone(notify.resolve_issue(run))

    def test_timeout_code(self):
        run = self.run_obj()
        self.assertEqual(notify.error_code(run, [{"conclusion": "timed_out"}]),
                         "PEDIDO_WORKFLOW_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
