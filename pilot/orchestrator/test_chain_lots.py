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
            "head": {"ref": "lf/native-integration/cp36data-run-901",
                     "repo": {"full_name": "paulozterra/lf-programming-sandbox"}}},
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


def test_train_labeled_pr_event_must_not_be_mistaken_for_main_branch():
    """Train operates on a PR event but verifies the resulting main merge."""
    trusted = {
        "id": 55, "path": ".github/workflows/sandbox-train.yml@refs/heads/main",
        "status": "completed", "run_attempt": 1, "conclusion": "success",
        "event": "pull_request", "head_branch": "lf/native-integration/demo-run-42",
        "repository": {"full_name": "paulozterra/lf-programming-sandbox"},
    }
    with patch.object(chain_lots, "api", return_value=trusted):
        assert chain_lots.event_kind(55, "a" * 40) == "TRAIN"
    with patch.object(chain_lots, "api", return_value={
            **trusted, "repository": {"full_name": "attacker/repository"}}):
        with pytest.raises(ChainBlocked, match="SOURCE_WORKFLOW_UNTRUSTED"):
            chain_lots.event_kind(55, "a" * 40)
    with patch.object(chain_lots, "api", return_value={
            **trusted, "event": "workflow_dispatch"}):
        with pytest.raises(ChainBlocked, match="TRAIN_SOURCE_BRANCH_INVALID"):
            chain_lots.event_kind(55, "a" * 40)


def test_cp36_event_dispatches_real_merge_successor_and_blocks_on_third_failure(tmp_path):
    """Exercise the orchestration entrypoint, not just the pure reducer."""
    lots, plan, data, backend = fixtures(tmp_path)
    bindings = validate_plan(plan, lots, "simulated")
    merged = "a" * 40
    newer_main = "b" * 40  # unrelated Train merge occurred before reconciliation
    pr = {"number": 501, "merged": True, "merge_commit_sha": merged,
          "base": {"ref": "main", "repo": {
              "full_name": "paulozterra/lf-programming-sandbox"}},
          "head": {"ref": "lf/native-integration/cp36data-run-901",
                   "repo": {"full_name": "paulozterra/lf-programming-sandbox"}}}
    history = [(merged, pr, {data, "standards/CAMBIOS.md"})]
    status = {"stage": "LOTS_PLANNED",
              "lots_sha256": plan["lots_sha256"]}
    emitted = []
    def sim_run(*args, **kwargs):
        if args[:3] == ("git", "cat-file", "-e"):
            return ""  # virtual merged-tree proof only in this isolated test
        raise AssertionError("Unexpected host operation " + repr(args))
    def ready(request, binding, receipts, head):
        emitted.append((request, binding["lot_id"], head, set(receipts)))
        return {"status": "DRAFT_PREPARED", "merge_authorized": False}
    shared = (
        patch.object(chain_lots, "check_main", return_value=newer_main),
        patch.object(chain_lots, "plans", return_value=[
            ("simulated", lots, status, bindings)]),
        patch.object(chain_lots, "first_parent_merges", return_value=history),
        patch.object(chain_lots, "merged_integration", return_value=(pr, {data})),
        patch.object(chain_lots, "run", side_effect=sim_run),
        patch.object(chain_lots, "prepare_successor", side_effect=ready),
        patch.object(chain_lots, "admit_registration", return_value=None),
        patch.object(chain_lots, "pending_draft", return_value=False),
    )
    from contextlib import ExitStack
    with ExitStack() as stack:
        for context in shared:
            stack.enter_context(context)
        with (patch.object(chain_lots, "event_kind", return_value="TRAIN"),
              patch.object(chain_lots, "failed_lots", return_value={})):
            result = chain_lots.process(501)
        assert result[0]["status"] == "DRAFT_PREPARED"
        assert emitted == [("simulated", "SOL-002", newer_main, {"SOL-001"})]
        with (patch.object(chain_lots, "event_kind", return_value="NATIVE_FAIL"),
              patch.object(chain_lots, "failed_lots",
                           return_value={"SOL-002": [101, 102, 103]}),
              patch.object(chain_lots, "block_request",
                           return_value={"status": "BLOCKED_PENDING_OWNER_MERGE",
                                         "reason_code": BLOCK_CODE})):
            result = chain_lots.process(103)
        assert result[0]["status"] == "BLOCKED_PENDING_OWNER_MERGE"
        assert result[0]["reason_code"] == BLOCK_CODE
        assert len(emitted) == 1  # no successor release after 3 failures


