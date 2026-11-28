"""T46.1: bounded replay, exact trust parity and issue notice (offline)."""
from __future__ import annotations

import json
from urllib.parse import parse_qs
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator import conflict_integration_replay as recovery
from pilot.orchestrator import native_integration_replay as original

REPO = chain_lots.REPO
TASK = "fixturebackend2"
RUN = 5012
SHA = "a" * 40
BRANCH = f"lf/native-integration/{TASK}-run-{RUN}"
ROW = {"kind": "integration", "branch": BRANCH, "number": 123,
       "sha": "b" * 40}
HISTORY = "actions/workflows/native-verified-integration.yml/runs?"


def source(**override):
    item = {"created_at": "2026-11-17T10:00:00Z", "id": RUN, "status": "completed", "conclusion": "success",
            "run_attempt": 1, "event": "workflow_run",
            "head_branch": "main",
            "path": ".github/workflows/worker-native.yml",
            "repository": {"full_name": REPO},
            "display_title": "lf-native-auto-lf/native-proposal/" + TASK + "-" + SHA}
    item.update(override)
    return item


def dispatch(identity, conclusion, *, status="completed", **changes):
    item = {"id": identity, "status": status, "conclusion": conclusion,
            "event": "workflow_dispatch", "head_branch": "main",
            "path": ".github/workflows/native-verified-integration.yml",
            "repository": {"full_name": REPO},
            "display_title": f"CP3.5 recovery native-run-{RUN}"}
    item.update(changes)
    return item


