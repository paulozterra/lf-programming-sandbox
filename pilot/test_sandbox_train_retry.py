"""Offline tests: Train retries transient GitHub failures and never merges a different HEAD."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sandbox_train", ROOT / "pilot/sandbox_train.py")
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)
HEAD = "a" * 40


class MergeRetry(unittest.TestCase):
    def run_with(self, responses, pr_reads):
        calls = {"put": 0}

        def api(method, path, payload=None, expected=(200,)):
            if method == "PUT":
                calls["put"] += 1
                item = responses.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            return pr_reads.pop(0)

        with mock.patch.object(train, "api", side_effect=api), \
                mock.patch.object(train.time, "sleep"):
            return train.merge_with_retry(118, HEAD, {"sha": HEAD}), calls["put"]

    def test_expected_checks_lag_then_success(self):
        lag = train.TrainError('HTTP 405 PUT /pulls/118/merge: 6 of 6 required status checks are expected.')
        result, puts = self.run_with([lag, lag, {"merged": True, "sha": "c" * 40}],
                                     [{"merged": False, "head": {"sha": HEAD}}] * 2)
        self.assertEqual(result["sha"], "c" * 40)
        self.assertEqual(puts, 3)

    def test_network_drop_but_already_merged_is_confirmed(self):
        result, puts = self.run_with([train.TrainError("NETWORK PUT /pulls/118/merge")],
                                     [{"merged": True, "merge_commit_sha": "d" * 40, "head": {"sha": HEAD}}])
        self.assertEqual(result, {"merged": True, "sha": "d" * 40})
        self.assertEqual(puts, 1)

    def test_head_changed_during_retry_blocks(self):
        lag = train.TrainError("HTTP 502 PUT /pulls/118/merge: bad gateway")
        with self.assertRaisesRegex(train.TrainError, "HEAD_CHANGED_DURING_MERGE_RETRY"):
            self.run_with([lag], [{"merged": False, "head": {"sha": "b" * 40}}])

    def test_real_rejection_not_retried(self):
        with self.assertRaisesRegex(train.TrainError, "409"):
            self.run_with([train.TrainError("HTTP 409 PUT /pulls/118/merge: Head branch was modified")], [])


class OwnChecksAndApproval(unittest.TestCase):
    def test_pending_bot_runs_are_approved_and_own_merge_check_ignored(self):
        calls = []

        def api(method, path, payload=None, expected=(200,)):
            calls.append((method, path))
            if path.startswith("/actions/runs?head_sha="):
                return {"workflow_runs": [{"id": 7, "head_sha": HEAD, "event": "pull_request",
                                           "head_repository": {"full_name": "o/r"}}]}
            return {}

        with mock.patch.object(train, "api", side_effect=api), \
                mock.patch.dict(train.os.environ, {"GITHUB_REPOSITORY": "o/r"}):
            train.approve_pending_runs(HEAD)
        self.assertIn(("POST", "/actions/runs/7/approve"), calls)
        self.assertIn("merge", train.TRAIN_OWN_CHECKS)


if __name__ == "__main__":
    unittest.main()
