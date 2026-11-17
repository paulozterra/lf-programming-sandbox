"""T32: attempts spent on a replaced defective exam are forgiven, exactly."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_run_history as history  # noqa: E402
from native_examiner_defect import verified_examiner_defects  # noqa: E402

TASK = "synthetic1"
PACK = "b" * 64
OLD_EXAM, NEW_EXAM = "1" * 64, "2" * 64
SHA_BAD, SHA_NEW, SHA_REAL = "a" * 40, "c" * 40, "d" * 40


def record(holdout=NEW_EXAM):
    return {"holdout_sha256": holdout, "task_spec": {}}


def write(root, **over):
    data = {"schema_version": "LF_NATIVE_EXAMINER_DEFECT_V1", "task": TASK,
            "superseded_holdout_sha256": OLD_EXAM,
            "current_holdout_sha256": NEW_EXAM,
            "forgiven": [{"run_id": 200, "proposal_commit_sha": SHA_BAD,
                          "task_pack_sha256": PACK}],
            "reason": "exam assumed a session it never established"}
    data.update(over)
    path = root / "pilot/worker_v08/examiner_defects" / (TASK + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_valid_record_forgives_exact_runs(tmp_path):
    write(tmp_path)
    assert verified_examiner_defects(tmp_path, TASK, record()) == {
        200: {"proposal_commit_sha": SHA_BAD, "task_pack_sha256": PACK}}


@pytest.mark.parametrize("over,rec", [
    ({}, record(OLD_EXAM)),                                   # exam not replaced
    ({"current_holdout_sha256": OLD_EXAM}, record(OLD_EXAM)), # same exam
    ({"task": "other"}, record()),
    ({"reason": " "}, record()),
    ({"forgiven": []}, record()),
    ({"forgiven": [{"run_id": 200}]}, record()),
    ({"extra": 1}, record()),
])
def test_invalid_records_forgive_nothing(tmp_path, over, rec):
    write(tmp_path, **over)
    assert verified_examiner_defects(tmp_path, TASK, rec) == {}


def test_missing_record_forgives_nothing(tmp_path):
    assert verified_examiner_defects(tmp_path, TASK, record()) == {}


def _run(i, sha, conclusion="failure"):
    return {"id": i, "event": "workflow_run", "head_branch": "main", "run_attempt": 1,
            "display_title": f"lf-native-auto-lf/native-proposal/{TASK}-{sha}",
            "status": "completed", "conclusion": conclusion}


def _admit(tmp_path, forgiven):
    runs = [_run(400, SHA_NEW, None), _run(100, SHA_REAL), _run(200, SHA_BAD)]
    runs[0]["status"] = "in_progress"
    proofs = {100: {"task_id": TASK, "attempt": 1, "run_id": 100, "task_pack_sha256": PACK},
              200: {"task_id": TASK, "attempt": 2, "run_id": 200, "task_pack_sha256": PACK}}
    with patch.object(history, "_api", return_value={"total_count": 3, "workflow_runs": runs}), \
         patch.object(history, "_artifact_json", side_effect=lambda b, t, i: proofs.get(i)), \
         patch("native_route_defect.verified_migration", return_value=None), \
         patch("native_examiner_defect.verified_examiner_defects", return_value=forgiven):
        return history.admit_attempt(
            repository="paulozterra/lf-programming-sandbox", token="offline",
            task=TASK, attempt=None, run_id=400, run_attempt=1, sha=SHA_NEW,
            output=tmp_path / "h.json", event="workflow_run",
            proposal_branch="lf/native-proposal/" + TASK)


def test_forgiven_run_does_not_spend_attempt(tmp_path):
    forgiven = {200: {"proposal_commit_sha": SHA_BAD, "task_pack_sha256": PACK}}
    assert _admit(tmp_path, forgiven) == 2
    assert json.loads((tmp_path / "h.json").read_text())["route_defect_run_ids"] == [200]


def test_without_record_both_failures_count(tmp_path):
    assert _admit(tmp_path, {}) == 3


def test_forgiveness_bound_to_exact_proposal_commit(tmp_path):
    wrong = {200: {"proposal_commit_sha": SHA_REAL, "task_pack_sha256": PACK}}
    assert _admit(tmp_path, wrong) == 3
