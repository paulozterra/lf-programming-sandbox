"""T49.1: unique trusted task ownership and fail-closed Worker boundaries."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pilot.orchestrator import request_lifecycle as lc
from pilot.worker_v08 import native_run as worker


def seed(tmp_path, owners=("req-275",)):
    (tmp_path / "pilot/worker_v08/native_tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pilot/worker_v08/native_tasks/item1.json").write_text("{}")
    for request in owners:
        folder = tmp_path / "pilot/runs" / request
        folder.mkdir(parents=True)
        plan = {"request_id": request, "bindings": [{"lot_id": "SOL-001",
                "task_name": "item1", "template_path": f"pilot/runs/{request}/templates/item1.task.json"}]}
        (folder / "chain_plan.json").write_text(json.dumps(plan))
    return tmp_path


def api(state, *, fail=False):
    def call(path):
        assert path == "issues/275"
        if fail:
            raise OSError("unavailable")
        return {"number": 275, "state": state}
    return call


def attest(root):
    folder = root / "pilot/runs/req-275"
    (folder / "lots.json").write_text(json.dumps({"lots": [{"id": "SOL-001"}]}))
    (folder / "H_REPORT.md").write_text("real merged report")
    registry = root / "pilot/registry/implemented.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"entries": [{"request": "req-275",
        "lot": "SOL-001", "status": "ATTESTED", "merge_sha": "a" * 40}]}))


@pytest.mark.parametrize("owners", [(), ("req-275", "req-276")])
def test_task_owner_missing_or_ambiguous_denied(tmp_path, owners):
    seed(tmp_path, owners)
    with pytest.raises(lc.RequestStateError, match=lc.CODE):
        lc.request_for_task("item1", root=tmp_path)


def test_task_owner_uses_plan_not_proposal(tmp_path):
    seed(tmp_path)
    assert lc.request_for_task("item1", root=tmp_path) == "req-275"
    assert lc.require_task_open("item1", root=tmp_path, api=api("open")) == "req-275"


@pytest.mark.parametrize("state,proof,expect", [
    ("open", False, lc.OPEN), ("closed", False, lc.CLOSED_CANCELLED),
    ("closed", True, lc.CLOSED_FINALIZED),
])
def test_state_matrix(tmp_path, state, proof, expect):
    seed(tmp_path)
    if proof:
        attest(tmp_path)
    assert lc.request_state("req-275", api(state), root=tmp_path) == expect
    if expect != lc.OPEN:
        with pytest.raises(lc.RequestStateError, match="REQUEST_CLOSED"):
            lc.require_task_open("item1", root=tmp_path, api=api(state))


def test_reopened_and_github_read_error(tmp_path):
    seed(tmp_path)
    attest(tmp_path)
    assert lc.require_task_open("item1", root=tmp_path, api=api("open")) == "req-275"
    with pytest.raises(lc.RequestStateError, match=lc.CODE):
        lc.require_task_open("item1", root=tmp_path, api=api("closed", fail=True))


@pytest.mark.parametrize("reason", ["REQUEST_CLOSED", "REQUEST_STATE_UNRESOLVED"])
def test_worker_preflight_blocks_without_outputs(tmp_path, monkeypatch, reason):
    output = tmp_path / "output"
    def reject(*_a, **_kw):
        raise lc.RequestStateError(reason)
    monkeypatch.setattr(worker, "require_task_open", reject)
    monkeypatch.setattr(worker, "load_registration",
                        lambda *_: pytest.fail("preflight read registration after denial"))
    with pytest.raises(lc.RequestStateError, match=reason):
        worker.preflight(tmp_path, "item1", output)
    assert not output.exists()


@pytest.mark.parametrize("deny_at", [1, 2])
def test_worker_no_attempt_no_model_no_feedback(tmp_path, monkeypatch, deny_at):
    control, source, proposal, private = [tmp_path / p for p in ("control", "source", "proposal", "private")]
    for p in (control, source, proposal, private):
        p.mkdir()
    (private / "holdout.oracle.json").write_text("{}")
    spec = SimpleNamespace(max_attempts=1, base_head_sha="a" * 40, source_snapshot_sha256="ok")
    monkeypatch.setattr(worker, "load_registration", lambda *_: ({"context_path_patterns": []}, "a"*64))
    monkeypatch.setattr(worker, "parse_worker_task", lambda *_: spec)
    monkeypatch.setattr(worker, "_git_head", lambda *_: "a" * 40)
    monkeypatch.setattr(worker, "source_snapshot_sha256", lambda *_: "ok")
    monkeypatch.setattr(worker, "read_proposal_envelope",
                        lambda *_: {"proposal": {"patch": "safe"}, "task_pack_sha256": "a"*64})
    monkeypatch.setattr(worker, "load_hidden_oracle", lambda *_: {})
    monkeypatch.setattr(worker, "assert_hidden_oracle_external", lambda *_: None)
    monkeypatch.setattr(worker, "parse_patch_proposal", lambda *_: SimpleNamespace(patch="safe"))
    monkeypatch.setattr(worker, "inspect_patch", lambda *_: None)
    monkeypatch.setattr(worker, "NativeProposalClient", lambda *_a, **_k: object())
    calls = []
    def gate(*_a, **_kw):
        calls.append(1)
        if len(calls) == deny_at:
            raise lc.RequestStateError("REQUEST_CLOSED")
    monkeypatch.setattr(worker, "require_task_open", gate)
    monkeypatch.setattr(worker, "run_verified_worker",
                        lambda *_a, **_kw: pytest.fail("model called on closed request"))
    with pytest.raises(lc.RequestStateError, match="REQUEST_CLOSED"):
        worker.execute(control, source, proposal, private, "item1", 1, 101)
    assert len(calls) == deny_at
    public = private / "public"
    assert not (public / "attempt-proof.json").exists()
    assert not (public / "feedback.json").exists()
    assert not (public / "cost.json").exists()
