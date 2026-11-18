"""T49: issue state, finalization proof and deny-by-default synthetic IDs."""
import json

import pytest

from pilot.orchestrator.request_lifecycle import (
    request_state, RequestStateError, OPEN, CLOSED_FINALIZED, CLOSED_CANCELLED,
)


def fixture(tmp_path, *, finalized=False):
    folder = tmp_path / "pilot/runs/req-275"
    folder.mkdir(parents=True)
    if finalized:
        (folder / "lots.json").write_text(json.dumps(
            {"lots": [{"id": "SOL-001"}, {"id": "SOL-002"}]}))
        (folder / "H_REPORT.md").write_text("# final report")
        registry = tmp_path / "pilot/registry/implemented.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"entries": [
            {"request": "req-275", "lot": x, "status": "ATTESTED",
             "merge_sha": "a" * 40} for x in ("SOL-001", "SOL-002")]}))
    config = tmp_path / "pilot/orchestrator/request_lifecycle_allowlist.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"allowed_non_issue_requests": ["synthetic-okay"]}))
    return config


def api_for(state, reason=None):
    def api(path):
        assert path == "issues/275"
        return {"number": 275, "state": state, "state_reason": reason}
    return api


def test_closed_not_planned_is_cancelled(tmp_path):
    fixture(tmp_path)
    assert request_state("req-275", api_for("closed", "not_planned"),
                         root=tmp_path) == CLOSED_CANCELLED


def test_closed_completed_without_proof_still_cancelled(tmp_path):
    fixture(tmp_path)
    assert request_state("req-275", api_for("closed", "completed"),
                         root=tmp_path) == CLOSED_CANCELLED


def test_closed_verified_is_finalized(tmp_path):
    fixture(tmp_path, finalized=True)
    assert request_state("req-275", api_for("closed", "not_planned"),
                         root=tmp_path) == CLOSED_FINALIZED


def test_reopened_uses_fresh_issue_state(tmp_path):
    fixture(tmp_path, finalized=True)
    state = {"value": "closed"}
    def api(_path):
        return {"number": 275, "state": state["value"]}
    assert request_state("req-275", api, root=tmp_path) == CLOSED_FINALIZED
    state["value"] = "open"
    assert request_state("req-275", api, root=tmp_path) == OPEN


def test_api_failure_and_invalid_issue_are_unresolved(tmp_path):
    fixture(tmp_path)
    def failing(_path):
        raise OSError("redacted network detail")
    with pytest.raises(RequestStateError, match="REQUEST_STATE_UNRESOLVED"):
        request_state("req-275", failing, root=tmp_path)
    with pytest.raises(RequestStateError, match="REQUEST_STATE_UNRESOLVED"):
        request_state("req-275", lambda _: {"number": 276, "state": "open"},
                      root=tmp_path)


def test_explicit_allowlist_and_unlisted_synthetic(tmp_path):
    fixture(tmp_path)
    assert request_state("synthetic-okay", lambda _: 1, root=tmp_path) == OPEN
    with pytest.raises(RequestStateError, match="REQUEST_STATE_UNRESOLVED"):
        request_state("synthetic-other", lambda _: 1, root=tmp_path)
