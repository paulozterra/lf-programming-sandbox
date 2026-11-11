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
