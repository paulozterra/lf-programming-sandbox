"""Offline auto-launch admission tests: no GitHub network or hidden oracle."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from native_run_history import admit_attempt


def run(number, *, event="push", branch="lf/native-proposal/ex6",
        head_sha=None, title=None, status="completed"):
    return {
        "id": 900 + number,
        "event": event,
        "head_branch": branch if event == "push" else "main",
        "head_sha": head_sha or ("%040x" % (number + 30)),
        "display_title": title or (
            "lf-native-ex6-push" if event == "push" else "lf-native-ex6-a" + str(number)),
        "status": status,
        "run_attempt": 1,
    }


def proof(n):
    return {"task_id": "ex6", "attempt": n,
            "task_pack_sha256": "%064x" % n, "run_id": 900 + n}


def call(tmp_path, runs, proofs, *, attempt=None, current=None, sha=None,
         event="push", branch="lf/native-proposal/ex6"):
    cur = current or runs[-1]
    with (patch("native_run_history._api",
                return_value={"total_count": len(runs), "workflow_runs": runs}),
          patch("native_run_history._artifact_json",
                side_effect=lambda repo, token, rid: proofs.get(rid))):
        return admit_attempt(
            repository="paulozterra/lf-programming-sandbox",
            token="offline", task="ex6", attempt=attempt,
            run_id=cur["id"], run_attempt=1,
            sha=sha or cur["head_sha"], output=tmp_path/"history.json",
            github_output=tmp_path/"github_output", event=event,
            head_branch=branch)


def test_push_first_attempt_derived(tmp_path):
    current = run(1, status="in_progress")
    assert call(tmp_path, [current], {}) == 1
    assert json.loads((tmp_path/"history.json").read_text())["attempt"] == 1
    assert (tmp_path/"github_output").read_text() == "attempt=1\n"


def test_manual_and_push_receipts_share_single_counter(tmp_path):
    a = run(1, event="workflow_dispatch")
    b = run(2)
    c = run(3, status="in_progress")
    assert call(tmp_path, [a,b,c], {a["id"]:proof(1), b["id"]:proof(2)}) == 3
    assert json.loads((tmp_path/"history.json").read_text())["prior_run_ids"] == [901,902]


def test_no_proof_does_not_consume_attempt(tmp_path):
    failed = run(1)
    current = run(2, status="in_progress")
    assert call(tmp_path, [failed,current], {}) == 1


def test_fourth_attempt_blocked(tmp_path):
    prior = [run(i) for i in (1,2,3)]
    fourth = run(4,status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_ATTEMPT_LIMIT_EXCEEDED"):
        call(tmp_path, prior+[fourth], {r["id"]:proof(i) for i,r in enumerate(prior,1)})


def test_same_proposal_sha_cannot_consume_another_attempt(tmp_path):
    old = run(1,head_sha="a"*40)
    current = run(2,head_sha="a"*40,status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_DUPLICATE_PROPOSAL_SHA"):
        call(tmp_path,[old,current],{901:proof(1)})


def test_push_wrong_branch_fails_closed(tmp_path):
    current = run(1,branch="other/branch",status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_ADMISSION_INPUT_INVALID"):
        call(tmp_path,[current],{},branch="other/branch")


def test_push_wrong_title_rejected(tmp_path):
    current = run(1,title="spoofed-run",status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_CURRENT_RUN_NOT_ATTESTED"):
        call(tmp_path,[current],{})


def test_manual_mismatched_attempt_is_rejected(tmp_path):
    current = run(2,event="workflow_dispatch",status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_ATTEMPT_COUNT_MISMATCH"):
        call(tmp_path,[current],{},attempt=2,event="workflow_dispatch",branch="main")


def test_tampered_prior_push_receipt_fails_closed(tmp_path):
    old = run(1)
    current = run(2,status="in_progress")
    invalid = dict(proof(1),task_pack_sha256="bad")
    with pytest.raises(ValueError,match="NATIVE_ATTEMPT_LIMIT_OR_HISTORY_INVALID"):
        call(tmp_path,[old,current],{901:invalid})
