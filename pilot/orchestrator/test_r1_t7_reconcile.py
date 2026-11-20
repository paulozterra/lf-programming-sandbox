"""R1: a T7 pending run displaced by concurrency is recoverable from main."""
import json
from pilot.orchestrator import t7_pending_reconcile as r1

SHA = "a" * 40


def test_t7_request_without_delivered_run_is_selected(tmp_path, monkeypatch):
    root = tmp_path
    folder = root / "requests" / "req-901"
    folder.mkdir(parents=True)
    (folder / "request.md").write_text("Create request")
    (folder / "request_meta.json").write_text(json.dumps({"issue": 901}))
    monkeypatch.setattr(r1, "storage_path", lambda *_a, **_k: root / "requests")
    monkeypatch.setattr(r1, "request_state", lambda *a, **k: "OPEN")
    monkeypatch.setattr(r1, "original_request_merge", lambda *a: SHA)
    monkeypatch.setattr(r1.chain_lots, "api_list", lambda *a: [])
    rows = []
    monkeypatch.setattr(r1.chain_lots, "api",
                        lambda *_a: {"total_count": len(rows), "workflow_runs": list(rows)})
    path = "requests/req-901/request.md"
    assert r1.select(root=root) == path
    rows.append({"id": 100, "display_title": "T7 req-901",
                 "status": "completed", "conclusion": "cancelled"})
    assert r1.select(root=root) == path
    rows[0].update(status="queued", conclusion=None)
    assert r1.select(root=root) is None
    rows[0].update(status="completed", conclusion="success")
    assert r1.select(root=root) is None


def test_t7_completed_analysis_is_not_regenerated(tmp_path, monkeypatch):
    folder = tmp_path / "requests" / "req-901"
    folder.mkdir(parents=True)
    (folder / "request.md").write_text("A")
    (folder / "analysis.json").write_text("{}")
    monkeypatch.setattr(r1, "storage_path", lambda *a, **k: tmp_path / "requests")
    monkeypatch.setattr(r1.chain_lots, "api", lambda *a: {
        "workflow_runs": [], "total_count": 0})
    monkeypatch.setattr(r1.chain_lots, "api_list", lambda *a: [])
    assert r1.select(root=tmp_path) is None
