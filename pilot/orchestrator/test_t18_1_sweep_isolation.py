"""T18.1: historical plans skipped; request failures are isolated; global alerts."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot import request_failure_notify as notifier
from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL

HEAD = "a" * 40


@pytest.fixture(autouse=True)
def isolate_retries_in_historical_sweep_tests():
    # The T18.1 tests exercise request-level recovery, while T20 tests own
    # real/authenticated GitHub CI retry behaviour in a separate suite.
    with patch.object(chain_lots, "retry_failed_bot_prs", return_value=[]), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
          patch.object(chain_lots, "replay_native_integration", return_value=[]), \
         patch.multiple(chain_lots,
                        recover_pending_worker=lambda *a, **kw: [],
                        recover_unstarted_integration=lambda *a, **kw: [],
                        sync_implemented_registry=lambda *a, **kw: {"status": "REGISTRY_CURRENT"}):
        yield


def test_route_requires_valid_issue_metadata_and_original_bot_commit(tmp_path):
    path = tmp_path / "pilot/runs/req-901/request_meta.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"issue":901,"author":"origin"}')
    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "run", return_value=
                      "41898282+github-actions[bot]@users.noreply.github.com") as run:
        assert chain_lots.route_request_metadata("req-901")
        run.assert_called_once()
        assert not chain_lots.route_request_metadata("f5-login")
        assert not chain_lots.route_request_metadata("p4-prioridad")
    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "run", return_value="person@example.invalid"):
        assert not chain_lots.route_request_metadata("req-901")
    path.write_text('{"issue":902,"author":"origin"}')
    with patch.object(chain_lots, "ROOT", tmp_path):
        assert not chain_lots.route_request_metadata("req-901")


def test_historical_names_skip_and_real_missing_pack_repaired_in_same_sweep():
    plans = [
        ("f5-login", {"lots": []}, {"stage": "BLOCKED"},
         {"L1": {"task_name": "f5data"}}),
        ("p4-prioridad", {"lots": []}, {"stage": "BLOCKED"},
         {"L2": {"task_name": "p4data"}}),
        ("random-historico_01", {"lots": []}, {"stage": "BLOCKED"},
         {"L3": {"task_name": "oldtask"}}),
        ("req-901", {"lots": []}, {"stage": "BLOCKED"},
         {"L4": {"task_name": "registeredtask"}}),
    ]
    prepared = []
    def publication(request, task, head):
        prepared.append((request, task, head))
        return {"status": "TASK_PACK_REPAIR_DRAFT", "task": task,
                "draft_pr": "https://example.invalid/new"}
    with patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "plans", return_value=plans), \
         patch.object(chain_lots, "route_request_metadata",
                      side_effect=lambda r: r == "req-901"), \
         patch.object(chain_lots, "publish_missing_registered_pack",
                      side_effect=publication), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "api", side_effect=fake_api({})), \
         patch.object(chain_lots, "sweep_request_enabled", return_value=False):
        rows = chain_lots.process(sweep=True, base_sha=HEAD)
    assert prepared == [("req-901", "registeredtask", HEAD)]
    assert {row["request"] for row in rows if
            row["status"] == "SKIPPED_NOT_ROUTE_REQUEST"} == {
        "f5-login", "p4-prioridad", "random-historico_01"}
    assert sum(row["status"] == "TASK_PACK_REPAIR_DRAFT" for row in rows) == 1


@pytest.mark.parametrize("suspended", [False, True])
def test_one_local_pack_error_does_not_stop_healthy_request(suspended):
    plans = [(f"req-{n}", {"lots": []}, {"stage": "BLOCKED"},
              {"L1": {"task_name": f"task{n}"}}) for n in (901, 902)]
    called = []
    def repair(request, task, head):
        called.append(request)
        if request == "req-901":
            raise chain_lots.ChainBlocked("TASK_PACK_HASH_MISMATCH")
        return {"status": "TASK_PACK_REPAIR_DRAFT"}
    with patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "plans", return_value=plans), \
         patch.object(chain_lots, "route_request_metadata", return_value=True), \
         patch.object(chain_lots, "publish_missing_registered_pack", side_effect=repair), \
         patch.object(chain_lots, "per_request_block",
                      side_effect=lambda r, phase, exc:
                      {"request": r, "status": "BLOCKED", "reason": str(exc)}), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "api", side_effect=fake_api({"req-901": {"state": "SUSPENDING", "authorization_pr": 77}} if suspended else {})), \
         patch.object(chain_lots, "sweep_request_enabled", return_value=False):
        rows = chain_lots.process(sweep=True, base_sha=HEAD)
    if suspended:
        assert called == ["req-902"]
        assert any(row["request"] == "req-901" and row["status"] == "REQUEST_SUSPENDED" for row in rows)
    else:
        assert called == ["req-901", "req-902"]
        assert any(row["request"] == "req-901" and row["status"] == "BLOCKED"
                   for row in rows)
    assert any(row["request"] == "req-902" and row["status"] == "TASK_PACK_REPAIR_DRAFT"
               for row in rows)


def test_one_chain_error_does_not_skip_next_healthy_chain():
    plans = [(f"req-{n}", {}, {"stage": "LOTS_PLANNED"}, {})
             for n in (901, 902)]
    called = []
    def one(request, *_args):
        called.append(request)
        if request == "req-901":
            raise ValueError("LOCAL_PLAN_ERROR")
        return [{"request": request, "status": "CHAIN_OK"}]
    with patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "plans", return_value=plans), \
         patch.object(chain_lots, "route_request_metadata", return_value=True), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "process_one_plan", side_effect=one), \
         patch.object(chain_lots, "per_request_block",
                      side_effect=lambda r, phase, exc:
                      {"request": r, "status": "BLOCKED", "reason": str(exc)}):
        rows = chain_lots.process(sweep=True, base_sha=HEAD)
    assert called == ["req-901", "req-902"]
    assert any(r["request"] == "req-901" and r["status"] == "BLOCKED" for r in rows)
    assert any(r["request"] == "req-902" and r["status"] == "CHAIN_OK" for r in rows)


def test_global_main_integrity_error_is_not_contained():
    with pytest.raises(Exception, match="CHAIN_SWEEP_BASE_INVALID"):
        with patch.object(chain_lots, "check_main", return_value=HEAD):
            chain_lots.process(sweep=True, base_sha="b" * 40)
    with pytest.raises(Exception, match="BASE_NO_VERDE"):
        with patch.object(chain_lots, "check_main", return_value=HEAD), \
             patch.object(chain_lots, "main_ci_decision",
                          side_effect=chain_lots.ChainBlocked("BASE_NO_VERDE")):
            chain_lots.process(sweep=True, base_sha=HEAD)


def global_run():
    return {"id": 12345, "path": ".github/workflows/chain-lots.yml",
            "event": "workflow_dispatch", "display_title": "CP3.6 12345",
            "head_branch": "main", "conclusion": "failure",
            "html_url": "https://github.com/" + notifier.REPO +
                        "/actions/runs/12345"}


class FakeAPI:
    def __init__(self, linked=True, suspended=False):
        self.linked = linked
        self.reader = fake_api({"req-901": {"state": "SUSPENDING", "authorization_pr": 77}} if suspended else {})
        self.calls = []
        self.comments = []
        self.alert_created = False

    def pages(self, path):
        if path == "/issues?state=open&labels=lf-request":
            return ([{"number": 901, "state": "open", "labels": [{"name": "lf-request"}]}]
                    if self.linked else [])
        if path == "/issues?state=open":
            return [] if not self.alert_created else [
                {"number": 777, "title": "[LF ROUTE ALERT] CP3.6 global sweep"}]
        if path in ("/issues/901/comments", "/issues/777/comments"):
            return self.comments
        raise AssertionError(path)

    def api(self, method, path, data=None):
        self.calls.append((method, path, data))
        if method == "GET" and path == "/contents/pilot/runs/req-901/request_meta.json?ref=main":
            return {"content": base64.b64encode(b'{"issue":901}').decode()}
        if method == "POST" and path == "/issues":
            self.alert_created = True
            return {"number": 777}
        if method == "POST" and path in ("/issues/901/comments", "/issues/777/comments"):
            self.comments.append({"body": data["body"]})
            return {}
        if method == "GET":
            return self.reader(path.removeprefix("/"))
        raise AssertionError((method, path))


def test_global_cp36_failure_reports_open_request_without_new_labels():
    api = FakeAPI(linked=True)
    assert notifier.notify_global_cp36_sweep(api, global_run()) == "RUTA_GLOBAL_CP36_NOTIFIED"
    assert notifier.notify_global_cp36_sweep(api, global_run()) == "RUTA_GLOBAL_CP36_NOTIFIED"
    posts = [c for c in api.calls if c[0] == "POST"]
    assert len(posts) == 1 and posts[0][1] == "/issues/901/comments"
    assert not any("labels" in str(c[1:]) for c in posts)


def test_global_cp36_failure_without_requests_creates_single_alert_issue():
    api = FakeAPI(linked=False)
    assert notifier.notify_global_cp36_sweep(api, global_run()) == "RUTA_GLOBAL_CP36_NOTIFIED"
    assert notifier.notify_global_cp36_sweep(api, global_run()) == "RUTA_GLOBAL_CP36_NOTIFIED"
    posts = [c for c in api.calls if c[0] == "POST"]
    assert [c[1] for c in posts] == ["/issues", "/issues/777/comments"]
    assert "labels" not in posts[0][2]


def test_unrelated_failed_train_not_reported_as_global_cp36():
    api = FakeAPI()
    other = dict(global_run(), display_title="CP3.6 PR 205")
    assert notifier.notify_global_cp36_sweep(api, other) == "RUTA_NOT_GLOBAL_CP36_SWEEP"
    assert api.calls == []


def test_global_cp36_suspended_request_uses_deduplicated_route_alert():
    api = FakeAPI(linked=True, suspended=True)
    for _ in range(2):
        assert notifier.notify_global_cp36_sweep(api, global_run()) == "RUTA_GLOBAL_CP36_NOTIFIED"
    posts = [c for c in api.calls if c[0] == "POST"]
    assert [c[1] for c in posts] == ["/issues", "/issues/777/comments"]
    assert not any("labels" in str(c[1:]) for c in posts)
