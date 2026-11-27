"""T49: issue state, finalization proof and deny-by-default synthetic IDs."""
import json

import pytest

from pilot.orchestrator.request_finalize import verified_chain_complete
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
    config.write_text(json.dumps({"allowed_non_issue_requests": ["synthetic-okay", "simulated"]}))
    return config


def api_for(state, reason=None, root=None):
    def api(path):
        from pilot.orchestrator.lifecycle_test_support import fake_api
        if path == "issues/275":
            return {"number": 275, "state": state, "state_reason": reason}
        return fake_api({}, issue_state=state, root=root)(path)
    return api


def test_closed_not_planned_is_cancelled(tmp_path):
    fixture(tmp_path)
    assert request_state("req-275", api_for("closed", "not_planned", root=tmp_path),
                         root=tmp_path) == CLOSED_CANCELLED


def test_closed_completed_without_proof_still_cancelled(tmp_path):
    fixture(tmp_path)
    assert request_state("req-275", api_for("closed", "completed", root=tmp_path),
                         root=tmp_path) == CLOSED_CANCELLED


def test_closed_verified_is_finalized(tmp_path):
    fixture(tmp_path, finalized=True)
    assert request_state("req-275", api_for("closed", "not_planned", root=tmp_path),
                         root=tmp_path) == CLOSED_FINALIZED


@pytest.mark.parametrize("finalized", [False, True])
def test_t49_canonical_finalization_parity(tmp_path, finalized):
    fixture(tmp_path, finalized=finalized)
    folder = tmp_path / "pilot/runs/req-275"
    expected = verified_chain_complete(folder, root=tmp_path)
    actual = request_state("req-275", api_for("closed", root=tmp_path), root=tmp_path)
    assert (actual == CLOSED_FINALIZED) is expected
    assert actual == (CLOSED_FINALIZED if expected else CLOSED_CANCELLED)


def test_reopened_uses_fresh_issue_state(tmp_path):
    fixture(tmp_path, finalized=True)
    from pilot.orchestrator.lifecycle_test_support import fake_api
    assert request_state("req-275", fake_api({}, issue_state="closed", root=tmp_path),
                         root=tmp_path) == CLOSED_FINALIZED
    assert request_state("req-275", fake_api({}, issue_state="open", root=tmp_path,
                         reopened=True), root=tmp_path) == CLOSED_FINALIZED


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
    config = fixture(tmp_path)
    assert request_state("synthetic-okay", lambda _: 1, root=tmp_path,
                         allowlist=config) == OPEN
    assert request_state("simulated", lambda _: 1, root=tmp_path,
                         allowlist=config) == OPEN
    with pytest.raises(RequestStateError, match="REQUEST_STATE_UNRESOLVED"):
        request_state("synthetic-other", lambda _: 1, root=tmp_path,
                      allowlist=config)


def test_train_closed_289_regression_never_requests_exam(tmp_path, monkeypatch):
    """The non-sweep TRAIN entry must not reach EXAM_REQUEST for closed #275."""
    fixture(tmp_path)
    from pilot.orchestrator import chain_lots as chain
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    monkeypatch.setattr(chain, "api", api_for("closed", "not_planned", root=tmp_path))
    def forbidden(*args, **kwargs):
        raise AssertionError("closed TRAIN attempted a publication")
    monkeypatch.setattr(chain, "request_all_lot_exams", forbidden)
    monkeypatch.setattr(chain, "complete_registered_exam_requests", forbidden)
    monkeypatch.setattr(chain, "prepare_successor", forbidden)
    outcomes = chain.process_one_plan(
        "req-275", {"lots": [{"id": "SOL-001"}]}, {"stage": "LOTS_PLANNED"},
        {"SOL-001": {"task_name": "req275backend1"}}, "a" * 40,
        "TRAIN", False, None, None, [])
    assert outcomes == [{"request": "req-275", "status": "REQUEST_CLOSED"}]


def test_train_unresolved_does_not_publish(tmp_path, monkeypatch):
    fixture(tmp_path)
    from pilot.orchestrator import chain_lots as chain
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    def down(_path):
        raise OSError("GitHub unavailable")
    monkeypatch.setattr(chain, "api", down)
    monkeypatch.setattr(chain, "request_all_lot_exams", lambda *_:
                        pytest.fail("published despite unresolved state"))
    result = chain.process_one_plan(
        "req-275", {"lots": [{"id": "SOL-001"}]}, {"stage": "LOTS_PLANNED"},
        {"SOL-001": {"task_name": "req275backend1"}}, "a" * 40,
        "TRAIN", False, None, None, [])
    assert result[0]["reason_code"] == "REQUEST_STATE_UNRESOLVED"


def test_exam_notice_never_comments_on_closed(tmp_path, monkeypatch):
    fixture(tmp_path)
    from pilot.orchestrator import chain_lots as chain
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    monkeypatch.setattr(chain, "api", api_for("closed", "completed", root=tmp_path))
    monkeypatch.setattr(chain, "run", lambda *_a, **_k:
                        pytest.fail("commented on closed request"))
    chain.exam_notice("req-275", "key", "EXAMEN_PENDIENTE")


def test_conflict_notice_suppressed_for_closed(tmp_path, monkeypatch):
    fixture(tmp_path)
    from pilot.orchestrator import chain_lots as chain
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    monkeypatch.setattr(chain, "conflicted_request", lambda *_: "req-275")
    monkeypatch.setattr(chain, "api", api_for("closed", "not_planned", root=tmp_path))
    monkeypatch.setattr(chain, "run", lambda *_a, **_k:
                        pytest.fail("notice published despite closed issue"))
    chain.notify_failed_conflict_replay({"number": 500}, [], 1234)


def test_worker_feedback_suppressed_for_closed(tmp_path, monkeypatch):
    fixture(tmp_path)
    from pilot.worker_v08 import native_feedback_delivery as feedback
    monkeypatch.setattr(feedback, "issue_for_task", lambda *_: 275)
    monkeypatch.setattr(feedback, "parse_feedback", lambda value, attempt:
                        {"schema_version": "test"})
    def forbidden(*_a, **_kw):
        pytest.fail("feedback published despite closed issue")
    result = feedback.publish(forbidden, api_for("closed", "completed", root=tmp_path),
                              "org/repo", tmp_path, "task202", "a" * 40,
                              1, {}, "FAIL")
    assert result == "REQUEST_CLOSED"
