"""T9.5 exact SHA CI handoff, fail-closed ordering and real PR177 failure."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SHA = "851ef1aa7bc438419d49117c74f50e5c664a2506"
REPO = "paulozterra/lf-programming-sandbox"


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


handoff = module("train_handoff")
notify = module("request_failure_notify")
static = module("test_workflow_base_ci")
MAPPING = json.loads((HERE / "train_handoff_map_v1.json").read_text())


def ci_run(conclusion="success", status="completed", sha=SHA, run_id=189):
    return {"id": run_id, "head_sha": sha, "head_branch": "main",
            "event": "workflow_dispatch", "run_attempt": 1,
            "path": ".github/workflows/ci.yml",
            "repository": {"full_name": REPO}, "status": status,
            "conclusion": conclusion, "created_at": "2026-11-14T20:00:00Z",
            "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}"}


GATE = handoff.main_ci_gate_config()
# These T9.5 cases exercise the dispatch fallback (no push CI for the SHA):
# one push probe, no push wait. T52 covers the push-first path.
FALLBACK_GATE = {**GATE, "push_wait_seconds": 0}


def green_jobs():
    jobs = [{"name": name, "status": "completed", "conclusion": "success"}
            for name in GATE["required_jobs"]]
    return {"total_count": len(jobs), "jobs": jobs}


class API:
    def __init__(self, rows=None, push_probe=True):
        self.rows = list(rows or [])
        self.calls = []
        self.push_probe = push_probe

    def call(self, method, path, body=None):
        from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL
        if method == "GET" and (path == f"/contents/{CONTROL}?ref=main" or
                                (path.startswith("/issues/") and path[8:].isdigit())):
            return fake_api({})(path[1:])
        self.calls.append((method, path, body))
        if method == "GET" and path == "/git/ref/heads/main":
            return {"object": {"sha": SHA}}
        if method == "GET" and "/jobs?filter=latest" in path:
            return green_jobs()
        if method == "GET" and path.startswith("/actions/workflows/ci.yml/runs?"):
            if self.push_probe:
                # T52 push probe: no push CI exists for this SHA.
                self.push_probe = False
                return {"workflow_runs": [], "total_count": 0}
            state = self.rows.pop(0) if len(self.rows) > 1 else (self.rows[0] if self.rows else None)
            rows = [state] if state is not None else []
            return {"workflow_runs": rows, "total_count": len(rows)}
        if method == "POST":
            return {}
        if method == "GET" and path == "/pulls/177":
            return {"number": 177, "merged": True, "merge_commit_sha": SHA,
                    "user": {"login": "github-actions[bot]"},
                    "head": {"ref": "lf/generated-t7/dacf5a8db725",
                             "sha": "b" * 40, "repo": {"full_name": REPO}},
                    "base": {"ref": "main", "repo": {"full_name": REPO}}}
        if method == "GET" and path == "/commits/" + SHA:
            return {"sha": SHA, "parents": [{"sha": "c"*40},{"sha":"b"*40}],
                    "commit":{"message":"Merge PR #177 via sandbox-train"}}
        raise AssertionError((method,path,body))


REAL_CP36 = {"id": 43636772339, "name": "CP3.6 PR 177",
             "display_title": "CP3.6 PR 177",
             "path": ".github/workflows/chain-lots.yml",
             "event": "workflow_dispatch",
             "head_branch": "main", "head_sha": SHA,
             "status": "completed", "conclusion": "failure",
             "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
             "html_url": f"https://github.com/{REPO}/actions/runs/43636772339"}


class NotificationAPI:
    def __init__(self):
        self.write = []
        self.comments = []
        self.labels = [{"name": "lf-request"}]

    def api(self, method, path, body=None):
        if method == "GET" and path == "/pulls/177":
            return {"number":177, "merged":True, "merge_commit_sha":SHA,
                    "base":{"ref":"main","repo":{"full_name":REPO}},
                    "head":{"ref":"lf/generated-t7/dacf5a8db725",
                            "repo":{"full_name":REPO}},
                    "user":{"login":"github-actions[bot]"}}
        if method == "GET" and path == "/pulls/177/files?per_page=100":
            return [{"filename":f"pilot/runs/req-175/{p}.json"}
                    for p in ("analysis","state","lots","chain_plan")]
        if method == "GET" and path.startswith("/pulls?state=all&head="):
            return [{"user":{"login":"github-actions[bot]"},
                     "head":{"ref":"lf/request/req-175"}}]
        if method == "GET" and path == "/issues/175":
            return {"number":175,"state":"open","labels":self.labels}
        if method == "GET" and path == (f"/actions/workflows/ci.yml/runs?head_sha={SHA}&per_page=100"):
            return {"total_count":0,"workflow_runs":[]}
        if method == "GET" and path == "/actions/runs/43636772339/jobs?per_page=100":
            return {"jobs":[{"name":"chain","conclusion":"failure"}]}
        if method == "POST":
            self.write.append((path,body))
            if path == "/issues/175/labels":
                self.labels.append({"name":"lf-request-blocked"})
            if path == "/issues/175/comments":
                self.comments.append({"user":{"login":"github-actions[bot]"},
                                      "body":body["body"]})
            return {}
        raise AssertionError((method,path,body))

    def pages(self,path):
        self.assert_path = path
        return self.comments


class Tests(unittest.TestCase):
    def setUp(self):
        gate = patch.object(handoff, "main_ci_gate_config", return_value=FALLBACK_GATE)
        gate.start()
        self.addCleanup(gate.stop)

    def test_main_ci_green_required_before_next_stage(self):
        api = API([None, ci_run(status="in_progress", conclusion=None), ci_run()])
        cfg = FALLBACK_GATE
        with patch.object(handoff, "git", return_value=SHA), \
             patch.object(handoff, "validate_train_run"):
            outcome = handoff.ensure_main_ci(api, SHA, required=True,
                                             config=cfg, sleep=lambda _:None)
        self.assertEqual(outcome["status"], "MAIN_CI_GREEN")
        self.assertEqual(api.calls[3], ("POST", "/actions/workflows/ci.yml/dispatches",
                                        {"ref":"main"}))
        self.assertEqual(outcome["run_id"], 189)

    def test_failed_ci_blocks_with_real_url(self):
        api = API([None, ci_run(conclusion="failure")])
        with self.assertRaisesRegex(handoff.HandoffBlocked, "BASE_NO_VERDE:.*actions/runs/189"):
            handoff.ensure_main_ci(api,SHA,required=True,sleep=lambda _:None)

    def test_wrong_sha_never_unblocks(self):
        api = API([None, ci_run(sha="d"*40)])
        cfg={**FALLBACK_GATE,"wait_seconds":60,"poll_seconds":60}
        with self.assertRaisesRegex(handoff.HandoffBlocked, "BASE_NO_VERDE"):
            handoff.ensure_main_ci(api,SHA,required=True,config=cfg,sleep=lambda _:None)

    def test_old_green_ci_cannot_release_newly_dispatched_pending_ci(self):
        old = ci_run(run_id=188)
        pending = ci_run(status="in_progress", conclusion=None, run_id=189)
        new = ci_run(run_id=189)
        api = API([old, pending, new])
        result = handoff.ensure_main_ci(
            api, SHA, required=True, sleep=lambda _: None)
        self.assertEqual(result["run_id"], 189)
        self.assertEqual(result["status"], "MAIN_CI_GREEN")

    def test_old_failed_ci_does_not_block_new_green_attempt(self):
        old = ci_run(conclusion="failure", run_id=188)
        new = ci_run(run_id=189)
        api = API([old, new])
        self.assertEqual(handoff.ensure_main_ci(
            api, SHA, required=True, sleep=lambda _: None)["run_id"], 189)

    def test_non_gated_request_still_dispatches_ci(self):
        api=API()
        self.assertEqual(handoff.ensure_main_ci(api,SHA,required=False)["status"],
                         "MAIN_CI_DISPATCHED")
        self.assertTrue(any(path.endswith("/ci.yml/dispatches")
                            for method,path,_ in api.calls if method=="POST"))

    def test_train_route_releases_cp36_only_after_green(self):
        api=API([None, ci_run()])
        with patch.object(handoff, "git", return_value=SHA), \
             patch.object(handoff, "validate_train_run"), \
             patch.object(handoff, "merged_request_slug", return_value="req-175"), \
             patch.object(handoff, "comment_analysis_report"):
            result=handoff.dispatch(api,177,SHA,42,MAPPING)
        paths=[p for method,p,_ in api.calls if method=="POST"]
        self.assertEqual(paths,["/actions/workflows/ci.yml/dispatches",
                                "/actions/workflows/chain-lots.yml/dispatches",
                                "/actions/workflows/chain-lots.yml/dispatches"])
        self.assertEqual(api.calls[-1][2]["inputs"], {"sweep": "true", "base_sha": SHA})
        self.assertEqual(result["inputs"]["request_slug"],"req-175")
        self.assertEqual(result["inputs"]["base_sha"],SHA)

    def test_failed_exact_ci_never_dispatches_cp36(self):
        api = API([None, ci_run(conclusion="failure")])
        with patch.object(handoff, "git", return_value=SHA), \
             patch.object(handoff, "validate_train_run"), \
             patch.object(handoff, "merged_request_slug", return_value="req-175"), \
             patch.object(handoff, "comment_analysis_report"):
            with self.assertRaisesRegex(handoff.HandoffBlocked,
                                        "BASE_NO_VERDE:.*actions/runs/189"):
                handoff.dispatch(api, 177, SHA, 42, MAPPING)
        dispatched = [path for method, path, _ in api.calls if method == "POST"]
        # T27.1: exactly one re-run of the failed jobs, then terminal; never CP3.6.
        self.assertEqual(dispatched, ["/actions/workflows/ci.yml/dispatches",
                                      "/actions/runs/189/rerun-failed-jobs"])

    def test_transient_main_ci_failure_rerun_turns_green_and_releases_cp36(self):
        failed = ci_run(conclusion="failure")
        rerun_green = dict(ci_run(), run_attempt=2)
        api = API([None, failed, rerun_green])
        with patch.object(handoff, "git", return_value=SHA), \
             patch.object(handoff, "validate_train_run"), \
             patch.object(handoff, "merged_request_slug", return_value="req-175"), \
             patch.object(handoff, "comment_analysis_report"), \
             patch.object(handoff.time, "sleep"):
            handoff.dispatch(api, 177, SHA, 42, MAPPING)
        posts = [path for method, path, _ in api.calls if method == "POST"]
        self.assertEqual(posts[:2], ["/actions/workflows/ci.yml/dispatches",
                                     "/actions/runs/189/rerun-failed-jobs"])
        self.assertIn("/actions/workflows/chain-lots.yml/dispatches", posts)

    def test_main_moved_blocks_before_ci_dispatch(self):
        class Moved(API):
            def call(self, method, path, body=None):
                if path == "/git/ref/heads/main":
                    return {"object": {"sha": "e" * 40}}
                return super().call(method, path, body)
        api = Moved()
        with self.assertRaisesRegex(handoff.HandoffBlocked,
                                    "BASE_NO_VERDE:MAIN_MOVED"):
            handoff.ensure_main_ci(api, SHA, required=True)
        self.assertFalse(any(method == "POST" for method, _, _ in api.calls))

    def test_worker_and_integration_titles_use_registered_task_scope(self):
        worker = {"path": ".github/workflows/worker-native.yml",
                  "display_title": "lf-native-req175backend2-a1"}
        integration = {"path": ".github/workflows/native-verified-integration.yml",
                       "display_title": "CP3.5 lf-native-req175backend2-a1"}
        with patch.object(notify, "request_for_task", return_value={"req-175"}):
            self.assertEqual(notify.task_stage_issue(worker), 175)
            self.assertEqual(notify.task_stage_issue(integration), 175)
        with patch.object(notify, "request_for_task", return_value={"req-175", "req-176"}):
            self.assertIsNone(notify.task_stage_issue(worker))

    def test_pg37_resolves_from_verified_bot_pr_and_files(self):
        class Source:
            def api(self, method, path, body=None):
                self_url = "lf/generated-t7/dacf5a8db725"
                if path.startswith("/pulls?state=all&head="):
                    return [{"number": 177, "head": {"ref": self_url},
                             "user": {"login": "github-actions[bot]"}}]
                if path == "/pulls/177":
                    return {"number":177, "merged": True,
                            "head":{"ref":self_url,"repo":{"full_name":REPO}},
                            "base":{"ref":"main","repo":{"full_name":REPO}},
                            "user":{"login":"github-actions[bot]"}}
                if path == "/pulls/177/files?per_page=100":
                    return [{"filename":"pilot/runs/req-175/analysis.json"},
                            {"filename":"pilot/runs/req-175/state.json"}]
                raise AssertionError((method,path))
        run = {"path": ".github/workflows/pg37-evidence.yml",
               "display_title": "CP3.7 lf/generated-t7/dacf5a8db725"}
        self.assertEqual(notify.verified_pg37_issue(Source(), run), 175)

    def test_real_cp36_pr177_notifies_issue175_and_is_idempotent(self):
        api=NotificationAPI()
        self.assertEqual(notify.check_run(api,dict(REAL_CP36)),"RUTA_NOTIFIED")
        self.assertEqual(notify.check_run(api,dict(REAL_CP36)),"RUTA_ALREADY_NOTIFIED")
        self.assertEqual([p for p,_ in api.write],
                         ["/issues/175/labels","/issues/175/comments"])
        body=api.comments[0]["body"]
        self.assertIn("BASE_NO_VERDE",body)
        self.assertIn("43636772339",body)
        self.assertIn("lf-request-blocked",{x["name"] for x in api.labels})

    def test_request_correlation_fails_closed_on_foreign_pr(self):
        api=NotificationAPI()
        original=api.api
        def spoof(method,path,body=None):
            item=original(method,path,body)
            if path == "/pulls/177":
                item["user"]["login"]="attacker"
            return item
        api.api=spoof
        self.assertEqual(notify.check_run(api,dict(REAL_CP36)),
                         "RUTA_NO_ISSUE_ASSOCIATION")
        self.assertFalse(api.write)

    def test_static_guard_catches_map_drift(self):
        self.assertEqual(static.check(),[])
        with tempfile.TemporaryDirectory() as tmp:
            # Test the static policy by temporarily replacing only its source
            # readback; production files stay unchanged.
            import shutil
            root=Path(tmp)
            for item in ("pilot/train_handoff.py","pilot/train_handoff_map_v1.json",
                         "pilot/train_main_ci_gate_v1.json",
                         "pilot/orchestrator/chain_lots.py",
                         ".github/workflows/train-handoff.yml",
                         ".github/workflows/ci.yml",
                         ".github/workflows/chain-lots.yml"):
                dst=root/item
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(HERE.parent/item,dst)
            mapping=root/"pilot/train_handoff_map_v1.json"
            doc=json.loads(mapping.read_text())
            doc["routes"][1]["requires_green_base"]=False
            mapping.write_text(json.dumps(doc))
            self.assertIn("WORKFLOW_BASE_SIN_CI:chain-lots.yml",
                          static.check(root))
            mapping.write_text(json.dumps(json.loads(
                (HERE / "train_handoff_map_v1.json").read_text())))
            ci_file = root / ".github/workflows/ci.yml"
            text = ci_file.read_text()
            self.assertIn("github.sha", text)
            ci_file.write_text(text.replace("github.sha", "github.ref"))
            self.assertIn("WORKFLOW_BASE_SIN_CI:TRAIN_HANDOFF",
                          static.check(root))



class SupersededSweepTests(unittest.TestCase):
    """Exercise the actual workflow shell gate with a two-merge git history."""

    def test_sweep_gate(self):
        import os
        import subprocess
        import yaml

        doc = yaml.safe_load((HERE.parent / ".github/workflows/chain-lots.yml").read_text())
        steps = doc["jobs"]["chain"]["steps"]
        gate = next(step for step in steps if step.get("id") == "chain_base")
        reconcile = next(step for step in steps if step["name"].startswith("Reconcile trusted"))
        retry = next(step for step in steps if step["name"].startswith("T27 retry"))
        self.assertEqual(reconcile["env"]["SWEEP_BASE"], "${{ steps.chain_base.outputs.sha }}")
        self.assertIn('--sweep --base-sha "$SWEEP_BASE"', reconcile["run"])
        self.assertEqual(retry["env"]["BASE_SHA"], "${{ steps.chain_base.outputs.sha }}")
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=tmp, text=True,
                                               stderr=subprocess.DEVNULL).strip()
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            git("commit", "--allow-empty", "-qm", "base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "other")
            git("commit", "--allow-empty", "-qm", "unrelated")
            other = git("rev-parse", "HEAD")
            git("checkout", "-q", "--detach", base)
            git("commit", "--allow-empty", "-qm", "first Train merge")
            first = git("rev-parse", "HEAD")
            git("commit", "--allow-empty", "-qm", "second Train merge")
            head = git("rev-parse", "HEAD")
            output = Path(tmp) / "output"
            for expected, sweep, ok in (
                (head, True, True), (first, True, True),
                (first, False, False), (other, True, False),
                ("invalid", True, False), ("0" * 40, True, False),
                (head, False, True),
            ):
                with self.subTest(expected=expected, sweep=sweep):
                    output.write_text("")
                    env = dict(os.environ, EXPECTED_BASE=expected,
                               REQUEST_SLUG="req-1", GITHUB_OUTPUT=str(output))
                    result = subprocess.run(
                        ["bash", "-e", "-c", gate["run"].replace(
                            "${{ inputs.sweep }}", str(sweep).lower())],
                        cwd=tmp, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, ok, result.stderr)
                    self.assertEqual(output.read_text(), f"sha={head}\n" if ok else "")
                    if ok and expected != head:
                        self.assertIn("CP36_SWEEP_BASE_SUPERSEDED", result.stdout)


if __name__=="__main__":
    unittest.main()
