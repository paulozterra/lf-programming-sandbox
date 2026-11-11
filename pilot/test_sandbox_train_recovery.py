"""Offline CP0.2 race regressions: GitHub PR propagation and missing CI."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sandbox_train", ROOT / "pilot/sandbox_train.py")
train = importlib.util.module_from_spec(spec)
# sandbox_train imports its sibling sandbox_train_merge.
import sys
sys.path.insert(0, str(ROOT / "pilot"))
spec.loader.exec_module(train)


def pr(sha="a" * 40):
    return {"state": "open", "draft": False, "base": {"ref": "main"},
            "head": {"ref": "feat/cp02", "sha": sha,
                     "repo": {"full_name": "paulozterra/lf-programming-sandbox"}},
            "labels": [{"name": "ready-to-merge"}], "mergeable": True}


def green_checks(sha):
    return {name: {"id": idx + 1, "status": "completed", "conclusion": "success"}
            for idx, name in enumerate(train.REQUIRED)}


class FakeClock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RacePolicyTests(unittest.TestCase):
    def test_delayed_pr_head_after_push_waits_then_dispatches(self):
        clock = FakeClock()
        old, new = pr(), pr("b" * 40)
        # First read is from run(), then three stale PR reads after the push.
        calls = [old, old, old, old, new, new, new]
        dispatched = []
        def get_pr(_):
            return calls.pop(0) if calls else new
        def api(method, path, payload=None, expected=(200,)):
            if path.startswith("/compare/"):
                if "a" * 40 in path:
                    return {"behind_by": 1, "status": "diverged"}
                return {"behind_by": 0, "status": "ahead"}
            if path.endswith("/dispatches"):
                dispatched.append(payload)
                return {}
            if path.endswith("/merge"):
                return {"merged": True, "sha": "c" * 40}
            if path == "/commits/" + "c" * 40:
                return {"parents": [{}, {}]}
            raise AssertionError(path)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox",
                                     "GH_TOKEN": "fake", "TRAIN_RECEIPT": os.devnull}), \\
             patch.object(train, "pr_data", side_effect=get_pr), \\
             patch.object(train, "main_sha", return_value="m" * 40), \\
             patch.object(train, "api", side_effect=api), \\
             patch.object(train, "update_branch_locally", return_value="b" * 40) as update, \\
             patch.object(train, "await_checks", return_value=green_checks("b" * 40)), \\
             patch.object(train.time, "monotonic", side_effect=clock.monotonic), \\
             patch.object(train.time, "sleep", side_effect=clock.sleep):
            train.run(81)
        update.assert_called_once()
        self.assertEqual(clock.now, 15)
        self.assertEqual(dispatched, [{"ref": "feat/cp02"}])

    def test_pr_head_visibility_timeout_fails_closed(self):
        clock = FakeClock()
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \\
             patch.object(train, "pr_data", return_value=pr()), \\
             patch.object(train.time, "monotonic", side_effect=clock.monotonic), \\
             patch.object(train.time, "sleep", side_effect=clock.sleep):
            with self.assertRaisesRegex(train.TrainError, "POST_PUSH_HEAD_VISIBILITY_TIMEOUT"):
                train.wait_for_pushed_head(81, "b" * 40)
        self.assertEqual(clock.now, 60)

    def exercise_missing_ci(self, run_status, expect_dispatch):
        clock = FakeClock()
        dispatched = []
        def api(method, path, payload=None, expected=(200,)):
            if path.startswith("/actions/workflows/ci.yml/runs?"):
                runs = [] if run_status == "none" else [{
                    "head_sha": "b" * 40, "event": "push", "status": run_status
                }]
                return {"workflow_runs": runs}
            if path.endswith("/dispatches"):
                dispatched.append(payload)
                return {}
            raise AssertionError(path)
        def checks(_):
            if clock.now >= 80:
                return green_checks("b" * 40)
            return {}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \\
             patch.object(train, "pr_data", return_value=pr("b" * 40)), \\
             patch.object(train, "api", side_effect=api), \\
             patch.object(train, "checks_for_head", side_effect=checks), \\
             patch.object(train.time, "monotonic", side_effect=clock.monotonic), \\
             patch.object(train.time, "sleep", side_effect=clock.sleep):
            dispatched_heads = set()
            result = train.await_checks(81, "b" * 40, dispatched_heads)
            self.assertEqual(set(result), set(train.REQUIRED))
            # A later invocation for the same SHA must NOT dispatch again.
            train.await_checks(81, "b" * 40, dispatched_heads)
        self.assertEqual(len(dispatched), expect_dispatch)
        if expect_dispatch:
            self.assertEqual(dispatched, [{"ref": "feat/cp02"}])

    def test_head_without_ci_dispatches_once(self):
        self.exercise_missing_ci("none", 1)

    def test_action_required_is_not_usable_ci(self):
        self.exercise_missing_ci("action_required", 1)

    def test_head_with_existing_ci_does_not_dispatch(self):
        self.exercise_missing_ci("in_progress", 0)


if __name__ == "__main__":
    unittest.main()
