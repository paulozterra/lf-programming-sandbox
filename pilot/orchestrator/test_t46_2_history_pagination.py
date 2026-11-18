"""T46.2: complete, filtered, source-bound CP3.5 history pagination (offline)."""
from __future__ import annotations

from urllib.parse import parse_qs

import pytest

from pilot.orchestrator import conflict_integration_replay as replay
from pilot.orchestrator.test_t46_1_bounded_replay import (
    REPO, RUN, ROW, source, dispatch,
)

PREFIX = "actions/workflows/native-verified-integration.yml/runs?"
CREATED = "2026-11-17T10:00:00Z"


def unrelated(identity):
    return dispatch(identity, "success",
                    display_title="CP3.5 automatic unrelated source " + str(identity))


def harness(rows, *, invalid_page=None, declared_total=None):
    pages = []
    dispatched = []
    def api(path):
        if path == "actions/runs/" + str(RUN):
            return source()
        if path == "actions/runs/" + str(RUN) + "/jobs?per_page=100":
            return {"jobs": [{"name": "native", "conclusion": "success"}]}
        assert path.startswith(PREFIX), path
        query = parse_qs(path.split("?", 1)[1])
        assert query["event"] == ["workflow_dispatch"]
        assert query["branch"] == ["main"]
        assert query["created"] == [">=" + CREATED]
        assert query["per_page"] == ["100"]
        page = int(query["page"][0])
        pages.append(page)
        if page == invalid_page:
            return {"total_count": len(rows), "workflow_runs": "corrupt"}
        return {"total_count": len(rows) if declared_total is None else declared_total,
                "workflow_runs": rows[(page - 1) * 100:page * 100]}

    def run(*argv):
        if argv[:3] == ("gh", "pr", "list"):
            return "[]"
        if argv[:3] == ("gh", "workflow", "run"):
            dispatched.append(argv)
            return ""
        raise AssertionError(argv)

    return run, api, pages, dispatched


def test_t46_2_250_third_page_failed_blocks():
    rows = [unrelated(i) for i in range(1000, 1249)]
    rows.append(dispatch(3000, "failure"))
    run, api, pages, sent = harness(rows)
    result = replay.recover(ROW, run, api, REPO)
    assert pages == [1, 2, 3]
    assert result["status"] == "BLOCKED"
    assert result["code"] == "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED"
    assert result["source_run_id"] == RUN
    assert result["failed_run_id"] == 3000
    assert sent == []


def test_t46_2_250_without_recovery_dispatches():
    run, api, pages, sent = harness([unrelated(i) for i in range(1000, 1250)])
    result = replay.recover(ROW, run, api, REPO)
    assert pages == [1, 2, 3]
    assert result["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert result["source_run_id"] == RUN
    assert len(sent) == 1 and "source_run_id=" + str(RUN) in sent[0]


def test_t46_2_regression_over_100_not_unresolved():
    # T46.1 rejected this count even if all entries were unrelated.
    run, api, pages, sent = harness([unrelated(i) for i in range(101, 252)])
    result = replay.recover(ROW, run, api, REPO)
    assert result["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert pages == [1, 2]
    assert len(sent) == 1


def test_t46_2_invalid_middle_page_blocks():
    run, api, pages, sent = harness([unrelated(i) for i in range(1000, 1250)],
                                     invalid_page=2)
    with pytest.raises(replay.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED$"):
        replay.recover(ROW, run, api, REPO)
    assert pages == [1, 2]
    assert sent == []


def test_t46_2_page_cap_blocks(monkeypatch):
    monkeypatch.setenv(replay.PAGE_LIMIT_ENV, "2")
    run, api, pages, sent = harness([unrelated(i) for i in range(1000, 1250)])
    with pytest.raises(replay.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED$"):
        replay.recover(ROW, run, api, REPO)
    assert pages == [1]
    assert sent == []


def test_t46_2_page_cap_exact_boundary_passes(monkeypatch):
    monkeypatch.setenv(replay.PAGE_LIMIT_ENV, "3")
    run, api, pages, sent = harness([unrelated(i) for i in range(1000, 1250)])
    assert replay.recover(ROW, run, api, REPO)["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert pages == [1, 2, 3] and len(sent) == 1


@pytest.mark.parametrize("invalid", ["0", "51", "-1", "invalid"])
def test_t46_2_invalid_page_cap_fails_closed(monkeypatch, invalid):
    monkeypatch.setenv(replay.PAGE_LIMIT_ENV, invalid)
    run, api, pages, sent = harness([unrelated(i) for i in range(1000, 1250)])
    with pytest.raises(replay.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED$"):
        replay.recover(ROW, run, api, REPO)
    assert pages == [] and sent == []


def test_t46_2_truncated_last_page_blocks():
    run, api, pages, sent = harness([unrelated(i) for i in range(1000, 1250)],
                                     declared_total=251)
    with pytest.raises(replay.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED$"):
        replay.recover(ROW, run, api, REPO)
    assert pages == [1, 2, 3]
    assert sent == []


def test_t46_2_timestamp_unavailable_fails_before_dispatch():
    calls = []
    def api(path):
        calls.append(path)
        if path == "actions/runs/" + str(RUN):
            return source(created_at=None)
        if path == "actions/runs/" + str(RUN) + "/jobs?per_page=100":
            return {"jobs": [{"name": "native", "conclusion": "success"}]}
        raise AssertionError(path)
    with pytest.raises(replay.ReplayBlocked,
                       match="^CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED$"):
        replay.recover(ROW, lambda *x: pytest.fail("no dispatch"), api, REPO)
    assert all(not x.startswith(PREFIX) for x in calls)
