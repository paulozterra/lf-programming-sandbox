"""T22: public-feedback schema, issue-marker idempotency and artifact recovery."""
import json
from pathlib import Path

import pytest

from pilot.worker_v08 import native_feedback_delivery as delivery
from pilot.orchestrator.lifecycle_test_support import content, CONTROL, fake_api, main_response

TASK, SHA, REPO = "synthetic1", "a" * 40, delivery.REPO
PUBLIC = {"schema_version": delivery.SCHEMA, "attempt": 1,
          "kind": "VISIBLE_ACCEPTANCE_ONLY", "commands": [{
              "name": "test-api", "status": "FAIL", "reason": "assertion failed",
              "returncode": 1, "stdout_excerpt": "", "stderr_excerpt": "expected 200"}]}


def root(tmp_path):
    record = tmp_path / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    record.parent.mkdir(parents=True)
    record.write_text("{}")
    requests = tmp_path / "pilot/runs/req-901"
    (requests / "proposal_requests").mkdir(parents=True)
    (requests / "request_meta.json").write_text('{"issue":901,"author":"test"}')
    (requests / "proposal_requests" / (TASK + ".proposal-request.json")).write_text(
        json.dumps({"branch": "lf/native-proposal/" + TASK}))
    return tmp_path


def feedback_file(tmp_path, data=PUBLIC):
    file = tmp_path / "feedback.json"
    file.write_text(json.dumps(data))
    return file


def test_synthetic_public_feedback_comment_once(tmp_path):
    control = root(tmp_path)
    visible = delivery.read_public(feedback_file(tmp_path), 1)
    comments = []
    calls = []

    def api(route):
        if route == f"contents/{CONTROL}?ref=main":
            return content({})
        if route == "issues/901":
            return {"number": 901, "state": "open", "labels": [{"name": "lf-request"}]}
        return main_response(route, control)

    def run(*args):
        calls.append(args)
        if args[:2] == ("gh", "api"):
            return json.dumps(comments)
        if args[:3] == ("gh", "issue", "comment"):
            comments.append({"user": {"login": "github-actions[bot]"},
                             "body": args[-1]})
            return ""
        raise AssertionError(args)

    assert delivery.publish(run, api, REPO, control, TASK, SHA, 1,
                            visible, "BLOCKED_OR_FAILED") == "FEEDBACK_PUBLISHED"
    assert delivery.publish(run, api, REPO, control, TASK, SHA, 1,
                            visible, "BLOCKED_OR_FAILED") == "FEEDBACK_ALREADY_PUBLISHED"
    assert len([c for c in calls if c[:3] == ("gh", "issue", "comment")]) == 1
    assert delivery.marker(TASK, SHA, 1) in comments[0]["body"]
    assert "expected 200" in comments[0]["body"]
    assert "1/3" in comments[0]["body"]
    assert "BLOCKED_OR_FAILED" in comments[0]["body"]


@pytest.mark.parametrize("tampering", [
    {"oracle": "super-secret"},
    {"commands": [{"name": "test", "status": "FAIL", "reason": "holdout oracle path",
                   "returncode": 1, "stdout_excerpt": "", "stderr_excerpt": ""}]},
    {"commands": [{"name": "test", "status": "FAIL", "reason": "hidden",
                   "returncode": 1, "stdout_excerpt": "", "stderr_excerpt": "",
                   "hidden_command": "python3 private/exam.py"}]},
])
def test_hidden_oracle_or_unknown_field_never_published(tmp_path, tampering):
    data = dict(PUBLIC)
    data.update(tampering)
    control = root(tmp_path)
    called = []
    with pytest.raises(delivery.FeedbackBlocked, match="FEEDBACK_NO_PUBLICO"):
        delivery.publish(lambda *args: called.append(args), lambda *_: {},
                         REPO, control, TASK, SHA, 1, data, "FAIL")
    assert called == []


def test_wrong_attempt_or_oversize_and_symlink_denied(tmp_path):
    with pytest.raises(delivery.FeedbackBlocked, match="FEEDBACK_NO_PUBLICO"):
        delivery.parse_feedback(json.dumps(PUBLIC).encode(), 2)
    with pytest.raises(delivery.FeedbackBlocked, match="FEEDBACK_NO_PUBLICO"):
        delivery.parse_feedback(b'{"private":"oracle"}', 1)
    path = feedback_file(tmp_path)
    link = tmp_path / "symlink.json"
    link.symlink_to(path)
    with pytest.raises(delivery.FeedbackBlocked, match="FEEDBACK_NO_PUBLICO"):
        delivery.read_public(link, 1)


