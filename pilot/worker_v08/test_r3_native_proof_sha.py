"""R3-b/R3-c: immutable proof admission and SHA-attested manual runs (no Worker/model)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
import native_run_history as h

REPO = "paulozterra/lf-programming-sandbox"
TASK = "ex6"
SHA = "a" * 40
OTHER = "b" * 40
WORKFLOW = ROOT / ".github/workflows/worker-native.yml"


def run(identity, title, *, completed=True):
    return {"id": identity, "event": "workflow_dispatch", "head_branch": "main",
            "run_attempt": 1, "display_title": title,
            "status": "completed" if completed else "in_progress",
            "conclusion": "failure" if completed else None}


def title(task=TASK, sha=SHA, request=None, ordinal=1):
    prefix = f"{request}-" if request else ""
    return f"lf-native-{prefix}{task}-a{ordinal}-{sha}"


def admission(tmp_path, past, *, old_proof=None, worker_conclusion="failure",
              marker=None, attempt=1, proposal_sha=SHA):
    current = run(900, title(sha=proposal_sha, ordinal=attempt), completed=False)
    records = [current, past]
    def api(repo, token, route):
        if "/runs?per_page=" in route:
            return {"total_count": len(records), "workflow_runs": records}
        if "/jobs?" in route:
            return {"total_count": 1, "jobs": [{"name": "native", "steps": [
                {"name": h._WORKER_STEP, "status": "completed",
                 "conclusion": worker_conclusion}]}]}
        if "/artifacts?" in route:
            return {"total_count": 0, "artifacts": []}
        raise AssertionError(route)
    def artifact(repo, token, rid, *, artifact_name=h._ARTIFACT):
        assert rid == past["id"]
        if artifact_name == h._NO_ATTEMPT_ARTIFACT:
            return marker
        return old_proof
    with patch.object(h, "_api", side_effect=api), patch.object(
            h, "_artifact_json", side_effect=artifact):
        return h.admit_attempt(
            repository=REPO, token="offline", task=TASK, attempt=attempt,
            run_id=900, run_attempt=1, sha=proposal_sha,
            output=tmp_path / "out.json")


def test_spent_worker_without_proof_must_fail_typed(tmp_path):
    prior = run(800, title(sha=OTHER))
    with pytest.raises(ValueError, match="^NATIVE_PRIOR_PROOF_MISSING$"):
        admission(tmp_path, prior, worker_conclusion="failure")


def test_pre_attempt_rejection_with_skipped_worker_does_not_count(tmp_path):
    prior = run(800, title(sha=OTHER))
    assert admission(tmp_path, prior, worker_conclusion="skipped") == 1
    assert json.loads((tmp_path / "out.json").read_text())["prior_run_ids"] == []



def test_cancelled_pending_run_without_any_job_is_not_an_attempt(tmp_path):
    prior = run(800, title(sha=OTHER))
    prior["conclusion"] = "cancelled"
    current = run(900, title(), completed=False)
    rows = [current, prior]
    def api(_repo, _token, route):
        if "/runs?per_page=" in route:
            return {"total_count": 2, "workflow_runs": rows}
        if "/jobs?" in route:
            return {"total_count": 0, "jobs": []}
        if "/artifacts?" in route:
            return {"total_count": 0, "artifacts": []}
        raise AssertionError(route)
    with patch.object(h, "_api", side_effect=api):
        assert h.admit_attempt(repository=REPO, token="offline", task=TASK,
                               attempt=1, run_id=900, run_attempt=1, sha=SHA,
                               output=tmp_path / "out.json") == 1



def test_trusted_no_attempt_marker_is_accepted_without_spending(tmp_path):
    prior = run(800, title(sha=OTHER))
    marker = {"schema_version": "LF_NATIVE_NO_ATTEMPT_V1", "task_id": TASK,
              "run_id": 800, "attempt": 1, "reason": "EXAMINER_CONTROL"}
    assert admission(tmp_path, prior, marker=marker) == 1


def test_mismatched_marker_does_not_erase_attempt(tmp_path):
    prior = run(800, title(sha=OTHER))
    marker = {"schema_version": "LF_NATIVE_NO_ATTEMPT_V1", "task_id": TASK,
              "run_id": 799, "attempt": 1, "reason": "EXAMINER_CONTROL"}
    with pytest.raises(ValueError, match="^NATIVE_PRIOR_PROOF_MISSING$"):
        admission(tmp_path, prior, marker=marker)


def test_new_manual_title_is_sha_bound_and_legacy_only_history():
    new = run(800, title())
    assert h._recognized_run(new, TASK, attempt=1, sha=SHA, allow_legacy_manual=False)
    assert not h._recognized_run(new, TASK, attempt=1, sha=OTHER)
    old = run(700, f"lf-native-{TASK}-a1")
    assert h._recognized_run(old, TASK, attempt=1)
    assert not h._recognized_run(old, TASK, attempt=1, allow_legacy_manual=False)


def test_request_slug_is_metadata_and_legacy_prefix_is_history_only():
    canonical = run(800, title())
    assert h._recognized_run(canonical, TASK, attempt=1, sha=SHA,
                             allow_legacy_manual=False)
    # No post-R3 manual run may use a scoped SHA title: it would be
    # indistinguishable from a registered task named req-286-ex6.
    scoped = run(801, title(request="req-286"))
    assert not h._recognized_run(scoped, TASK, attempt=1, sha=SHA,
                                 allow_legacy_manual=False)
    old = run(700, f"lf-native-req-286-{TASK}-a1")
    assert h._recognized_run(old, TASK, attempt=1)
    assert not h._recognized_run(old, TASK, attempt=1,
                                 allow_legacy_manual=False)



def test_req_prefixed_task_name_is_resolved_from_registered_task_not_greedy_slug():
    ambiguous_task = "req-286-test"
    candidate = run(810, title(task=ambiguous_task, sha=SHA))
    assert h._recognized_run(
        candidate, ambiguous_task, attempt=1, sha=SHA, allow_legacy_manual=False)
    assert not h._recognized_run(candidate, TASK, attempt=1, sha=SHA)



def test_duplicate_manual_sha_is_rejected_even_with_valid_prior_proof(tmp_path):
    prior = run(800, title())
    proof = {"task_id": TASK, "attempt": 1, "task_pack_sha256": "c" * 64,
             "run_id": 800}
    with pytest.raises(ValueError, match="^NATIVE_DUPLICATE_PROPOSAL_SHA$"):
        admission(tmp_path, prior, old_proof=proof, attempt=2)


def test_old_manual_attempt_with_valid_proof_remains_counted(tmp_path):
    prior = run(800, f"lf-native-{TASK}-a1")
    proof = {"task_id": TASK, "attempt": 1, "task_pack_sha256": "c" * 64,
             "run_id": 800}
    assert admission(tmp_path, prior, old_proof=proof, attempt=2) == 2


def test_expired_artifact_rejected_without_legacy_grandfather():
    with patch.object(h, "_api", return_value={"total_count": 1, "artifacts": [{
            "name": "native-attempt-proof", "expired": True,
            "workflow_run": {"id": 800}}]}):
        with pytest.raises(ValueError, match="^NATIVE_PRIOR_PROOF_MISSING$"):
            h._artifact_json(REPO, "offline", 800)


def test_native_job_skipped_without_steps_is_definitely_not_an_attempt():
    old = {"id": 745, "status": "completed", "conclusion": "skipped",
           "event": "workflow_run", "head_branch": "main", "run_attempt": 1,
           "display_title": "lf-native-auto-lf/native-proposal/ex6-" + OTHER}
    with patch.object(h, "_artifact_json", return_value=None), patch.object(
            h, "_api", return_value={"total_count": 1, "jobs": [
                {"name": "native", "conclusion": "skipped"}]}):
        assert h._no_attempt_attested(REPO, "offline", old, TASK)


def test_pr370_merge_sha_is_immutable_cutover_reference():
    from datetime import datetime, timezone
    data = {"merged": True, "merge_commit_sha": "f" * 40,
            "merged_at": "2026-11-21T10:00:00Z"}
    with patch.object(h, "_api", return_value=data):
        sha, cutover = h._r3_merge_cutover(REPO, "offline")
    assert sha == "f" * 40
    assert cutover == datetime(2026, 11, 21, 10, tzinfo=timezone.utc)
    with patch.object(h, "_api", return_value={**data, "merged": False}):
        with pytest.raises(ValueError, match="NATIVE_PROOF_CUTOFF_UNRESOLVED"):
            h._r3_merge_cutover(REPO, "offline")


def test_old_missing_proof_worker_failure_is_legacy_but_new_fails(tmp_path):
    from datetime import datetime, timezone
    prior = run(800, title(sha=OTHER))
    prior["created_at"] = "2026-11-19T10:00:00Z"
    cut = ("f" * 40, datetime(2026, 11, 20, 12, tzinfo=timezone.utc))
    with patch.object(h, "_r3_merge_cutover", return_value=cut):
        assert admission(tmp_path, prior, worker_conclusion="failure") == 1
    prior["created_at"] = "2026-11-21T10:00:00Z"
    with patch.object(h, "_r3_merge_cutover", return_value=cut):
        with pytest.raises(ValueError, match="^NATIVE_PRIOR_PROOF_MISSING$"):
            admission(tmp_path, prior, worker_conclusion="failure")


def test_expired_proof_old_is_legacy_new_is_blocked(tmp_path):
    from datetime import datetime, timezone
    prior = run(800, title(sha=OTHER))
    prior["created_at"] = "2026-11-19T10:00:00Z"
    current = run(900, title(), completed=False)
    cut = ("f" * 40, datetime(2026, 11, 20, 12, tzinfo=timezone.utc))
    def api(_repo, _token, route):
        if "/runs?per_page=" in route:
            return {"total_count": 2, "workflow_runs": [current, prior]}
        raise AssertionError(route)
    def artifact(_repo, _token, rid):
        assert rid == 800
        raise ValueError("NATIVE_PRIOR_PROOF_MISSING")
    with patch.object(h, "_api", side_effect=api), patch.object(
            h, "_artifact_json", side_effect=artifact), patch.object(
            h, "_r3_merge_cutover", return_value=cut):
        assert h.admit_attempt(repository=REPO, token="offline", task=TASK,
                               attempt=1, run_id=900, run_attempt=1,
                               sha=SHA, output=tmp_path / "old.json") == 1
        prior["created_at"] = "2026-11-21T10:00:00Z"
        with pytest.raises(ValueError, match="^NATIVE_PRIOR_PROOF_MISSING$"):
            h.admit_attempt(repository=REPO, token="offline", task=TASK,
                            attempt=1, run_id=900, run_attempt=1,
                            sha=SHA, output=tmp_path / "new.json")


def test_historical_exception_disables_legacy_skip():
    from datetime import datetime, timezone
    prior = {"id": 800, "created_at": "2026-11-19T10:00:00Z"}
    cut = ("f" * 40, datetime(2026, 11, 20, 12, tzinfo=timezone.utc))
    with patch.object(h, "_r3_historical_exceptions", return_value=frozenset()):
        assert h._r3_pre_cutover(REPO, "offline", prior, cut)
    with patch.object(h, "_r3_historical_exceptions", return_value=frozenset({800})):
        assert not h._r3_pre_cutover(REPO, "offline", prior, cut)


def test_workflow_requires_either_proof_or_same_job_no_attempt_marker():
    # This job deliberately runs without optional PyYAML installed.
    content = WORKFLOW.read_text(encoding="utf-8")
    assert "- name: Require durable attempt or trusted NO_ATTEMPT evidence" in content
    assert "NATIVE_ATTEMPT_EVIDENCE_MISSING" in content
    assert 'test -s "$proof"' in content
    assert 'test -s "$marker"' in content
    assert "steps.worker.outcome" in content
    assert "name: native-no-attempt" in content
    assert "inputs.proposal_commit_sha" in content
    assert "inputs.request_slug" not in content.splitlines()[1]
    assert "MANUAL_REQUEST_SLUG: ${{ inputs.request_slug }}" in content
    assert "cancel-in-progress: false" in content