def test_p4_priority_chain_plan_data_merge_releases_backend_offline(tmp_path):
    """Actual owner-enrolled plan: a trusted p4data merge queues p4be only."""
    plans = chain_lots.plans()
    selected = [row for row in plans if row[0] == "p4-prioridad"]
    assert len(selected) == 1
    request, lots, state, bindings = selected[0]
    assert state["stage"] == "LOTS_PLANNED"
    assert bindings["SOL-002"]["task_name"] == "p4data"
    assert bindings["SOL-001"]["task_name"] == "p4be"
    assert bindings["SOL-001"]["template_path"] == (
        "pilot/runs/p4-prioridad/templates/p4be.task.json")
    assert bindings["SOL-001"]["holdout_metadata_path"] == (
        "pilot/runs/p4-prioridad/claude_meta/p4be.json")
    assert next_ready(lots, set())[0]["id"] == "SOL-002"
    assert next_ready(lots, {"SOL-002"})[0]["id"] == "SOL-001"

    merged = "a" * 40
    current_main = "b" * 40
    source_pr = {
        "number": 110, "merged": True, "merge_commit_sha": merged,
        "base": {"ref": "main", "repo": {
            "full_name": "paulozterra/lf-programming-sandbox"}},
        "head": {"ref": "lf/native-integration/p4data-run-43146245998",
                 "repo": {"full_name": "paulozterra/lf-programming-sandbox"}},
    }
    merged_paths = {
        "db/migration/V1__reminders_priority.sql", "standards/CAMBIOS.md",
        "standards/changes/CHG-0065.json",
    }
    emitted = []

    def simulate_run(*args, **kwargs):
        if args[:3] == ("git", "cat-file", "-e"):
            assert args[3] == merged + ":db/migration/V1__reminders_priority.sql"
            return ""
        raise AssertionError("Unexpected host operation " + repr(args))

    def capture_prepare(selected_request, binding, proofs, head):
        emitted.append((selected_request, binding["lot_id"], binding["task_name"],
                        binding["template_path"], binding["holdout_metadata_path"],
                        set(proofs), head))
        return {"status": "DRAFT_PREPARED", "model_invoked": False}

    from contextlib import ExitStack
    with ExitStack() as stack:
        for manager in (
            patch.object(chain_lots, "check_main", return_value=current_main),
            patch.object(chain_lots, "event_kind", return_value="TRAIN"),
            patch.object(chain_lots, "plans", return_value=selected),
            patch.object(chain_lots, "first_parent_merges",
                         return_value=[(merged, source_pr, merged_paths)]),
            patch.object(chain_lots, "run", side_effect=simulate_run),
            patch.object(chain_lots, "failed_lots", return_value={}),
            patch.object(chain_lots, "prepare_successor",
                         side_effect=capture_prepare),
            patch.object(chain_lots, "admit_registration", return_value=None),
            patch.object(chain_lots, "pending_draft", return_value=False),
            # Hermetic: the real repo may already contain native_tasks/p4be.json
            # once the lot is registered; the simulation must not depend on it.
            patch.object(chain_lots, "ROOT", tmp_path),
        ):
            stack.enter_context(manager)
        result = chain_lots.process(43238891957)
    assert result == [{"request": "p4-prioridad", "lot_id": "SOL-001",
                       "status": "DRAFT_PREPARED", "model_invoked": False}]
    assert emitted == [(
        "p4-prioridad", "SOL-001", "p4be",
        "pilot/runs/p4-prioridad/templates/p4be.task.json",
        "pilot/runs/p4-prioridad/claude_meta/p4be.json",
        {"SOL-002"}, current_main,
    )]


def test_p4_priority_plan_rejects_mixed_or_cross_request_binding_paths():
    """P4 path enrollment is exact; unrelated or mixed metadata is denied."""
    root = Path(__file__).resolve().parents[2]
    lots = json.loads((root / "pilot/runs/p4-prioridad/lots.json").read_text("utf-8"))
    plan = json.loads((root / "pilot/orchestrator/chain_plans/p4-prioridad.json")
                      .read_text("utf-8"))
    assert set(validate_plan(plan, lots, "p4-prioridad")) == {"SOL-001", "SOL-002"}
    for target in (
        "pilot/runs/other/templates/p4be.task.json",
        "pilot/orchestrator/native_inputs/p4be.task.json",
    ):
        mutated = json.loads(json.dumps(plan))
        mutated["bindings"][1]["template_path"] = target
        with pytest.raises(ChainBlocked, match="BINDING_PATH_INVALID"):
            validate_plan(mutated, lots, "p4-prioridad")

