"""Offline policy C regression tests. No network or token."""
import base64
import copy
import json
import unittest
from unittest.mock import patch

import auto_integrate as ai

HEAD = "a" * 40
RUN = 43317808597

def pr(kind="integration"):
    return {
        "number": 129, "state": "open", "draft": True, "changed_files": 2,
        "base": {"ref": "main", "repo": {"full_name": ai.REPOSITORY}},
        "head": {"ref": "lf/native-" + kind + "/sandbox", "sha": HEAD,
                 "repo": {"full_name": ai.REPOSITORY}},
        "user": {"login": ai.BOT}, "labels": [],
        "body": "Task: f5backend · run: " + str(RUN),
    }

def paths():
    return ["apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java",
            "standards/changes/CHG-0085.json"]

def checks():
    return [{"id": i+100, "name": name, "head_sha": HEAD, "status": "completed",
             "conclusion": "success", "app": {"slug": "github-actions"}}
            for i, name in enumerate(ai.REQUIRED)]

def proof(attempt):
    return {"task_id": "f5backend", "attempt": attempt, "run_id": RUN,
            "task_pack_sha256": "1" * 64}

def status(attempt):
    return {"schema_version": "LF_NATIVE_RESULT_SUMMARY_V1",
            "task_id": "f5backend", "attempt": attempt,
            "task_pack_sha256": "1" * 64, "status": "PASS",
            "production_authority": False, "receipt_authenticated": False,
            "authority": "REAL_SANDBOX_UNAUTHENTICATED"}

def native_run():
    return {"id": RUN, "conclusion": "success", "status": "completed",
            "repository": {"full_name": ai.REPOSITORY}, "head_branch": "main",
            "path": ai.NATIVE_WORKFLOW, "event": "workflow_run", "run_attempt": 1}

def chg():
    return {"schema_version": "LF_STANDARD_CHANGE_V1", "change_id": "CHG-0085",
            "title": "CP3.5: integración verificada nativa f5backend (run " + str(RUN) + ")",
            "reason": "Parche nativo PASS " + str(RUN)}

class FakeAPI:
    def __init__(self, item, files, runs):
        self.item, self.files, self.runs = item, files, runs
        self.writes = []
    def pages(self, path, field):
        if path.startswith("/pulls/") and path.endswith("/files"):
            return [{"filename": p} for p in self.files]
        if path.endswith("/check-runs"):
            return self.runs
        if path.endswith("/comments"):
            return []
        raise AssertionError("unexpected pages " + path)
    def request(self, method, path, data=None):
        if method == "GET" and path.startswith("/pulls/"):
            return copy.deepcopy(self.item)
        if method == "GET" and path.startswith("/contents/"):
            b = json.dumps(chg()).encode("utf-8")
            return {"type": "file", "size": len(b), "encoding": "base64",
                    "content": base64.b64encode(b).decode("ascii")}
        if method == "GET" and path.startswith("/actions/runs/"):
            return native_run()
        if method == "POST":
            self.writes.append((path, data))
            return {}
        raise AssertionError("unexpected request " + method + path)

class PolicyTests(unittest.TestCase):
    def blocked(self, reason, fn):
        with self.assertRaisesRegex(ai.PolicyBlocked, reason):
            fn()

    def test_foreign_branch(self):
        item = pr()
        item["head"]["ref"] = "feature/manual"
        self.blocked("PR_BRANCH_NOT_ALLOWED", lambda: ai.eligible_pr(item, paths()))

    def test_forbidden_paths(self):
        for path in (".github/workflows/ci.yml", "pilot/sandbox_train.py",
                     "pilot/holdouts/f5.age", "standards/tools/changes.py",
                     "vendor/pkg", "pilot/orchestrator/plan_lots.py",
                     "pilot/auto_integrate.py"):
            with self.subTest(path=path):
                self.blocked("PR_PATH_PROHIBITED",
                             lambda: ai.eligible_pr(pr(), [path, paths()[1]]))

    def test_author_not_bot(self):
        item = pr()
        item["user"]["login"] = "paulozterra"
        self.blocked("PR_UNTRUSTED", lambda: ai.eligible_pr(item, paths()))

    def test_red_and_stale_checks(self):
        bad = checks()
        bad[0]["conclusion"] = "failure"
        self.blocked("CHECKS_NOT_GREEN", lambda: ai.validate_checks(bad, HEAD))
        stale = checks()
        stale[0]["head_sha"] = "b" * 40
        self.blocked("CHECKS_MISSING", lambda: ai.validate_checks(stale, HEAD))
        newer = checks() + [{**checks()[0], "id": 400, "conclusion": "failure"}]
        self.blocked("CHECKS_NOT_GREEN", lambda: ai.validate_checks(newer, HEAD))

    def test_attempt_three_comment_and_no_label(self):
        api = FakeAPI(pr(), paths(), checks())
        with patch.object(ai, "artifact_json", side_effect=[proof(3), status(3)]):
            self.blocked("ATTEMPT_3_REQUIRES_HUMAN", lambda: ai.evaluate_one(api, 129))
        self.assertEqual(api.writes,
                         [("/issues/129/comments", {"body": ai.HUMAN_COMMENT})])

    def test_valid_registration_label_and_train_dispatch(self):
        api = FakeAPI(pr("registration"), paths(), checks())
        self.assertEqual(ai.evaluate_one(api, 129), "LABEL_AND_TRAIN_DISPATCHED")
        self.assertEqual(api.writes, [
            ("/issues/129/labels", {"labels": ["ready-to-merge"]}),
            ("/actions/workflows/sandbox-train.yml/dispatches",
             {"ref": "main", "inputs": {"pr_number": "129"}})])

    def test_valid_integration_attempts_one_and_two(self):
        for attempt in (1, 2):
            api = FakeAPI(pr(), paths(), checks())
            with patch.object(ai, "artifact_json",
                              side_effect=[proof(attempt), status(attempt)]):
                self.assertEqual(ai.evaluate_one(api, 129),
                                 "LABEL_AND_TRAIN_DISPATCHED")
            self.assertEqual(len(api.writes), 2)

    def test_chg_run_mismatch(self):
        bad = chg()
        bad["title"] = "no run"
        self.blocked("INTEGRATION_CHG_RUN_MISMATCH",
                     lambda: ai.native_run_reference(pr()["body"], bad))

    def test_trigger_ci_cp35_and_fork(self):
        trigger = {"status": "completed", "conclusion": "success",
                   "repository": {"full_name": ai.REPOSITORY},
                   "head_repository": {"full_name": ai.REPOSITORY},
                   "head_branch": "lf/native-integration/f5", "event": "pull_request",
                   "run_attempt": 1, "path": ".github/workflows/ci.yml",
                   "name": "ci"}
        self.assertEqual(ai.verify_trigger(trigger), trigger["path"])
        trigger["path"] = ".github/workflows/native-verified-integration.yml"
        trigger["name"] = "CP3.5 native verified patch to draft PR"
        trigger["head_branch"] = "main"
        trigger["event"] = "workflow_run"
        self.assertEqual(ai.verify_trigger(trigger), trigger["path"])
        trigger["head_repository"]["full_name"] = "someone/fork"
        self.blocked("TRIGGER_NOT_TRUSTED", lambda: ai.verify_trigger(trigger))

if __name__ == "__main__":
    unittest.main()
