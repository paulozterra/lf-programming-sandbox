"""T16: real generate -> prepare_native_lot -> vendor-accepted native registration.

Entirely offline in a disposable Git worktree/branch; no real exam or user
request is touched, no network, no model, no merge or GitHub mutation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

import pytest

from pilot.orchestrator import generate_chain
from pilot.orchestrator import prepare_native_lot
from pilot.orchestrator import worker_template_contract
import native_lot_registration as registration

REPO_ROOT = Path(__file__).resolve().parents[2]


def git(root, *argv):
    return subprocess.run(["git", "-C", str(root), *argv],
                          capture_output=True, text=True, check=True).stdout.strip()


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()


def test_real_prepare_native_lot_accepts_generated_data_task_in_temp_branch(tmp_path):
    working = tmp_path / "checkout"
    temp_branch = "t16-offline-" + uuid4().hex[:16]
    original_main = git(REPO_ROOT, "rev-parse", "refs/remotes/origin/main")
    git(REPO_ROOT, "worktree", "add", "-b", temp_branch, str(working), "HEAD")
    try:
        git(working, "config", "user.name", "T16 offline test")
        git(working, "config", "user.email", "t16@example.invalid")
        run_id = "t16offline"
        db_path = "apps/time-service/src/main/resources/db/migration/V999__t16_fixture.sql"
        lots = {
            "schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": False, "handoff_allowed": False,
            "worker_invoked": False,
            "lots": [{
                "id": "SOL-001", "area": "DATA",
                "profile_code": "PERFIL-PROG-DATA-EXP",
                "write_paths": [db_path],
                "depends_on": [], "requirement_ids": ["REQ-T16"],
            }],
        }
        folder = working / "pilot/runs" / run_id
        folder.mkdir(parents=True)
        (folder / "analysis.json").write_bytes(canonical({
            "requirements": [{"requirement_id": "REQ-T16", "outcome": "DATA sample"}]}))
        (folder / "lots.json").write_bytes(canonical(lots))
        (folder / "state.json").write_bytes(canonical({
            "stage": "LOTS_PLANNED",
            "lots_sha256": hashlib.sha256(canonical(lots)).hexdigest(),
        }))
        plan = generate_chain.generate(working, run_id, lots)
        entry = plan["bindings"][0]
        task_name = entry["task_name"]
        template = json.loads((working / entry["template_path"]).read_text())
        worker_template_contract.validate_template_worker(
            template, "DATA", pending_shas=True)
        # Opaque offline admission fixture: not a real examiner oracle.
        ciphertext = working / f"pilot/holdouts/{task_name}.oracle.json.age"
        ciphertext.parent.mkdir(parents=True, exist_ok=True)
        ciphertext.write_bytes(b"T16-offline-opaque-ciphertext-fixture")
        metadata = working / entry["holdout_metadata_path"]
        metadata.parent.mkdir(parents=True, exist_ok=True)
        holdout = {"holdout_sha256": "c" * 64,
                   "holdout_ref": f"pilot/holdouts/{task_name}.oracle.json.age",
                   "project_ref": "lf_java"}
        metadata.write_bytes(canonical(holdout))
        git(working, "add", "-f", "--", str(ciphertext.relative_to(working)))
        git(working, "add", "--", "pilot/runs/" + run_id,
            "pilot/orchestrator/chain_plans/" + run_id + ".json")
        git(working, "commit", "-m", "T16 synthetic offline planning")
        # The real preflight only accepts a base already on origin/main.
        # Simulate that trusted merge in local Git metadata, never push it.
        git(working, "update-ref", "refs/remotes/origin/main",
            git(working, "rev-parse", "HEAD"))
        assert not git(working, "status", "--porcelain")

        from programming_agent_runner.hashutil import source_snapshot_sha256
        template["task_spec"]["base_head_sha"] = git(working, "rev-parse", "HEAD")
        template["task_spec"]["source_snapshot_sha256"] = source_snapshot_sha256(working)
        worker_template_contract.validate_template_worker(template, "DATA")

        # Diagnostic wrapper invokes the actual vendored Worker unmodified.
        # The test reports only a bounded, secret-checked preflight reason.
        import export_task_pack
        from programming_agent_runner.worker_secrets import secret_text_reason
        original_run_worker = export_task_pack.run_worker

        def assert_worker_capture(*args, **kwargs):
            output = original_run_worker(*args, **kwargs)
            reason = output.receipt.get("reason")
            if reason != "NATIVE_CAPTURE_ONLY":
                detail = str(reason)
                if secret_text_reason(detail):
                    detail = "REDACTED"
                raise AssertionError("T16_WORKER_CAPTURE_REASON:" + detail[:100])
            return output

        with (patch.object(prepare_native_lot, "ROOT", working),
              patch.object(registration, "ROOT", working),
              patch.object(registration, "WORKER", working / "pilot/worker_v08"),
              patch.object(export_task_pack, "run_worker", side_effect=assert_worker_capture)):
            result = prepare_native_lot.run(
                working, run_id, "SOL-001", task_name, template, holdout, [])

        assert result["result"] == "CP35_PREPARED_NO_MODEL_NO_PUSH"
        native = working / "pilot/worker_v08/native_tasks" / (task_name + ".json")
        assert native.is_file()
        from programming_agent_runner.worker_spec import parse_worker_task
        parsed = parse_worker_task(json.loads(native.read_text())["task_spec"])
        assert parsed.task_id == template["task_spec"]["task_id"]
        assert result["model_invoked"] is False
        assert result["task_pack_path"]
        assert (working / result["task_pack_path"]).is_file()
        assert not git(working, "status", "--porcelain",
                       "--untracked-files=no")  # exported pack is untracked only
    finally:
        git(REPO_ROOT, "update-ref", "refs/remotes/origin/main", original_main)
        git(REPO_ROOT, "worktree", "remove", "--force", str(working))
        git(REPO_ROOT, "branch", "-D", temp_branch)