def test_cp36_real_errors_are_printed_not_masked(monkeypatch, capsys):
    from native_verified_integration import IntegrationBlocked
    monkeypatch.setenv("GITHUB_REPOSITORY", chain_lots.REPO)
    monkeypatch.setenv("GH_TOKEN", "offline-token")
    monkeypatch.setattr(sys, "argv", ["chain_lots.py", "--source-run-id", "17"])
    for failure in (IntegrationBlocked("CP35_C9_CHECK_FAILED"),
                    ChainBlocked("CP36_UNTRUSTED_EVENT")):
        with patch.object(chain_lots, "process", side_effect=failure):
            assert chain_lots.main() == 1
        captured = capsys.readouterr()
        assert str(failure) in captured.err
        assert "UNEXPECTED" not in captured.err


def test_cp36_manual_pr_requires_train_and_ancestry():
    sha, head = "a" * 40, "b" * 40
    pr = {"number": 110, "merged": True, "merge_commit_sha": sha,
          "base": {"ref": "main", "repo": {"full_name": chain_lots.REPO}},
          "head": {"ref": "lf/native-integration/p4data-run-43146245998",
                   "repo": {"full_name": chain_lots.REPO}}}
    def git_sim(*args, **kwargs):
        if args[:3] == ("git", "rev-list", "--first-parent"):
            return head + "\n" + sha
        if args[:3] == ("git", "log", "-1"):
            return "Merge PR #110 via sandbox-train"
        if args[:3] == ("git", "rev-list", "--parents"):
            return f"{sha} {'c' * 40} {'d' * 40}"
        raise AssertionError(repr(args))
    with (patch.object(chain_lots, "api", return_value=pr),
          patch.object(chain_lots, "run", side_effect=git_sim),
          patch.object(chain_lots.subprocess, "run",
              return_value=subprocess.CompletedProcess(["git"], 0, b"", b""))):
        assert chain_lots.validated_manual_integration(110, head) == sha
    with (patch.object(chain_lots, "api", return_value={**pr, "merged": False}),
          pytest.raises(ChainBlocked, match="MANUAL_INTEGRATION_PR_UNTRUSTED")):
        chain_lots.validated_manual_integration(110, head)
    with (patch.object(chain_lots, "api", return_value=pr),
          patch.object(chain_lots.subprocess, "run",
              return_value=subprocess.CompletedProcess(["git"], 1, b"", b"")),
          pytest.raises(ChainBlocked, match="MANUAL_INTEGRATION_NOT_ANCESTOR")):
        chain_lots.validated_manual_integration(110, head)


def test_cp36_manual_recovery_releases_only_unregistered_pending_free_p4be(tmp_path):
    selected = [row for row in chain_lots.plans() if row[0] == "p4-prioridad"]
    assert len(selected) == 1
    sha, head = "a" * 40, "b" * 40
    pr = {"number": 110, "merged": True, "merge_commit_sha": sha,
          "base": {"ref": "main", "repo": {"full_name": chain_lots.REPO}},
          "head": {"ref": "lf/native-integration/p4data-run-43146245998",
                   "repo": {"full_name": chain_lots.REPO}}}
    changed = {"db/migration/V1__reminders_priority.sql", "standards/CAMBIOS.md",
               "standards/changes/CHG-0065.json"}
    recorded = []
    def git_sim(*args, **kwargs):
        if args[:3] == ("git", "cat-file", "-e"):
            return ""
        raise AssertionError(repr(args))
    def prepare(request, binding, proofs, commit):
        recorded.append((request, binding["task_name"], commit))
        return {"status": "DRAFT_PREPARED"}
    from contextlib import ExitStack
    def simulate(pending):
        with ExitStack() as stack:
            for item in (
                patch.object(chain_lots, "check_main", return_value=head),
                patch.object(chain_lots, "validated_manual_integration", return_value=sha),
                patch.object(chain_lots, "plans", return_value=selected),
                patch.object(chain_lots, "first_parent_merges",
                             return_value=[(sha, pr, changed)]),
                patch.object(chain_lots, "failed_lots", return_value={}),
                patch.object(chain_lots, "run", side_effect=git_sim),
                patch.object(chain_lots, "pending_draft", return_value=pending),
                patch.object(chain_lots, "prepare_successor", side_effect=prepare),
                patch.object(chain_lots, "admit_registration", return_value=None),
                patch.object(chain_lots, "ROOT", tmp_path),  # hermetic: ignore real native_tasks
            ):
                stack.enter_context(item)
            return chain_lots.process(integration_pr=110)
    assert simulate(False)[0]["status"] == "DRAFT_PREPARED"
    assert recorded == [("p4-prioridad", "p4be", head)]
    assert simulate(True)[0]["status"] == "ALREADY_PREPARED"
    assert len(recorded) == 1
