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


def test_more_recent_action_required_does_not_retire_successful_registration():
    """Same SHA: executed SUCCESS followed by unexecuted action_required."""
    pulls = [{"number": 987, "headRefName": BRANCH, "headRefOid": SHA,
              "isDraft": True, "author": {"login": "github-actions[bot]"}}]
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps(pulls)
        if args[:2] == ("gh", "api"):
            raise AssertionError("No file inspection on green CI")
        if args[:3] == ("gh", "pr", "close"):
            raise AssertionError("Successful registration must remain open")
        raise AssertionError(args)

    rows = {"total_count": 2, "workflow_runs": [
        {"id": 43729617525, "head_sha": SHA, "head_branch": BRANCH,
         "event": "pull_request", "status": "completed",
         "conclusion": "action_required", "created_at": "2026-11-15T10:00:01Z"},
        {"id": 43729614995, "head_sha": SHA, "head_branch": BRANCH,
         "event": "workflow_dispatch", "status": "completed",
         "conclusion": "success", "created_at": "2026-11-15T10:00:00Z"}]}
    with patch.object(chain_lots, "run", side_effect=fake_run), \
         patch.object(chain_lots, "api", return_value=rows):
        assert chain_lots.close_failed_old_registration_drafts("t17fake", "a" * 40) == []
    assert not any(x[:3] == ("gh", "pr", "close") for x in calls)


def test_watchdog_rejects_unknown_generated_pr_author():
    run = {"path": ".github/workflows/ci.yml", "head_branch": BRANCH,
           "head_sha": SHA, "conclusion": "failure"}
    class FakeAPI:
        def api(self, method, path):
            return [{"number": 987, "head": {
                "ref": BRANCH, "sha": SHA, "repo": {"full_name": notify.REPO}},
                "user": {"login": "outsider"}}]
    assert notify.generated_ci_issue(FakeAPI(), run) is None


def test_one_sweep_closes_legacy_red_registration_and_regenerates_next_chg(tmp_path):
    """End-to-end CP3.6 orchestration, with mocked GitHub and native staging.

    Closing the obsolete PR must make the pending-draft gate false *within
    the same process()* call. The next CHG is selected from the existing
    standards ledger, never recycled from the discarded PR.
    """
    from pilot.orchestrator import native_verified_integration as integration

    head = "a" * 40
    branch = "lf/native-registration/t17fake-" + head[:12]
    sha = SHA
    pr_open = {"value": True}
    commands = []
    lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": False, "handoff_allowed": False,
            "worker_invoked": False,
            "lots": [{"id": "SOL-001", "area": "CONTRATO", "depends_on": []}]}
    bindings = {"SOL-001": {"task_name": "t17fake", "lot_id": "SOL-001",
                            "template_path": "t17template.json",
                            "holdout_metadata_path": "t17holdout.json"}}
    standards = tmp_path / "standards/changes"
    standards.mkdir(parents=True)
    (standards / "CHG-0121.json").write_text("{}\n")
    # The retired PR had CHG-0122 but was not merged to main.
    # The next available number is still CHG-0122.
    (tmp_path / "pilot/worker_v08/native_tasks").mkdir(parents=True)
    closed = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[:3] == ("gh", "pr", "list"):
            if "headRefOid" in args[-1]:
                return json.dumps([{
                    "number": 987, "headRefName": branch, "headRefOid": sha,
                    "isDraft": True, "author": {"login": "github-actions[bot]"}
                }] if pr_open["value"] else [])
            if args[-1] == "headRefName":
                return json.dumps([{"headRefName": branch}] if pr_open["value"] else [])
        if args[:2] == ("gh", "api"):
            return json.dumps([{"filename": "standards/changes/CHG-0122.json"},
                               {"filename": ".lf/worker-context/t17fake/lf_rules.md"}])
        if args[:3] == ("gh", "pr", "close"):
            assert pr_open["value"]
            pr_open["value"] = False
            closed.append(int(args[3]))
            return ""
        raise AssertionError("Unexpected command: " + repr(args))

    def fake_api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path == "issues/901":
            return {"number": 901, "state": "open"}
        assert "actions/workflows/ci.yml/runs?" in path
        return {"total_count": 2, "workflow_runs": [
            {"id": 43729617525, "head_sha": sha, "head_branch": branch,
             "event": "pull_request", "status": "completed",
             "conclusion": "action_required",
             "created_at": "2026-11-15T10:00:01Z"},
            {"id": 43729614995, "head_sha": sha, "head_branch": branch,
             "event": "workflow_dispatch", "status": "completed",
             "conclusion": "failure",
             "created_at": "2026-11-15T10:00:00Z"},
        ]}

    prepared = []
    def fake_prepare(request, binding, completed, main_sha):
        assert closed == [987]
        assert pr_open["value"] is False
        assert main_sha == head
        with patch.object(integration, "command", return_value=b"[]"):
            number = integration.next_chg(tmp_path)
        prepared.append((request, binding["task_name"], number))
        return {"status": "DRAFT_PREPARED", "draft_pr":
                "https://github.com/paulozterra/lf-programming-sandbox/pull/999",
                "chg": f"CHG-{number:04d}", "head_sha": head}

    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "check_main", return_value=head), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "plans", return_value=[
             ("req-901", lots, {"stage": "LOTS_PLANNED"}, bindings)]), \
         patch.object(chain_lots, "sweep_request_enabled", return_value=True), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "complete_registered_exam_requests", return_value=[]), \
         patch.object(chain_lots, "request_all_lot_exams", return_value=[]), \
         patch.object(chain_lots, "completed_lots", return_value={}), \
         patch.object(chain_lots, "failed_lots", return_value={}), \
         patch.object(chain_lots, "run", side_effect=fake_run), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "retry_failed_bot_prs", return_value=[]), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
          patch.multiple(chain_lots,
                        replay_native_integration=lambda *a, **k: [],
                        recover_pending_worker=lambda *a, **k: [],
                        recover_unstarted_integration=lambda *a, **k: [],
                        sync_implemented_registry=lambda *a, **k: {"status": "REGISTRY_CURRENT"}), \
         patch.object(chain_lots, "api", side_effect=fake_api), \
         patch.object(chain_lots, "admit_registration", return_value=None), \
         patch.object(chain_lots, "prepare_successor", side_effect=fake_prepare):
        result = chain_lots.process(sweep=True, base_sha=head)

    assert closed == [987]
    assert prepared == [("req-901", "t17fake", 122)]
    assert any(x.get("status") == "STALE_REGISTRATION_RETIRED"
               and x["closed_prs"] == [987] for x in result)
    assert any(x.get("status") == "DRAFT_PREPARED"
               and x["chg"] == "CHG-0122" for x in result)
    assert not any(x.get("status") == "ALREADY_PREPARED" for x in result)
