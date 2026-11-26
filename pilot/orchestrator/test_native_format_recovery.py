"""CP3.6 classification and feedback recovery regressions."""
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"pilot/worker_v08"))
from pilot.orchestrator.native_format_recovery import Recovery
import native_format_history as h
from test_native_format_history import row,evidence,envelope,TASK,SHA


def fixture(monkeypatch, statuses):
    r=Recovery(None,None,h.REPO,ROOT)
    rows=[row(i,str(i)*40) for i in range(1,len(statuses)+1)]
    data={i:evidence(i,str(i)*40,envelope("patch"+str(i)),status)
          for i,status in enumerate(statuses,1)}
    monkeypatch.setattr(r,"task_rows",lambda task:rows)
    monkeypatch.setattr(r,"result",lambda run,task:data[run["id"]])
    monkeypatch.setattr(h,"envelope_at",lambda api,task,sha:envelope("patch1" if sha=="1"*40 else "corrected"))
    return r


def test_rejected_never_redispatched(monkeypatch):
    r=fixture(monkeypatch,["FORMAT_FAIL"])
    for _ in range(5):
        assert r.decision(TASK,"1"*40)=="FORMAT_DUPLICATE_REJECTED_PATCH"
    assert r.decision(TASK,SHA)=="CONTINUE"


def test_exhausted(monkeypatch):
    assert fixture(monkeypatch,["FORMAT_FAIL"]*3).decision(TASK,SHA)=="FORMAT_REJECTION_LIMIT_EXCEEDED"


@pytest.mark.parametrize("status,expected",[("BASELINE_FAIL","BASELINE_FAIL"),("INVALID_PROPOSAL","INVALID_PROPOSAL"),
                                            ("INFRA_ERROR","FORMAT_INFRA_RETRY"),("PASS","CONTINUE"),("SKIPPED","CONTINUE")])
def test_status(monkeypatch,status,expected):
    assert fixture(monkeypatch,[status]).decision(TASK,"1"*40)==expected


def test_feedback_recovery_only(monkeypatch):
    from datetime import datetime,timezone
    r=fixture(monkeypatch,["FORMAT_FAIL"])
    r._boundary=datetime(2026,11,26,tzinfo=timezone.utc)
    monkeypatch.setattr(r,"rows",lambda:[row(1,"1"*40,status="cancelled")])
    calls=[]
    monkeypatch.setattr(h,"publish",lambda *args:calls.append(args[-1]) or "FORMAT_FEEDBACK_PUBLISHED")
    assert r.recover_feedback(lambda task:True)[0]["status"]=="FORMAT_FEEDBACK_PUBLISHED"
    assert len(calls)==1
    assert r.recover_feedback(lambda task:False)==[]


def test_workflow_and_sweep_wired():
    source=(ROOT/"pilot/orchestrator/chain_lots.py").read_text()
    assert "format_recovery.decision" in source
    assert "format_recovery.recover_feedback" in source
    assert "FORMAT_INFRA_RETRY" in (ROOT/"pilot/orchestrator/native_infra_retry.py").read_text()
    assert "format_decision" in (ROOT/"pilot/orchestrator/native_pending_recovery.py").read_text()


def test_distinct_governed_format_block(monkeypatch):
    from datetime import datetime,timezone
    from pilot.orchestrator import chain_contract
    r=fixture(monkeypatch,["FORMAT_FAIL"]*3)
    r._boundary=datetime(2026,11,26,tzinfo=timezone.utc)
    monkeypatch.setattr(r,"rows",lambda:[row(i,str(i)*40) for i in range(1,4)])
    monkeypatch.setattr(h,"publish",lambda *a:"FORMAT_FEEDBACK_ALREADY_PUBLISHED")
    outcomes=r.recover_feedback(lambda task:True)
    assert r.exhausted_tasks=={TASK}
    assert outcomes[-1]["reason"]==chain_contract.FORMAT_BLOCK_CODE
    state=chain_contract.blocked_state({"stage":"LOTS_PLANNED"},
            {"stage":"BLOCKED","reason_code":chain_contract.FORMAT_BLOCK_CODE,"blocked_lot_ids":["LOT"]})
    assert state["reason_code"]=="FORMAT_REJECTION_LIMIT_EXCEEDED"
    assert state["handoff_allowed"] is False
