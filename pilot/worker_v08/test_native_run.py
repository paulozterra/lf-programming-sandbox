"""Offline S2 controls: run history comes from Actions; feedback is visible only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

from native_run_history import admit_attempt
from native_run import _visible_feedback, load_registration


def _run(i: int) -> dict:
    return {
        "id": 700 + i, "display_title": f"lf-native-ex6-a{i}",
        "head_branch": "main", "event": "workflow_dispatch",
        "run_attempt": 1, "status": "completed" if i < 3 else "in_progress",
    }


def _github_response(runs: list[dict]) -> dict:
    return {"total_count": len(runs), "workflow_runs": runs}


def _proof(i: int) -> dict:
    return {"task_id": "ex6", "attempt": i,
            "task_pack_sha256": f"{i:064x}", "run_id": 700 + i}


def admission(tmp_path: Path, attempt: int, runs: list[dict]) -> None:
    with (patch("native_run_history._api", return_value=_github_response(runs)),
          patch("native_run_history._artifact_json", side_effect=lambda repo, token, rid: _proof(rid - 700))):
        admit_attempt(repository="paulozterra/lf-programming-sandbox",
                      token="offline-test", task="ex6", attempt=attempt,
                      run_id=700 + attempt, run_attempt=1,
                      sha="f" * 40, output=tmp_path / "history.json")


def test_admit_first_and_third(tmp_path):
    admission(tmp_path, 1, [_run(1)])
    assert json.loads((tmp_path / "history.json").read_text())["prior_run_ids"] == []
    admission(tmp_path, 3, [_run(1), _run(2), _run(3)])
    assert json.loads((tmp_path / "history.json").read_text())["prior_run_ids"] == [701, 702]


def test_fourth_attempt_cannot_reuse_history(tmp_path):
    with pytest.raises(ValueError, match="NATIVE_ADMISSION_INPUT_INVALID"):
        admission(tmp_path, 4, [_run(1), _run(2), _run(3)])


def test_duplicate_or_skipped_attempt_is_blocked(tmp_path):
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT_HISTORY_GAP_OR_DUPLICATE"):
        admission(tmp_path, 2, [_run(1), _run(1), _run(2)])
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT_HISTORY_GAP_OR_DUPLICATE"):
        admission(tmp_path, 3, [_run(1), _run(3)])


def test_missing_prior_artifact_blocks(tmp_path):
    with (patch("native_run_history._api", return_value=_github_response([_run(1), _run(2)])),
          patch("native_run_history._artifact_json", side_effect=ValueError("NATIVE_PRIOR_PROOF_MISSING_OR_DUPLICATE"))):
        with pytest.raises(ValueError, match="NATIVE_PRIOR_PROOF_MISSING_OR_DUPLICATE"):
            admit_attempt(repository="paulozterra/lf-programming-sandbox",
                          token="offline-test", task="ex6", attempt=2,
                          run_id=702, run_attempt=1, sha="a" * 40,
                          output=tmp_path / "history.json")


def test_rerun_blocked(tmp_path):
    with pytest.raises(ValueError, match="NATIVE_ADMISSION_INPUT_INVALID"):
        with patch("native_run_history._api", return_value=_github_response([_run(1)])):
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