def test_recover_existing_native_run_verifies_sha_and_proof_then_comments_once(tmp_path):
    control = root(tmp_path)
    rid = 90001
    item = {"id": rid, "event": "workflow_dispatch", "status": "completed",
            "conclusion": "failure", "head_branch": "main", "run_attempt": 1,
            "path": ".github/workflows/worker-native.yml",
            "repository": {"full_name": REPO},
            "display_title": f"lf-native-infra-retry-{TASK}-{SHA}"}
    comments = []
    dispatched = []
    def api(route):
        if route == f"contents/{CONTROL}?ref=main":
            return content({})
        if route == f"actions/runs/{rid}/jobs?per_page=100":
            return {"total_count": 1, "jobs": [{"name": "native", "steps": [
                {"name": "Execute original run_verified_worker using native proposal (single attempt)",
                 "conclusion": "failure"}]}]}
        if route == f"actions/runs/{rid}/artifacts?per_page=100":
            return {"total_count": 2, "artifacts": [
                {"name": "native-attempt-proof", "workflow_run": {"id": rid}},
                {"name": "native-visible-feedback-and-cost", "workflow_run": {"id": rid}}]}
        if route == "issues/901":
            return {"number": 901, "state": "open", "labels": [{"name": "lf-request"}]}
        return main_response(route, control)
    def run(*args):
        if args[:3] == ("gh", "run", "download"):
            name = args[args.index("--name") + 1]
            folder = Path(args[args.index("--dir") + 1])
            if name == "native-attempt-proof":
                (folder / "attempt-proof.json").write_text(json.dumps({
                    "task_id": TASK, "attempt": 1, "task_pack_sha256": "b" * 64,
                    "run_id": rid}))
            else:
                (folder / "feedback.json").write_text(json.dumps(PUBLIC))
            return ""
        if args[:2] == ("gh", "api"):
            return json.dumps(comments)
        if args[:3] == ("gh", "issue", "comment"):
            comments.append({"user": {"login": "github-actions[bot]"},
                             "body": args[-1]})
            return ""
        if args[:3] == ("gh", "workflow", "run"):
            dispatched.append(args)
        raise AssertionError(args)

    assert delivery.recover_one(run, api, REPO, control, item) == "FEEDBACK_PUBLISHED"
    assert delivery.recover_one(run, api, REPO, control, item) == "FEEDBACK_ALREADY_PUBLISHED"
    assert len(comments) == 1 and not dispatched
    assert SHA in comments[0]["body"]


def test_recovery_does_not_publish_without_spent_worker_step(tmp_path):
    control = root(tmp_path)
    item = {"id": 999, "event": "workflow_dispatch", "status": "completed",
            "conclusion": "failure", "head_branch": "main", "run_attempt": 1,
            "path": ".github/workflows/worker-native.yml",
            "repository": {"full_name": REPO},
            "display_title": f"lf-native-infra-retry-{TASK}-{SHA}"}
    def api(route):
        if route == f"contents/{CONTROL}?ref=main":
            return content({})
        assert route == "actions/runs/999/jobs?per_page=100"
        return {"total_count": 1, "jobs": [{"name": "native", "steps": [
            {"name": "Execute original run_verified_worker using native proposal (single attempt)",
             "conclusion": "skipped"}]}]}
    assert delivery.recover_one(lambda *_: (_ for _ in ()).throw(AssertionError()),
                                api, REPO, control, item) == "FEEDBACK_NO_SPENT_ATTEMPT"


def test_sweep_reads_latest_page_even_when_total_native_history_exceeds_100(tmp_path, monkeypatch):
    root(tmp_path)
    item = {"id": 43783407265, "event": "workflow_dispatch",
            "display_title": f"lf-native-infra-retry-{TASK}-{SHA}",
            "head_branch": "main", "run_attempt": 1,
            "status": "completed", "conclusion": "failure",
            "path": ".github/workflows/worker-native.yml",
            "repository": {"full_name": REPO}}
    seen = []
    def api(path):
        assert path == "actions/workflows/worker-native.yml/runs?per_page=100"
        return {"total_count": 150, "workflow_runs": [item]}
    monkeypatch.setattr(delivery, "recover_one", lambda *args: seen.append(args[-1]["id"]) or "FEEDBACK_PUBLISHED")
    outcome = delivery.recover_sweep(lambda *_: "", api, REPO, tmp_path)
    assert seen == [43783407265]
    assert outcome == [{"status": "FEEDBACK_PUBLISHED", "run_id": 43783407265}]


def test_non_issue_backed_historical_worker_does_not_block_recovery(tmp_path):
    item = {"id": 90002, "event": "workflow_dispatch",
            "display_title": f"lf-native-infra-retry-{TASK}-{SHA}",
            "head_branch": "main", "run_attempt": 1,
            "status": "completed", "conclusion": "failure",
            "path": ".github/workflows/worker-native.yml",
            "repository": {"full_name": REPO}}
    assert delivery.recover_one(
        lambda *_: (_ for _ in ()).throw(AssertionError("No GitHub IO")),
        lambda *_: (_ for _ in ()).throw(AssertionError("No GitHub IO")),
        REPO, tmp_path, item) == "FEEDBACK_NO_SOURCE_ISSUE"


def test_feedback_late_suspension_prevents_comment(tmp_path):
    control = root(tmp_path)
    visible = delivery.read_public(feedback_file(tmp_path), 1)
    paused = fake_api({"req-901": {"state": "SUSPENDING", "authorization_pr": 77}})
    active = fake_api({})
    observed = []
    def api(route):
        return (paused if observed else active)(route)
    def run(*args):
        assert args[:2] == ("gh", "api")
        observed.append(args)
        return "[]"
    assert delivery.publish(run, api, REPO, control, TASK, SHA, 1, visible,
                            "BLOCKED_OR_FAILED") == "REQUEST_SUSPENDED"
    assert len(observed) == 1
