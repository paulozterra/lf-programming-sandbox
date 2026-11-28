"""Offline tests for T0 intervention_report (synthetic git repos)."""
import importlib.util
import hashlib
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

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def sync(self):
        self.git("update-ref", "refs/remotes/origin/main", self.git("rev-parse", "HEAD"))

    def merge(self, number):
        branch = self.git("branch", "--show-current")
        self.git("checkout", "-q", "main")
        self.git("-c", "user.name=Train", "-c", "user.email=train@example.test",
                 "merge", "--no-ff", "-m", f"Merge PR #{number} via sandbox-train", branch)
        self.sync()

    def exercise(self):
        self.commit(BOT, {"pilot/orchestrator/control.py": "v1\n",
                          "pilot/orchestrator/request_lifecycle_control.json":json.dumps(
                              {"schema_version":"LF_REQUEST_LIFECYCLE_CONTROL_V1","requests":{}}),
                          "pilot/orchestrator/lot_recovery.json":json.dumps(
                              {"schema_version":"LF_LOT_RECOVERY_V1","recoveries":[]}),
                          "pilot/worker_v08/native_format_activation.json":json.dumps(
                              {"schema_version":"LF_NATIVE_FORMAT_ACTIVATION_V1","tasks":{}})})
        self.git("checkout", "-qb", "intake")
        self.commit(BOT, {"pilot/runs/req-101/request.md": "pedido\n",
                          "pilot/runs/req-101/request_meta.json": json.dumps(
                              {"issue":101,"author":"owner","date":"2026-01-01T00:00:00Z"})})
        self.merge(101)
        self.commit(BOT, {"pilot/runs/req-101/analysis.json": "{}",
                          "pilot/runs/req-101/lots.json": '{"lots":[{"id":"SOL-1"}]}'})
        self.git("checkout", "-qb", "register")
        self.commit(CLAUDE, {"pilot/runs/req-101/claude_meta/t1.json":"{}",
                             "pilot/holdouts/t1.oracle.json.age":"fixture-not-a-real-exam"})
        self.commit(BOT, {".lf/worker-context/t1/"+name: "fixture"
                          for name in ("profile.md","skills.md","receipt.json")})
        base = self.git("rev-parse", "HEAD")
        self.spec = {"task_id":"LF-WORKER-NATIVE-T1","base_head_sha":base,
                     "source_snapshot_sha256":"a"*64,"max_attempts":1,
                     "acceptance_commands":[],"write_path_patterns":["apps/x.txt"]}
        self.pack_path = "pilot/runs/req-101/proposal_requests/t1.task-pack.json"
        self.meta_path = "pilot/runs/req-101/proposal_requests/t1.proposal-request.json"
        self.reg_path = "pilot/worker_v08/native_tasks/t1.json"
        self.meta = {"schema_version":"CP34_NATIVE_PROPOSAL_REQUEST_V1",
                     "task_name":"t1","task_spec_path":self.reg_path,"task_pack_path":self.pack_path,
                     "task_pack_sha256":hashlib.sha256(b"{}").hexdigest(),"base_head_sha":base,
                     "lot_id":"SOL-1","production_authority":False,"model_invoked":False,"merge_authorized":False}
        self.commit(BOT, {self.pack_path:"{}",self.meta_path:json.dumps(self.meta),
                          self.reg_path:json.dumps({"task_spec":self.spec,"holdout_sha256":"b"*64})})
        self.merge(102)
        return self

    def conditions(self):
        self.sync()
        return load(self.root).exercise_conditions("req-101","HEAD")


