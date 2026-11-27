import copy
import json
import subprocess

import pytest

from pilot.orchestrator.lot_recovery import (
    POLICY, append_only, for_request, for_successor, load, parse,
    require_unused, schedule_recovery, verify_original,
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
    git("add", ".")
    git("commit", "-m", "owner enrollment")
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
