"""CHG-0246: orphan branches and ambiguous owners must not starve another task."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.orchestrator.request_lifecycle import RequestStateError
from pilot.orchestrator import chain_lots, native_pending_recovery as r1
from pilot.orchestrator import native_infra_retry as t20
from pilot.orchestrator import native_route_recovery as t23

HEAD = "b" * 40
SHA = "a" * 40
REPO = "paulozterra/lf-programming-sandbox"
BAD = "aaaambiguous"
GOOD = "zzzhealthy"
ORPHAN = "aaorphan"


def admission(task, *, ambiguous=False):
    # Simulates the precise callback contract of chain_lots.task_live.
    # Unowned task branches are stale and must not be interpreted as a failure.
    owners = {GOOD: {"req-286"}, BAD: {"req-186", "req-286"}
              if ambiguous else {"req-186"}}
    candidates = owners.get(task, set())
    if not candidates:
        return False
    if len(candidates) > 1:
        raise RequestStateError("REQUEST_STATE_UNRESOLVED")
    return True


@pytest.mark.parametrize("bad,ambiguous,expected", [
    (ORPHAN, False, None),
    (BAD, True, "REQUEST_STATE_UNRESOLVED"),
])
def test_r1_bad_owner_does_not_prevent_healthy_dispatch(
        tmp_path, monkeypatch, bad, ambiguous, expected):
    folder = tmp_path / "registrations"
    folder.mkdir()
    (folder / (GOOD + ".json")).write_text("{}")
    monkeypatch.setattr(r1, "storage_path", lambda *_a, **_kw: folder)
    monkeypatch.setattr(r1, "validate_proposal_only",
                        lambda *_a, **kw: {"task": kw["branch"].rsplit("/", 1)[-1]})
    dispatched = []
    def run(*args):
        if args[:3] == ("git", "ls-remote", "--heads"):
            return (f"{SHA} refs/heads/lf/native-proposal/{bad}\n"
                    f"{SHA} refs/heads/lf/native-proposal/{GOOD}")
        if args[:2] == ("git", "fetch"):
            return ""
        if args[:3] == ("gh", "workflow", "run"):
            dispatched.append(args)
            return ""
        raise AssertionError(args)
    result = r1.recover(HEAD, run,
                        lambda _: {"total_count": 0, "workflow_runs": []},
                        REPO, tmp_path,
                        allowed_task=lambda task: admission(task, ambiguous=ambiguous))
    assert len(dispatched) == 1 and "task=" + GOOD in dispatched[0]
    assert len([x for x in result if x["status"] == "R1_WORKER_PENDING_REDISPATCHED"]) == 1
    if expected is None:
        assert not any(x.get("task") == bad for x in result)
    else:
        assert {"status": "BLOCKED", "task": bad, "reason": expected} in result


@pytest.mark.parametrize("bad,ambiguous,expected", [
    (ORPHAN, False, "REQUEST_CLOSED"),
    (BAD, True, "BLOCKED"),
])
def test_t20_bad_owner_does_not_prevent_healthy_dispatch(
        bad, ambiguous, expected):
    def failure(task, id):
        return {"id": id, "event": "workflow_run", "status": "completed",
                "conclusion": "failure",
                "display_title": f"lf-native-auto-lf/native-proposal/{task}-{SHA}"}
    rows = [failure(bad, 101), failure(GOOD, 102)]
    def api(path):
        if path == "actions/workflows/worker-native.yml/runs?per_page=100":
            return {"total_count": 2, "workflow_runs": rows}
        if path == "actions/runs/102/jobs?per_page=100":
            return {"total_count": 1, "jobs": [
                {"name": "native", "steps": [
                    {"name": t20.INFRA_STEP, "conclusion": "failure"},
                    {"name": "Admit task and registered base (fail closed until Claude registers ex6)",
                     "conclusion": "skipped"}]}]}
        raise AssertionError(path)
    dispatched = []
    def run(*args):
        if args[:3] == ("git", "ls-remote", "origin"):
            return SHA + " refs/heads/lf/native-proposal/" + GOOD
        if args[:2] == ("git", "fetch"):
            return ""
        if args[:3] == ("gh", "workflow", "run"):
            dispatched.append(args)
            return ""
        raise AssertionError(args)
    with patch.object(t20, "validate_proposal_only", return_value={"task": GOOD}):
        result = t20.retry_native_infra(
            HEAD, run, api, REPO, Path("."),
            allowed_task=lambda task: admission(task, ambiguous=ambiguous))
    assert result[0]["task"] == bad and result[0]["status"] == expected
    if ambiguous:
        assert result[0]["reason"] == "REQUEST_STATE_UNRESOLVED"
    assert result[1]["status"] == "NATIVE_INFRA_RETRY_DISPATCHED"
    assert result[1]["task"] == GOOD
    assert len(dispatched) == 1


@pytest.mark.parametrize("bad,ambiguous,expected", [
    (ORPHAN, False, "REQUEST_CLOSED"),
    (BAD, True, "BLOCKED"),
])
def test_t23_sweep_bad_owner_does_not_prevent_healthy_evidence(
        tmp_path, bad, ambiguous, expected):
    rows = [{"id": 101, "conclusion": "failure", "display_title": bad},
            {"id": 102, "conclusion": "failure", "display_title": GOOD}]
    actions = []
    def inspected(_run, _api, _repo, _root, row):
        return {"task": row["display_title"], "run_id": row["id"],
                "request": 286, "sha": SHA}
    def comment(*args, allowed_task=None):
        assert allowed_task is not None and allowed_task(args[3]["task"])
        actions.append(("comment", args[3]["task"]))
        return "ROUTE_DEFECT_RECORDED"
    def prepare(*args):
        actions.append(("prepare", args[5]["task"]))
        return {"status": "ROUTE_DEFECT_REGISTRATION_DRAFT"}
    with patch.object(t23, "history", return_value=rows), \
         patch.object(t23, "_run_identity", side_effect=lambda x, _: (x["display_title"], SHA)), \
         patch.object(t23, "inspect", side_effect=inspected), \
         patch.object(t23, "comment_defect", side_effect=comment), \
         patch.object(t23, "prepare_repair", side_effect=prepare), \
         patch.object(t23, "replay_corrected", return_value=[]):
        result = t23.sweep(HEAD, lambda *_: "", lambda *_: {}, REPO, tmp_path,
                           None, None, None,
                           allowed_task=lambda task: admission(task, ambiguous=ambiguous))
    assert result[0]["task"] == bad and result[0]["status"] == expected
    if ambiguous:
        assert result[0]["reason"] == "REQUEST_STATE_UNRESOLVED"
    assert [x["task"] for x in result if x.get("status") == "ROUTE_DEFECT_RECORDED"] == [GOOD]
    assert actions == [("comment", GOOD), ("prepare", GOOD)]


@pytest.mark.parametrize("bad,ambiguous,expected", [
    (ORPHAN, False, "REQUEST_CLOSED"),
    (BAD, True, "BLOCKED"),
])
def test_t23_replay_bad_owner_does_not_prevent_good_replay(
        tmp_path, bad, ambiguous, expected):
    migrations = tmp_path / "pilot/worker_v08/route_migrations"
    migrations.mkdir(parents=True)
    for task in (bad, GOOD):
        (migrations / (task + ".json")).write_text("{}")
    folder = tmp_path / "registrations"
    folder.mkdir()
    (folder / (GOOD + ".json")).write_text("{}")
    dispatched = []
    def run(*args):
        if args[:3] == ("git", "ls-remote", "origin"):
            return SHA + " refs/heads/lf/native-proposal/" + GOOD
        if args[:2] == ("git", "fetch"):
            return ""
        if args[:2] == ("git", "show"):
            return "{}"
        if args[:3] == ("gh", "workflow", "run"):
            dispatched.append(args)
            return ""
        raise AssertionError(args)
    with patch.object(t23, "storage_path", return_value=folder), \
         patch.object(t23, "verified_migration", return_value={
             "proposal_commit_sha": SHA, "source_run_id": 102,
             "legacy_task_pack_sha256": "c" * 64}), \
         patch.object(t23, "_run_identity", return_value=(GOOD, SHA)), \
         patch.object(t23, "issue_for_task", return_value=286), \
         patch.object(t23, "comment_defect", return_value="ROUTE_DEFECT_ALREADY_RECORDED"), \
         patch.object(t23, "validate_proposal_only", return_value={"task": GOOD}), \
         patch.object(t23, "comment_resubmit", return_value="ROUTE_DEFECT_RESUBMIT_NOTIFIED"):
        result = t23.replay_corrected(
            HEAD, run, lambda _: {"conclusion": "failure"}, REPO, tmp_path, [],
            allowed_task=lambda task: admission(task, ambiguous=ambiguous))
    assert result[0]["task"] == bad and result[0]["status"] == expected
    if ambiguous:
        assert result[0]["reason"] == "REQUEST_STATE_UNRESOLVED"
    assert result[-1]["status"] == "ROUTE_DEFECT_RESUBMIT_NOTIFIED"
    assert len(dispatched) == 0