class ExerciseConditions(unittest.TestCase):
    def test_functional_advancement_and_canonical_metadata_enrichment(self):
        from pilot.orchestrator.native_submission_contract import enrich_request
        r = Repo().exercise()
        original = r.conditions()
        self.assertEqual(original["status"],"GIT_CONDITIONS_BOUND_BASELINE_UNATTESTED",original)
        r.commit(BOT, {"apps/x.txt":"new","pilot/runs/req-102/state.json":"{}",
                       r.meta_path:json.dumps(enrich_request(r.meta,r.spec)),
                       "pilot/registry/implemented.json":"{}"})
        later = r.conditions()
        self.assertEqual(later["status"],original["status"],later)
        self.assertEqual(later["exercise_id"],original["exercise_id"])
        self.assertEqual(later["task_seals"],original["task_seals"])
        self.assertFalse(later["autonomy_certified"])

    def test_route_change_and_revert_invalidates(self):
        r = Repo().exercise()
        r.commit(PAULO, {"pilot/orchestrator/control.py":"v2\n"})
        r.commit(PAULO, {"pilot/orchestrator/control.py":"v1\n"})
        result = r.conditions()
        self.assertEqual(result["status"],"INVALIDATED_CONDITION_DRIFT",result)
        self.assertEqual(result["route_sha256"],result["observed_route_sha256"])
        self.assertEqual(len(result["drift"]),2)

    def test_pack_rehash_and_exam_change_detected(self):
        r = Repo().exercise()
        updated = dict(r.meta, task_pack_sha256=hashlib.sha256(b'{"x":1}').hexdigest())
        r.commit(BOT, {r.pack_path:'{"x":1}',r.meta_path:json.dumps(updated),
                       "pilot/holdouts/t1.oracle.json.age":"different-fixture"})
        result = r.conditions()
        self.assertEqual(result["status"],"INVALIDATED_CONDITION_DRIFT",result)
        self.assertEqual(result["task_seals"][0]["task_pack_sha256"],r.meta["task_pack_sha256"])
        self.assertTrue(any(r.pack_path in x["paths"] for x in result["drift"]))

    def test_scoped_policy_changes_only_affect_the_request(self):
        r = Repo().exercise()
        path = "pilot/worker_v08/native_format_activation.json"
        r.commit(BOT, {path:json.dumps({"schema_version":"LF_NATIVE_FORMAT_ACTIVATION_V1",
                                      "tasks":{"other":900}})})
        self.assertEqual(r.conditions()["status"],"GIT_CONDITIONS_BOUND_BASELINE_UNATTESTED")
        r.commit(PAULO, {path:json.dumps({"schema_version":"LF_NATIVE_FORMAT_ACTIVATION_V1",
                                         "tasks":{"other":900,"t1":901}})})
        self.assertEqual(r.conditions()["status"],"INVALIDATED_CONDITION_DRIFT")

    def test_verified_terminal_boundary_excludes_later_maintenance(self):
        from pilot.orchestrator.lifecycle_test_support import evidence_fixture
        from pilot.orchestrator.pg37_evidence import render
        r = Repo().exercise()
        sha = r.git("rev-parse","HEAD")
        record = evidence_fixture("req-101","SOL-1",sha)
        r.commit(BOT, {"pilot/runs/req-101/state.json":json.dumps({"stage":"LOTS_PLANNED","request_id":"req-101"}),
                       "pilot/registry/implemented.json":json.dumps({"entries":[{"request":"req-101","lot":"SOL-1","merge_sha":sha,"status":"ATTESTED"}]}),
                       f"pilot/runs/req-101/evidence/SOL-1-{sha[:12]}.json":json.dumps(record),
                       "pilot/runs/req-101/H_REPORT.md":render("req-101",[record])})
        closed = r.git("rev-parse","HEAD")
        r.commit(PAULO, {"pilot/orchestrator/control.py":"post-close maintenance"})
        result = r.conditions()
        self.assertEqual(result["exercise_end_sha"],closed,result)
        self.assertEqual(result["status"],"GIT_CONDITIONS_BOUND_BASELINE_UNATTESTED",result)

    def test_invalid_intake_is_unresolved(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/req-101/request.md":"manual"})
        result = r.conditions()
        self.assertEqual(result["status"],"UNRESOLVED")
        self.assertFalse(result["autonomy_certified"])



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

    def test_bot_registration_publishes_pack_without_manual_intervention(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\\n"})
        r.commit(BOT, {
            "pilot/runs/demo/proposal_requests/t1.task-pack.json": '{"version":1}',
            "pilot/runs/demo/proposal_requests/t1.proposal-request.json": '{"task_name":"t1"}',
            "pilot/worker_v08/native_tasks/t1.json": "{}",
        })
        rep = self.run_report(r)
        self.assertEqual(rep["intervencion_manual"], "NO", rep["by_code"])
        pack_rows = [row for row in rep["rows"] if
                     "/proposal_requests/" in row["path"]]
        self.assertEqual(len(pack_rows), 2)
        self.assertTrue(all(row["actor"] == "BOT" and
                            row["verdict"] == "AUTOMATIC" for row in pack_rows))

    def test_person_publishing_pack_remains_manual_registration(self):
        r = Repo()
        r.commit(PAULO, {"pilot/runs/demo/request.md": "pedido\\n"})
        r.commit(PAULO, {
            "pilot/runs/demo/proposal_requests/t1.task-pack.json": "{}",
            "pilot/runs/demo/proposal_requests/t1.proposal-request.json": "{}",
        })
        rep = self.run_report(r)
        self.assertIn("MANUAL_REGISTRATION", rep["by_code"])
        self.assertEqual(rep["intervencion_manual"], "SI")

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
