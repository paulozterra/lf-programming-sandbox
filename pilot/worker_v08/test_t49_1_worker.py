"""T49.1: unique trusted task ownership and fail-closed Worker boundaries."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pilot.orchestrator.test_request_lifecycle_suspension import fake_api
from pilot.orchestrator import request_lifecycle as lc
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pilot/worker_v08'))
import native_run as worker


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
        if fail:
            raise OSError("unavailable")
        return fake_api({}, issue_state=state)(path)
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


def test_trusted_recheck_blocks_closed_without_touching_worker(tmp_path, monkeypatch, capsys):
    import request_lifecycle_gate as gate
    seed(tmp_path)
    monkeypatch.setattr(gate, "require_task_open",
                        lambda task, *, root: lc.require_task_open(
                            task, root=root, api=api("closed")))
    monkeypatch.setattr(sys, "argv",
                        ["lifecycle-gate", "--control", str(tmp_path), "--task", "item1"])
    assert gate.main() == 1
    assert "REQUEST_CLOSED" in capsys.readouterr().err
    assert not list(tmp_path.rglob("attempt-proof.json"))
    assert not list(tmp_path.rglob("feedback.json"))


def test_trusted_recheck_unresolved_blocks_without_attempt(tmp_path, monkeypatch, capsys):
    import request_lifecycle_gate as gate
    seed(tmp_path)
    monkeypatch.setattr(gate, "require_task_open",
                        lambda task, *, root: lc.require_task_open(
                            task, root=root, api=api("open", fail=True)))
    monkeypatch.setattr(sys, "argv",
                        ["lifecycle-gate", "--control", str(tmp_path), "--task", "item1"])
    assert gate.main() == 1
    assert "REQUEST_STATE_UNRESOLVED" in capsys.readouterr().err
    assert not list(tmp_path.rglob("attempt-proof.json"))


def test_trusted_recheck_open_is_authorized(tmp_path, monkeypatch, capsys):
    import request_lifecycle_gate as gate
    seed(tmp_path)
    monkeypatch.setattr(gate, "require_task_open",
                        lambda task, *, root: lc.require_task_open(
                            task, root=root, api=api("open")))
    monkeypatch.setattr(sys, "argv",
                        ["lifecycle-gate", "--control", str(tmp_path), "--task", "item1"])
    assert gate.main() == 0
    assert "REQUEST_OPEN_VERIFIED" in capsys.readouterr().out


def test_execute_has_no_state_reader_or_token_calls():
    import ast
    source = (ROOT / "pilot/worker_v08/native_run.py").read_text()
    module = ast.parse(source)
    execute = next(x for x in module.body
                   if isinstance(x, ast.FunctionDef) and x.name == "execute")
    calls = [x.func for x in ast.walk(execute) if isinstance(x, ast.Call)]
    names = {x.id for x in calls if isinstance(x, ast.Name)}
    assert "require_task_open" not in names
    assert "github_issue_api" not in names
    assert "run_verified_worker" in names  # still performs real acceptance


def test_gate_not_worker_owns_early_abort(tmp_path, monkeypatch):
    import request_lifecycle_gate as gate
    seed(tmp_path)
    invoked = []
    monkeypatch.setattr(gate, "require_task_open",
                        lambda *_a, **_kw: (_ for _ in ()).throw(
                            lc.RequestStateError("REQUEST_CLOSED")))
    monkeypatch.setattr(worker, "execute",
                        lambda *_a, **_kw: invoked.append("model"))
    with pytest.raises(lc.RequestStateError, match="REQUEST_CLOSED"):
        gate.recheck(tmp_path, "item1", checker=gate.require_task_open)
    assert invoked == []
    assert not list(tmp_path.rglob("attempt-proof.json"))
    assert not list(tmp_path.rglob("feedback.json"))
