"""T24: a genuine native PASS is recovered through CP3.5 only, once.

No Worker, proposal branch, secret oracle, source patch or label is modified.
The CP3.5 replay workflow itself must verify the original PASS/proof/patch.
"""
from __future__ import annotations
from pilot.config.testing import install_project_config

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.orchestrator import native_integration_replay as replay

REPO = "paulozterra/lf-programming-sandbox"
TASK = "req186contrato1"
RUN_ID = 43797847761
FAILED = 43797998417
SHA = "68e7f09392d631bbb520308fad277c09265f829b"
HEAD = "a" * 40
TITLE = f"lf-native-auto-lf/native-proposal/{TASK}-{SHA}"


def worker(**updates):
    return {
        "id": RUN_ID, "status": "completed", "conclusion": "success",
        "event": "workflow_run", "head_branch": "main", "head_sha": HEAD,
        "run_attempt": 1, "repository": {"full_name": REPO},
        "path": ".github/workflows/worker-native.yml",
        "display_title": TITLE,
        **updates,
    }


def failure(**updates):
    return {
        "id": FAILED, "status": "completed", "conclusion": "failure",
        "event": "workflow_run", "head_branch": "main", "head_sha": HEAD,
        "run_attempt": 1, "repository": {"full_name": REPO},
        "path": ".github/workflows/native-verified-integration.yml",
        "display_title": "CP3.5 " + TITLE,
        **updates,
    }


def fixture(tmp_path, *, paths=None):
    install_project_config(tmp_path)
    file = tmp_path / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({
        "task_spec": {"base_head_sha": HEAD,
                      "write_path_patterns": paths or [
                          "contracts/sbx-rem-list.openapi.yaml"]}}))


def exercise(tmp_path, *, first=None, second=None, existing=False,
             logs="CP35_TASK_SCOPE_UNSAFE", job_status="failure",
             worker_rows=None, allowed_task=None):
    fixture(tmp_path)
    records = [first or failure()]
    if second is not None:
        records.append(second)
    calls = []
    def api(path):
        if path == "actions/workflows/native-verified-integration.yml/runs?per_page=100":
            return {"total_count": len(records), "workflow_runs": records}
        if path == "actions/workflows/worker-native.yml/runs?per_page=100":
            pool = worker_rows if worker_rows is not None else [worker()]
            return {"total_count": len(pool), "workflow_runs": pool}
        if path == f"actions/runs/{FAILED}/jobs?per_page=100":
            return {"total_count": 1, "jobs": [{
                "name": "integrate", "conclusion": "failure",
                "steps": [{"name": "Integrate PASS artifact into a draft PR with C9 and head-specific CI",
                           "conclusion": job_status}]}]}
        raise AssertionError(path)
    def run(*args):
        calls.append(args)
        if args[:3] == ("git", "ls-remote", "origin"):
            return ("f" * 40 + " refs/heads/lf/native-integration/" +
                    TASK + "-run-" + str(RUN_ID)) if existing else ""
        if args[:3] == ("gh", "run", "view"):
            return logs
        if args[:3] == ("gh", "workflow", "run"):
            return ""
        raise AssertionError(args)
    result = replay.recover(HEAD, run, api, REPO, tmp_path, allowed_task=allowed_task)
    return result, calls


def test_actual_req186_pass_replays_integration_only_and_keeps_attempt():
    import tempfile
    with tempfile.TemporaryDirectory(prefix="t24-") as dirname:
        result, calls = exercise(Path(dirname))
    assert result == [{
        "status": "NATIVE_INTEGRATION_REPLAY_DISPATCHED",
        "source_run_id": RUN_ID, "failed_integration_run_id": FAILED,
        "task": TASK,
    }]
    dispatches = [x for x in calls if x[:3] == ("gh", "workflow", "run")]
    assert len(dispatches) == 1
    assert dispatches[0][3] == "native-verified-integration.yml"
    assert "source_run_id=" + str(RUN_ID) in dispatches[0]
    assert "worker-native.yml" not in dispatches[0]
    assert not any(x[:2] == ("git", "push") for x in calls)
    assert not any(x[:2] == ("gh", "issue") for x in calls)


def test_original_pass_not_replayed_twice_after_workflow_dispatch(tmp_path):
    ledger = {"id": FAILED + 2,
              "display_title": "CP3.5 recovery native-run-" + str(RUN_ID),
              "event": "workflow_dispatch", "status": "queued"}
    result, calls = exercise(tmp_path, second=ledger)
    assert result == []
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)


def test_existing_integration_branch_is_never_recreated(tmp_path):
    result, calls = exercise(tmp_path, existing=True)
    assert result == [{"status": "INTEGRATION_ALREADY_PUBLISHED",
                       "source_run_id": RUN_ID, "task": TASK}]
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)


@pytest.mark.parametrize("invalid", [
    "CP35_PATCH_SCOPE_UNSAFE",
    "CP35_TASK_BASE_STALE",
    "CP35_TASK_SCOPE_UNSAFE_SPOOF",
    "",
])
def test_no_replay_when_original_failure_is_not_exact_route_scope(tmp_path, invalid):
    result, calls = exercise(tmp_path, logs=invalid)
    assert result == []
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)


def test_no_replay_if_wrong_job_or_native_was_not_pass(tmp_path):
    assert exercise(tmp_path, job_status="success")[0] == []
    assert exercise(tmp_path, worker_rows=[worker(conclusion="failure")])[0] == []
    assert exercise(tmp_path, worker_rows=[worker(path=".github/workflows/untrusted.yml")])[0] == []
    assert exercise(tmp_path, worker_rows=[worker(head_branch="untrusted")])[0] == []
    assert exercise(tmp_path, worker_rows=[worker(), worker(id=RUN_ID - 1)])[0] == []


def test_no_replay_for_mismatched_native_and_integration_sha(tmp_path):
    assert exercise(tmp_path, first=failure(head_sha="b" * 40))[0] == []
    assert exercise(tmp_path, first=failure(display_title="CP3.5 unrelated"))[0] == []


def test_no_replay_when_registration_missing_or_has_unsafe_path(tmp_path):
    fixture(tmp_path, paths=["pilot/holdouts/hidden.age"])
    with patch.object(replay, "_listed", side_effect=[
        [failure()], [worker()],
    ]):
        results = replay.recover(HEAD, lambda *_: "", lambda *_: {}, REPO, tmp_path)
    assert results == []


def test_replay_workflow_is_not_worker_and_rechecks_original_proof():
    import yaml
    root = Path(__file__).resolve().parents[2]
    wf = yaml.safe_load((root / ".github/workflows/native-verified-integration.yml").read_text("utf-8"))
    events = wf.get("on", wf.get(True, {}))
    assert "workflow_dispatch" in events
    assert events["workflow_dispatch"]["inputs"]["source_run_id"]["required"] is True
    script = " ".join(str(step.get("run", "")) for step in
                      wf["jobs"]["integrate"]["steps"])
    assert "native_verified_integration.py" in script
    assert "--run-id" in script
    assert "native_run.py" not in script
    from pilot.orchestrator import native_verified_integration
    import inspect
    auth = inspect.getsource(native_verified_integration.get_verified_patch)
    assert "verify_run(run, jobs, run_id)" in auth
    assert "native-attempt-proof" in inspect.getsource(native_verified_integration)


def test_late_suspension_prevents_cp35_replay(tmp_path):
    checked = []
    result, calls = exercise(tmp_path, allowed_task=lambda task: checked.append(task) or False)
    assert checked == [TASK]
    assert result == []
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)
