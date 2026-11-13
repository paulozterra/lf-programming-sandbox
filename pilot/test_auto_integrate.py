"""Offline policy C regression tests. No network or token."""
import base64
import sys
from pathlib import Path
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

    def test_redirect_strips_token_and_disallows_http(self):
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/repos/example/repo/actions/artifacts/123/zip",
            headers={"Authorization": "Bearer secret"})
        handler = ai.SafeRedirect()
        redirected = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://pipelines.actions.githubusercontent.com/download")
        self.assertIsNone(redirected.get_header("Authorization"))
        self.blocked("UNSAFE_API_REDIRECT",
                     lambda: handler.redirect_request(
                         req, None, 302, "Found", {}, "http://example.org/downgrade"))

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

class T7GeneratedPolicyTests(unittest.TestCase):
    """Policy C uses the same authorize/check/label/Train flow as native PRs."""

    def generated_checks(self):
        return checks() + [{"id": 500, "name": "T7 generated content byte equality",
                            "head_sha": HEAD, "status": "completed",
                            "conclusion": "success", "app": {"slug": "github-actions"}}]

    def generated(self, family, paths):
        obj = pr("registration")
        obj["head"]["ref"] = family + "/" + HEAD[:12]
        obj["changed_files"] = len(paths)
        return obj

    def test_generated_prs_label_and_dispatch_without_manual_label(self):
        cases = [
            ("lf/generated-t7", ["pilot/runs/sample/analysis.json",
                                  "pilot/runs/sample/state.json",
                                  "pilot/runs/sample/chain_plan.json",
                                  "pilot/runs/sample/templates/module.skeleton.json"]),
            ("lf/implemented-registry", ["pilot/registry/implemented.json"]),
        ]
        for family, allowed in cases:
            with self.subTest(family=family):
                item = self.generated(family, allowed)
                api = FakeAPI(item, allowed, self.generated_checks())
                with patch.object(ai, "verify_generated_content") as validate:
                    self.assertEqual(ai.evaluate_one(api, 129),
                                     "LABEL_AND_TRAIN_DISPATCHED")
                    validate.assert_called_once()
                self.assertEqual(api.writes[0][0], "/issues/129/labels")
                self.assertEqual(api.writes[1][0],
                                 "/actions/workflows/sandbox-train.yml/dispatches")

    def test_generated_requires_additional_exact_head_ci_check(self):
        allowed = ["pilot/registry/implemented.json"]
        item = self.generated("lf/implemented-registry", allowed)
        api = FakeAPI(item, allowed, checks())
        with patch.object(ai, "verify_generated_content"):
            with self.assertRaisesRegex(ai.PolicyBlocked, "CHECKS_MISSING"):
                ai.evaluate_one(api, 129)
        self.assertEqual(api.writes, [])

    def test_extra_paths_and_human_author_block_before_label(self):
        for family, allowed in (
            ("lf/generated-t7", ["pilot/runs/sample/analysis.json"]),
            ("lf/implemented-registry", ["pilot/registry/implemented.json"]),
        ):
            with self.subTest(family=family):
                extra = allowed + ["pilot/orchestrator/chain_plans/sample.json"]
                item = self.generated(family, extra)
                with self.assertRaisesRegex(ai.PolicyBlocked, "PR_PATH_NOT_ALLOWED"):
                    ai.eligible_pr(item, extra)
                item = self.generated(family, allowed)
                item["user"]["login"] = "human"
                with self.assertRaisesRegex(ai.PolicyBlocked, "PR_AUTHOR_NOT_BOT"):
                    ai.eligible_pr(item, allowed)

    def test_renamed_source_path_is_not_accepted_as_generated(self):
        allowed = ["pilot/registry/implemented.json"]
        item = self.generated("lf/implemented-registry", allowed)
        api = FakeAPI(item, allowed, self.generated_checks())
        real_pages = api.pages
        def renamed(path, field):
            if path.endswith("/files"):
                return [{"filename": allowed[0], "status": "renamed",
                         "previous_filename": "pilot/orchestrator/config.py"}]
            return real_pages(path, field)
        api.pages = renamed
        with self.assertRaisesRegex(ai.PolicyBlocked, "PR_PATH_NOT_ALLOWED"):
            ai.evaluate_one(api, 129)
        self.assertEqual(api.writes, [])

    def test_tampered_registry_bytes_block_automatic_label(self):
        registry_paths = ["pilot/registry/implemented.json"]
        item = self.generated("lf/implemented-registry", registry_paths)
        api = FakeAPI(item, registry_paths, checks())
        from types import SimpleNamespace
        with patch.object(ai.subprocess, "run", return_value=SimpleNamespace(
                     stdout=HEAD + "\n")):
            with patch("pilot.orchestrator.implemented_registry.reconstruct",
                       return_value={"schema_version": "T7_IMPLEMENTED_REGISTRY_V1",
                                     "source_main_sha": HEAD, "entries": []}):
                with patch.object(ai, "_content", return_value=b'{"tampered":true}\n'):
                    with self.assertRaisesRegex(ai.PolicyBlocked, "GENERATED_CONTENT_DRIFT"):
                        ai.evaluate_one(api, 129)
        self.assertEqual(api.writes, [])

    def test_generated_analysis_drift_blocks_without_label(self):
        allowed = ["pilot/runs/sample/analysis.json"]
        item = self.generated("lf/generated-t7", allowed)
        api = FakeAPI(item, allowed, self.generated_checks())
        from types import SimpleNamespace
        class FakeFixture:
            def __init__(self, where):
                self.where = where
            def __enter__(self):
                return self.where
            def __exit__(self, *exc):
                return False
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            stage = __import__("pathlib").Path(tmp)
            outputs = iter([SimpleNamespace(stdout=HEAD + "\n", returncode=0),
                            SimpleNamespace(stdout=b"request SCREEN-A\n", returncode=0)])
            def run_f4(root, slug, fixtures):
                folder = root / "pilot/runs" / slug
                (folder / "analysis.json").write_bytes(b'{"trusted":true}\n')
            with patch.object(ai.subprocess, "run", side_effect=lambda *a, **kw: next(outputs)):
                with patch("analysis.host.request_catalog.resolve",
                           return_value=("SCREEN-A", stage)):
                    with patch("analysis.host.run_a1_a9_fixture.run_f4",
                               side_effect=run_f4):
                        with patch.object(ai, "_content",
                                          return_value=b'{"tampered":true}\n'):
                            with self.assertRaisesRegex(ai.PolicyBlocked,
                                                        "GENERATED_CONTENT_DRIFT"):
                                ai.evaluate_one(api, 129)
        self.assertEqual(api.writes, [])

    def test_generated_commit_is_reported_automatic(self):
        from orchestrator.intervention_report import (
            actor, classify, scope_paths, BOT_EMAIL,
        )
        self.assertEqual(actor(BOT_EMAIL, "github-actions[bot]"), "BOT")
        with patch("orchestrator.intervention_report.write_paths", return_value=[]):
            self.assertIn("pilot/registry/implemented.json",
                          scope_paths("sample", [], rev="HEAD"))
        for path in ("pilot/runs/sample/analysis.json",
                     "pilot/runs/sample/chain_plan.json",
                     "pilot/registry/implemented.json"):
            self.assertEqual(classify(path, "BOT", "sample")[0], "AUTOMATIC")


