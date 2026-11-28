"""R1: recovery from persisted issue and merged-plan state, no event payload."""
from pathlib import Path

from pilot.orchestrator import issue_intake
from pilot.orchestrator import pg37_publish

HEAD = "a" * 40
REPO = "paulozterra/lf-programming-sandbox"


def test_intake_sweep_rebuilds_missing_request_and_dispatches_exact_ci(monkeypatch):
    issue = {"number": 901, "state": "open", "title": "Pedido: prueba", "body": "### Pedido\n\nPrueba", "labels": [{"name": "lf-request"}]}
    state = {"created": False, "dispatched": []}

    class API:
        def issue(self, number):
            assert number == 901
            return issue

        def call(self, method, path, payload=None):
            from pilot.orchestrator.lifecycle_test_support import content, CONTROL, main_response
            if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                return content({})
            if method == "GET" and path.startswith("/issues?"):
                return [issue]
            if method == "GET" and path == "/issues/901/events?per_page=100":
                return []
            if method == "GET" and path.startswith("/pulls?"):
                assert state["created"]
                return [{"number": 321, "head": {
                    "ref": "lf/request/req-901", "sha": HEAD}}]
            if method == "POST" and path == "/actions/workflows/ci.yml/dispatches":
                state["dispatched"].append(payload)
                return {}
            if method == "GET":
                return main_response(path.lstrip("/"))
            raise AssertionError((method, path, payload))

    def intake(_api, event):
        assert event["issue"]["number"] == 901
        if state["created"]:
            return "PEDIDO_YA_REGISTRADO"
        state["created"] = True
        return "https://github.com/paulozterra/lf-programming-sandbox/pull/321"

    monkeypatch.setattr(issue_intake, "intake", intake)
    api = API()
    first = issue_intake.sweep(api)
    second = issue_intake.sweep(api)
    assert first == [{"issue": 901, "status": "R1_INTAKE_PR_CREATED"}]
    assert second == [{"issue": 901, "status": "PEDIDO_YA_REGISTRADO"}]
    assert state["dispatched"] == [{
        "ref": "lf/request/req-901",
        "inputs": {"pr_number": "321", "pr_sha": HEAD}}]


def test_cp37_sweep_uses_completed_train_and_missing_report(tmp_path, monkeypatch):
    from pilot.config import project_config
    folder = tmp_path / "requests" / "req-901"
    folder.mkdir(parents=True)
    plan = ("req-901", {"lots": [{"id": "L1"}]}, {}, {})
    monkeypatch.setattr(pg37_publish.chain_lots, "check_main", lambda: HEAD)
    monkeypatch.setattr(pg37_publish.chain_lots, "plans", lambda: [plan])
    monkeypatch.setattr(pg37_publish, "request_state", lambda *a, **kw: "OPEN")
    monkeypatch.setattr(project_config, "storage_path",
                        lambda _key, *, root: tmp_path / "requests")
    monkeypatch.setattr(pg37_publish, "storage_path", lambda _key, *, root: tmp_path / "requests")
    monkeypatch.setattr(pg37_publish.chain_lots, "pending_draft", lambda *a: False)
    monkeypatch.setattr(pg37_publish.chain_lots, "first_parent_merges",
                        lambda *a, **kw: [(HEAD, {}, [])])
    monkeypatch.setattr(pg37_publish.chain_lots, "completed_lots",
                        lambda *a: {"L1": {"merge_sha": HEAD}})
    row = {"id": 12345, "status": "completed", "conclusion": "success",
           "path": ".github/workflows/sandbox-train.yml",
           "repository": {"full_name": REPO}}
    monkeypatch.setattr(pg37_publish.chain_lots, "api",
                        lambda _path: {"workflow_runs": [row], "total_count": 1})
    monkeypatch.setattr(pg37_publish.chain_lots, "event_kind",
                        lambda run, head: "TRAIN")
    calls = []
    monkeypatch.setattr(pg37_publish, "reconcile",
                        lambda run_id, *, root: calls.append(run_id) or [
                            {"status": "EVIDENCE_DRAFT_CREATED"}])
    result = pg37_publish.sweep(root=tmp_path)
    assert result == [{"status": "EVIDENCE_DRAFT_CREATED"}]
    assert calls == [12345]
    import json
    from pilot.orchestrator.lifecycle_test_support import evidence_fixture
    from pilot.orchestrator.pg37_evidence import render
    record = evidence_fixture("req-901", "L1", HEAD)
    (folder / "evidence").mkdir()
    (folder / "evidence" / ("L1-"+HEAD[:12]+".json")).write_text(json.dumps(record))
    (folder / "H_REPORT.md").write_text(render("req-901", [record]))
    assert pg37_publish.sweep(root=tmp_path) == [
        {"status": "R1_CP37_NO_MISSING_EVIDENCE"}]
    assert calls == [12345]
