"""Independent format history; no GitHub or real Maven required."""
from datetime import datetime, timezone
import json

import pytest

import native_format_history as h
from native_format_admission import identity
from programming_agent_runner.hashutil import sha256_json

TASK = "req9backend2"
SHA = "a"*40
JAVA = "service/src/main/java/Example.java"
NOW = "2026-11-26T20:00:00Z"


def envelope(patch="patch1", summary="summary"):
    proposal = {"patch": patch, "summary": summary, "changed_paths": [JAVA], "schema_version": 1}
    return {"task_pack_sha256": "c"*64, "proposal_sha256": sha256_json(proposal),
            "proposal": proposal, "author": "GPT_NATIVE"}


def evidence(i, sha, env, status="FORMAT_FAIL"):
    return {"schema_version": "LF_NATIVE_FORMAT_RESULT_V2", "task_id": TASK,
            "run_id": i, "proposal_commit_sha": sha, "next_functional_attempt": 1,
            "functional_attempt_consumed": False, **identity(env), "status": status,
            "reason": "SPOTLESS_VIOLATIONS" if status == "FORMAT_FAIL" else "FORMAT_TOTAL_TIMEOUT",
            "paths": [JAVA] if status == "FORMAT_FAIL" else [],
            "diagnostics": [JAVA + ": original line 1, 1 lines; formatted line 1, 1 lines"] if status == "FORMAT_FAIL" else []}


def row(i, sha, *, status="failure", event="workflow_run", old=False):
    return {"id": i, "head_branch": "main", "run_attempt": 1, "status": "completed",
            "conclusion": status, "event": event,
            "display_title": f"lf-native-auto-lf/native-proposal/{TASK}-{sha}" if event == "workflow_run"
                else f"lf-native-route-retry-{TASK}-{sha}",
            "created_at": "2026-11-25T20:00:00Z" if old else NOW,
            "repository": {"full_name": h.REPO}, "path": ".github/workflows/worker-native.yml"}


def scenario(monkeypatch, entries, current=9, current_sha=SHA, event="workflow_run"):
    rows = [item[0] for item in entries] + [row(current, current_sha, event=event)]
    data = {item[0]["id"]: item[1] for item in entries}
    env = {item[0]["display_title"].rsplit("-", 1)[-1]: item[2] for item in entries}
    monkeypatch.setattr(h, "cutover", lambda api: datetime(2026, 11, 26, tzinfo=timezone.utc))
    monkeypatch.setattr(h, "listed", lambda api: rows)
    monkeypatch.setattr(h, "steps", lambda api, run: {h.GATE: "failure", h.UPLOAD: "success", h.WORKER: "skipped"})
    monkeypatch.setattr(h, "download", lambda api, cmd, repo, rid: data[rid])
    monkeypatch.setattr(h, "envelope_at", lambda api, task, sha: env[sha])
    return h.historical_rejections(None, None, h.REPO, TASK, current, current_sha)


def entries(n):
    return [(row(i, str(i)*40), evidence(i, str(i)*40, envelope("patch"+str(i))), envelope("patch"+str(i)))
            for i in range(1,n+1)]


@pytest.mark.parametrize("n", [0,1,2,3])
def test_budget_three_independent_rejections(monkeypatch,n):
    rejected = scenario(monkeypatch, entries(n))
    assert len(rejected) == n
    assert h.budget(rejected, identity(envelope("corrected"))) == (
        "FORMAT_REJECTION_LIMIT_EXCEEDED" if n == 3 else "FORMAT_BUDGET_AVAILABLE")
    assert all(x["next_functional_attempt"] == 1 and not x["functional_attempt_consumed"] for x in rejected.values())


@pytest.mark.parametrize("sha,summary", [("1"*40,"summary"),("2"*40,"summary"),("3"*40,"different summary")])
def test_duplicate_patch(monkeypatch,sha,summary):
    rejected = scenario(monkeypatch, entries(1), current_sha=sha)
    assert h.budget(rejected, identity(envelope("patch1",summary))) == "FORMAT_DUPLICATE_REJECTED_PATCH"


def test_duplicate_historical_patch_counted_once(monkeypatch):
    env = envelope("patch1","new summary")
    rejected = scenario(monkeypatch, entries(1)+[(row(2,"2"*40),evidence(2,"2"*40,env),env)])
    assert len(rejected) == 1


@pytest.mark.parametrize("status", ["BASELINE_FAIL","INFRA_ERROR","INVALID_PROPOSAL"])
def test_nonformat_not_counted(monkeypatch,status):
    env = envelope()
    assert not scenario(monkeypatch, [(row(1,"1"*40),evidence(1,"1"*40,env,status),env)])


def test_cancelled_and_legacy(monkeypatch):
    env = envelope()
    assert not scenario(monkeypatch, [(row(1,"1"*40,status="cancelled"),None,env),
                                      (row(2,"2"*40,old=True),None,env)])


def test_t23_replay_identity(monkeypatch):
    assert not scenario(monkeypatch, [],event="workflow_dispatch")


@pytest.mark.parametrize("bad", ["run_id","proposal_commit_sha","patch_sha256","task_pack_sha256","proposal_sha256","task_id"])
def test_inconsistent_proof(monkeypatch,bad):
    env = envelope()
    data = evidence(1,"1"*40,env)
    data[bad] = "bad"
    with pytest.raises(ValueError):
        scenario(monkeypatch, [(row(1,"1"*40),data,env)])


@pytest.mark.parametrize("artifacts", [[], [{"name":h.ARTIFACT}]*2,
    [{"name":h.ARTIFACT,"expired":True,"workflow_run":{"id":1},"size_in_bytes":50}]])
def test_artifact_missing_duplicate_expired(artifacts):
    with pytest.raises(ValueError):
        h.download(lambda route: {"artifacts":artifacts,"total_count":len(artifacts)},
                   lambda *a: pytest.fail("must not download"),h.REPO,1)


def test_publish_idempotent(monkeypatch,tmp_path):
    monkeypatch.setattr(h,"issue_for_task",lambda *a:9)
    monkeypatch.setattr(h,"request_state",lambda *a,**k:h.OPEN)
    comments=[]
    def command(*args):
        if args[:2] == ("gh","api"):
            return json.dumps(comments)
        comments.append({"body":args[-1],"user":{"login":"github-actions[bot]"}})
        return ""
    api=lambda route:{"number":9,"state":"open"}
    data=evidence(1,"1"*40,envelope())
    assert h.publish(command,api,h.REPO,tmp_path,TASK,data)=="FORMAT_FEEDBACK_PUBLISHED"
    assert h.publish(command,api,h.REPO,tmp_path,TASK,data)=="FORMAT_FEEDBACK_ALREADY_PUBLISHED"
    assert len(comments)==1


def test_functional_budget_precedes_format():
    text=(h.ROOT/".github/workflows/worker-native.yml").read_text()
    assert text.index("Determine and gate attempt") < text.index("Admit independent format rejection budget") < text.index(h.GATE)
    assert text.index(h.UPLOAD) < text.index("Publish independent format feedback")
    assert "NATIVE_ATTEMPT" not in text.split("Admit independent format rejection budget",1)[1].split("      - name:",1)[0]
