"""Offline P0 policy gates: no network, token, database, or merge."""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sandbox-train.yml"
CODE = ROOT / "pilot/sandbox_train.py"
spec = importlib.util.spec_from_file_location("sandbox_train", CODE)
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)


def sample_pr(draft=False, fork=False):
    return {"state": "open", "draft": draft,
            "base": {"ref": "main"},
            "head": {"ref": "feat/test", "sha": "a" * 40,
                     "repo": {"full_name": "foreign/repo" if fork else "paulozterra/lf-programming-sandbox"}},
            "labels": [{"name": "ready-to-merge"}], "mergeable": True}


class PolicyTests(unittest.TestCase):
    def setUp(self):
        # These original Train tests isolate the merge/CI protocol. Dedicated
        # D22 regressions exercise the new lifecycle guard itself.
        guard = patch.object(train, "guard_request_lifecycle")
        guard.start()
        self.addCleanup(guard.stop)

    def test_no_target_no_custom_secrets_no_external_privileges(self):
        data = WORKFLOW.read_text()
        self.assertNotIn("pull_request_target", data)
        # T47: exactly one owner secret, only in the merge step (workflow-file pushes).
        self.assertEqual(re.findall(r"secrets\.[A-Z_]+", data), ["secrets.TRAIN_PUSH_TOKEN"])
        merge = data.split("- name: Merge checked HEAD; fail closed", 1)[1].split("- name:", 1)[0]
        self.assertIn("GH_TOKEN: ${{ secrets.TRAIN_PUSH_TOKEN || github.token }}", merge)
        self.assertIn("actions: write", data)
        self.assertIn("contents: write", data)
        self.assertIn("pull-requests: write", data)
        self.assertIn("checks: read", data)
        self.assertIn("cancel-in-progress: false", data)
        self.assertIn("group: sandbox-train", data)
        self.assertIn("persist-credentials: false", data)
        self.assertIn("ref: main", data)
        self.assertIn("types: [labeled]", data)
        self.assertIn("workflow_dispatch:", data)

    def test_draft_and_fork_denied(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}):
            for pr in (sample_pr(draft=True), sample_pr(fork=True)):
                with self.assertRaises(train.TrainError):
                    train.check_pr(pr)

    def test_labeled_draft_transitions_then_normal_merge_flow(self):
        draft = sample_pr(draft=True)
        draft["node_id"] = "PR_eligible"
        ready = sample_pr(draft=False)
        ready["node_id"] = "PR_eligible"
        seen = []
        def fake_graphql(query, variables):
            seen.append((query, variables))
            return {"markPullRequestReadyForReview": {
                "pullRequest": {"id": "PR_eligible", "isDraft": False}}}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox",
                                     "GH_TOKEN": "test-token", "TRAIN_RECEIPT": os.devnull}), \
             patch.object(train, "pr_data", side_effect=[draft, ready, ready, ready]) as read, \
             patch.object(train, "graphql", side_effect=fake_graphql), \
             patch.object(train, "main_sha", return_value="m" * 40), \
             patch.object(train, "await_checks", return_value={"backend": {"conclusion": "success"}}), \
             patch.object(train, "update_branch_locally", return_value="a" * 40), \
             patch.object(train, "api") as api_mock:
            api_mock.side_effect = lambda method, path, payload=None, expected=(200,): (
                {"behind_by": 0, "status": "ahead", "files": []} if path.startswith("/compare/") else
                {"merged": True, "sha": "c" * 40} if path.endswith("/merge") else
                {"parents": [{}, {}]} if path == "/commits/" + "c" * 40 else
                (_ for _ in ()).throw(AssertionError(path)))
            train.run(101)
        self.assertEqual(len(seen), 1)
        self.assertIn("markPullRequestReadyForReview", seen[0][0])
        self.assertEqual(seen[0][1], {"id": "PR_eligible"})
        self.assertEqual(read.call_count, 3)
        self.assertTrue(any(c.args[0] == "PUT" and c.args[1] == "/pulls/101/merge"
                            for c in api_mock.call_args_list))

    def test_draft_without_label_denied_before_graphql(self):
        draft = sample_pr(draft=True)
        draft["labels"] = []
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft), \
             patch.object(train, "graphql") as mutation:
            with self.assertRaisesRegex(train.TrainError, "PR_CLOSED_OR_DRAFT"):
                train.run(101)
            mutation.assert_not_called()

    def test_forked_draft_denied_before_graphql(self):
        draft = sample_pr(draft=True, fork=True)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft), \
             patch.object(train, "graphql") as mutation:
            with self.assertRaisesRegex(train.TrainError, "FORK_REJECTED"):
                train.run(101)
            mutation.assert_not_called()

    def test_failed_mutation_blocks_without_followup(self):
        draft = sample_pr(draft=True)
        draft["node_id"] = "PR_eligible"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft) as read, \
             patch.object(train, "graphql", side_effect=train.TrainError("GRAPHQL_RESPONSE_INVALID")), \
             patch.object(train, "main_sha") as main, \
             patch.object(train, "api") as api_mock:
            with self.assertRaisesRegex(train.TrainError, "DRAFT_READY_FAILED"):
                train.run(101)
            self.assertEqual(read.call_count, 1)
            main.assert_not_called()
            api_mock.assert_not_called()

    def test_closed_pr_denied_even_with_label(self):
        draft = sample_pr(draft=True)
        draft["state"] = "closed"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=draft), \
             patch.object(train, "graphql") as mutation:
            with self.assertRaisesRegex(train.TrainError, "PR_CLOSED_OR_DRAFT"):
                train.run(101)
            mutation.assert_not_called()

    def test_label_missing_denied(self):
        pr = sample_pr()
        pr["labels"] = []
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}):
            with self.assertRaisesRegex(train.TrainError, "LABEL_MISSING"):
                train.check_pr(pr)

    def test_merge_requires_exact_sha_and_merge_commit(self):
        source = CODE.read_text()
        self.assertIn('"sha": initial_head, "merge_method": "merge"', source)
        self.assertIn('len(commit["parents"]) != 2', source)
        self.assertNotIn('"merge_method": "squash"', source)
        self.assertNotIn('"merge_method": "rebase"', source)
        self.assertIn("update_branch_locally(", source)
        self.assertIn('"sha": initial_head, "merge_method": "merge"', source)

    def test_checks_must_be_from_exact_head(self):
        self.assertIn('run["head_sha"] != sha', CODE.read_text())
        self.assertIn('run["app"]["slug"] != "github-actions"', CODE.read_text())
        self.assertIn('"CHECK_WAIT_TIMEOUT"', CODE.read_text())
        self.assertIn('"RESTART_LIMIT_EXCEEDED"', CODE.read_text())
        self.assertTrue(train.REQUIRED)
        self.assertLessEqual(train.MAX_RESTARTS, 3)


    def test_dispatch_after_update_only(self):
        """Simulate a stale PR: updated HEAD must trigger CI exactly once."""
        pr = sample_pr()
        updated = sample_pr()
        updated["head"]["sha"] = "b" * 40
        responses = {"pr": [pr, updated, updated, updated, updated]}
        calls = []
        def fake_pr(_):
            return responses["pr"].pop(0) if responses["pr"] else updated
        def fake_api(method, path, payload=None, expected=(200,)):
            calls.append((method, path, payload))
            if path.startswith("/compare/"):
                return {"behind_by": 1, "status": "diverged", "files": []} if len([c for c in calls if c[1].startswith("/compare/")]) == 1 else {"behind_by": 0, "status": "ahead", "files": []}
            if path.endswith("/dispatches"):
                return {}
            if path.endswith("/merge"):
                return {"merged": True, "sha": "c" * 40}
            if path == "/commits/" + "c" * 40:
                return {"parents": [{"sha": "a" * 40}, {"sha": "b" * 40}]}
            raise AssertionError(path)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox", "GH_TOKEN": "test-token", "TRAIN_RECEIPT": os.devnull}), \
             patch.object(train, "api", side_effect=fake_api), \
             patch.object(train, "pr_data", side_effect=fake_pr), \
             patch.object(train, "main_sha", return_value="m" * 40), \
             patch.object(train, "await_checks", return_value={"backend (Maven verify)": {"conclusion": "success"}}), \
             patch.object(train, "update_branch_locally", return_value="b" * 40) as local_update, \
             patch.object(train.time, "sleep", return_value=None):
            train.run(77)
        dispatch = [c for c in calls if c[1] == "/actions/workflows/ci.yml/dispatches"]
        self.assertEqual(len(dispatch), 1)
        self.assertEqual(dispatch[0][2], {"ref": "feat/test"})
        local_update.assert_called_once_with("feat/test", "a" * 40, "m" * 40, "test-token", "paulozterra/lf-programming-sandbox")

    def test_no_dispatch_if_branch_not_updated(self):
        pr = sample_pr()
        calls = []
        def fake_api(method, path, payload=None, expected=(200,)):
            calls.append((method, path, payload))
            if path.startswith("/compare/"):
                return {"behind_by": 0, "status": "ahead", "files": []}
            if path.endswith("/merge"):
                return {"merged": True, "sha": "c" * 40}
            if path == "/commits/" + "c" * 40:
                return {"parents": [{}, {}]}
            raise AssertionError(path)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox", "GH_TOKEN": "test-token", "TRAIN_RECEIPT": os.devnull}), \
             patch.object(train, "api", side_effect=fake_api), \
             patch.object(train, "pr_data", return_value=pr), \
             patch.object(train, "main_sha", return_value="m" * 40), \
             patch.object(train, "await_checks", return_value={"backend (Maven verify)": {"conclusion": "success"}}), \
             patch.object(train, "update_branch_locally", return_value="a" * 40) as render:
            train.run(77)
            render.assert_called_once()
        self.assertFalse(any(c[1] == "/actions/workflows/ci.yml/dispatches" for c in calls))

    def test_ci_dispatch_is_enabled_and_restricted_to_updated_head(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("  workflow_dispatch:", ci)
        source = CODE.read_text()
        self.assertIn('dispatch_updated_head_ci(updated["head"]["ref"], merged_head)', source)
        self.assertIn('expected=(204,)', source)


    def test_all_workflows_reject_runner_context_in_job_env(self):
        checker_path = ROOT / "pilot/check_workflow_job_env.py"
        checker_spec = importlib.util.spec_from_file_location("workflow_env_guard", checker_path)
        checker = importlib.util.module_from_spec(checker_spec)
        checker_spec.loader.exec_module(checker)
        self.assertEqual(checker.main(), 0)

    def test_workflow_env_guard_rejects_invalid_job_env(self):
        checker_path = ROOT / "pilot/check_workflow_job_env.py"
        checker_spec = importlib.util.spec_from_file_location("workflow_env_guard", checker_path)
        checker = importlib.util.module_from_spec(checker_spec)
        checker_spec.loader.exec_module(checker)
        invalid = """name: invalid
on: push
jobs:
  merge:
    runs-on: ubuntu-latest
    env:
      TRAIN_RECEIPT: ${{ runner.temp }}/receipt.json
    steps:
      - run: echo done
"""
        self.assertEqual(len(checker.violations(invalid, "invalid.yml")), 1)
        valid = invalid.replace("      TRAIN_RECEIPT: ${{ runner.temp }}/receipt.json", "      TRAIN_RECEIPT: sandbox-train-receipt.json")
        self.assertEqual(checker.violations(valid), [])
        # runner context is legal in a step-level env; only reject job-level.
        step_env = """jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Read artifact
        env:
          TRAIN_RECEIPT: ${{ runner.temp }}/receipt.json
        run: echo ok
"""
        self.assertEqual(checker.violations(step_env), [])

class RetirementMergeTests(unittest.TestCase):
    def test_workflow_entrypoint_import(self):
        subprocess.run([sys.executable, "-m", "pilot.workflow_entrypoint",
                        "--smoke", "pilot/sandbox_train.py"], cwd=ROOT, check=True)

    def test_retirement_guard(self):
        branch = "lf/native-registration/t1-aaaaaaaaaaaa"
        head = "a" * 40
        same = {"number": 42, "state": "open", "head": {"ref": "lf/exam-retire/t1-abc"}}
        other = {"number": 43, "state": "open", "head": {"ref": "lf/exam-retire/t2-abc"}}
        for rows, error in [
            ([], None), ([same], "POLICY_C_RETIRO_PENDIENTE.*#42"),
            ([other], None), (None, "POLICY_C_RETIRO_API_ERROR"),
            ([dict(same, state="closed")], "POLICY_C_RETIRO_API_ERROR"),
        ]:
            with self.subTest(rows=rows):
                def fake_api(method, path, payload=None):
                    if method == "GET":
                        self.assertIn("state=open", path)
                        if rows is None:
                            raise train.TrainError("NETWORK GET")
                        return rows
                    return {"merged": True}
                with patch.object(train, "api", side_effect=fake_api) as mock_api:
                    if error:
                        with self.assertRaisesRegex(train.TrainError, error):
                            train.merge_with_retry(101, head, {}, branch=branch)
                    else:
                        self.assertTrue(train.merge_with_retry(101, head, {}, branch=branch)["merged"])
                    self.assertEqual(sum(c.args[0] == "PUT" for c in mock_api.call_args_list),
                                     0 if error else 1)

    def test_retirement_appears_during_retry(self):
        head = "a" * 40
        rows = [{"number": 42, "state": "open", "head": {"ref": "lf/exam-retire/t1-abc"}}]
        with patch.object(train, "api", side_effect=[
            [], train.TrainError("NETWORK PUT merge"),
            {"merged": False, "head": {"sha": head}}, rows,
        ]) as mock_api:
            with self.assertRaisesRegex(train.TrainError, "POLICY_C_RETIRO_PENDIENTE"):
                train.merge_with_retry(101, head, {}, branch="lf/native-registration/t1-aaaaaaaaaaaa",
                                       sleep=lambda _: None)
            self.assertEqual(sum(c.args[0] == "PUT" for c in mock_api.call_args_list), 1)



class CheckRecoveryTests(unittest.TestCase):
    def test_recovery_is_exact_and_bounded(self):
        sha = "a" * 40
        repo = "paulozterra/lf-programming-sandbox"
        name = train.REQUIRED[-1]
        run = {"id": 11, "head_sha": sha, "status": "completed",
               "conclusion": "success", "head_repository": {"full_name": repo}}
        job = {"id": 22, "run_id": 11, "head_sha": sha, "name": name,
               "status": "in_progress", "conclusion": "success",
               "check_run_url": "https://api.github.com/repos/example/check-runs/22"}
        check = {"id": 22, "status": "in_progress", "conclusion": "success"}
        budget = set()
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": repo}), \
             patch.object(train, "ci_workflow_runs_for_head", side_effect=lambda sha, pending_approval=False: [] if pending_approval else [run]), \
             patch.object(train, "api", return_value={"total_count": 1, "jobs": [job]}) as api:
            self.assertEqual(train.recover_inconsistent_ci_job(sha, [name], {name: check}, budget), "RECOVERY_REQUESTED")
            self.assertEqual(train.recover_inconsistent_ci_job(sha, [name], {name: check}, budget), "RECOVERY_SKIPPED:BUDGET_USED")
            self.assertEqual(sum(c.args[0] == "POST" for c in api.call_args_list), 1)
            self.assertEqual(api.call_args_list[-1].args[1], "/actions/jobs/22/rerun")

    def test_recovery_rejects_untrusted_or_real_failure(self):
        sha = "a" * 40
        repo = "paulozterra/lf-programming-sandbox"
        name = train.REQUIRED[-1]
        run = {"id": 11, "head_sha": sha, "status": "completed",
               "conclusion": "success", "head_repository": {"full_name": repo}}
        job = {"id": 22, "run_id": 11, "head_sha": sha, "name": name,
               "status": "completed", "conclusion": "success",
               "check_run_url": "https://api.github.com/repos/example/check-runs/22"}
        check = {"id": 22, "status": "in_progress", "conclusion": None}
        cases = [
            ([dict(run, status="in_progress")], [job], check),
            ([dict(run, conclusion="failure")], [job], check),
            ([dict(run, head_repository={"full_name": "foreign/repo"})], [job], check),
            ([run], [dict(job, head_sha="b" * 40)], check),
            ([run], [dict(job, conclusion="failure")], check),
            ([run], [dict(job, run_id=12)], check),
            ([run], [job, job], check),
            ([run], [job], dict(check, id=99)),
            ([run], [job], dict(check, conclusion="failure")),
            ([run], [job], dict(check, status="completed")),
        ]
        for runs, jobs, observed in cases:
            with self.subTest(runs=runs, jobs=jobs, observed=observed), \
                 patch.dict(os.environ, {"GITHUB_REPOSITORY": repo}), \
                 patch.object(train, "ci_workflow_runs_for_head", side_effect=lambda sha, pending_approval=False: [] if pending_approval else runs), \
                 patch.object(train, "api", return_value={"total_count": len(jobs), "jobs": jobs}) as api:
                budget = set()
                self.assertTrue(train.recover_inconsistent_ci_job(sha, [name], {name: observed}, budget).startswith("RECOVERY_SKIPPED:"))
                self.assertFalse(budget)
                self.assertFalse(any(c.args[0] == "POST" for c in api.call_args_list))

    def test_await_checks_never_accepts_incomplete_success(self):
        sha = "a" * 40
        name = train.REQUIRED[-1]
        green = {n: {"id": i + 1, "status": "completed", "conclusion": "success"}
                 for i, n in enumerate(train.REQUIRED)}
        stuck = dict(green, **{name: dict(green[name], status="in_progress")})
        clock = iter(range(0, 10000, 200))
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
             patch.object(train, "pr_data", return_value=sample_pr()), \
             patch.object(train, "needs_rehearsal", return_value=False), \
             patch.object(train, "approve_pending_runs"), \
             patch.object(train, "ci_workflow_runs_for_head", return_value=[{"id": 1}]), \
             patch.object(train, "checks_for_head", side_effect=[stuck, stuck, green]), \
             patch.object(train, "recover_inconsistent_ci_job", return_value="RECOVERY_REQUESTED") as recovery, \
             patch.object(train.time, "monotonic", side_effect=lambda: next(clock)), \
             patch.object(train.time, "sleep"), \
             patch.object(train, "WAIT_SECONDS", 10000):
            self.assertEqual(train.await_checks(77, sha), green)
            recovery.assert_called()


    def test_recovery_evidence_and_post_failure(self):
        sha = "a" * 40
        repo = "paulozterra/lf-programming-sandbox"
        name = train.REQUIRED[-1]
        run = {"id": 11, "head_sha": sha, "status": "completed",
               "conclusion": "success", "head_repository": {"full_name": repo}}
        job = {"id": 22, "run_id": 11, "head_sha": sha, "name": name,
               "status": "in_progress", "conclusion": "success",
               "check_run_url": "https://api.github.com/repos/example/check-runs/22"}
        check = {"id": 22, "status": "in_progress", "conclusion": "success"}
        for pending, rows, count, observed, reason in [
            ([run], [job], 1, {name: check}, "CI_PENDING_APPROVAL"),
            ([], [job], 2, {name: check}, "JOBS_INCOMPLETE"),
            ([], [job] * 100, 100, {name: check}, "JOBS_INCOMPLETE"),
            ([], [job], 1, {}, "CHECK_ABSENT"),
        ]:
            with self.subTest(reason=reason, count=count), \
                 patch.dict(os.environ, {"GITHUB_REPOSITORY": repo}), \
                 patch.object(train, "ci_workflow_runs_for_head",
                              side_effect=lambda sha, pending_approval=False: pending if pending_approval else [run]), \
                 patch.object(train, "api", return_value={"total_count": count, "jobs": rows}) as api:
                budget = set()
                self.assertEqual(train.recover_inconsistent_ci_job(sha, [name], observed, budget),
                                 "RECOVERY_SKIPPED:" + reason)
                self.assertFalse(budget)
                self.assertFalse(any(c.args[0] == "POST" for c in api.call_args_list))
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": repo}), \
             patch.object(train, "ci_workflow_runs_for_head",
                          side_effect=lambda sha, pending_approval=False: [] if pending_approval else [run]), \
             patch.object(train, "api", side_effect=[{"total_count": 1, "jobs": [job]},
                                                    train.TrainError("NETWORK POST")]) as api:
            budget = set()
            with self.assertRaisesRegex(train.TrainError, "CHECK_RECOVERY_POST_FAILED"):
                train.recover_inconsistent_ci_job(sha, [name], {name: check}, budget)
            self.assertIn(("check_recovery", sha), budget)
            self.assertEqual(train.recover_inconsistent_ci_job(sha, [name], {name: check}, budget),
                             "RECOVERY_SKIPPED:BUDGET_USED")
            self.assertEqual(sum(c.args[0] == "POST" for c in api.call_args_list), 1)

    def test_wait_loop_recovery_paths(self):
        sha = "a" * 40
        repo = "paulozterra/lf-programming-sandbox"
        name = train.REQUIRED[-1]
        other = train.REQUIRED[-2]
        green = {n: {"id": i + 1, "status": "completed", "conclusion": "success"}
                 for i, n in enumerate(train.REQUIRED)}
        stuck = dict(green, **{name: dict(green[name], status="in_progress")})
        two = dict(stuck, **{other: dict(green[other], status="in_progress")})
        slow = dict(stuck, **{name: dict(stuck[name], conclusion=None)})
        run = {"id": 11, "head_sha": sha, "status": "completed",
               "conclusion": "success", "head_repository": {"full_name": repo}}
        cases = [
            ("grace", stuck, 180, "CHECK_INCONSISTENT_UNRECOVERED", "GRACE_NOT_MET", 0),
            ("multiple", two, 240, "CHECK_INCONSISTENT_UNRECOVERED", "MULTIPLE_CHECKS", 0),
            ("head_changed", stuck, 240, None, None, 0),
            ("pending", stuck, 240, "CHECK_INCONSISTENT_UNRECOVERED", "CI_PENDING_APPROVAL", 0),
            ("post_failure", stuck, 240, "CHECK_RECOVERY_POST_FAILED", None, 1),
            ("recovery_timeout", stuck, 260, "CHECK_RECOVERY_TIMEOUT", None, 1),
            ("slow", slow, 240, "CHECK_WAIT_TIMEOUT", "CI_RUNNING", 0),
        ]
        for scenario, checks, wait, error, reason, posts in cases:
            with self.subTest(scenario=scenario), ExitStack() as stack:
                now = [0]
                budget = set()
                job = {"id": 22, "run_id": 11, "head_sha": sha, "name": name,
                       "status": "in_progress", "conclusion": "success",
                       "check_run_url": "https://api.github.com/repos/example/check-runs/" + str(green[name]["id"])}
                def read_pr(_):
                    pr = sample_pr()
                    if scenario == "head_changed" and now[0] >= 180 and read_pr.reads_at_180:
                        pr["head"]["sha"] = "b" * 40
                    if now[0] >= 180:
                        read_pr.reads_at_180 += 1
                    return pr
                read_pr.reads_at_180 = 0
                def fake_runs(_sha, pending_approval=False):
                    if pending_approval:
                        return [run] if scenario == "pending" else []
                    return [dict(run, status="in_progress")] if scenario == "slow" else [run]
                def fake_api(method, path, payload=None, expected=(200,)):
                    if method == "GET":
                        return {"total_count": 1, "jobs": [job]}
                    if scenario == "post_failure":
                        raise train.TrainError("NETWORK POST")
                    return {}
                stack.enter_context(patch.dict(os.environ, {"GITHUB_REPOSITORY": repo}))
                for attr, kwargs in [
                    ("pr_data", {"side_effect": read_pr}),
                    ("needs_rehearsal", {"return_value": False}),
                    ("approve_pending_runs", {}),
                    ("ci_workflow_runs_for_head", {"side_effect": fake_runs}),
                    ("checks_for_head", {"return_value": checks}),
                    ("WAIT_SECONDS", {"new": wait}),
                ]:
                    stack.enter_context(patch.object(train, attr, **kwargs))
                api = stack.enter_context(patch.object(train, "api", side_effect=fake_api))
                helper = stack.enter_context(patch.object(train, "recover_inconsistent_ci_job",
                                                         wraps=train.recover_inconsistent_ci_job))
                log = stack.enter_context(patch("builtins.print"))
                stack.enter_context(patch.object(train.time, "monotonic", side_effect=lambda: now[0]))
                stack.enter_context(patch.object(train.time, "sleep", side_effect=lambda secs: now.__setitem__(0, now[0] + secs)))
                if error:
                    with self.assertRaisesRegex(train.TrainError, error):
                        train.await_checks(77, sha, budget)
                else:
                    self.assertIsNone(train.await_checks(77, sha, budget))
                self.assertEqual(sum(c.args[0] == "POST" for c in api.call_args_list), posts)
                self.assertEqual(("check_recovery", sha) in budget, bool(posts))
                if scenario in ("grace", "multiple", "head_changed"):
                    helper.assert_not_called()
                if reason:
                    matching = [c for c in log.call_args_list if "ci_check_recovery_skipped" in str(c)
                                and "RECOVERY_SKIPPED:" + reason in str(c)]
                    self.assertEqual(len(matching), 1)

if __name__ == "__main__":
    unittest.main()
