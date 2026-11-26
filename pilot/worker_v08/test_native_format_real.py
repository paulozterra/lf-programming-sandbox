"""CI-only real Maven/Spotless test, no real registration, examiner or proposal."""
import json
import os
from dataclasses import replace
import pytest

from test_native_format_preflight import baseline, git, JAVA, POM, CONFIG, CHECK, proposal, ROOT
import native_format_admission as admission
import native_format_preflight as preflight
import native_format_history as history
from programming_agent_runner.hashutil import sha256_json
from pilot.orchestrator.native_format_recovery import Recovery

pytestmark=pytest.mark.skipif(os.environ.get("LF_TEST_REAL_SPOTLESS")!="YES",reason="CI real Maven opt-in")


def test_real_spotless_rejection_and_correction(baseline,tmp_path,monkeypatch):
    source,spec=baseline
    (source/POM).write_text((ROOT/"apps/time-service/pom.xml").read_text())
    git(source,"add",".")
    git(source,"-c","user.name=Test","-c","user.email=test@example.invalid","commit","-qm","real formatter")
    spec=replace(spec,base_head_sha=git(source,"rev-parse","HEAD"),acceptance_commands=(replace(CHECK,timeout_seconds=240),))
    checkout=tmp_path/"proposal"
    file=checkout/admission.proposal_path("synthetic")
    file.parent.mkdir(parents=True)
    # Exercise actual patch application and Spotless, with a synthetic
    # registration and pack boundary (already tested separately).
    def evaluate(control,source,checkout,task,sha,attempt,route_retry):
        submitted=admission.read_proposal_envelope(file)
        return preflight.prevalidate(source,spec,submitted["proposal"],CONFIG,total_timeout_seconds=300)
    monkeypatch.setattr(admission,"_evaluate",evaluate)
    def submit(value,run):
        env={"task_pack_sha256":"b"*64,"proposal_sha256":sha256_json(value),"proposal":value,"author":"GPT_NATIVE"}
        file.write_text(json.dumps(env))
        out=tmp_path/f"result-{run}"
        passed=admission.admit(tmp_path,source,checkout,"synthetic","a"*40,1,run,out)
        assert not (out/"attempt-proof.json").exists()
        return passed,json.loads((out/"format-result.json").read_text()),env
    ok,bad,env=submit(proposal(new="class Example{int  x;}"),1)
    assert not ok and bad["status"]=="FORMAT_FAIL",bad
    assert bad["paths"]==[JAVA] and bad["diagnostics"]
    assert (tmp_path/"result-1/no-attempt.json").is_file()
    history.validate(bad,"synthetic",1,"a"*40,"failure",env)
    r=Recovery(None,None,history.REPO,tmp_path)
    monkeypatch.setattr(r,"task_rows",lambda task:[{"id":1,"status":"completed"}])
    monkeypatch.setattr(r,"result",lambda row,task:bad)
    monkeypatch.setattr(history,"envelope_at",lambda *a:env)
    for _ in range(3):
        assert r.decision("synthetic","a"*40)=="FORMAT_DUPLICATE_REJECTED_PATCH"
    # Actual R1 dispatcher must not enqueue a cancelled run whose rejection
    # already has durable evidence, even on repeated CP3.6 sweeps.
    from pilot.orchestrator import native_pending_recovery as pending
    registrations=tmp_path/"registrations"
    registrations.mkdir()
    (registrations/"synthetic.json").write_text("{}")
    monkeypatch.setattr(pending,"storage_path",lambda *a,**kw:registrations)
    cancelled={"id":1,"status":"completed","conclusion":"cancelled",
               "display_title":"lf-native-auto-lf/native-proposal/synthetic-"+"a"*40}
    def run(*args):
        if args[:3]==("git","ls-remote","--heads"):
            return "a"*40+"\trefs/heads/lf/native-proposal/synthetic"
        pytest.fail("unexpected requeue: "+str(args[:3]))
    for _ in range(3):
        outcome=pending.recover("f"*40,run,lambda route:{"total_count":1,"workflow_runs":[cancelled]},
                                history.REPO,tmp_path,allowed_task=lambda task:True,format_decision=r.decision)
        assert outcome[0]["status"]=="FORMAT_DUPLICATE_REJECTED_PATCH", outcome
    # Palantir formats a field onto its own line.
    ok,good,_=submit({**proposal(), "patch": proposal()["patch"].replace("@@ -1 +1 @@","@@ -1 +1,3 @@").replace("+class Example { int x; }","+class Example {\n+    int x;\n+}")},2)
    assert ok and good["status"]=="PASS",good
