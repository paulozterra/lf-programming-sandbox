"""Offline privileged workflow_run attempt admission; no secrets, network or holdout."""
from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from native_run_history import admit_attempt

def run(n, *, task="ex6", event="workflow_run", sha=None, title=None, status="completed"):
    sha=sha or ("%040x"%(n+30))
    display=(f"lf-native-auto-lf/native-proposal/{task}-{sha}"
             if event=="workflow_run" else f"lf-native-{task}-a{n}")
    return {"id":900+n,"event":event,"head_branch":"main",
            "head_sha":"f"*40,"display_title":title or display,
            "status":status,"run_attempt":1}
def proof(n,task="ex6"):
    return {"task_id":task,"attempt":n,
            "task_pack_sha256":"%064x"%n,"run_id":900+n}
def call(tmp_path,runs,proofs,*,task="ex6",attempt=None,current=None,sha=None,
         event="workflow_run",branch=None):
    cur=current or runs[-1]
    if sha is None:
        name=cur["display_title"]
        sha=name[-40:] if event=="workflow_run" else "a"*40
    if branch is None and event=="workflow_run":
        branch="lf/native-proposal/"+task
    with (patch("native_run_history._api",
                return_value={"total_count":len(runs),"workflow_runs":runs}),
          patch("native_run_history._artifact_json",
                side_effect=lambda repo,token,rid:proofs.get(rid))):
        return admit_attempt(repository="paulozterra/lf-programming-sandbox",
            token="offline",task=task,attempt=attempt,run_id=cur["id"],
            run_attempt=1,sha=sha,output=tmp_path/"history.json",
            github_output=tmp_path/"github_output",event=event,
            head_branch="main",proposal_branch=branch)

def test_first_workflow_run_attempt(tmp_path):
    current=run(1,status="in_progress")
    assert call(tmp_path,[current],{})==1
    assert (tmp_path/"github_output").read_text()=="attempt=1\n"

def test_manual_and_workflow_run_share_attempt_counter(tmp_path):
    a=run(1,event="workflow_dispatch")
    b=run(2)
    c=run(3,status="in_progress")
    assert call(tmp_path,[a,b,c],{901:proof(1),902:proof(2)})==3

def test_other_registered_task_independent_counter(tmp_path):
    old=run(1,task="ex6")
    current=run(2,task="sample",status="in_progress")
    assert call(tmp_path,[old,current],{901:proof(1)},task="sample")==1

def test_no_proof_does_not_consume_attempt(tmp_path):
    assert call(tmp_path,[run(1),run(2,status="in_progress")],{})==1

def test_fourth_attempt_denied(tmp_path):
    prior=[run(i) for i in (1,2,3)]
    current=run(4,status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_ATTEMPT_LIMIT_EXCEEDED"):
        call(tmp_path,prior+[current],{900+i:proof(i) for i in (1,2,3)})

def test_duplicate_proposal_sha_denied(tmp_path):
    prior=run(1,sha="a"*40)
    current=run(2,sha="a"*40,status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_DUPLICATE_PROPOSAL_SHA"):
        call(tmp_path,[prior,current],{901:proof(1)})

def test_trigger_branch_task_mismatch_denied(tmp_path):
    current=run(1,status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_ADMISSION_INPUT_INVALID"):
        call(tmp_path,[current],{},branch="lf/native-proposal/sample")

def test_spoofed_current_title_denied(tmp_path):
    current=run(1,title="untrusted-source",status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_CURRENT_RUN_NOT_ATTESTED"):
        call(tmp_path,[current],{},sha="a"*40)

def test_manual_requested_ordinal_mismatch(tmp_path):
    cur=run(2,event="workflow_dispatch",status="in_progress")
    with pytest.raises(ValueError,match="NATIVE_ATTEMPT_COUNT_MISMATCH"):
        call(tmp_path,[cur],{},attempt=2,event="workflow_dispatch",branch=None)

def test_tampered_prior_proof_denied(tmp_path):
    old=run(1)
    current=run(2,status="in_progress")
    invalid=dict(proof(1),task_pack_sha256="bad")
    with pytest.raises(ValueError,match="NATIVE_ATTEMPT_LIMIT_OR_HISTORY_INVALID"):
        call(tmp_path,[old,current],{901:invalid})
