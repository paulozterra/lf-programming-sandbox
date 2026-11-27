"""T51: targeted T9.1 recovery and existing-state idempotence (offline)."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t51_notifier", ROOT / "pilot/request_failure_notify.py")
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)

SOURCES = (
    "auto-integrate", "chain-lots", "native-verified-integration",
    "pg37-evidence", "request-finalize", "t7-request", "train-handoff",
)


def test_manual_fallbacks_target_exact_origin_and_never_increase_dispatches():
    for name in SOURCES:
        text = (ROOT / ".github/workflows" / (name + ".yml")).read_text()
        assert text.count("gh workflow run request-failure-watchdog.yml") == 1
        assert 'request-failure-watchdog.yml --repo "$GITHUB_REPOSITORY" --ref main -f source_run_id="$GITHUB_RUN_ID"' in text
    # Seven manual dispatch sites, exactly the same cardinality as baseline,
    # but each one invokes only one source rather than a 400-run sweep.


def test_watcher_sweep_only_on_cron_or_explicit_unspecified_manual_dispatch():
    text = (ROOT / ".github/workflows/request-failure-watchdog.yml").read_text()
    assert "cron: '*/10 * * * *'" in text
    assert "source_run_id:" in text
    assert '--run-id "$SOURCE_RUN_ID"' in text
    assert text.count("python3 -m pilot.workflow_entrypoint pilot/request_failure_notify.py --sweep") == 1
    assert 'if [ -n "$SOURCE_RUN_ID" ]; then' in text
    assert 'test "${{ github.event_name }}" = "schedule" -o "${{ github.event_name }}" = "workflow_dispatch"' in text


def test_successful_event_short_circuits_without_fetching_jobs_or_sweep():
    class Api:
        def api(self, *_):
            raise AssertionError("success must not perform GitHub API calls")
    assert notify.check_run(Api(), {"id": 42, "conclusion": "success"}) == "RUTA_SOURCE_NOT_FAILED"


def test_source_conclusion_idempotence_uses_existing_issue_comments():
    class Api:
        def __init__(self):
            self.comments = []
            self.writes = []
        def api(self, method, path, body=None):
            from pilot.orchestrator.lifecycle_test_support import content, CONTROL
            if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                return content({})
            if method == "GET" and path == "/issues/160":
                return {"number": 160, "state": "open", "labels": [{"name": "lf-request-blocked"}, {"name": "lf-request"}]}
            if method == "POST" and path.endswith("/comments"):
                self.writes.append(body)
                self.comments.append({"user": {"login": "github-actions[bot]"}, "body": body["body"]})
                return {}
            raise AssertionError((method, path))
        def pages(self, path):
            return self.comments
    run = {"id": 123, "name": "T9 issue request intake",
           "repository": {"full_name": notify.REPO},
           "display_title": "T9 intake req-160", "conclusion": "failure",
           "html_url": f"https://github.com/{notify.REPO}/actions/runs/123"}
    api = Api()
    assert notify.emit(api, run, []) == "RUTA_NOTIFIED"
    assert "LF_ROUTE_FAILURE_RUN:123:failure" in api.comments[0]["body"]
    assert notify.emit(api, run, []) == "RUTA_ALREADY_NOTIFIED"
    assert len(api.writes) == 1
    # Old markers remain valid after migrating the watchdog.
    legacy = Api()
    legacy.comments = [{"user": {"login": "github-actions[bot]"},
                        "body": "<!-- LF_ROUTE_FAILURE_RUN:123 -->"}]
    assert notify.emit(legacy, run, []) == "RUTA_ALREADY_NOTIFIED"
    assert not legacy.writes


def test_missing_workflow_run_event_is_caught_by_targeted_manual_id(monkeypatch, capsys):
    """A GITHUB_TOKEN source can be delivered without a workflow_run event."""
    requested = []
    class Api:
        def __init__(self, token):
            assert token == "token"
        def api(self, method, path, body=None):
            from pilot.orchestrator.lifecycle_test_support import content, CONTROL
            if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                return content({})
            requested.append((method, path))
            assert path == "/actions/runs/123"
            return {"id": 123, "conclusion": "success"}
    monkeypatch.setattr(notify, "Github", Api)
    monkeypatch.setenv("GITHUB_REPOSITORY", notify.REPO)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(sys, "argv", ["notifier", "--run-id", "123"])
    notify.main()
    assert requested == [("GET", "/actions/runs/123")]
    assert "RUTA_SOURCE_NOT_FAILED" in capsys.readouterr().out


def test_missing_event_recovers_failure_via_existing_sweep(monkeypatch, capsys):
    """If both events disappear, the cron still sees recent failures."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    checked = []
    source = {"id": 456, "conclusion": "failure", "created_at": now,
              "name": "T9 issue request intake", "path": ".github/workflows/request-intake.yml"}
    class Api:
        def __init__(self, token):
            assert token == "token"
        def api(self, method, path, body=None):
            from pilot.orchestrator.lifecycle_test_support import content, CONTROL
            if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                return content({})
            assert path.startswith("/actions/runs?per_page=100&page=")
            return {"workflow_runs": [source]}
    monkeypatch.setattr(notify, "Github", Api)
    monkeypatch.setattr(notify, "audit_undispatched_requests", lambda *_: [])
    monkeypatch.setattr(notify, "check_run", lambda _api, run: checked.append(run["id"]) or "RUTA_NOTIFIED")
    monkeypatch.setenv("GITHUB_REPOSITORY", notify.REPO)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr(sys, "argv", ["notifier", "--sweep"])
    notify.main()
    assert checked == [456]
