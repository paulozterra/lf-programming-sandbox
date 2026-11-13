"""Offline tests for T0 intervention_report (synthetic git repos)."""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
CLAUDE = ("Claude", "noreply@anthropic.com")
PAULO = ("Pauloz", "66433825+paulozterra@users.noreply.github.com")


def load(root):
    spec = importlib.util.spec_from_file_location("ir_t", HERE / "intervention_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = root
    return mod


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        self.commit(PAULO, {"README.md": "base\n"})

    def commit(self, who, files):
        for path, text in files.items():
            p = self.root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        env = dict(os.environ, GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1],
                   GIT_COMMITTER_NAME=who[0], GIT_COMMITTER_EMAIL=who[1])
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "c"], check=True, env=env)


class InterventionReport(unittest.TestCase):
    def run_report(self, repo):
        mod = load(repo.root)
        return mod.report("demo", "HEAD", with_labels=False)

    def test_fully_automatic_request_reports_no(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\n"})
        r.commit(BOT, {"pilot/runs/demo/analysis.json": "{}", "pilot/runs/demo/lots.json":
                       json.dumps({"lots": [{"write_paths": ["apps/x/src/main/A.java"]}]}),
                       "pilot/runs/demo/templates/t1.task.json": "{}"})
        r.commit(CLAUDE, {"pilot/runs/demo/claude_meta/t1.json": "{}",
                          "pilot/holdouts/t1.oracle.json.age": "x"})
        r.commit(BOT, {"pilot/worker_v08/native_tasks/t1.json": "{}", "apps/x/src/main/A.java": "class A{}"})
        rep = self.run_report(r)
        self.assertEqual(rep["intervencion_manual"], "NO", rep["by_code"])

    def test_manual_division_contract_base_and_registration_reported(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\n",
                         "pilot/runs/demo/planning_fixture.json": "{}"})
        r.commit(CLAUDE, {"apps/x/API_SPEC.md": "x", "apps/x/pom.xml": "<p/>",
                          "pilot/runs/demo/templates/t1.task.json": "{}",
                          "pilot/runs/demo/claude_meta/t1.json": "{}"})
        r.commit(CLAUDE, {"pilot/worker_v08/native_tasks/t1.json": "{}",
                          "apps/x/src/test/T.java": "class T{}"})
        rep = self.run_report(r)
        self.assertEqual(rep["intervencion_manual"], "SI")
        for code in ("MANUAL_LOT_DIVISION", "MANUAL_CONTRACT", "MANUAL_BASE_PREP",
                     "MANUAL_TASK_TEMPLATE", "MANUAL_REGISTRATION", "MANUAL_TEST_EDIT"):
            self.assertIn(code, rep["by_code"])

    def test_handwritten_openapi_is_manual_contract(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\n"})
        r.commit(BOT, {"pilot/runs/demo/lots.json": json.dumps({
            "lots": [{"write_paths": ["contracts/sample.openapi.yaml"]}]})})
        r.commit(PAULO, {"contracts/sample.openapi.yaml": "openapi: 3.0.3\n"})
        self.assertIn("MANUAL_CONTRACT", self.run_report(r)["by_code"])

    def test_worker_openapi_is_not_manual_contract(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\n"})
        r.commit(BOT, {"pilot/runs/demo/lots.json": json.dumps({
            "lots": [{"write_paths": ["contracts/sample.openapi.yaml"]}]})})
        r.commit(BOT, {"contracts/sample.openapi.yaml": "openapi: 3.0.3\n"})
        self.assertEqual(self.run_report(r)["intervencion_manual"], "NO")

    def test_history_before_request_is_ignored(self):
        r = Repo()
        r.commit(PAULO, {"apps/x/src/main/A.java": "old"})
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\n"})
        r.commit(BOT, {"pilot/runs/demo/lots.json":
                       json.dumps({"lots": [{"write_paths": ["apps/x/src/main/A.java"]}]}),
                       "apps/x/src/main/A.java": "new"})
        self.assertEqual(self.run_report(r)["intervencion_manual"], "NO")

    def test_manual_code_on_write_path_is_intervention(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\n"})
        r.commit(BOT, {"pilot/runs/demo/lots.json":
                       json.dumps({"lots": [{"write_paths": ["apps/x/src/main/A.java"]}]})})
        r.commit(PAULO, {"apps/x/src/main/A.java": "hand written"})
        self.assertIn("MANUAL_CODE", self.run_report(r)["by_code"])


if __name__ == "__main__":
    unittest.main()
