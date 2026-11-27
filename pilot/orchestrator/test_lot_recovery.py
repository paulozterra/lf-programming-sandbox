import copy
import json
import subprocess

import pytest

from pilot.orchestrator.lot_recovery import (
    POLICY, append_only, for_request, for_successor, load, parse,
    require_unused, schedule_recovery, verify_original, public_task,
)


def authorization():
    return {"schema_version": "LF_LOT_RECOVERY_V1", "recoveries": [{
        "request_id": "req-12", "lot_id": "SOL-001", "original_task": "req12backend1",
        "successor_task": "req12backend12", "original_run_ids": [10, 11, 13],
        "forgiven_run_ids": [12], "max_additional_attempts": 1, "blocked_pr": 17,
        "blocked_pr_head": "a" * 40,
    }]}


def test_schedule_is_one_opportunity_and_history_not_mutated():
    row = next(iter(parse(json.dumps(authorization())).values()))
    spent = [10, 11, 13]
    assert schedule_recovery(row, spent, [])
    assert not schedule_recovery(row, spent, [14])
    assert spent == [10, 11, 13]
    require_unused([])
    with pytest.raises(ValueError, match="LOT_RECOVERY_ATTEMPT_EXHAUSTED"):
        require_unused([{"attempt": 1}])
    with pytest.raises(ValueError):
        schedule_recovery(row, [10, 12, 13], [])


def test_worker_requires_exact_three_failures_and_forgiveness():
    row = authorization()["recoveries"][0]
    proofs = [{"attempt": n, "run_id": run, "task_id": row["original_task"],
               "task_pack_sha256": "a" * 64} for n, run in enumerate([10, 11, 13], 1)]
    runs = [{"id": run, "status": "completed", "conclusion": "failure"} for run in [10, 11, 13]]
    verify_original(row, proofs, [12], runs)
    for changed in ([10], [], [12, 14]):
        with pytest.raises(ValueError):
            verify_original(row, proofs, changed, runs)
    runs[-1]["conclusion"] = "success"
    with pytest.raises(ValueError):
        verify_original(row, proofs, [12], runs)


def test_no_additional_identity_or_budget_and_append_only():
    data = authorization()
    rows = parse(json.dumps(data))
    for field, value in (("successor_task", "req12backend13"), ("max_additional_attempts", 2)):
        altered = copy.deepcopy(data)
        altered["recoveries"][0][field] = value
        with pytest.raises(ValueError):
            append_only(rows, parse(json.dumps(altered)))
    altered = copy.deepcopy(data)
    altered["recoveries"].append(dict(data["recoveries"][0], successor_task="req12backend13"))
    with pytest.raises(ValueError):
        parse(json.dumps(altered))
    with pytest.raises(ValueError):
        append_only(rows, {})


def test_trusted_git_history_and_exact_binding(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    path = tmp_path / POLICY
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(authorization()))
    folder = tmp_path / "pilot/runs/req-12"
    template = folder / "templates/req12backend1.task.json"
    template.parent.mkdir(parents=True)
    template.write_text(json.dumps({"task_spec": {"write_path_patterns": ["src/a"]}}))
    (folder / "chain_plan.json").write_text(json.dumps({"request_id": "req-12", "bindings": [{
        "lot_id": "SOL-001", "task_name": "req12backend1",
        "template_path": template.relative_to(tmp_path).as_posix()}]}))
    git("add", ".")
    git("commit", "-m", "owner enrollment")
    assert public_task(tmp_path, "req-12", "req12backend12", lot="SOL-001") == "req12backend1"
    from pilot.orchestrator.examiner_queue import template_matches
    issue = {"request": "req-12", "task": "req12backend12", "lot": "SOL-001", "write_paths": ["src/a"]}
    assert template_matches(tmp_path, issue)
    assert not template_matches(tmp_path, dict(issue, task="req12backend13"))
    assert not template_matches(tmp_path, dict(issue, lot="SOL-002"))
    with pytest.raises(ValueError):
        public_task(tmp_path, "req-13", "req12backend12")
    assert for_successor(tmp_path, "req12backend12")["lot_id"] == "SOL-001"
    assert for_successor(tmp_path, "req12backend13") is None
    assert for_request(tmp_path, "req-12", {"SOL-001": {"task_name": "req12backend1"}})
    with pytest.raises(ValueError):
        for_request(tmp_path, "req-12", {"SOL-001": {"task_name": "wrong"}})
    data = authorization()
    data["recoveries"][0]["successor_task"] = "req12backend13"
    path.write_text(json.dumps(data))
    git("add", ".")
    git("commit", "-m", "attempt rewrite")
    with pytest.raises(ValueError):
        load(tmp_path)


def test_worker_admission_one_use_and_concurrent_run(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from pilot.orchestrator import lot_recovery
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "worker_v08"))
    import native_run_history as history
    import native_route_defect
    import native_examiner_defect
    import native_route_tool_defect
    import native_intake_defect

    row = authorization()["recoveries"][0]
    old, new = row["original_task"], row["successor_task"]
    sha = "c" * 40
    pack = "a" * 64
    def run(n, task, status="completed"):
        return {"id": n, "head_branch": "main", "run_attempt": 1,
                "event": "workflow_run", "status": status,
                "conclusion": "failure" if status == "completed" else None,
                "display_title": "lf-native-auto-lf/native-proposal/" + task + "-" + sha}
    runs = [run(n, old) for n in [10, 11, 12, 13]] + [run(20, new, "in_progress")]
    proofs = {n: {"run_id": n, "task_id": old, "attempt": a, "task_pack_sha256": pack}
              for n, a in [(10, 1), (11, 2), (12, 3), (13, 3)]}
    monkeypatch.setattr(lot_recovery, "for_successor", lambda root, task: row if task == new else None)
    monkeypatch.setattr(history, "_api", lambda *args: {"total_count": len(runs), "workflow_runs": runs})
    monkeypatch.setattr(history, "_artifact_json", lambda repo, token, n: proofs.get(n))
    monkeypatch.setattr(native_route_defect, "verified_migration", lambda *a: None)
    monkeypatch.setattr(native_examiner_defect, "verified_examiner_defects", lambda *a: {})
    monkeypatch.setattr(native_intake_defect, "verified_intake_defects", lambda *a: {})
    monkeypatch.setattr(native_route_tool_defect, "verified_route_tool_defects",
                        lambda root, task, record: {12: {"task_pack_sha256": pack,
                            "proposal_commit_sha": sha}} if task == old else {})
    def admit():
        return history.admit_attempt(repository="paulozterra/lf-programming-sandbox",
            token="test", task=new, attempt=None, run_id=20, run_attempt=1,
            sha=sha, output=tmp_path / "admission.json", event="workflow_run",
            proposal_branch="lf/native-proposal/" + new)
    assert admit() == 1
    assert json.loads((tmp_path / "admission.json").read_text())["prior_run_ids"] == []
    runs.append(run(16, new, "in_progress"))
    with pytest.raises(ValueError, match="LOT_RECOVERY_CONCURRENT_RUN"):
        admit()
    runs.pop()
    spent = run(15, new)
    spent["display_title"] = spent["display_title"].replace(sha, "d" * 40)
    runs.append(spent)
    proofs[15] = {"run_id": 15, "task_id": new, "attempt": 1, "task_pack_sha256": pack}
    with pytest.raises(ValueError, match="LOT_RECOVERY_ATTEMPT_EXHAUSTED"):
        admit()
