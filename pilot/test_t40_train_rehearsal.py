"""T40: the Train requires a green exam rehearsal on PRs touching lots/exams,
and dispatches it once when a bot PR did not trigger it."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sandbox_train as train  # noqa: E402

SHA = "b" * 40


def pr():
    return {"number": 81, "state": "open", "draft": False, "head": {"sha": SHA, "ref": "feat/x",
            "repo": {"full_name": "paulozterra/lf-programming-sandbox"}},
            "base": {"ref": "main"}, "labels": [{"name": "ready-to-merge"}],
            "user": {"login": "paulozterra"}}


class Clock:
    now = 0
    def monotonic(self):
        return self.now
    def sleep(self, s):
        self.now += s


def green(extra=None):
    found = {n: {"id": 1, "status": "completed", "conclusion": "success"} for n in train.REQUIRED}
    found.update(extra or {})
    return found


def run(files, rehearsal, runs_exist=False):
    clock, dispatched = Clock(), []
    def api(method, path, payload=None, expected=(200,)):
        if path.startswith("/pulls/81/files"):
            return [{"filename": f} for f in files]
        if path.startswith("/actions/workflows/ci.yml/runs?"):
            return {"workflow_runs": [{"head_sha": SHA, "event": "push", "status": "completed"}]}
        if path.startswith("/actions/workflows/exam-rehearsal.yml/runs?"):
            return {"workflow_runs": [{"head_sha": SHA, "status": "completed"}] if runs_exist else []}
        if path.endswith("/dispatches"):
            dispatched.append((path, payload))
            return {}
        raise AssertionError(path)
    def checks(_):
        if clock.now >= 200 and rehearsal is not None:
            return green({"rehearse": {"id": 2, "status": "completed", "conclusion": rehearsal}})
        return green()
    with patch.dict(os.environ, {"GITHUB_REPOSITORY": "paulozterra/lf-programming-sandbox"}), \
         patch.object(train, "pr_data", return_value=pr()), \
         patch.object(train, "check_pr"), patch.object(train, "approve_pending_runs"), \
         patch.object(train, "api", side_effect=api), \
         patch.object(train, "checks_for_head", side_effect=checks), \
         patch.object(train, "WAIT_SECONDS", 400), \
         patch.object(train.time, "monotonic", side_effect=clock.monotonic), \
         patch.object(train.time, "sleep", side_effect=clock.sleep):
        try:
            return train.await_checks(81, SHA, set()), dispatched
        except train.TrainError as exc:
            return str(exc), dispatched


def test_unrelated_pr_needs_no_rehearsal():
    result, dispatched = run(["pilot/x.py"], None)
    assert set(result) == set(train.REQUIRED) and dispatched == []


def test_lot_pr_waits_for_rehearsal_and_dispatches_once():
    result, dispatched = run(["pilot/worker_v08/native_tasks/req9backend2.json"], "success")
    assert "rehearse" in result
    assert [p for p, _ in dispatched] == ["/actions/workflows/exam-rehearsal.yml/dispatches"]


def test_failed_rehearsal_blocks_merge():
    result, _ = run(["pilot/holdouts/req9backend2.reference.json.age"], "failure", runs_exist=True)
    assert isinstance(result, str) and result.startswith("CHECK_FAILED") and "rehearse" in result


def test_missing_rehearsal_times_out_closed():
    result, _ = run(["pilot/holdouts/req9backend2.oracle.json.age"], None, runs_exist=True)
    assert result == "CHECK_WAIT_TIMEOUT"
