"""T17.4 offline conflict recovery; all GitHub writes are mocked."""
from __future__ import annotations

import json
from unittest.mock import patch

from pilot.orchestrator import chain_lots
from pilot.orchestrator import generated_conflict_recovery as recovery
from pilot.orchestrator import native_verified_integration as integration

HEAD = "a" * 40
OLD = "b" * 40
REPO = chain_lots.REPO
BRANCH = "lf/native-registration/req186contrato1-2f384485df66"


def metadata(*, dirty=True, label=True, author="github-actions[bot]"):
    row = {"number": 205, "headRefName": BRANCH, "headRefOid": OLD,
           "author": {"login": author}}
    detail = {"number": 205, "state": "open", "merged": False,
              "mergeable_state": "dirty" if dirty else "blocked",
              "user": {"login": author},
              "labels": [{"name": "ready-to-merge"}] if label else [],
              "base": {"ref": "main"},
              "head": {"ref": BRANCH, "sha": OLD,
                       "repo": {"full_name": REPO}}}
    return row, detail


def test_real_205_dirty_retired_without_touching_unrelated_pr():
    row, detail = metadata()
    unrelated, _ = metadata(author="paulozterra")
    calls = []

    def command(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([row, unrelated])
        if args[:3] == ("gh", "pr", "close"):
            return ""
        raise AssertionError(args)

    def api(path):
        assert path == "pulls/205"
        return detail

    retired = recovery.retire_conflicted_generated(HEAD, command, api, REPO)
    assert len(retired) == 1 and retired[0]["number"] == 205
    close = next(x for x in calls if x[:3] == ("gh", "pr", "close"))
    assert close[3] == "205" and "--delete-branch" in close
    assert "--comment" in close and "dirty" in close[-1]


def test_train_failure_requires_bound_pr_and_sha_not_only_red_status():
    row, detail = metadata(dirty=False)
    failed = {"id": 43744674496, "event": "workflow_dispatch",
              "head_branch": "main", "status": "completed",
              "conclusion": "failure", "created_at": "2026-11-15T18:24:00Z"}
    log = ('{"event": "local_merge_and_render", "pr": 205, '
           '"head": "' + OLD + '", "main": "' + HEAD + '"}\n'
           'TRAIN_BLOCKED BRANCH_CONFLICT standards/CAMBIOS.md,'
           'standards/changes/CHG-0123.json')
    calls = []

    def command(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([row])
        if args[:3] == ("gh", "run", "view"):
            return log
        if args[:3] == ("gh", "pr", "close"):
            return ""
        raise AssertionError(args)

    def api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path == "issues/901":
            return {"number": 901, "state": "open"}
        if path == "pulls/205":
            return detail
        if path.startswith("actions/workflows/sandbox-train.yml/runs?"):
            return {"total_count": 400, "workflow_runs": [failed]}
        raise AssertionError(path)

    assert recovery._train_conflict(log, 205, OLD)
    assert not recovery._train_conflict(log, 206, OLD)
    assert not recovery._train_conflict(log, 205, "c" * 40)
    retired = recovery.retire_conflicted_generated(HEAD, command, api, REPO)
    assert len(retired) == 1 and "Train BRANCH_CONFLICT" in retired[0]["reason"]


def test_two_branches_same_chg_first_merges_second_regenerates_same_sweep(tmp_path):
    """Mocked #206 merged CHG-0123 while bot #205 had the same CHG."""
    chgs = tmp_path / "standards/changes"
    chgs.mkdir(parents=True)
    (chgs / "CHG-0123.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "pilot/worker_v08/native_tasks").mkdir(parents=True)
    row, detail = metadata()
    state = {"open": True}
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            if not state["open"]:
                return "[]"
            if "headRefOid" in args[-1]:
                return json.dumps([row])
            return json.dumps([{"headRefName": BRANCH}])
        if args[:3] == ("gh", "pr", "close"):
            assert state["open"]
            state["open"] = False
            return ""
        raise AssertionError(args)

    def api(path):
        if path == "issues/901":
            return {"number": 901, "state": "open"}
        if path == "pulls/205":
            return detail
        if path.startswith("actions/workflows/ci.yml/runs?"):
            return {"total_count": 0, "workflow_runs": []}
        raise AssertionError(path)

    lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": False, "handoff_allowed": False,
            "worker_invoked": False,
            "lots": [{"id": "SOL-1", "area": "CONTRATO", "depends_on": []}]}
    bindings = {"SOL-1": {"task_name": "req186contrato1",
                          "template_path": "template.json",
                          "holdout_metadata_path": "holdout.json"}}
    prepared = []

    def prepare(request, binding, completed, head):
        assert not state["open"], "Closure precedes ALREADY_PREPARED"
        assert head == HEAD
        with patch.object(integration, "command", return_value=b"[]"):
            number = integration.next_chg(tmp_path)
        prepared.append(number)
        return {"status": "DRAFT_PREPARED", "chg": f"CHG-{number:04d}",
                "mergeable_state": "clean"}

    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "plans", return_value=[
             ("req-901", lots, {"stage": "LOTS_PLANNED"}, bindings)]), \
         patch.object(chain_lots, "sweep_request_enabled", return_value=True), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "complete_registered_exam_requests", return_value=[]), \
         patch.object(chain_lots, "request_all_lot_exams", return_value=[]), \
         patch.object(chain_lots, "completed_lots", return_value={}), \
         patch.object(chain_lots, "failed_lots", return_value={}), \
         patch.object(chain_lots, "run", side_effect=command), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
          patch.multiple(chain_lots,
                        replay_native_integration=lambda *a, **k: [],
                        recover_pending_worker=lambda *a, **k: [],
                        recover_unstarted_integration=lambda *a, **k: [],
                        sync_implemented_registry=lambda *a, **k: {"status": "REGISTRY_CURRENT"}), \
         patch.object(chain_lots, "api", side_effect=api), \
         patch.object(chain_lots, "admit_registration", return_value=None), \
         patch.object(chain_lots, "prepare_successor", side_effect=prepare):
        outcomes = chain_lots.process(sweep=True, base_sha=HEAD)
    assert prepared == [124]
    assert any(x.get("pr") == 205 and x.get("status") ==
               "CONFLICT_REGISTRATION_RETIRED" for x in outcomes)
    assert any(x.get("chg") == "CHG-0124" and
               x.get("mergeable_state") == "clean" for x in outcomes)
    assert not any(x.get("status") == "ALREADY_PREPARED" for x in outcomes)
    assert any(x[:3] == ("gh", "pr", "close") and
               "--delete-branch" in x for x in calls)