if __name__ == "__main__":
    unittest.main()


class ScriptImportPathTest(unittest.TestCase):
    """Policy C runs as `python3 pilot/...`; the trusted generators it imports
    live in repo-root packages, so a fresh interpreter must resolve them."""

    def test_generator_packages_import_from_script_entrypoint(self):
        import subprocess as sp
        root = Path(__file__).resolve().parents[1]
        code = ("import runpy,sys;sys.argv=['x'];"
                "g=runpy.run_path('pilot/auto_integrate.py');"
                "import inspect;src=inspect.getsource(g['verify_generated_content']);"
                "assert 'sys.path.insert' in src;"
                "sys.path.insert(0,'.');"
                "import pilot.orchestrator.implemented_registry")
        r = sp.run([sys.executable, "-I", "-c", code], cwd=root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class ScheduledSweepTest(unittest.TestCase):
    """Bot-dispatched ci emits no workflow_run, so a schedule must sweep."""

    def test_scheduled_sweep_skips_trigger_and_still_evaluates(self):
        api = FakeAPI(pr("registration"), paths(), checks())
        with patch.object(ai, "evaluate_one", return_value="LABEL_AND_TRAIN_DISPATCHED") as ev:
            out = ai.run(api, None, numbers=[129], scheduled=True)
        ev.assert_called_once_with(api, 129)
        self.assertEqual(out, [{"pr": 129, "decision": "LABEL_AND_TRAIN_DISPATCHED"}])

    def test_unscheduled_without_trigger_still_blocks(self):
        with self.assertRaises(ai.PolicyBlocked):
            ai.run(FakeAPI(pr("registration"), paths(), checks()), None, numbers=[129])
