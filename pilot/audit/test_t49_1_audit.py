"""T49.1 audit: only CLOSED_FINALIZED is eligible, including forced requests."""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

from pilot.orchestrator.lifecycle_test_support import content, CONTROL

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
rt = importlib.import_module("request_trigger")


def proof(root, complete):
    folder = root / "pilot/runs/req-275"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lots.json").write_text(json.dumps({"lots": [{"id": "SOL-001"}]}))
    if complete:
        (folder / "H_REPORT.md").write_text("# merged report")
        ledger = root / "pilot/registry/implemented.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"entries": [{"request": "req-275",
             "lot": "SOL-001", "merge_sha": "a"*40, "status": "ATTESTED"}]}))


@pytest.mark.parametrize("state,complete,eligible", [
    ("open", False, False), ("closed", False, False), ("closed", True, True),
])
def test_audit_state_matrix(tmp_path, state, complete, eligible):
    proof(tmp_path, complete)
    assert rt._finalized_request("req-275", "o/r", tmp_path,
          api=lambda path: content({}) if path == f"contents/{CONTROL}?ref=main"
          else {"number": 275, "state": state}) is eligible


def test_audit_unreadable_state_blocks(tmp_path):
    proof(tmp_path, True)
    with pytest.raises(ValueError, match="REQUEST_STATE_UNRESOLVED"):
        rt._finalized_request("req-275", "o/r", tmp_path,
            api=lambda _: (_ for _ in ()).throw(OSError("offline")))


@pytest.mark.parametrize("state,complete,expected", [
    ("open", True, 0), ("closed", False, 0),
    ("closed", True, 1),
])
def test_forced_audit_creates_only_finalized_issue(tmp_path, monkeypatch,
                                                   state, complete, expected):
    proof(tmp_path, complete)
    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "load", lambda *_: {"audit": {
        "enabled": True, "trigger": "REQUEST_CLOSED",
        "sample_n": 1, "mode": "SHADOW", "auditor": "CLAUDE_ROUTINE",
        "skill": {"repository": "o/r", "commit": "a"*40, "path": "skills/a"}}})
    monkeypatch.setitem(sys.modules, "chain_lots", SimpleNamespace(plans=lambda: []))
    monkeypatch.setattr(rt.bi, "completed_from_history", lambda *_: (
        {"lots": [{"id": "SOL-001"}]}, {"SOL-001": {"merge_sha": "a"*40}}))
    monkeypatch.setattr(rt.bi, "build", lambda *_: {
        "base_commit": "a"*40, "evidence_destination": "pilot/runs/req-275/audit"})
    (tmp_path / "pilot/runs/req-275/analysis.json").write_text("{}")
    created = []
    def gh(*args, data=None):
        endpoint = args[0]
        if endpoint.endswith(f'/contents/{CONTROL}?ref=main'):
            return json.dumps(content({}))
        if endpoint.endswith("/issues/275"):
            return json.dumps({"number": 275, "state": state})
        if "issues?labels=" in endpoint:
            return json.dumps([])
        if endpoint.endswith("/issues") and data is not None:
            created.append(data)
            return json.dumps({"number": 999})
        pytest.fail("unexpected GitHub side effect " + endpoint)
    monkeypatch.setattr(rt, "gh", gh)
    monkeypatch.setattr(sys, "argv", ["request_trigger", "--project", "lf",
                                    "--repository", "o/r", "--request", "req-275"])
    assert rt.main() == 0
    assert len(created) == expected


