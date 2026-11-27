"""T9.3 offline checks: missing selector opt-in and exact T7 failure payload."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


policy = load("test_selector_environment")
notify = load("request_failure_notify")
REAL_T7_RUN = {
    "id": 43623385305,
    "name": "T7 req-167",
    "display_title": "T7 req-167",
    "path": ".github/workflows/t7-request.yml@refs/heads/main",
    "event": "workflow_dispatch",
    "head_branch": "main",
    "conclusion": "failure",
    "repository": {"full_name": notify.REPO},
    "head_repository": {"full_name": notify.REPO},
    "html_url": "https://github.com/" + notify.REPO + "/actions/runs/43623385305",
}


class SimulatedGithub:
    def __init__(self):
        self.writes = []
        self.comments = []
        self.labels = [{"name": "lf-request"}]

    def api(self, method, path, body=None):

        from pilot.orchestrator.lifecycle_test_support import content, CONTROL

        if method == "GET" and path == f"/contents/{CONTROL}?ref=main":

            return content({})
        if method == "GET" and path.startswith("/pulls?state=all&head="):
            return [{"user": {"login": "github-actions[bot]"},
                     "head": {"ref": "lf/request/req-167"}}]
        if method == "GET" and path == "/issues/167":
            return {"number": 167, "state": "open", "labels": self.labels}
        if method == "POST":
            self.writes.append((path, body))
            if path == "/issues/167/labels":
                self.labels.append({"name": "lf-request-blocked"})
            if path == "/issues/167/comments":
                self.comments.append({"user": {"login": "github-actions[bot]"},
                                      "body": body["body"]})
            return {}
        raise AssertionError((method, path))

    def pages(self, path):
        if not path.startswith("/issues/167/comments"):
            raise AssertionError(path)
        return self.comments


class Tests(unittest.TestCase):
    def test_actual_t7_failure_payload_notifies_exact_issue_once(self):
        self.assertEqual(notify.resolve_issue(REAL_T7_RUN), 167)
        self.assertEqual(notify.error_code(REAL_T7_RUN, []), "PEDIDO_T7_FALLIDO")
        api = SimulatedGithub()
        self.assertEqual(notify.emit(api, REAL_T7_RUN, []), "RUTA_NOTIFIED")
        self.assertEqual(notify.emit(api, REAL_T7_RUN, []), "RUTA_ALREADY_NOTIFIED")
        self.assertEqual([p for p, _ in api.writes],
                         ["/issues/167/labels", "/issues/167/comments"])
        self.assertEqual({x["name"] for x in api.labels},
                         {"lf-request", "lf-request-blocked"})
        body = api.comments[0]["body"]
        self.assertIn("PEDIDO_T7_FALLIDO", body)
        self.assertIn("43623385305", body)

    def test_untrusted_t7_title_is_not_a_source(self):
        for changes in ({"path": ".github/workflows/evil.yml"},
                        {"event": "push"},
                        {"display_title": "T7 req-167 other"},
                        {"display_title": "T7 req-168"}):
            run = dict(REAL_T7_RUN, **changes)
            self.assertIsNone(notify.resolve_issue(run))

    def test_other_workflow_spoofed_run_name_cannot_notify(self):
        run = dict(REAL_T7_RUN, path=".github/workflows/ci.yml")
        self.assertIsNone(notify.notification(run, []))

    def test_duplicate_selector_bootstrap_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            wf = Path(td) / "bad.yml"
            wf.write_text("""name: broken
on: workflow_dispatch
jobs:
  selector:
    runs-on: ubuntu-latest
    steps:
      - run: python3 pilot/orchestrator/selector_db.py --t1-patterns
""")
            self.assertEqual(policy.check_workflow(wf),
                             ["WORKFLOW_ENTORNO_SELECTOR_DUPLICADO:bad.yml"])
            wf.write_text("""name: good
on: workflow_dispatch
jobs:
  selector:
    runs-on: ubuntu-latest
    steps:
      - run: bash pilot/orchestrator/prepare_selector.sh
""")
            self.assertEqual(policy.check_workflow(wf), [])

    def test_all_repository_workflows_use_shared_bootstrap(self):
        self.assertEqual(policy.scan(HERE.parent), [])
        ci = (HERE.parent / ".github/workflows/ci.yml").read_text()
        t7 = (HERE.parent / ".github/workflows/t7-request.yml").read_text()
        self.assertIn("bash pilot/orchestrator/prepare_selector.sh", ci)
        self.assertIn("bash pilot/orchestrator/prepare_selector.sh", t7)
        setup = (HERE / "orchestrator/prepare_selector.sh").read_text()
        self.assertIn("ATOMIZE_T1_SELECTOR=YES", setup)
        self.assertIn("python3 -m pilot.orchestrator.selector_db --t1-patterns", setup)


if __name__ == "__main__":
    unittest.main()
