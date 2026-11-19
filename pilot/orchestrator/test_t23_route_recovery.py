"""T23 CP3.6 issue-backed recovery is offline, SHA bound and idempotent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from pilot.config.testing import install_project_config
from pilot.config.project_config import ProjectConfigError
from pilot.orchestrator import native_route_recovery as recovery
from pilot.worker_v08.native_route_defect import (
    canonical, convert, migration, sha, verified_migration,
)

REPO = "paulozterra/lf-programming-sandbox"
TASK = "synthetic1"
PROPOSAL = "a" * 40
BASE = "b" * 40
RUN = 43783407265
OLD = {"holdout_sha256": "e" * 64, "holdout_ref": "pilot/holdouts/opaque.age",
       "task_spec": {"base_head_sha": BASE, "acceptance_commands": [{
           "name": "contract-source-coverage",
           "argv": ["python3", "pilot/orchestrator/contract_validate.py"]}]}}
VISIBLE = {"kind": "VISIBLE_ACCEPTANCE_ONLY", "commands": [{
    "name": "contract-source-coverage", "status": "FAIL",
    "reason": "EXIT_NONZERO", "returncode": 2,
    "stderr_excerpt": "BLOCKED:CONTRACT_SPEC_VALIDATOR_UNAVAILABLE\n",
    "stdout_excerpt": ""}], "attempt": 1,
    "schema_version": "LF_NATIVE_VISIBLE_FEEDBACK_V1"}
EVENT = {"id": RUN, "event": "workflow_dispatch", "head_branch": "main",
         "head_sha": "c" * 40, "status": "completed", "conclusion": "failure",
         "run_attempt": 1, "path": ".github/workflows/worker-native.yml",
         "repository": {"full_name": REPO},
         "display_title": f"lf-native-infra-retry-{TASK}-{PROPOSAL}"}


def fixture(tmp_path, registration=OLD):
    record = tmp_path / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    record.parent.mkdir(parents=True)
    record.write_bytes(canonical(registration))
    req = tmp_path / "pilot/runs/req-901"
    (req / "proposal_requests").mkdir(parents=True)
    (req / "request_meta.json").write_text('{"issue":901,"author":"origin"}')
    pack = req / "proposal_requests" / (TASK + ".task-pack.json")
    pack.write_bytes(b"original visible package")
    digest = hashlib.sha256(pack.read_bytes()).hexdigest()
    (req / "proposal_requests" / (TASK + ".proposal-request.json")).write_text(
        json.dumps({"branch": "lf/native-proposal/" + TASK,
                    "task_pack_sha256": digest}))
    return digest


def evidence(pack):
    return {"task": TASK, "sha": PROPOSAL, "run_id": RUN, "attempt": 1,
            "request": 901, "original": OLD, "legacy_pack": pack, "base": BASE}


def test_historical_run_437834_classified_only_with_original_proof_and_visible_tool():
    from pilot.orchestrator.native_route_recovery import inspect
    from pilot.worker_v08.native_route_defect import classify
    assert classify(VISIBLE, OLD)
    # All data-supplying boundaries are simulated, including main historical
    # registration and published GitHub artifact proof.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        digest = fixture(root)
        with patch.object(recovery, "_source_record", return_value=OLD), \
             patch.object(recovery, "_artifact_payload", return_value=(
                 {"task_id": TASK, "run_id": RUN, "attempt": 1,
                  "task_pack_sha256": digest}, VISIBLE)):
            result = inspect(lambda *_: "", lambda *_: {}, REPO, root, EVENT)
        assert result == evidence(digest)
        invalid = dict(VISIBLE, commands=[dict(VISIBLE["commands"][0],
                    stderr_excerpt="BLOCKED:CONTRACT_OPENAPI_INVALID\n")])
        with patch.object(recovery, "_source_record", return_value=OLD), \
             patch.object(recovery, "_artifact_payload", return_value=(
                 {"task_id": TASK, "run_id": RUN, "attempt": 1,
                  "task_pack_sha256": digest}, invalid)):
            assert inspect(lambda *_: "", lambda *_: {}, REPO, root, EVENT) is None


def test_route_defect_issue_comment_is_single_and_excludes_spent_attempt(tmp_path):
    fixture(tmp_path)
    comments = []
    called = []
    def run(*args):
        called.append(args)
        if args[:2] == ("gh", "api"):
            return json.dumps(comments)
        if args[:3] == ("gh", "issue", "comment"):
            comments.append({"user": {"login": "github-actions[bot]"}, "body": args[-1]})
            return ""
        raise AssertionError(args)
    def api(path):
        assert path == "issues/901"
        return {"number": 901, "labels": [{"name": "lf-request"}]}
    data = evidence("d" * 64)
    assert recovery.comment_defect(run, api, REPO, data) == "ROUTE_DEFECT_RECORDED"
    assert recovery.comment_defect(run, api, REPO, data) == "ROUTE_DEFECT_ALREADY_RECORDED"
    assert len(comments) == 1
    assert "ROUTE_DEFECT" in comments[0]["body"] and "no cuenta" in comments[0]["body"]
    assert sum(x[:3] == ("gh", "issue", "comment") for x in called) == 1


def test_generated_registration_draft_preserves_old_exam_and_baseline(tmp_path):
    legacy_pack = fixture(tmp_path)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("git", "ls-remote", "--heads"):
            return ""
        raise AssertionError(args)
    def worktree(_, branch, cb):
        assert branch.startswith("lf/native-registration/route-python-")
        return cb(tmp_path)
    def draft(_, branch, request, paths, reason, title):
        assert request == "req-901"
        assert "pilot/worker_v08/native_tasks/synthetic1.json" in paths
        assert "pilot/worker_v08/route_migrations/synthetic1.json" in paths
        assert "pilot/runs/req-901/proposal_requests/synthetic1.task-pack.json" in paths
        return {"draft_pr": "https://example.invalid/draft"}
    new_raw = b"corrected visible package"
    def export(_, __, ___, ____, pack, _____):
        assert pack.read_bytes() == b"original visible package"
        pack.write_bytes(new_raw)
        return hashlib.sha256(new_raw).hexdigest()
    with patch.object(recovery, "_export_fixed_pack", side_effect=export), \
         patch("pilot.orchestrator.native_submission_contract.enrich_request",
               side_effect=lambda req, spec: req):
        result = recovery.prepare_repair(
            "f" * 40, run, lambda *_: {}, REPO, tmp_path,
            evidence(legacy_pack), worktree, draft, lambda *_: False)
    assert result["status"] == "ROUTE_DEFECT_REGISTRATION_DRAFT"
    fixed = json.loads((tmp_path / "pilot/worker_v08/native_tasks" /
                        (TASK + ".json")).read_text())
    assert fixed["holdout_sha256"] == OLD["holdout_sha256"]
    assert fixed["holdout_ref"] == OLD["holdout_ref"]
    assert fixed["task_spec"]["base_head_sha"] == BASE
    assert fixed["task_spec"]["acceptance_commands"][0]["argv"][0] == "lf-python"
    assert verified_migration(tmp_path, TASK, fixed, proposal_sha=PROPOSAL)


def test_new_main_replays_same_sha_once_without_changing_branch(tmp_path):
    fixture(tmp_path)
    fixed, _ = convert(OLD)
    (tmp_path / "pilot/worker_v08/native_tasks" / (TASK + ".json")).write_bytes(canonical(fixed))
    obj = migration(TASK, OLD, fixed, "d" * 64, "e" * 64, RUN, PROPOSAL, BASE)
    path = tmp_path / "pilot/worker_v08/route_migrations" / (TASK + ".json")
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical(obj))
    calls = []
    def command(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("gh", "api", f"repos/{REPO}/issues/901/comments?per_page=100"):
            return "[]"
        if args[:2] == ("gh", "api"):
            return "[]"
        if args[:3] == ("git", "ls-remote", "origin"):
            return PROPOSAL + "\trefs/heads/lf/native-proposal/" + TASK
        if args[:2] == ("git", "show"):
            proposal = {"schema_version": 1, "summary": "synthetic",
                        "patch": "diff --git a/a b/a", "changed_paths": ["a"]}
            return json.dumps({"task_pack_sha256": "d" * 64, "author": "GPT_NATIVE",
                               "proposal": proposal, "proposal_sha256":
                               hashlib.sha256(json.dumps(proposal, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()})
        return ""
    def api(route):
        if route == f"actions/runs/{RUN}":
            return EVENT
        if route == "issues/901":
            return {"number": 901, "labels": [{"name": "lf-request"}]}
        raise AssertionError(route)
    with patch.object(recovery, "validate_proposal_only", return_value={"task": TASK}):
        first = recovery.replay_corrected("f" * 40, command, api, REPO, tmp_path, [])
        later = recovery.replay_corrected("f" * 40, command, api, REPO, tmp_path, [
            {"display_title": f"lf-native-route-retry-{TASK}-{PROPOSAL}",
             "event": "workflow_dispatch"}])
    assert first[0]["status"] == "ROUTE_DEFECT_REEVALUATION_DISPATCHED"
    assert later == []
    assert sum(x[:3] == ("gh", "workflow", "run") for x in calls) == 1
    assert "route_retry=true" in next(x for x in calls if x[:3] == ("gh", "workflow", "run"))
    assert not any(x[:2] == ("git", "push") for x in calls)
