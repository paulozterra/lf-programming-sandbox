"""T49.1 CP3.5: direct and recovered native PASS cannot integrate a closed request."""
import json
from pathlib import Path
import sys

import pytest
from pilot.orchestrator.lifecycle_test_support import fake_api
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pilot/orchestrator'))
import native_verified_integration as cp35


def setup(tmp_path):
    reg = tmp_path / "pilot/worker_v08/native_tasks"
    reg.mkdir(parents=True)
    (reg / "item1.json").write_text(json.dumps({"task_spec": {}}))
    folder = tmp_path / "pilot/runs/req-275"
    folder.mkdir(parents=True)
    (folder / "chain_plan.json").write_text(json.dumps({
        "request_id": "req-275", "bindings": [
            {"lot_id": "SOL-001", "task_name": "item1",
             "template_path": "pilot/runs/req-275/templates/item1.task.json"}]}))
    return folder


@pytest.mark.parametrize("state,valid", [
    ("closed", False), ("closed", True), ("open", False),
])
def test_closed_rejects_before_branch_chg_or_pr(tmp_path, monkeypatch, state, valid):
    folder = setup(tmp_path)
    if valid:
        (folder / "lots.json").write_text(json.dumps({"lots": [{"id": "SOL-001"}]}))
        (folder / "H_REPORT.md").write_text("merged report")
        p = tmp_path / "pilot/registry/implemented.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"entries": [{"request": "req-275",
            "lot": "SOL-001", "merge_sha": "a"*40, "status": "ATTESTED"}]}))
    calls = []
    def gh(path):
        calls.append(("api", path))
        return json.dumps(fake_api({}, issue_state=state)(path.split(f"repos/{cp35.REPOSITORY}/", 1)[1])).encode()
    monkeypatch.setattr(cp35, "gh_api", gh)
    monkeypatch.setattr(cp35, "command",
                        lambda *_a, **_kw: pytest.fail("branch/CHG/PR side effect"))
    status = {"task_id": "item1"}
    proof = {"task_id": "item1"}
    if state == "open":
        # A genuinely OPEN request passes the lifecycle gate; next validation
        # may legitimately reject its dummy registration, never a lifecycle error.
        cp35._require_live_task(tmp_path, "item1")
        return
    with pytest.raises(cp35.IntegrationBlocked, match="CP35_REQUEST_CLOSED"):
        cp35.publish(tmp_path, 12, b"patch", status, proof)
    assert all(v[0] == "api" for v in calls)
    assert not (tmp_path / "standards/changes").exists()


def test_cp35_unresolved_and_multiple_owners_deny(tmp_path, monkeypatch):
    setup(tmp_path)
    monkeypatch.setattr(cp35, "gh_api", lambda *_: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(cp35.IntegrationBlocked, match="CP35_REQUEST_STATE_UNRESOLVED"):
        cp35._require_live_task(tmp_path, "item1")
    other = tmp_path / "pilot/runs/req-276"
    other.mkdir()
    (other / "chain_plan.json").write_text(json.dumps({
        "request_id": "req-276", "bindings": [{
            "task_name": "item1", "lot_id": "SOL-002",
            "template_path": "pilot/runs/req-276/templates/item1.task.json"}]}))
    with pytest.raises(cp35.IntegrationBlocked, match="CP35_REQUEST_STATE_UNRESOLVED"):
        cp35._require_live_task(tmp_path, "item1")


def test_cp35_t46_source_run_replay_uses_same_gate(tmp_path, monkeypatch, capsys):
    setup(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", cp35.REPOSITORY)
    from pilot.orchestrator.lifecycle_test_support import fake_api
    monkeypatch.setattr(cp35, "gh_api", lambda path: json.dumps(
        fake_api({}, issue_state="closed", root=tmp_path)(path.removeprefix("repos/" + cp35.REPOSITORY + "/"))).encode())
    monkeypatch.setattr(cp35, "get_verified_patch",
                        lambda _id: (b"patch", {"task_id": "item1"}, {"task_id": "item1"}))
    monkeypatch.setattr(cp35, "command",
                        lambda *_a, **_k: pytest.fail("replay published an effect"))
    monkeypatch.setattr("sys.argv", ["cp35", "--root", str(tmp_path), "--run-id", "123"])
    assert cp35.main() == 1
    assert "CP35_REQUEST_CLOSED" in capsys.readouterr().err
