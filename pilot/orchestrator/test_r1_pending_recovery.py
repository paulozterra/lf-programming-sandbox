"""R1: cancelled pending delivery, idempotence, synthetic interleavings."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from unittest.mock import patch

import pytest

from pilot.orchestrator import native_pending_recovery as pending
from pilot.orchestrator import native_integration_replay as integration

REPO = "paulozterra/lf-programming-sandbox"
TASK = "r1fixturetask"
SHA = "a" * 40
HEAD = "b" * 40


def native_row(identity, *, status="completed", conclusion="cancelled"):
    return {"id": identity, "head_branch": "main", "run_attempt": 1,
            "event": "workflow_run", "status": status, "conclusion": conclusion,
            "display_title": f"lf-native-auto-lf/native-proposal/{TASK}-{SHA}"}


def test_cancelled_or_skipped_worker_pending_is_not_admitted():
    for conclusion in ("cancelled", "skipped"):
        assert pending.replay_decision(TASK, SHA, [
            native_row(20, conclusion=conclusion)]) == ("SKIPPED" if conclusion == "skipped" else "REPLAY")
    assert pending.replay_decision(TASK, SHA, [
        native_row(20, status="queued", conclusion=None)]) == "WAITING"
    assert pending.replay_decision(TASK, SHA, [
        native_row(20, conclusion="success")]) == "DELIVERED"


def test_worker_cancelled_by_retry_replays_once_then_noop(tmp_path, monkeypatch):
    reg = tmp_path / "registrations" / (TASK + ".json")
    reg.parent.mkdir(parents=True)
    reg.write_text("{}")
    state = [native_row(20)]
    issued = []
    monkeypatch.setattr(pending, "storage_path", lambda *_args, **_kwargs: reg.parent)
    monkeypatch.setattr(pending, "validate_proposal_only", lambda *args, **kwargs: {"task": TASK})
    monkeypatch.setattr(pending, "_artifact_json", lambda *args: None)
    monkeypatch.setenv("GH_TOKEN", "synthetic-test-token")

    def api(path):
        assert "worker-native.yml/runs" in path
        return {"total_count": len(state), "workflow_runs": list(state)}

    def run(*args):
        if args[:3] == ("git", "ls-remote", "--heads"):
            return f"{SHA} refs/heads/lf/native-proposal/{TASK}"
        if args[:2] == ("git", "fetch"):
            return ""
        if args[:3] == ("gh", "workflow", "run"):
            issued.append(args)
            state.append(dict(native_row(21, status="queued", conclusion=None),
                              event="workflow_dispatch",
                              display_title=f"lf-native-pending-retry-{TASK}-{SHA}"))
            return ""
        raise AssertionError(args)

    first = pending.recover(HEAD, run, api, REPO, tmp_path,
                            allowed_task=lambda task: task == TASK)
    second = pending.recover(HEAD, run, api, REPO, tmp_path,
                             allowed_task=lambda task: task == TASK)
    assert [x["status"] for x in first] == ["R1_WORKER_PENDING_REDISPATCHED"]
    assert second == []
    assert len(issued) == 1
    assert "pending_retry=true" in issued[0]


def test_worker_prior_proof_fails_closed_without_dispatch(tmp_path, monkeypatch):
    reg = tmp_path / "registrations" / (TASK + ".json")
    reg.parent.mkdir(parents=True)
    reg.write_text("{}")
    monkeypatch.setattr(pending, "storage_path", lambda *_args, **_kwargs: reg.parent)
    monkeypatch.setattr(pending, "validate_proposal_only", lambda *args, **kwargs: {"task": TASK})
    monkeypatch.setattr(pending, "_artifact_json", lambda *args: {"attempt": 1})
    monkeypatch.setenv("GH_TOKEN", "synthetic-test-token")
    other = dict(native_row(10, conclusion="failure"),
                 display_title="lf-native-auto-lf/native-proposal/" + TASK + "-" + "c" * 40)
    def api(_path):
        return {"total_count": 1, "workflow_runs": [other]}
    calls = []
    def run(*args):
        calls.append(args)
        if args[:3] == ("git", "ls-remote", "--heads"):
            return f"{SHA} refs/heads/lf/native-proposal/{TASK}"
        if args[:2] == ("git", "fetch"):
            return ""
        raise AssertionError(args)
    result = pending.recover(HEAD, run, api, REPO, tmp_path,
                             allowed_task=lambda task: task == TASK)
    assert result[0]["reason"] == "R1_WORKER_PRIOR_ATTEMPT_REQUIRES_REVIEW"
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


def test_cp35_cancelled_then_queued_is_recovered_once(tmp_path, monkeypatch):
    reg = tmp_path / "registrations" / (TASK + ".json")
    reg.parent.mkdir(parents=True)
    reg.write_text("{}")
    monkeypatch.setattr(integration, "storage_path", lambda *_args, **_kwargs: reg.parent)
    source = dict(native_row(55, conclusion="success"),
                  path=integration.WORKER_PATH,
                  repository={"full_name": REPO})
    cancelled = {"id": 70, "event": "workflow_run", "status": "completed",
                 "conclusion": "cancelled",
                 "path": integration.INTEGRATION_PATH,
                 "repository": {"full_name": REPO},
                 "display_title": "CP3.5 " + source["display_title"]}
    integrations = [cancelled]
    dispatched = []

    def api(path):
        rows = [source] if "worker-native.yml" in path else integrations
        return {"total_count": len(rows), "workflow_runs": list(rows)}

    def run(*args):
        if args[:3] == ("git", "ls-remote", "origin"):
            return ""
        if args[:3] == ("gh", "workflow", "run"):
            dispatched.append(args)
            integrations.append(dict(cancelled, id=71, event="workflow_dispatch",
                                     status="queued", conclusion=None,
                                     display_title="CP3.5 recovery native-run-55"))
            return ""
        raise AssertionError(args)

    first = integration.recover_unstarted(HEAD, run, api, REPO, tmp_path,
                                          allowed_tasks={TASK})
    second = integration.recover_unstarted(HEAD, run, api, REPO, tmp_path,
                                           allowed_tasks={TASK})
    assert first[0]["status"] == "R1_CP35_REDISPATCHED"
    assert second == []
    assert len(dispatched) == 1


def test_c01_three_event_queue_replacement_then_state_sweep():
    """Concurrent synthetic event arrivals: pending #2 is displaced by #3.

    The recovery must derive all three transitions from persisted state, not
    from the surviving event's payload.
    """
    barrier = threading.Barrier(3)
    guard = threading.Lock()
    persisted = {"lot-a", "lot-b", "lot-c"}
    completed = set()
    queue = []
    def producer(lot):
        barrier.wait(timeout=5)
        with guard:
            queue[:] = [lot]  # GitHub's single pending slot
    threads = [threading.Thread(target=producer, args=(x,))
               for x in ("lot-b", "lot-c")]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(queue) == 1
    # An event consumer can see only the surviving pending event.
    completed.update(queue)
    # The real CP3.6 sweep reads plans/registrations, not queue.
    completed.update(persisted)
    assert completed == persisted


def test_skipped_guard_is_not_concurrency_loss():
    assert pending.replay_decision(TASK, SHA, [
        native_row(51, conclusion="skipped")]) == "SKIPPED"
    assert pending.replay_decision(TASK, SHA, [
        native_row(51, conclusion="cancelled"),
        native_row(52, conclusion="skipped")]) == "SKIPPED"


def test_bad_registration_does_not_starve_recoverable_task(tmp_path, monkeypatch):
    broken = "aaaunregistered"
    healthy = "zzzregistered"
    folder = tmp_path / "registrations"
    folder.mkdir()
    (folder / (healthy + ".json")).write_text("{}")
    monkeypatch.setattr(pending, "storage_path", lambda *_a, **_k: folder)
    monkeypatch.setattr(pending, "validate_proposal_only",
                        lambda *_a, **kw: {"task": kw["branch"].rsplit("/", 1)[1]})
    monkeypatch.setenv("GH_TOKEN", "fixture-token")
    outcomes = []
    rows = [native_row(10, conclusion="cancelled")]
    def api(_path):
        return {"total_count": len(rows), "workflow_runs": list(rows)}
    def run(*args):
        if args[:3] == ("git", "ls-remote", "--heads"):
            return ("{sha} refs/heads/lf/native-proposal/{a}\n"
                    "{sha} refs/heads/lf/native-proposal/{b}".format(
                        sha=SHA, a=broken, b=healthy))
        if args[:2] == ("git", "fetch"):
            return ""
        if args[:3] == ("gh", "workflow", "run"):
            outcomes.append(args)
            rows.append(dict(native_row(11, status="queued", conclusion=None),
                             event="workflow_dispatch",
                             display_title="lf-native-pending-retry-" + healthy + "-" + SHA))
            return ""
        raise AssertionError(args)
    first = pending.recover(HEAD, run, api, REPO, tmp_path,
                             allowed_task=lambda *_a: True)
    second = pending.recover(HEAD, run, api, REPO, tmp_path,
                              allowed_task=lambda *_a: True)
    assert first == [
        {"status": "BLOCKED", "task": broken,
         "reason": "R1_WORKER_REGISTRATION_MISSING"},
        {"status": "R1_WORKER_PENDING_REDISPATCHED", "task": healthy,
         "proposal_sha": SHA}]
    assert second[0]["status"] == "BLOCKED"
    assert len(outcomes) == 1


def test_skipped_worker_never_redispaches(tmp_path, monkeypatch):
    folder = tmp_path / "registrations"
    folder.mkdir()
    (folder / (TASK + ".json")).write_text("{}")
    monkeypatch.setattr(pending, "storage_path", lambda *_a, **_k: folder)
    def api(_path):
        return {"total_count": 1, "workflow_runs": [native_row(
            25, conclusion="skipped")]}
    def run(*args):
        if args[:3] == ("git", "ls-remote", "--heads"):
            return f"{SHA} refs/heads/lf/native-proposal/{TASK}"
        raise AssertionError("skipped must not dispatch: " + repr(args))
    assert pending.recover(HEAD, run, api, REPO, tmp_path,
                           allowed_task=lambda *_a: True) == []


def test_b3_cp36_event_and_state_sweep_have_same_legitimate_transitions(tmp_path):
    """The lost new-plan event and a state sweep prepare the same eligible lot."""
    from pilot.orchestrator import chain_lots
    request = "req-901"
    head = HEAD
    lots = {"lots": [{"id": "L1", "area": "CONTRATO",
                       "depends_on": []}]}
    binding = {"L1": {"task_name": "fixture1", "lot_id": "L1"}}
    state = {"stage": "LOTS_PLANNED"}
    effects = []

    def prepare(*args):
        effects.append(("PREPARE", args[0], args[1]["lot_id"]))
        return {"status": "DRAFT_PREPARED"}

    def exam(*args):
        effects.append(("EXAM", args[0]))
        return [{"status": "EXAM_REQUESTED"}]

    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "request_state", return_value="OPEN"), \
         patch.object(chain_lots, "complete_registered_exam_requests", return_value=[]), \
         patch.object(chain_lots, "request_all_lot_exams", side_effect=exam), \
         patch.object(chain_lots, "completed_lots", return_value={}), \
         patch.object(chain_lots, "failed_lots", return_value={}), \
         patch.object(chain_lots, "progress", return_value={"stage": "LOTS_PLANNED",
                                                            "ready_lot_ids": ["L1"]}), \
         patch.object(chain_lots, "storage_path", return_value=tmp_path), \
         patch.object(chain_lots, "pending_draft", return_value=False), \
         patch.object(chain_lots, "admit_registration", return_value=None), \
         patch.object(chain_lots, "prepare_successor", side_effect=prepare), \
         patch.object(chain_lots, "close_failed_old_registration_drafts",
                      return_value=[]):
        event = chain_lots.process_one_plan(
            request, lots, state, binding, head, "TRAIN", False,
            request, None, [])
        event_effects = list(effects)
        effects.clear()
        sweep = chain_lots.process_one_plan(
            request, lots, state, binding, head, "TRAIN", True,
            None, None, [])
        sweep_effects = list(effects)
    assert event == sweep
    assert event_effects == sweep_effects == [
        ("EXAM", request), ("PREPARE", request, "L1")]
