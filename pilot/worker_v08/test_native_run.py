"""Offline S2 controls: only CI-generated proof artifacts count as attempts."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

from native_run_history import admit_attempt, _artifact_json
from native_run import _visible_feedback, load_registration


def _run(i: int, *, run_id: int | None = None, title: str | None = None) -> dict:
    return {
        "id": run_id if run_id is not None else 700 + i,
        "display_title": title if title is not None else f"lf-native-ex6-a{i}",
        "head_branch": "main", "event": "workflow_dispatch",
        "run_attempt": 1, "status": "completed" if i < 3 else "in_progress",
    }


def _github_response(runs: list[dict]) -> dict:
    return {"total_count": len(runs), "workflow_runs": runs}


def _proof(i: int, *, run_id: int | None = None) -> dict:
    return {"task_id": "ex6", "attempt": i,
            "task_pack_sha256": f"{i:064x}",
            "run_id": run_id if run_id is not None else 700 + i}


def admission(tmp_path: Path, attempt: int, runs: list[dict],
              receipts: dict[int, dict | None], *, current_id: int | None = None) -> None:
    with (patch("native_run_history._api", return_value=_github_response(runs)),
          patch("native_run_history._artifact_json",
                side_effect=lambda repo, token, rid: receipts.get(rid))):
        admit_attempt(repository="paulozterra/lf-programming-sandbox",
                      token="offline-test", task="ex6", attempt=attempt,
                      run_id=current_id if current_id is not None else 700 + attempt,
                      run_attempt=1, sha="f" * 40,
                      output=tmp_path / "history.json")


def test_preflight_failed_run_without_proof_does_not_consume_attempt(tmp_path):
    # Run 701 failed before it produced an artifact, run 702 is valid attempt 1.
    failed = _run(1)
    failed["status"] = "completed"
    current = _run(1, run_id=702)
    current["status"] = "in_progress"
    admission(tmp_path, 1, [failed, current], {}, current_id=702)
    assert json.loads((tmp_path / "history.json").read_text())["prior_run_ids"] == []


def test_proof_consumes_attempt(tmp_path):
    prior = _run(1)
    current = _run(2)
    admission(tmp_path, 2, [prior, current], {701: _proof(1)})
    assert json.loads((tmp_path / "history.json").read_text())["prior_run_ids"] == [701]
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT_COUNT_MISMATCH"):
        admission(tmp_path, 2, [prior, current], {})


def test_three_proofs_block_fourth_attempt(tmp_path):
    runs = [_run(i) for i in (1, 2, 3)]
    for run in runs:
        run["status"] = "completed"
    future = _run(3, run_id=704, title="lf-native-ex6-a3")
    future["status"] = "in_progress"
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT_COUNT_MISMATCH"):
        admission(tmp_path, 3, runs + [future],
                  {701: _proof(1), 702: _proof(2), 703: _proof(3)},
                  current_id=704)
    with pytest.raises(ValueError, match="NATIVE_ADMISSION_INPUT_INVALID"):
        admission(tmp_path, 4, runs, {701: _proof(1), 702: _proof(2), 703: _proof(3)})


def test_duplicate_proof_blocks(tmp_path):
    runs = [_run(1), _run(1, run_id=705), _run(2)]
    runs[1]["status"] = "completed"
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT_COUNT_MISMATCH|NATIVE_ATTEMPT_LIMIT_OR_HISTORY_INVALID"):
        admission(tmp_path, 2, runs,
                  {701: _proof(1), 705: _proof(1, run_id=705)})


@pytest.mark.parametrize("tamper", ["wrong_id", "wrong_sha", "wrong_ordinal", "wrong_title"])
def test_tampered_proof_blocks(tmp_path, tamper):
    prior = _run(1)
    current = _run(2)
    proof = _proof(1)
    if tamper == "wrong_id":
        proof["run_id"] = 999
    elif tamper == "wrong_sha":
        proof["task_pack_sha256"] = "malformed"
    elif tamper == "wrong_ordinal":
        proof["attempt"] = 2
    else:
        prior["display_title"] = "untrusted-run"
    with pytest.raises(ValueError, match="NATIVE_PRIOR_PROOF_MISMATCH|NATIVE_ATTEMPT_LIMIT_OR_HISTORY_INVALID"):
        admission(tmp_path, 2, [prior, current], {701: proof})


def test_absent_artifact_is_ignored_and_duplicate_archive_blocks():
    with patch("native_run_history._api", return_value={
        "total_count": 0, "artifacts": []}):
        assert _artifact_json("repo", "test", 701) is None
    with patch("native_run_history._api", return_value={
        "total_count": 2, "artifacts": [
            {"name": "native-attempt-proof"},
            {"name": "native-attempt-proof"}]}):
        with pytest.raises(ValueError, match="NATIVE_PRIOR_PROOF_DUPLICATE_OR_EXPIRED"):
            _artifact_json("repo", "test", 701)


def test_rerun_blocked(tmp_path):
    with pytest.raises(ValueError, match="NATIVE_ADMISSION_INPUT_INVALID"):
        admit_attempt(repository="paulozterra/lf-programming-sandbox",
                      token="offline-test", task="ex6", attempt=1,
                      run_id=701, run_attempt=2, sha="a" * 40,
                      output=tmp_path / "history.json")


def test_feedback_only_visible_commands():
    receipt = {"attempts": [{"acceptance": [
        {"name": "visible-unit", "status": "FAIL", "reason": "EXIT_NONZERO",
         "returncode": 1, "stdout_excerpt": "visible only",
         "stderr_excerpt": "failure"}
    ]}], "hidden_oracle": {"secret": "NEVER_EXPORT"}}
    output = _visible_feedback(receipt, 2)
    assert output["commands"][0]["name"] == "visible-unit"
    assert "hidden_oracle" not in json.dumps(output)
    assert "NEVER_EXPORT" not in json.dumps(output)


def test_unregistered_ex6_is_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="NATIVE_EX6_REGISTRATION_PENDING_CLAUDE"):
        load_registration(tmp_path, "ex6")
