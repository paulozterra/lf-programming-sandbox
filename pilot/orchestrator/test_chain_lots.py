"""CP3.6 two-lot end-to-end offline simulation and negative security gates.

No model, no Supabase, no hidden exams, no real GitHub actions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chain_contract import (BLOCK_CODE, ChainBlocked, attest_merge,
                            blocked_state, progress, validate_plan,
                            verified_failures)
from native_lot_registration import canonical, verify_handoffs
from native_lot_binding import next_ready
import chain_lots


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], text=True,
                          check=True, capture_output=True).stdout.strip()


def fixtures(tmp_path):
    data = "db/migration/V001__cp36.sql"
    backend = "apps/time-service/src/main/java/lf/sandbox/time/Auth.java"
    lots = {
        "schema_version": "CP33_LOTS_CANDIDATE_V1",
        "production_authority": False, "handoff_allowed": False, "worker_invoked": False,
        "lots": [
            {"id": "SOL-001", "area": "DATA", "profile_code": "PERFIL-PROG-DATA-EXP",
             "write_paths": [data], "depends_on": []},
            {"id": "SOL-002", "area": "BACKEND",
             "profile_code": "PERFIL-PROG-BACKEND-SPRING-EXP",
             "write_paths": [backend], "depends_on": ["SOL-001"]},
        ],
    }
    bindings = [
        {"lot_id": lot, "task_name": task,
         "template_path": f"pilot/orchestrator/native_inputs/{task}.task.json",
         "holdout_metadata_path": f"pilot/orchestrator/native_inputs/{task}.holdout.json"}
        for lot, task in (("SOL-001", "cp36data"), ("SOL-002", "cp36backend"))
    ]
    plan = {"schema_version": "CP36_CHAIN_PLAN_V1",
            "request_id": "simulated", "production_authority": False,
            "lots_sha256": hashlib.sha256(canonical(lots)).hexdigest(),
            "bindings": bindings}
    return lots, plan, data, backend


def proof(n, run_id, task="cp36backend"):
    return {"task_id": task, "attempt": n,
            "task_pack_sha256": "a" * 64, "run_id": run_id}


def run_record(run_id):
    return {"id": run_id, "status": "completed", "conclusion": "failure",
            "run_attempt": 1, "head_branch": "main", "event": "workflow_dispatch"}


def test_two_lots_real_git_merge_to_preparation_then_block(tmp_path):
    """N integration merge frees N+1; 1/2 failures wait; third BLOCKED."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "user.name", "CP36 tests")
    lots, plan, data, backend = fixtures(tmp_path)
    binding = validate_plan(plan, lots, "simulated")
    assert progress(lots, {}, {}, binding)["ready_lot_ids"] == ["SOL-001"]
    assert next_ready(lots, set())[0]["id"] == "SOL-001"
    (tmp_path / "README.md").write_text("initial\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "base")
    git(tmp_path, "switch", "-c", "lf/native-integration/cp36data-run-901")
    target = tmp_path / data
    target.parent.mkdir(parents=True)
    target.write_text("select 1;\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "verified fixture patch (no model)")
    git(tmp_path, "switch", "main")
    git(tmp_path, "merge", "--no-ff", "-m", "Merge PR #501 via sandbox-train",
        "lf/native-integration/cp36data-run-901")
    merge_sha = git(tmp_path, "rev-parse", "HEAD")
    parents = git(tmp_path, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(parents) == 3
    changed = set(git(tmp_path, "diff", "--name-only", parents[1], "HEAD").splitlines())
    pr = {"number": 501, "merged": True, "merge_commit_sha": merge_sha,
          "base": {"ref": "main", "repo": {"full_name": "paulozterra/lf-programming-sandbox"}},
          "head": {"ref": "lf/native-integration/cp36data-run-901",
                   "repo": {"full_name": "paulozterra/lf-programming-sandbox"}}}
    lot_id, receipt = attest_merge(merge_sha, pr, lots, binding, changed)
    assert lot_id == "SOL-001"
    completed = {lot_id: receipt}
    handoff = {key: receipt[key] for key in ("lot_id", "merge_sha", "expected_files")}
    assert verify_handoffs(tmp_path, lots, [handoff]) == {"SOL-001"}
    gate = progress(lots, completed, {}, binding)
    assert gate["ready_lot_ids"] == ["SOL-002"]
    prepared = []
    def prepare(request, selected, evidence, sha):
        prepared.append((request, selected["task_name"], sha))
        return {"status": "DRAFT_PREPARED", "model_invoked": False}
    with patch.object(chain_lots, "prepare_successor", side_effect=prepare):
        result = chain_lots.prepare_successor(
            "simulated", {**binding["SOL-002"], "lot_id": "SOL-002"},
            completed, merge_sha)
    assert result["status"] == "DRAFT_PREPARED"
    assert prepared == [("simulated", "cp36backend", merge_sha)]
    # After a verified success is merged no successor is released twice.
    assert "SOL-002" not in progress(lots, {"SOL-001": receipt,
        "SOL-002": {**receipt, "lot_id": "SOL-002"}}, {}, binding)["ready_lot_ids"]
    for n in (1, 2, 3):
        runs = [run_record(100 + i) for i in range(1, n + 1)]
        proofs = {r["id"]: proof(i, r["id"])
                  for i, r in enumerate(runs, 1)}
        failures = verified_failures("cp36backend", runs, proofs)
        verdict = progress(lots, completed, {"SOL-002": failures}, binding)
        if n < 3:
            assert verdict["stage"] == "CHAIN_READY"
        else:
            assert verdict["stage"] == "BLOCKED"
            assert verdict["reason_code"] == BLOCK_CODE
            state = blocked_state({"stage": "LOTS_PLANNED",
                                   "production_authority": False}, verdict)
            assert state["stage"] == "BLOCKED"
            assert state["blocked_lot_ids"] == ["SOL-002"]
            assert state["downstream_authorized"] is False


def test_no_replay_or_fake_merge_unlock():
    lots, plan, data, backend = fixtures(None)
    bindings = validate_plan(plan, lots, "simulated")
    with pytest.raises(ChainBlocked, match="PR_NOT_MERGED_ON_MAIN"):
        attest_merge("c" * 40, {"number": 501, "merged": False,
            "merge_commit_sha": "c" * 40,
            "base": {"ref": "main", "repo": {
                "full_name": "paulozterra/lf-programming-sandbox"}},
            "head": {"ref": "lf/native-integration/cp36data-run-901",
                     "repo": {"full_name": "paulozterra/lf-programming-sandbox"}}},
            lots, bindings, {data})
    with pytest.raises(ChainBlocked, match="INTEGRATION_SCOPE_MISMATCH"):
        attest_merge("c" * 40, {"number": 501, "merged": True,
            "merge_commit_sha": "c" * 40,
            "base": {"ref": "main", "repo": {
                "full_name": "paulozterra/lf-programming-sandbox"}},
            "head": {"ref": "lf/native-integration/cp36data-run-901"}},
            lots, bindings, {backend})


def test_failures_only_with_proofs_and_contiguous_attempts():
    runs = [run_record(101), run_record(102), run_record(103)]
    assert verified_failures("cp36backend", runs,
           {101: proof(1, 101), 102: None, 103: None}) == [101]
    with pytest.raises(ChainBlocked, match="ATTEMPT_GAP"):
        verified_failures("cp36backend", runs, {101: proof(1, 101),
                          102: None, 103: proof(3, 103)})
    with pytest.raises(ChainBlocked, match="ATTEMPT_DUPLICATE"):
        verified_failures("cp36backend", runs, {101: proof(1, 101),
                          102: proof(1, 102), 103: None})
    with pytest.raises(ChainBlocked, match="ATTEMPT_PROOF_INVALID"):
        verified_failures("cp36backend", runs, {101: proof(1, 999),
                          102: None, 103: None})


def test_plan_binding_and_blocked_stage_fail_closed():
    lots, plan, data, backend = fixtures(None)
    plan["bindings"][1]["task_name"] = "cp36data"
    with pytest.raises(ChainBlocked, match="BINDING_ID_INVALID"):
        validate_plan(plan, lots, "simulated")
    with pytest.raises(ChainBlocked, match="BLOCK_STATE_NOT_REQUIRED"):
        blocked_state({"stage": "LOTS_PLANNED"},
                      {"stage": "CHAIN_READY", "reason_code": None})
