"""H15/H16: task enrollment, historical boundary and actual R1 dispatch."""
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

import native_format_activation as a
import native_format_history as h
from pilot.orchestrator.native_format_recovery import Recovery
from pilot.orchestrator import native_pending_recovery as pending

TASK="synthetic"
SHA="a"*40
ROOT=Path(__file__).resolve().parents[2]
WHEN=datetime(2026,11,26,20,tzinfo=timezone.utc)


def raw(tasks):
    return json.dumps({"schema_version":a.SCHEMA,"tasks":tasks})


def test_merge_default_off_without_history(monkeypatch):
    assert a.policy_at_root()=={}
    monkeypatch.setattr(a,"git_policy",lambda *args:{})
    assert not a.select(ROOT,TASK,SHA,lambda *args:pytest.fail("history queried"))
    r=Recovery(None,lambda *args:pytest.fail("history queried"),h.REPO,ROOT)
    assert r.decision(TASK,SHA)=="CONTINUE"
    assert r.pending_decision(TASK,SHA)=="CONTINUE"
    assert r.recover_feedback(lambda task:True)==[]


def test_enrollment_is_task_scoped(monkeypatch):
    monkeypatch.setattr(a,"policy_at_root",lambda root:{TASK:900})
    monkeypatch.setattr(a,"git_policy",lambda *args:{TASK:900})
    monkeypatch.setattr(a,"load_registration",lambda *args:({},None))
    monkeypatch.setattr(a,"parse_worker_task",lambda value:object())
    monkeypatch.setattr(a,"load",lambda *args,**kw:{})
    monkeypatch.setattr(a,"active_project",lambda **kw:"test")
    monkeypatch.setattr(a,"_select",lambda *args:object())
    monkeypatch.setattr(a,"boundary",lambda *args:WHEN)
    assert a.select(ROOT,TASK,SHA,None)
    assert not a.select(ROOT,"other",SHA,None)
    # A run queued with an older workflow snapshot cannot acquire enrollment.
    monkeypatch.setattr(a,"git_policy",lambda *args:{})
    assert not a.select(ROOT,TASK,SHA,None)
    monkeypatch.setattr(a,"_select",lambda *args:None)
    with pytest.raises(ValueError,match="NO_REGISTERED_SPOTLESS"):
        a.eligible(ROOT,TASK,{TASK:900})


@pytest.mark.parametrize("tasks",[{TASK:899},{TASK:816},{TASK:True},{"*":900}])
def test_invalid_or_rewritten_policy(tasks):
    if tasks=={TASK:899}:
        with pytest.raises(ValueError,match="HISTORY_REWRITE"):
            a.assert_append_only({TASK:900},tasks)
    else:
        with pytest.raises(ValueError):
            a.parse_policy(raw(tasks))


def test_real_merge_metadata_required(monkeypatch):
    monkeypatch.setattr(h,"cutover",lambda api:WHEN)
    b=raw({TASK:900}).encode()
    pr={"number":900,"merged":True,"merge_commit_sha":SHA,"merged_at":WHEN.isoformat(),
        "base":{"ref":"main","repo":{"full_name":h.REPO}},"head":{"repo":{"full_name":h.REPO}}}
    content={"type":"file","encoding":"base64","size":len(b),"content":base64.b64encode(b).decode()}
    api=lambda route:pr if route=="pulls/900" else content
    assert a.boundary(api,TASK,{TASK:900})==WHEN
    pr["merged"]=False
    with pytest.raises(ValueError,match="PR_UNVERIFIED"):
        a.boundary(api,TASK,{TASK:900})


def retry_row(created):
    return {"id":1,"status":"completed","conclusion":"cancelled","event":"workflow_dispatch",
            "display_title":f"lf-native-pending-retry-{TASK}-{SHA}",
            "created_at":created,"head_branch":"main","run_attempt":1,
            "repository":{"full_name":h.REPO},"path":".github/workflows/worker-native.yml"}


@pytest.mark.parametrize("enabled,created,expected",[
    (False,"2026-11-27T00:00:00Z","R1_WORKER_PENDING_REDISPATCHED"),
    (True,"2026-11-25T00:00:00Z","R1_WORKER_PENDING_REDISPATCHED"),
    (True,"2026-11-27T00:00:00Z","FORMAT_PENDING_RETRY_EXHAUSTED"),
])
def test_real_r1_scope(monkeypatch,tmp_path,enabled,created,expected):
    prior=retry_row(created)
    regs=tmp_path/"registrations"
    regs.mkdir()
    (regs/(TASK+".json")).write_text("{}")
    monkeypatch.setattr(pending,"storage_path",lambda *args,**kw:regs)
    monkeypatch.setattr(pending,"validate_proposal_only",lambda *args,**kw:{"task":TASK})
    monkeypatch.setattr(pending,"_artifact_json",lambda *args,**kw:None)
    monkeypatch.setenv("GH_TOKEN","offline")
    calls=[]
    def run(*args):
        calls.append(args)
        if args[:3]==("git","ls-remote","--heads"):
            return f"{SHA}\trefs/heads/lf/native-proposal/{TASK}"
        return ""
    api=lambda route:{"total_count":1,"workflow_runs":[prior]}
    r=Recovery(run,api,h.REPO,tmp_path)
    monkeypatch.setattr(r,"enabled",lambda task:enabled)
    monkeypatch.setattr(r,"boundary",lambda task:WHEN)
    monkeypatch.setattr(r,"result",lambda *args:None)
    result=pending.recover("f"*40,run,api,h.REPO,tmp_path,allowed_task=lambda task:True,
                           format_decision=r.pending_decision)
    assert result[0]["status"]==expected,result
    assert any(x[:3]==("gh","workflow","run") for x in calls)==(expected=="R1_WORKER_PENDING_REDISPATCHED")


def test_workflow_only_optional_gates_are_conditional():
    workflow=(ROOT/".github/workflows/worker-native.yml").read_text()
    assert workflow.index("Determine and gate attempt") < workflow.index("Resolve governed format activation")
    for step in ("format_budget","format"):
        block=workflow.split("        id: "+step+"\n",1)[1].split("      - name:",1)[0]
        assert "if: "+chr(36)+"{{ steps.format_activation.outputs.enabled == 'true' }}" in block
    original=workflow.split("      - name: Execute original run_verified_worker",1)[1].split("      - name:",1)[0]
    assert "format_activation" not in original