def test_audit_second_live_check_prevents_issue(tmp_path, monkeypatch):
    proof(tmp_path, True)
    monkeypatch.setattr(rt, "ROOT", tmp_path)
    monkeypatch.setattr(rt, "load", lambda *_: {"audit": {
        "enabled": True, "trigger": "REQUEST_CLOSED", "sample_n": 1}})
    monkeypatch.setitem(sys.modules, "chain_lots", SimpleNamespace(plans=lambda: []))
    monkeypatch.setattr(rt.bi, "completed_from_history", lambda *_: (
        {"lots": [{"id": "SOL-001"}]}, {"SOL-001": {"merge_sha": "a"*40}}))
    monkeypatch.setattr(rt.bi, "build", lambda *_: {
        "base_commit": "a"*40, "evidence_destination": "pilot/runs/req-275/audit"})
    (tmp_path / "pilot/runs/req-275/analysis.json").write_text("{}")
    states = iter(["closed", "open"])
    def gh(endpoint, data=None):
        if endpoint.endswith(f'/contents/{CONTROL}?ref=main'):
            return json.dumps(content({}))
        if endpoint.endswith("/issues/275"):
            return json.dumps({"number": 275, "state": next(states)})
        if "issues?labels=" in endpoint:
            return "[]"
        pytest.fail("created audit after issue reopened")
    monkeypatch.setattr(rt, "gh", gh)
    monkeypatch.setattr(sys, "argv", ["request_trigger", "--project", "lf",
                       "--repository", "o/r", "--request", "req-275"])
    assert rt.main() == 0

