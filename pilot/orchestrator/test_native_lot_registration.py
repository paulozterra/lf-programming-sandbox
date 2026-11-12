"""CP3.4 visible merged-handoff attestation; no model and no private oracle."""
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_lot_registration import verify_handoffs
from native_lot_binding import NativeLotBlocked


def run(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_merge_proof_checks_actual_sha_and_file(tmp_path):
    run(tmp_path, "init", "-b", "main")
    run(tmp_path, "config", "user.email", "test@example.invalid")
    run(tmp_path, "config", "user.name", "CP34 Test")
    db = tmp_path / "db"
    db.mkdir()
    file = db / "V001__auth.sql"
    file.write_text("select 1;\n")
    run(tmp_path, "add", "db/V001__auth.sql")
    run(tmp_path, "commit", "-m", "Simulated verified lot L1 merge")
    merged = run(tmp_path, "rev-parse", "HEAD")
    lots = {"lots": [{"id": "L1", "write_paths": ["db/V001__auth.sql"]}]}
    proof = {"lot_id": "L1", "merge_sha": merged,
             "expected_files": ["db/V001__auth.sql"]}
    assert verify_handoffs(tmp_path, lots, [proof]) == {"L1"}
    assert verify_handoffs(tmp_path, lots, []) == set()
    with pytest.raises(NativeLotBlocked, match="HANDOFF_PROOF_INVALID"):
        verify_handoffs(tmp_path, lots, [{**proof, "expected_files": ["db/other.sql"]}])
    with pytest.raises(NativeLotBlocked, match="HANDOFF_PROOF_INVALID"):
        verify_handoffs(tmp_path, lots, [proof, proof])
    with pytest.raises(NativeLotBlocked, match="GIT_UNAVAILABLE"):
        verify_handoffs(tmp_path, lots, [{**proof, "merge_sha": "a" * 40}])


def test_cp34_two_lot_candidate_handoff_with_real_paths(tmp_path):
    """Full offline CP3.4 adapter simulation: DATA ready, then BACKEND ready."""
    import hashlib
    import json
    from native_lot_registration import choose
    from register_task_context import canonical

    run(tmp_path, "init", "-b", "main")
    run(tmp_path, "config", "user.email", "test@example.invalid")
    run(tmp_path, "config", "user.name", "CP34 Test")
    (tmp_path / "db").mkdir()
    (tmp_path / "apps/time-service").mkdir(parents=True)
    db_path = tmp_path / "db/V001__auth.sql"
    db_path.write_text("create table auth_candidate(id integer);\n")
    run(tmp_path, "add", "db/V001__auth.sql")
    run(tmp_path, "commit", "-m", "Simulated DATA handoff (no Worker)")
    merge_sha = run(tmp_path, "rev-parse", "HEAD")

    lots = {
        "schema_version": "CP33_LOTS_CANDIDATE_V1",
        "production_authority": False, "handoff_allowed": False, "worker_invoked": False,
        "lots": [
            {"id": "L1", "area": "DATA", "profile_code": "PERFIL-PROG-DATA-EXP",
             "write_paths": ["db/V001__auth.sql"], "depends_on": []},
            {"id": "L2", "area": "BACKEND",
             "profile_code": "PERFIL-PROG-BACKEND-SPRING-EXP",
             "write_paths": ["apps/time-service/src/main/java/lf/sandbox/time/AuthController.java"],
             "depends_on": ["L1"]},
        ],
    }
    folder = tmp_path / "pilot/runs/cp34-simulated"
    folder.mkdir(parents=True)
    (folder / "lots.json").write_bytes(canonical(lots))
    state = {"stage": "LOTS_PLANNED",
             "lots_sha256": hashlib.sha256(canonical(lots)).hexdigest()}
    (folder / "state.json").write_bytes(canonical(state))

    _, first, mapped_first, paths_first = choose(
        tmp_path, "cp34-simulated", "L1", [])
    assert first["id"] == "L1"
    assert mapped_first["native_profile_code"] == "PERFIL-PROG-DATA-EXP"
    assert paths_first == ["db/V001__auth.sql"]
    with pytest.raises(NativeLotBlocked, match="DEPENDENCY_NOT_VERIFIED"):
        choose(tmp_path, "cp34-simulated", "L2", [])

    receipt = {"lot_id": "L1", "merge_sha": merge_sha,
               "expected_files": ["db/V001__auth.sql"]}
    _, second, mapped_second, paths_second = choose(
        tmp_path, "cp34-simulated", "L2", [receipt])
    assert second["id"] == "L2"
    assert mapped_second["native_profile_code"] == "PERFIL-PROG-BACKEND-EXP"
    assert paths_second == [
        "apps/time-service/src/main/java/lf/sandbox/time/AuthController.java"]
