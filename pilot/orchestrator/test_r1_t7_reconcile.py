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


def _setup_failed(tmp_path, monkeypatch, changed, failures=1):
    folder = tmp_path / "requests" / "req-901"
    folder.mkdir(parents=True)
    (folder / "request.md").write_text("Create request")
    (folder / "request_meta.json").write_text(json.dumps({"issue": 901}))
    monkeypatch.setattr(r1, "storage_path", lambda *_a, **_k: tmp_path / "requests")
    monkeypatch.setattr(r1, "request_state", lambda *a, **k: "OPEN")
    monkeypatch.setattr(r1, "original_request_merge", lambda *a: SHA)
    monkeypatch.setattr(r1.chain_lots, "api_list", lambda *a: [])
    rows = [{"id": 100 + i, "display_title": "T7 req-901", "head_sha": "b" * 40,
             "created_at": f"2026-11-25T0{i}:00:00Z",
             "status": "completed", "conclusion": "failure"} for i in range(failures)]
    monkeypatch.setattr(r1.chain_lots, "api",
                        lambda *_a: {"total_count": len(rows), "workflow_runs": list(rows)})
    monkeypatch.setattr(r1, "route_changed_since", lambda root, run: changed)
    return rows


def test_failed_t7_is_retried_after_a_route_fix(tmp_path, monkeypatch):
    _setup_failed(tmp_path, monkeypatch, changed=True)
    assert r1.select(root=tmp_path) == "requests/req-901/request.md"


def test_failed_t7_stays_stopped_without_route_change(tmp_path, monkeypatch):
    _setup_failed(tmp_path, monkeypatch, changed=False)
    assert r1.select(root=tmp_path) is None


def test_failed_t7_is_not_retried_forever(tmp_path, monkeypatch):
    _setup_failed(tmp_path, monkeypatch, changed=True, failures=r1.MAX_T7_FAILURES)
    assert r1.select(root=tmp_path) is None


def test_running_retry_is_not_duplicated(tmp_path, monkeypatch):
    rows = _setup_failed(tmp_path, monkeypatch, changed=True)
    rows.append({"id": 200, "display_title": "T7 req-901", "status": "in_progress",
                 "conclusion": None})
    assert r1.select(root=tmp_path) is None


def test_route_change_ignores_request_data(tmp_path):
    import subprocess
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True,
                              text=True).stdout.strip()
    git("init", "-q"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (tmp_path / "pilot/runs/req-1").mkdir(parents=True)
    (tmp_path / "pilot/x.py").write_text("a")
    git("add", "."); git("commit", "-qm", "base"); base = git("rev-parse", "HEAD")
    (tmp_path / "pilot/runs/req-1/analysis.json").write_text("{}")
    git("add", "."); git("commit", "-qm", "data")
    assert not r1.route_changed_since(tmp_path, {"head_sha": base})
    (tmp_path / "pilot/x.py").write_text("b")
    git("add", "."); git("commit", "-qm", "fix")
    assert r1.route_changed_since(tmp_path, {"head_sha": base})