# D22 R1 — use real temporary Git history, not a live repository or audit.
@pytest.fixture
def historical_route(tmp_path):
    import base64
    from pilot.audit.test_t46_audit_stage import _historical_case
    from pilot.orchestrator.lifecycle_test_support import fake_api
    root, report_file, report, data, _skill, git = _historical_case(tmp_path)
    data["schema_version"] = "LF_DEEP_AUDIT_INPUT_V2"
    (report_file.parent / "audit_input_v2.json").write_text(json.dumps(data))
    (report_file.parent.parent / "H_REPORT.md").write_text("# finalized")
    git("add", "pilot/runs/req-9/H_REPORT.md")
    git("commit", "-qm", "finalized")
    git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))
    prefix = "pilot/runs/req-9/audit/"
    issue = {"number": 901, "state": "open", "user": {"login": "github-actions[bot]"},
             "labels": [{"name": "audit-request"}], "title": "[AUDIT][lf] req-9",
             "body": "<!-- audit-request:req-9 -->\n```json\n" + json.dumps(data) + "\n```"}
    # Local synthetic blob ids for the typed API double; no remote calls.
    blobs = {"a"*40: data, "b"*40: report, "c"*40: {"ok": True}}
    files = [{"filename": prefix + name, "status": "added", "sha": sha}
             for name, sha in (("audit_input_v2.json", "a"*40), ("report.json", "b"*40),
                               ("capture.json", "c"*40))]
    pr = {"number": 902, "state": "open", "merged": False, "draft": False,
          "user": {"login": "github-actions[bot]"}, "title": "[AUDIT][lf] req-9",
          "body": "Auditoría automática del pedido `req-9` (issue #901). Auditor: Claude.",
          "head": {"ref": "audit-req-9", "sha": "d"*40, "repo": {"full_name": "o/r"}},
          "base": {"ref": "main", "repo": {"full_name": "o/r"}},
          "changed_files": len(files)}
    state = {"issue": "closed"}
    modes = {}
    entries = {}
    runs = [{"id": 1, "head_sha": "d"*40, "status": "completed", "conclusion": "success"}]

    def api(path):
        if path == "issues/901":
            return issue
        if path == "pulls/902":
            return pr
        if path == "pulls/902/files?per_page=100&page=1":
            return files
        if path == "git/trees/" + "d"*40 + "?recursive=1":
            return {"truncated": False, "tree": [
                {"path": f["filename"], "sha": f["sha"], "type": "blob",
                 "mode": modes.get(f["filename"], "100644")} for f in files]}
        if path.startswith("git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            raw = json.dumps(blobs[sha]).encode()
            return {"sha": sha, "size": len(raw), "encoding": "base64",
                    "content": base64.b64encode(raw).decode()}
        if path.startswith("actions/workflows/audit-stage.yml/runs?"):
            return {"total_count": len(runs), "workflow_runs": runs}
        return fake_api(entries, issue_state=state["issue"])(path)

    return SimpleNamespace(root=root, report_file=report_file, data=data, issue=issue,
                           pr=pr, files=files, blobs=blobs, state=state, entries=entries,
                           runs=runs, modes=modes, api=api)


def test_historical_audit_after_suspension_resume_and_finalization(historical_route):
    from pilot.orchestrator import request_lifecycle as life
    r = historical_route
    def gate():
        life.require_pr_open("audit-req-9", [f["filename"] for f in r.files],
                             r.api, root=r.root, pr=r.pr)
    r.state["issue"] = "open"
    with pytest.raises(life.RequestStateError, match="AUDIT_REQUEST_NOT_FINALIZED"):
        gate()
    for paused in (life.SUSPENDING, life.SUSPENDED):
        r.entries["req-9"] = {"state": paused, "authorization_pr": 77}
        with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
            gate()
    r.entries["req-9"] = {"state": "ACTIVE", "authorization_pr": 77}
    with pytest.raises(life.RequestStateError, match="AUDIT_REQUEST_NOT_FINALIZED"):
        gate()
    r.state["issue"] = "closed"
    gate()
    # The exception does not make the original functional request active.
    with pytest.raises(life.RequestStateError, match="REQUEST_CLOSED"):
        life.require_pr_open("lf/request/req-9", ["pilot/runs/req-9/state.json"],
                             r.api, root=r.root)
    # Even a finalized closed issue cannot override an active suspension.
    r.entries["req-9"]["state"] = life.SUSPENDED
    with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
        gate()
    r.entries["req-9"]["state"] = "ACTIVE"
    (r.report_file.parent.parent / "H_REPORT.md").unlink()
    with pytest.raises(life.RequestStateError, match="AUDIT_REQUEST_NOT_FINALIZED"):
        gate()


@pytest.mark.parametrize("fault", ["mixed", "other_request", "rename", "wrong_branch",
                                   "wrong_issue", "wrong_author", "wrong_blob",
                                   "wrong_report", "unverified_authority", "ambiguous_marker", "symlink"])
def test_audit_exception_rejects_ambiguous_provenance_and_scope(historical_route, fault):
    from pilot.orchestrator import request_lifecycle as life
    r = historical_route
    if fault == "mixed":
        r.files.append({"filename": "pilot/runs/req-9/state.json", "status": "added", "sha": "e"*40})
    elif fault == "other_request":
        r.files.append({"filename": "pilot/runs/req-10/audit/capture.json", "status": "added", "sha": "e"*40})
    elif fault == "rename":
        r.files[0]["status"] = "renamed"
        r.files[0]["previous_filename"] = "pilot/runs/req-9/state.json"
    elif fault == "wrong_branch":
        r.pr["head"]["ref"] = "feat/audit"
    elif fault == "wrong_issue":
        r.pr["body"] = r.pr["body"].replace("#901", "#903")
    elif fault == "wrong_author":
        r.issue["user"]["login"] = "someone"
    elif fault == "wrong_blob":
        r.blobs["a"*40] = dict(r.data, base_commit="f"*40)
    elif fault == "symlink":
        r.modes[r.files[2]["filename"]] = "120000"
    elif fault == "wrong_report":
        r.blobs["b"*40] = {"audit_context": {"source_revision": "f"*40, "promotion_authorized": False}}
    elif fault == "unverified_authority":
        r.data["authority_refs"][0]["expected_sha256"] = "f"*64
        r.issue["body"] = "<!-- audit-request:req-9 -->\n```json\n" + json.dumps(r.data) + "\n```"
    else:
        r.issue["body"] = "<!-- audit-request:req-10 -->\n" + r.issue["body"]
    r.pr["changed_files"] = len(r.files)
    with pytest.raises(life.RequestStateError):
        life.require_pr_open(r.pr["head"]["ref"], [f["filename"] for f in r.files],
                             r.api, root=r.root, pr=r.pr)


def test_audit_prepare_rechecks_after_listing_prs(historical_route, monkeypatch):
    import shutil
    from pilot.audit import auditor_job as aj
    from pilot.orchestrator import request_lifecycle as life
    r = historical_route
    shutil.rmtree(r.report_file.parent)
    monkeypatch.setattr(aj, "ROOT", r.root)
    def gh(endpoint, data=None):
        assert data is None
        path = endpoint.removeprefix("repos/o/r/")
        if path.startswith("pulls?"):
            r.state["issue"] = "open"
            return "[]"
        return json.dumps(r.api(path))
    monkeypatch.setattr(aj, "gh", gh)
    with pytest.raises(life.RequestStateError, match="AUDIT_REQUEST_NOT_FINALIZED"):
        aj.prepare(901, "o/r")
    assert not r.report_file.parent.exists()


def test_audit_publish_rechecks_after_local_commit_before_push(historical_route, monkeypatch):
    from pilot.audit import auditor_job as aj
    from pilot.orchestrator import request_lifecycle as life
    r = historical_route
    monkeypatch.setattr(aj, "ROOT", r.root)
    git, run = aj.git, aj.subprocess.run
    def local_git(*args):
        result = git(*args)
        if "commit" in args:
            r.state["issue"] = "open"
        return result
    def no_push(cmd, *args, **kwargs):
        assert "push" not in cmd, "a suspended audit attempted a remote push"
        return run(cmd, *args, **kwargs)
    def gh(endpoint, data=None):
        assert data is None, "a suspended audit attempted a GitHub write"
        return json.dumps(r.api(endpoint.removeprefix("repos/o/r/")))
    monkeypatch.setattr(aj, "git", local_git)
    monkeypatch.setattr(aj.subprocess, "run", no_push)
    monkeypatch.setattr(aj, "gh", gh)
    monkeypatch.setenv("GH_TOKEN", "offline-test")
    with pytest.raises(life.RequestStateError, match="AUDIT_REQUEST_NOT_FINALIZED"):
        aj.publish("req-9", "lf", 901, "o/r", {"rules": 1, "findings": 0, "confirmed": 0})


@pytest.mark.parametrize("late", ["after_checks", "after_label"])
def test_audit_land_never_dispatches_after_state_changes(historical_route, monkeypatch, late):
    from pilot.audit import auditor_job as aj
    from pilot.orchestrator import request_lifecycle as life
    r = historical_route
    monkeypatch.setattr(aj, "ROOT", r.root)
    writes = []
    def gh(*args, data=None):
        if data is not None:
            writes.append(args)
            assert args == ("repos/o/r/issues/902/labels",)
            r.state["issue"] = "open"
            return "{}"
        path = args[0].removeprefix("repos/o/r/")
        if "/check-runs?" in path:
            if late == "after_checks":
                r.state["issue"] = "open"
            return json.dumps({"check_runs": [{"name": str(i), "status": "completed", "conclusion": "success"}
                                              for i in range(5)]})
        return json.dumps(r.api(path))
    monkeypatch.setattr(aj, "gh", gh)
    with pytest.raises(life.RequestStateError, match="AUDIT_REQUEST_NOT_FINALIZED"):
        aj.land(902, "o/r", timeout_s=1)
    assert len(writes) == (1 if late == "after_label" else 0)


def test_audit_stage_receipt_must_be_latest_and_exact(historical_route):
    from pilot.audit import audit_lifecycle as al
    from pilot.orchestrator import request_lifecycle as life
    r = historical_route
    al.require_audit_check(r.api, "d"*40)
    r.runs.append({"id": 2, "head_sha": "d"*40, "status": "completed", "conclusion": "failure"})
    r.runs.append({"id": 3, "head_sha": "e"*40, "status": "completed", "conclusion": "success"})
    with pytest.raises(life.RequestStateError, match="AUDIT_STAGE_NOT_GREEN"):
        al.require_audit_check(r.api, "d"*40)
    r.runs.append({"id": 4, "head_sha": "d"*40, "status": "completed", "conclusion": "success"})
    al.require_audit_check(r.api, "d"*40)
