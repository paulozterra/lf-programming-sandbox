"""T50: CP3.7 isolates one blocked request from an otherwise healthy chain."""
import json
from pilot.orchestrator.test_request_lifecycle_suspension import fake_api

from pilot.orchestrator import pg37_publish as pub

cl = pub.chain_lots
from chain_contract import ChainBlocked


def test_bad_request_does_not_prevent_healthy_h_report(tmp_path, monkeypatch):
    requests = ("req-186", "req-286")
    lots = {"lots": [{"id": "SOL-001", "write_paths": ["src/example.py"]}]}
    for req in requests:
        folder = tmp_path / "pilot/runs" / req
        folder.mkdir(parents=True)
        (folder / "analysis.json").write_text("{}")
    sha = "a" * 40
    monkeypatch.setattr(cl, "check_main", lambda: "b" * 40)
    monkeypatch.setattr(cl, "event_kind", lambda *_: "TRAIN")
    monkeypatch.setattr(cl, "plans",
        lambda: [(req, lots, {}, {}) for req in requests])
    monkeypatch.setattr(cl, "api",
        fake_api({}))
    monkeypatch.setattr(cl, "first_parent_merges",
        lambda req, **_kw: [(sha, {}, {"src/example.py"})])
    def complete(_lots, _bindings, history):
        if complete.calls == 0:
            complete.calls += 1
            raise ChainBlocked("CP36_CHAIN_HISTORY_INCOMPLETE")
        return {"SOL-001": {"merge_sha": sha}}
    complete.calls = 0
    monkeypatch.setattr(cl, "completed_lots", complete)
    monkeypatch.setattr(cl, "pending_draft", lambda *_: False)
    monkeypatch.setattr(cl, "run", lambda *_: "")
    monkeypatch.setattr(cl, "worktree", lambda _head, _branch, fn: fn(tmp_path))
    monkeypatch.setattr(pub, "render", lambda *_: "# H_REPORT")
    results = pub.reconcile(100, root=tmp_path,
        evidence_generator=lambda *_: {"lot_id": "SOL-001",
            "merge_sha": sha, "complete": True},
        publisher=lambda *_: {"pr": 999})
    assert results[0] == {"request": "req-186", "status": "BLOCKED",
                          "code": "CP36_CHAIN_HISTORY_INCOMPLETE"}
    assert results[1]["request"] == "req-286"
    assert results[1]["status"] == "EVIDENCE_DRAFT_CREATED"
    assert (tmp_path / "pilot/runs/req-286/H_REPORT.md").is_file()
