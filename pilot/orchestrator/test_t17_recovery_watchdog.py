"""T17 offline recovery and verified generated-PR CI watchdog regressions."""
from __future__ import annotations

import json
from unittest.mock import patch

from pilot.orchestrator import chain_lots
from pilot import request_failure_notify as notify

SHA = "b" * 40
BRANCH = "lf/native-registration/t17fake-aaaaaaaaaaaa"


def test_sweep_replaces_only_old_failed_registration_draft():
    pulls = [{"number": 987, "headRefName": BRANCH, "headRefOid": SHA,
              "isDraft": True, "author": {"login": "github-actions[bot]"}}]
    rows = {"total_count": 1, "workflow_runs": [
        {"id": 9, "head_sha": SHA, "head_branch": BRANCH,
         "event": "workflow_dispatch", "status": "completed",
         "conclusion": "failure", "created_at": "2026-11-15T00:00:00Z"}]}
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps(pulls)
        if args[:2] == ("gh", "api"):
            return json.dumps([{"filename": "standards/changes/CHG-9998.json"},
                               {"filename": ".lf/worker-context/t17fake/protocolo.md"}])
        if args[:3] == ("gh", "pr", "close"):
            return ""
        raise AssertionError(args)

    with patch.object(chain_lots, "run", side_effect=fake_run), \
         patch.object(chain_lots, "api", return_value=rows):
        assert chain_lots.close_failed_old_registration_drafts("t17fake", "a" * 40) == [987]
    assert any(x[:3] == ("gh", "pr", "close") for x in commands)


def test_sweep_preserves_unrelated_failed_draft_and_pending_ci():
    rows = [{"number": 987, "headRefName": BRANCH, "headRefOid": SHA,
             "isDraft": True, "author": {"login": "github-actions[bot]"}}]
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps(rows)
        if args[:2] == ("gh", "api"):
            return json.dumps([{"filename": "standards/changes/CHG-9998.json"},
                               {"filename": "standards/CAMBIOS.md"}])
        raise AssertionError("No close expected")

    def ci(status, conclusion):
        return {"total_count": 1, "workflow_runs": [{
            "head_sha": SHA, "head_branch": BRANCH, "event": "workflow_dispatch",
            "status": status, "conclusion": conclusion,
            "created_at": "2026-11-15T00:00:00Z", "id": 1}]}

    with patch.object(chain_lots, "run", side_effect=fake_run), \
         patch.object(chain_lots, "api", return_value=ci("completed", "failure")):
        assert chain_lots.close_failed_old_registration_drafts("t17fake", "a" * 40) == []
    with patch.object(chain_lots, "run", side_effect=fake_run), \
         patch.object(chain_lots, "api", return_value=ci("in_progress", None)):
        assert chain_lots.close_failed_old_registration_drafts("t17fake", "a" * 40) == []
    assert not any(x[:3] == ("gh", "pr", "close") for x in commands)


def test_watchdog_comments_verified_generated_ci_without_label():
    run = {"id": 888, "path": ".github/workflows/ci.yml@refs/heads/main",
           "name": "ci", "event": "workflow_dispatch", "head_branch": BRANCH,
           "head_sha": SHA, "conclusion": "failure",
           "repository": {"full_name": notify.REPO},
           "head_repository": {"full_name": notify.REPO},
           "html_url": f"https://github.com/{notify.REPO}/actions/runs/888"}
    calls = []
    class FakeAPI:
        def api(self, method, path, body=None):
            calls.append((method, path, body))
            if "lf/native-registration/t17fake-" in path:
                return [{"number": 987, "head": {
                    "ref": BRANCH, "sha": SHA,
                    "repo": {"full_name": notify.REPO}},
                    "user": {"login": "github-actions[bot]"}}]
            if "lf/request/req-999" in path:
                return [{"number": 900, "head": {"ref": "lf/request/req-999"},
                         "user": {"login": "github-actions[bot]"}}]
            if path == "/issues/999":
                return {"number": 999, "state": "open",
                        "labels": [{"name": "lf-request"}]}
            if method == "POST" and path == "/issues/999/comments":
                return {}
            raise AssertionError((method, path))
        def pages(self, path):
            return []

    with patch.object(notify, "request_for_task", return_value={"req-999"}):
        assert notify.emit(FakeAPI(), run, []) == "RUTA_NOTIFIED"
    assert any(method == "POST" and path == "/issues/999/comments"
               and "PEDIDO_CI_FALLIDO" in payload["body"]
               for method, path, payload in calls)
    assert not any("/labels" in path for _, path, _ in calls)


def test_watchdog_rejects_unknown_generated_pr_author():
    run = {"path": ".github/workflows/ci.yml", "head_branch": BRANCH,
           "head_sha": SHA, "conclusion": "failure"}
    class FakeAPI:
        def api(self, method, path):
            return [{"number": 987, "head": {
                "ref": BRANCH, "sha": SHA, "repo": {"full_name": notify.REPO}},
                "user": {"login": "outsider"}}]
    assert notify.generated_ci_issue(FakeAPI(), run) is None