def fixture(history, *, source_row=None):
    calls = []
    def api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path == f"actions/runs/{RUN}":
            return source() if source_row is None else source_row
        if path == f"actions/runs/{RUN}/jobs?per_page=100":
            return {"jobs": [{"name": "native", "conclusion": "success"}]}
        if path.startswith(HISTORY):
            query = parse_qs(path.split("?", 1)[1])
            assert query["event"] == ["workflow_dispatch"]
            assert query["branch"] == ["main"]
            assert query["created"] == [">=2026-11-17T10:00:00Z"]
            assert query["page"] == ["1"]
            if isinstance(history, dict) and isinstance(history.get("workflow_runs"), list):
                return {"total_count": len(history["workflow_runs"]), **history}
            return history
        raise AssertionError(path)
    def run(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return "[]"
        if args[:3] == ("gh", "workflow", "run"):
            return ""
        raise AssertionError(args)
    return run, api, calls


def test_t46_1_prior_failed_run_blocks_with_full_receipt(monkeypatch):
    monkeypatch.delenv(recovery.FAIL_LIMIT_ENV, raising=False)
    run, api, calls = fixture({"workflow_runs": [dispatch(990, "failure")]})
    row = recovery.recover(ROW, run, api, REPO)
    assert row == {"status": "BLOCKED",
                   "reason": "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED",
                   "code": "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED",
                   "phase": "CONFLICT_RECOVERY", "step": recovery.INTEGRATION,
                   "source_run_id": RUN, "failed_run_id": 990, "task": TASK}
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


def test_t46_1_success_after_failure_allows_dispatch():
    run, api, calls = fixture({"workflow_runs": [
        dispatch(991, "success"), dispatch(990, "failure")]})
    outcome = recovery.recover(ROW, run, api, REPO)
    assert outcome["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert sum(c[:3] == ("gh", "workflow", "run") for c in calls) == 1


def test_t46_1_only_failures_after_last_success_count(monkeypatch):
    monkeypatch.setenv(recovery.FAIL_LIMIT_ENV, "2")
    rows = [dispatch(994, "failure"), dispatch(993, "success"),
            dispatch(992, "failure"), dispatch(991, "cancelled")]
    run, api, calls = fixture({"workflow_runs": rows})
    assert recovery.recover(ROW, run, api, REPO)["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert sum(c[:3] == ("gh", "workflow", "run") for c in calls) == 1
    run, api, calls = fixture({"workflow_runs": [
        dispatch(995, "cancelled"), *rows]})
    result = recovery.recover(ROW, run, api, REPO)
    assert result["status"] == "BLOCKED"
    assert result["failed_run_id"] == 995
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


@pytest.mark.parametrize("history", [
    {"workflow_runs": [{}] },
    {"workflow_runs": [dispatch(12, "failure")] * 100},
    {"workflow_runs": [dispatch(12, "failure"), dispatch(12, "failure")]},
    {"workflow_runs": [dispatch(12, "failure", head_branch="other")]},
    {"workflow_runs": [dispatch(12, "failure", path=".github/workflows/other.yml")]},
    {"workflow_runs": [dispatch(12, "failure", repository={"full_name": "other/repo"})]},
    {"workflow_runs": [dispatch(12, None, status="completed")]},
    {"workflow_runs": "invalid"},
    {"workflow_runs": [], "total_count": 101},
    {"workflow_runs": [{"id": 12, "status": [], "display_title": "bad"}]},
    {},
])
def test_t46_1_ambiguous_history_denies_dispatch(history):
    run, api, calls = fixture(history)
    with pytest.raises(recovery.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED$"):
        recovery.recover(ROW, run, api, REPO)
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


def test_t46_1_history_unavailable_denies_dispatch():
    run, api, calls = fixture({"workflow_runs": []})
    def broken(path):
        if path.startswith(HISTORY):
            raise OSError("No network")
        return api(path)
    with pytest.raises(recovery.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED$"):
        recovery.recover(ROW, run, broken, REPO)
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


@pytest.mark.parametrize("value", ["0", "-1", "11", "abc", "1.5"])
def test_t46_1_invalid_limit_fails_closed(monkeypatch, value):
    monkeypatch.setenv(recovery.FAIL_LIMIT_ENV, value)
    run, api, calls = fixture({"workflow_runs": []})
    with pytest.raises(recovery.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_FAILURE_LIMIT_INVALID$"):
        recovery.recover(ROW, run, api, REPO)
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


@pytest.mark.parametrize("change", [
    {},
    {"display_title": "lf-native-route-retry-" + TASK + "-" + SHA},
    {"display_title": "lf-native-infra-retry-" + TASK + "-" + SHA},
    {"display_title": "lf-native-auto-lf/native-proposal/" + TASK + "-" + SHA.upper()},
    {"display_title": "lf-native-auto-lf/native-proposal/" + TASK + "-other"},
    {"run_attempt": 2},
    {"event": "push"},
    {"head_branch": "feature"},
    {"status": "in_progress"},
    {"conclusion": "failure"},
    {"path": ".github/workflows/another.yml"},
    {"repository": {"full_name": "another/repo"}},
])
def test_t46_1_trusted_worker_parity_shared_table(change):
    item = source(**change)
    accepted = original._trusted_worker(item, REPO)
    if accepted:
        match = original.WORKER_TITLE.fullmatch(item["display_title"])
        assert match is not None and match.group(1) == TASK
    run, api, _ = fixture({"workflow_runs": []}, source_row=item)
    with patch.object(recovery, "block", wraps=recovery.block):
        if accepted:
            recovery._native_pass(api, REPO, RUN, TASK)
        else:
            with pytest.raises(recovery.ReplayBlocked,
                               match="^CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED$"):
                recovery._native_pass(api, REPO, RUN, TASK)


def test_t46_1_notice_dedupes_by_failed_run_id():
    comments = []
    def api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL, main_response
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path == "issues/123":
            return {"number": 123, "state": "open", "labels": [{"name": "lf-request"}]}
        return main_response(path)
    def api_list(path):
        assert path == "issues/123/comments"
        return [{"body": text, "user": {"login": "github-actions[bot]"}}
                for text in comments]
    def run(*args):
        assert args[:3] == ("gh", "issue", "comment")
        comments.append(args[-1])
        return ""
    plans = [("req-123", {}, {}, {"lot-1": {"task_name": TASK}})]
    with patch.object(chain_lots, "api", side_effect=api), \
         patch.object(chain_lots, "api_list", side_effect=api_list), \
         patch.object(chain_lots, "run", side_effect=run):
        chain_lots.notify_failed_conflict_replay(ROW, plans, 990)
        chain_lots.notify_failed_conflict_replay(ROW, plans, 990)
        chain_lots.notify_failed_conflict_replay(ROW, plans, 991)
    assert len(comments) == 2
    assert "LF_CP36_CP35_FAILED:990" in comments[0]
    assert "LF_CP36_CP35_FAILED:991" in comments[1]
