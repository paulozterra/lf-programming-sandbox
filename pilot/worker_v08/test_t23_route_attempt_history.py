"""T23 attempt accounting: route-owned failures never spend a constructor slot."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_run_history as history

TASK = "synthetic1"
SHA = "a" * 40
OLD_PACK = "b" * 64
PROOF = {"task_id": TASK, "attempt": 1, "run_id": 200,
         "task_pack_sha256": OLD_PACK}
CURRENT = {"id": 300, "event": "workflow_dispatch",
           "head_branch": "main", "run_attempt": 1,
           "display_title": f"lf-native-route-retry-{TASK}-{SHA}"}
OLD = {"id": 200, "event": "workflow_dispatch",
       "head_branch": "main", "run_attempt": 1,
       "display_title": f"lf-native-infra-retry-{TASK}-{SHA}",
       "status": "completed", "conclusion": "failure"}


def test_replayed_route_defect_is_recorded_but_not_counted(tmp_path):
    mapping = {"source_run_id": 200, "proposal_commit_sha": SHA,
               "legacy_task_pack_sha256": OLD_PACK}
    def api(*args):
        return {"total_count": 2, "workflow_runs": [CURRENT, OLD]}
    dest = tmp_path / "history.json"
    with patch.object(history, "_api", side_effect=api), \
         patch.object(history, "_artifact_json", return_value=PROOF), \
         patch("native_route_defect.verified_migration", return_value=mapping):
        attempt = history.admit_attempt(
            repository="paulozterra/lf-programming-sandbox",
            token="offline", task=TASK, attempt=1,
            run_id=300, run_attempt=1, sha=SHA, output=dest,
            route_retry=True)
    assert attempt == 1
    written = json.loads(dest.read_text())
    assert written["prior_run_ids"] == []
    assert written["route_defect_run_ids"] == [200]
    assert written["attempt"] == 1


def test_replay_requires_verified_migration_and_exact_original_pack(tmp_path):
    def api(*args):
        return {"total_count": 2, "workflow_runs": [CURRENT, OLD]}
    mapping = {"source_run_id": 200, "proposal_commit_sha": SHA,
               "legacy_task_pack_sha256": OLD_PACK}
    with patch.object(history, "_api", side_effect=api), \
         patch.object(history, "_artifact_json", return_value=PROOF), \
         patch("native_route_defect.verified_migration", return_value=None):
        with pytest.raises(ValueError, match="NATIVE_ROUTE_RETRY_NOT_ATTESTED"):
            history.admit_attempt(repository="paulozterra/lf-programming-sandbox",
                                  token="offline", task=TASK, attempt=1,
                                  run_id=300, run_attempt=1, sha=SHA,
                                  output=tmp_path / "not-admitted.json",
                                  route_retry=True)
    with patch.object(history, "_api", side_effect=api), \
         patch.object(history, "_artifact_json", return_value={
             **PROOF, "task_pack_sha256": "c" * 64}), \
         patch("native_route_defect.verified_migration", return_value=mapping):
        with pytest.raises(ValueError, match="NATIVE_DUPLICATE_PROPOSAL_SHA"):
            history.admit_attempt(repository="paulozterra/lf-programming-sandbox",
                                  token="offline", task=TASK, attempt=1,
                                  run_id=300, run_attempt=1, sha=SHA,
                                  output=tmp_path / "bad.json",
                                  route_retry=True)


def test_route_replay_name_is_bound_to_task_sha_and_attempt_one():
    assert history._recognized_run(CURRENT, TASK, attempt=1, sha=SHA)
    assert not history._recognized_run(CURRENT, TASK, attempt=2, sha=SHA)
    assert not history._recognized_run(CURRENT, TASK, attempt=1, sha="e" * 40)
