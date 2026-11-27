"""T49.1 audit: only CLOSED_FINALIZED is eligible, including forced requests."""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

from pilot.orchestrator.lifecycle_test_support import content, CONTROL

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
rt = importlib.import_module("request_trigger")


def proof(root, complete):
    folder = root / "pilot/runs/req-275"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lots.json").write_text(json.dumps({"lots": [{"id": "SOL-001"}]}))
    if complete:
        (folder / "H_REPORT.md").write_text("# merged report")
        ledger = root / "pilot/registry/implemented.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"entries": [{"request": "req-275",
             "lot": "SOL-001", "merge_sha": "a"*40, "status": "ATTESTED"}]}))


@pytest.mark.parametrize("state,complete,eligible", [
    ("open", False, False), ("closed", False, False), ("closed", True, True),
])
def test_audit_state_matrix(tmp_path, state, complete, eligible):
    proof(tmp_path, complete)
    assert rt._finalized_request("req-275", "o/r", tmp_path,
          api=lambda path: content({}) if path == f"contents/{CONTROL}?ref=main"
          else {"number": 275, "state": state}) is eligible


def test_audit_unreadable_state_blocks(tmp_path):
    proof(tmp_path, True)
    with pytest.raises(ValueError, match="REQUEST_STATE_UNRESOLVED"):
        rt._finalized_request("req-275", "o/r", tmp_path,
            api=lambda _: (_ for _ in ()).throw(OSError("offline")))


@pytest.mark.parametrize("state,complete,expected", [
    ("open", True, 0), ("closed", False, 0),
    ("closed", True, 1),
])
def test_forced_audit_creates_only_finalized_issue(tmp_path, monkeypatch,
                                                   state, complete, expected):
    proof(tmp_path, complete)
    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "load", lambda *_: {"audit": {
        "enabled": True, "trigger": "REQUEST_CLOSED",
        "sample_n": 1, "mode": "SHADOW", "auditor": "CLAUDE_ROUTINE",
        "skill": {"repository": "o/r", "commit": "a"*40, "path": "skills/a"}}})
    monkeypatch.setitem(sys.modules, "chain_lots", SimpleNamespace(plans=lambda: []))
    monkeypatch.setattr(rt.bi, "completed_from_history", lambda *_: (
        {"lots": [{"id": "SOL-001"}]}, {"SOL-001": {"merge_sha": "a"*40}}))
    monkeypatch.setattr(rt.bi, "build", lambda *_: {
        "base_commit": "a"*40, "evidence_destination": "pilot/runs/req-275/audit"})
    (tmp_path / "pilot/runs/req-275/analysis.json").write_text("{}")
    created = []
    def gh(*args, data=None):
        endpoint = args[0]
        if endpoint.endswith(f'/contents/{CONTROL}?ref=main'):
            return json.dumps(content({}))
        if endpoint.endswith("/issues/275"):
            return json.dumps({"number": 275, "state": state})
        if "issues?labels=" in endpoint:
            return json.dumps([])
        if endpoint.endswith("/issues") and data is not None:
            created.append(data)
            return json.dumps({"number": 999})
        pytest.fail("unexpected GitHub side effect " + endpoint)
    monkeypatch.setattr(rt, "gh", gh)
    monkeypatch.setattr(sys, "argv", ["request_trigger", "--project", "lf",
                                    "--repository", "o/r", "--request", "req-275"])
    assert rt.main() == 0
    assert len(created) == expected


def test_audit_second_live_check_prevents_issue(tmp_path, monkeypatch):
    proof(tmp_path, True)
    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "load", lambda *_: {"audit": {
        "enabled": True, "trigger": "REQUEST_CLOSED", "sample_n": 1}})
    monkeypatch.setitem(sys.modules, "chain_lots", SimpleNamespace(plans=lambda: []))
    monkeypatch.setattr(rt.bi, "completed_from_history", lambda *_: (
        {"lots": [{"id": "SOL-001"}]}, {"SOL-001": {"merge_sha": "a"*40}}))
    monkeypatch.setattr(rt.bi, "build", lambda *_: {
        "base_commit": "a"*40, "evidence_destination": "pilot/runs/req-275/audit"})
    (tmp_path / "pilot/runs/req-275/analysis.json").write_text("{}")
    states = iter(["closed", "open"])
    def gh(endpoint, data=None):
        if endpoint.endswith(f'/contents/{CONTROL}?ref=main'):
            return json.dumps(content({}))
        if endpoint.endswith("/issues/275"):
            return json.dumps({"number": 275, "state": next(states)})
        if "issues?labels=" in endpoint:
            return "[]"
        pytest.fail("created audit after issue reopened")
    monkeypatch.setattr(rt, "gh", gh)
    monkeypatch.setattr(sys, "argv", ["request_trigger", "--project", "lf",
                       "--repository", "o/r", "--request", "req-275"])
    assert rt.main() == 0
