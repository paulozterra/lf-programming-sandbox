"""T17.1: execute CI evidence selection on exact SHA, no network or secrets."""
from __future__ import annotations

from unittest.mock import patch

from pilot.generated_ci_selection import (
    last_executed_ci_run, latest_executed_checks,
)
from pilot import request_failure_notify as notify

SHA = "a" * 40
BRANCH = "lf/native-registration/testtask-aaaaaaaaaaaa"


def ci_run(id, conclusion, status="completed", branch=BRANCH):
    return {"id": id, "head_sha": SHA, "head_branch": branch,
            "event": "workflow_dispatch" if id == 43729614995 else "pull_request",
            "status": status, "conclusion": conclusion,
            "created_at": ("2026-11-15T10:00:00Z" if id == 43729614995
                           else "2026-11-15T10:00:01Z")}


def test_real_ids_failure_and_action_required_choose_executed_failure():
    latest = last_executed_ci_run([
        ci_run(43729614995, "failure"),
        ci_run(43729617525, "action_required")])
    assert latest["id"] == 43729614995
    assert latest["conclusion"] == "failure"


def test_success_and_action_required_choose_executed_success():
    latest = last_executed_ci_run([
        ci_run(43729614995, "success"),
        ci_run(43729617525, "action_required")])
    assert latest["id"] == 43729614995
    assert latest["conclusion"] == "success"


def test_neutral_skipped_cancelled_cannot_eclipse_real_execution():
    rows = [ci_run(43729614995, "success")]
    rows += [ci_run(43729617525 + index, conclusion)
             for index, conclusion in enumerate((
                 "neutral", "skipped", "cancelled", "action_required"))]
    assert last_executed_ci_run(rows)["conclusion"] == "success"


def test_newer_running_execution_prevents_false_retirement():
    rows = [ci_run(43729614995, "failure"),
            ci_run(43729617525, None, status="in_progress")]
    assert last_executed_ci_run(rows)["status"] == "in_progress"


def test_only_nonexecuted_is_neither_success_nor_failure():
    assert last_executed_ci_run([
        ci_run(43729617525, "action_required"),
        ci_run(43729617526, "skipped")]) is None


def test_wrong_sha_check_cannot_masquerade_as_success():
    check = {"id": 1, "name": "required", "head_sha": SHA,
             "status": "completed", "conclusion": "success",
             "app": {"slug": "github-actions"}}
    ghost = dict(check, id=2, conclusion="action_required")
    wrong = dict(check, id=3, head_sha="b" * 40)
    chosen = latest_executed_checks([wrong, ghost, check], ("required",), SHA)
    assert chosen["required"]["id"] == 1


def test_watchdog_ignores_superseded_failure_by_successful_executed_ci():
    old = ci_run(43729614995, "failure")
    old.update({"name": "ci", "path": ".github/workflows/ci.yml",
                "repository": {"full_name": notify.REPO},
                "head_repository": {"full_name": notify.REPO}})
    new = ci_run(43729617525, "success")
    class API:
        def api(self, method, path):
            assert path.startswith("/actions/workflows/ci.yml/runs?")
            return {"total_count": 2, "workflow_runs": [old, new]}
    with patch.object(notify, "notify_t20_retry_exhaustion",
                      return_value="T20_NOT_RETRY_EXHAUSTION"), \
         patch.object(notify, "emit") as emit:
        assert notify.check_run(API(), old) == "RUTA_CI_SUPERADA_O_NO_EJECUTADA"
        emit.assert_not_called()


def test_watchdog_failure_still_reports_when_only_newer_action_required():
    old = ci_run(43729614995, "failure")
    old.update({"name": "ci", "path": ".github/workflows/ci.yml",
                "repository": {"full_name": notify.REPO},
                "head_repository": {"full_name": notify.REPO}})
    ignored = ci_run(43729617525, "action_required")
    class API:
        def api(self, method, path):
            if path.startswith("/actions/workflows/ci.yml/runs?"):
                return {"total_count": 2, "workflow_runs": [old, ignored]}
            if path.endswith("/jobs?per_page=100"):
                return {"jobs": []}
            raise AssertionError(path)
    with patch.object(notify, "notify_t20_retry_exhaustion",
                      return_value="T20_NOT_RETRY_EXHAUSTION"), \
         patch.object(notify, "emit", return_value="RUTA_NOTIFIED") as emit:
        assert notify.check_run(API(), old) == "RUTA_NOTIFIED"
        emit.assert_called_once()
