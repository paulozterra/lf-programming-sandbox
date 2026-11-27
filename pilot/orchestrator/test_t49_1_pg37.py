"""T49.1: CP3.7 must still publish H_REPORT before T9 closes the issue."""
import importlib
import json
import sys
from pathlib import Path
import pytest
from pilot.orchestrator.test_request_lifecycle_suspension import fake_api, content

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
stage = importlib.import_module("pg37_publish")


def setup(tmp_path, monkeypatch, state):
    folder = tmp_path / "pilot/runs/req-275"
    folder.mkdir(parents=True)
    (folder / "analysis.json").write_text("{}")
    lots = {"lots": [{"id": "SOL-001", "write_paths": ["src/main.py"]}]}
    (folder / "lots.json").write_text(json.dumps(lots))
    merge = "a" * 40
    monkeypatch.setattr(stage.chain_lots, "check_main", lambda: "b" * 40)
    monkeypatch.setattr(stage.chain_lots, "event_kind", lambda *_: "TRAIN")
    monkeypatch.setattr(stage.chain_lots, "first_parent_merges",
                        lambda *_a, **_kw: [(merge, {}, {"src/main.py"})])
    monkeypatch.setattr(stage.chain_lots, "plans",
                        lambda: [("req-275", lots, {}, {})])
    monkeypatch.setattr(stage.chain_lots, "completed_lots",
                        lambda *_: {"SOL-001": {"merge_sha": merge}})
    monkeypatch.setattr(stage.chain_lots, "pending_draft", lambda *_: False)
    monkeypatch.setattr(stage.chain_lots, "run", lambda *_: "")
    monkeypatch.setattr(stage.chain_lots, "api",
                        fake_api({}, issue_state=state))
    monkeypatch.setattr(stage, "render", lambda *_: "# H_REPORT real")
    monkeypatch.setattr(stage.chain_lots, "worktree",
                        lambda _head, _branch, fn: fn(tmp_path))
    return folder


@pytest.mark.parametrize("state", ["closed", "open"])
def test_cp37_h_report_before_close_and_no_pr_after_close(tmp_path, monkeypatch, state):
    folder = setup(tmp_path, monkeypatch, state)
    published = []
    def publish(_work, _branch, _request, paths, *_):
        published.append(list(paths))
        return {"pr": 1}
    result = stage.reconcile(42, root=tmp_path,
        evidence_generator=lambda *_args: {"lot_id": "SOL-001",
            "merge_sha": "a"*40, "complete": True}, publisher=publish)
    if state == "open":
        assert result[0]["status"] == "EVIDENCE_DRAFT_CREATED"
        assert (folder / "H_REPORT.md").read_text() == "# H_REPORT real"
        assert len(published) == 1
    else:
        assert result == [{"request": "req-275", "status": "REQUEST_CLOSED"}]
        assert published == [] and not (folder / "H_REPORT.md").exists()


def test_cp37_rechecks_before_publication(tmp_path, monkeypatch):
    folder = setup(tmp_path, monkeypatch, "open")
    states = iter(["open", "closed"])
    monkeypatch.setattr(stage.chain_lots, "api",
                        lambda path: content({}) if path.startswith("contents/") else {"number": 275, "state": next(states)})
    monkeypatch.setattr(stage.chain_lots, "worktree",
                        lambda *_: pytest.fail("worktree created after closure"))
    result = stage.reconcile(42, root=tmp_path,
        evidence_generator=lambda *_a: {"lot_id": "SOL-001",
             "merge_sha": "a"*40, "complete": True})
    assert result[0]["status"] == "REQUEST_CLOSED"
    assert not (folder / "H_REPORT.md").exists()


def test_cp37_api_failure_does_not_create_pr(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, "open")
    def down(_):
        raise OSError("unavailable")
    monkeypatch.setattr(stage.chain_lots, "api", down)
    monkeypatch.setattr(stage.chain_lots, "worktree",
                        lambda *_: pytest.fail("published despite API failure"))
    assert stage.reconcile(42, root=tmp_path) == [
        {"request": "req-275", "status": "REQUEST_STATE_UNRESOLVED"}]


def test_cp37_finalized_keeps_existing_evidence_untouched(tmp_path, monkeypatch):
    folder = setup(tmp_path, monkeypatch, "closed")
    (folder / "H_REPORT.md").write_text("# prior published report")
    registry = tmp_path / "pilot/registry/implemented.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"entries": [{
        "request": "req-275", "lot": "SOL-001",
        "status": "ATTESTED", "merge_sha": "a"*40}]}))
    monkeypatch.setattr(stage.chain_lots, "worktree",
                        lambda *_: pytest.fail("modified finalized evidence"))
    result = stage.reconcile(42, root=tmp_path)
    assert result == [{"request": "req-275", "status": "REQUEST_CLOSED"}]
    assert (folder / "H_REPORT.md").read_text() == "# prior published report"


def test_cp37_reopened_request_never_overwrites_existing_report(tmp_path, monkeypatch):
    folder = setup(tmp_path, monkeypatch, "open")
    (folder / "H_REPORT.md").write_text("# existing report")
    monkeypatch.setattr(stage.chain_lots, "worktree",
                        lambda *_: pytest.fail("overwrote historical evidence"))
    assert stage.reconcile(42, root=tmp_path) == [
        {"request": "req-275", "status": "REPORT_ALREADY_PRESENT"}]
    assert (folder / "H_REPORT.md").read_text() == "# existing report"
