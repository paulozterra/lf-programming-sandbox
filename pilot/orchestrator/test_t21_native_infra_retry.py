"""T21: deterministic native pre-admission retry, plus real git ancestry."""
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pilot.orchestrator.native_infra_retry import retry_native_infra, INFRA_STEP
from pilot.worker_v08.native_proposal_push_guard import validate_proposal_only

REPO = "paulozterra/lf-programming-sandbox"
SHA = "a" * 40
TASK = "synthetic1"
TITLE = f"lf-native-auto-lf/native-proposal/{TASK}-{SHA}"


def entry(id=200, title=TITLE, event="workflow_run", status="completed",
          conclusion="failure"):
    return dict(id=id, display_title=title, event=event,
                status=status, conclusion=conclusion)


def exercise(rows, step=INFRA_STEP, branch_sha=SHA):
    called = []
    def api(path):
        if path == "actions/workflows/worker-native.yml/runs?per_page=100":
            return {"total_count": len(rows), "workflow_runs": rows}
        if path == "actions/runs/200/jobs?per_page=100":
            return {"total_count": 1, "jobs": [{
                "name": "native", "steps": [
                    {"name": step, "conclusion": "failure"},
                    {"name": "Admit task and registered base (fail closed until Claude registers ex6)",
                     "conclusion": "skipped"}]}]}
        raise AssertionError(path)
    def run(*args):
        called.append(args)
        if args[:3] == ("git", "ls-remote", "origin"):
            return branch_sha + "\trefs/heads/lf/native-proposal/" + TASK
        return ""
    with patch("pilot.orchestrator.native_infra_retry.validate_proposal_only",
               return_value={"task": TASK}):
        result = retry_native_infra("b" * 40, run, api, REPO, Path("."))
    return result, called


def test_pre_admission_runtime_failure_dispatch_once_without_proposal_write():
    result, calls = exercise([entry()])
    assert result[0]["status"] == "NATIVE_INFRA_RETRY_DISPATCHED"
    dispatch = [x for x in calls if x[:3] == ("gh", "workflow", "run")]
    assert len(dispatch) == 1
    assert "proposal_commit_sha=" + SHA in dispatch[0]
    assert "infra_retry=true" in dispatch[0]
    assert not any("push" in x for x in calls)


def test_retry_run_ledger_prevents_second_dispatch_even_when_retry_failed():
    manual = entry(201, f"lf-native-infra-retry-{TASK}-{SHA}",
                   "workflow_dispatch", conclusion="failure")
    result, calls = exercise([entry(), manual])
    assert result == []
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)


def test_failure_after_admission_never_retries_and_head_change_blocks():
    result, calls = exercise([entry()], step="Execute original run_verified_worker")
    assert result == [] and not any(x[:3] == ("gh", "workflow", "run") for x in calls)
    result, calls = exercise([entry()], branch_sha="c" * 40)
    assert result == [] and not any(x[:3] == ("gh", "workflow", "run") for x in calls)


def _git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd), *args],
                                   stderr=subprocess.DEVNULL).decode().strip()


def test_historical_main_ancestor_proposal_remains_eligible():
    with TemporaryDirectory() as td:
        repo = Path(td)
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.name", "synthetic")
        _git(repo, "config", "user.email", "synthetic@example.invalid")
        task = "synthetic1"
        reg = repo / "pilot/worker_v08/native_tasks"
        reg.mkdir(parents=True)
        (reg / (task + ".json")).write_text(json.dumps({"task_spec": {
            "write_path_patterns": ["contracts/synthetic.openapi.yaml"]}}))
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "registered")
        base = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-b", "lf/native-proposal/" + task)
        proposals = repo / "pilot/native_proposals"
        proposals.mkdir(parents=True)
        (proposals / (task + ".json")).write_text("{}")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "one proposal")
        proposal = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "main")
        (repo / "later.txt").write_text("Train merged another change")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "unrelated Train main merge")
        head = _git(repo, "rev-parse", "HEAD")
        assert head != base
        result = validate_proposal_only(
            repo, proposal, main_sha=head, branch="lf/native-proposal/" + task,
            allow_historical_base=True)
        assert result["base_commit_sha"] == base
        assert result["task"] == task
