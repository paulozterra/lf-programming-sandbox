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


class API:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/git/ref/heads/main":
            return {"object": {"sha": SHA}}
        if method == "GET" and path.startswith("/actions/workflows/ci.yml/runs?"):
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
    def test_main_ci_green_required_before_next_stage(self):
        api = API([None, ci_run(status="in_progress", conclusion=None), ci_run()])
        cfg = handoff.main_ci_gate_config()
        with patch.object(handoff, "git", return_value=SHA), \
             patch.object(handoff, "validate_train_run"):
            outcome = handoff.ensure_main_ci(api, SHA, required=True,
                                             config=cfg, sleep=lambda _:None)
        self.assertEqual(outcome["status"], "MAIN_CI_GREEN")
        self.assertEqual(api.calls[2], ("POST", "/actions/workflows/ci.yml/dispatches",
                                        {"ref":"main"}))
        self.assertEqual(outcome["run_id"], 189)

    def test_failed_ci_blocks_with_real_url(self):
        api = API([None, ci_run(conclusion="failure")])
        with self.assertRaisesRegex(handoff.HandoffBlocked, "BASE_NO_VERDE:.*actions/runs/189"):
            handoff.ensure_main_ci(api,SHA,required=True,sleep=lambda _:None)

    def test_wrong_sha_never_unblocks(self):
        api = API([None, ci_run(sha="d"*40)])
        cfg={**handoff.main_ci_gate_config(),"wait_seconds":60,"poll_seconds":60}
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
             patch.object(handoff, "merged_request_slug", return_value="req-175"):
            result=handoff.dispatch(api,177,SHA,42,MAPPING)
        paths=[p for method,p,_ in api.calls if method=="POST"]
        self.assertEqual(paths,["/actions/workflows/ci.yml/dispatches",
                                "/actions/workflows/chain-lots.yml/dispatches"])
        self.assertEqual(result["inputs"]["request_slug"],"req-175")
        self.assertEqual(result["inputs"]["base_sha"],SHA)

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


if __name__=="__main__":
    unittest.main()