def test_registry_rebuilds_from_new_main():
    row = {"kind": "implemented-registry", "number": 300,
           "branch": "lf/implemented-registry/bbbbbbbbbbbb", "sha": OLD}
    with patch.object(chain_lots, "sync_implemented_registry",
                      return_value={"status": "REGISTRY_DRAFT"}) as fn:
        assert chain_lots.regenerate_conflicted(row, HEAD, []) == {
            "status": "CONFLICT_REGISTRY_REBUILT",
            "registry": {"status": "REGISTRY_DRAFT"}}
    fn.assert_called_once_with(HEAD)


def test_integration_reuses_trusted_cp35_dispatch():
    row = {"kind": "integration", "number": 300, "sha": OLD,
           "branch": "lf/native-integration/task1-run-2500"}
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return "[]"
        if args[:3] == ("gh", "workflow", "run"):
            return ""
        raise AssertionError(args)

    def source(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path == "issues/901":
            return {"number": 901, "state": "open"}
        if path == "actions/runs/2500":
            return {"created_at": "2026-11-17T10:00:00Z", "id": 2500, "status": "completed",
                    "conclusion": "success", "run_attempt": 1,
                    "event": "workflow_run", "head_branch": "main",
                    "path": ".github/workflows/worker-native.yml",
                    "repository": {"full_name": REPO},
                    "display_title": "lf-native-auto-lf/native-proposal/task1-" + HEAD}
        if path == "actions/runs/2500/jobs?per_page=100":
            return {"jobs": [{"name": "native", "conclusion": "success"}]}
        if path.startswith("actions/workflows/native-verified-integration.yml/runs?"):
            return {"total_count": 0, "workflow_runs": []}
        raise AssertionError(path)

    with patch.object(chain_lots, "run", side_effect=command), \
         patch.object(chain_lots, "api", side_effect=source), \
         patch.object(chain_lots, "conflicted_request", return_value="req-901"):
        result = chain_lots.regenerate_conflicted(row, HEAD, [])
    assert result["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert result["source_run_id"] == 2500
    assert any(x[:3] == ("gh", "workflow", "run")
               and "source_run_id=2500" in x for x in calls)
    assert not any(x[0] == "git" or x[0] == "python3" for x in calls)


def test_generated_t7_redispatches_trusted_request_merged_on_main():
    row = {"kind": "generated-t7", "number": 301, "sha": OLD,
           "branch": "lf/generated-t7/bbbbbbbbbbbb-req-901"}
    calls = []

    def command(*args):
        calls.append(args)
        if args[:2] == ("gh", "api"):
            return json.dumps([{"filename": "pilot/runs/req-901/analysis.json"}])
        if args[:3] == ("gh", "workflow", "run"):
            return ""
        raise AssertionError(args)

    from pilot.orchestrator.lifecycle_test_support import fake_api
    with patch.object(chain_lots, "run", side_effect=command), \
         patch("pilot.auto_integrate.original_request_merge",
               return_value=HEAD), \
         patch.object(chain_lots, "conflicted_request", return_value="req-901"), \
         patch.object(chain_lots, "api", side_effect=fake_api({})):
        result = chain_lots.regenerate_conflicted(row, HEAD, [])
    assert result == {"status": "CONFLICT_T7_REDISPATCHED", "request": "req-901"}
    dispatch = next(x for x in calls if x[:3] == ("gh", "workflow", "run"))
    assert dispatch[3] == "t7-request.yml"
    assert "merge_sha=" + HEAD in dispatch and "rerun=true" in dispatch
