"""T23.1: all registration subfamilies dispatch sweep, only real tasks close exams."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.native_registration_family import registration_family, is_native_registration
from pilot.exam_issue_lifecycle import registration_task, close_registered, LifecycleBlocked
from pilot import train_handoff
from pilot.auto_integrate import accepted_branch_kind
from pilot.orchestrator.generated_conflict_recovery import GENERATED
from pilot.request_failure_notify import is_native_registration as watchdog_accepts
from pilot.policy_c_handoff import should_notify

SHA = "a" * 40
TASK = "req186contrato1"
SUFFIX = "5cf9183dcf42"
REAL = f"lf/native-registration/{TASK}-{SUFFIX}"
AUX = [
    f"lf/native-registration/pack-{TASK}-{SUFFIX}",
    f"lf/native-registration/envelope-{TASK}-{SUFFIX}",
    f"lf/native-registration/route-python-{TASK}-{SUFFIX}",
]


@pytest.mark.parametrize("branch", AUX)
def test_auxiliary_subfamilies_never_look_like_exam_registrations(branch):
    family, task = registration_family(branch)
    assert family == "auxiliary" and task == TASK
    assert registration_task(branch) is None
    assert accepted_branch_kind(branch) == "registration"
    assert should_notify(branch)
    assert watchdog_accepts(branch)
    assert accepted_branch_kind(branch) in GENERATED


def test_real_registration_and_ambiguous_names():
    assert registration_family(REAL) == ("registration", TASK)
    assert registration_task(REAL) == TASK
    for branch in (
        "lf/native-registration/route-python-req186contrato1-wrongsha",
        "lf/native-registration/pack--" + SUFFIX,
        "lf/native-registration/envelope-req186contrato1-" + "z" * 12,
        "lf/native-registration/route-python-" + TASK + "-" + SUFFIX + "-extra",
        "lf/native-registration/" + TASK + "-" + SUFFIX + "-extra",
        "lf/native-registration/" + TASK + "-123",
    ):
        assert registration_family(branch)[0] == "invalid"
        assert registration_task(branch) is None
        assert not is_native_registration(branch)
        assert accepted_branch_kind(branch) is None


class API:
    def __init__(self, branch):
        self.branch, self.posts = branch, []

    def call(self, method, route, body=None):
        if method == "GET" and route == "/pulls/777":
            return {
                "number": 777, "merged": True, "merge_commit_sha": SHA,
                "base": {"ref": "main", "repo": {"full_name": train_handoff.REPO}},
                "head": {"ref": self.branch, "sha": "b" * 40,
                         "repo": {"full_name": train_handoff.REPO}},
            }
        if method == "GET" and route == "/commits/" + SHA:
            return {"sha": SHA,
                    "parents": [{"sha": "c" * 40}, {"sha": "b" * 40}],
                    "commit": {"message": "Merge PR #777 via sandbox-train"}}
        if method == "POST":
            self.posts.append((route, body))
            return {}
        raise AssertionError((method, route, body))


def run_handoff(branch, *, exam=None):
    api = API(branch)
    exam = exam if exam is not None else lambda *args: "EXAM_ISSUE_CLOSED"
    with patch.object(train_handoff, "git", return_value=SHA), \
         patch.object(train_handoff, "validate_train_run"), \
         patch.object(train_handoff, "ensure_main_ci", return_value={"status": "MAIN_CI_GREEN"}), \
         patch("pilot.exam_issue_lifecycle.close_registered", side_effect=exam) as close:
        mapping = json.loads((Path(__file__).with_name(
            "train_handoff_map_v1.json")).read_text("utf-8"))
        result = train_handoff.dispatch(api, 777, SHA, 555, mapping)
    return result, api.posts, close


@pytest.mark.parametrize("branch", AUX)
def test_merge_of_every_auxiliary_family_completes_handoff_without_exam_close(branch):
    result, posts, close = run_handoff(branch)
    assert result["status"] == "SWEEP_DISPATCHED"
    assert result["exam"] == "NO_EXAM_REGISTRATION"
    close.assert_not_called()
    assert posts == [("/actions/workflows/chain-lots.yml/dispatches",
                      {"ref": "main", "inputs": {"sweep": "true", "base_sha": SHA}})]


def test_actual_registration_still_closes_exam_after_verified_merged_task():
    result, posts, close = run_handoff(REAL)
    assert result["exam"] == "EXAM_ISSUE_CLOSED"
    close.assert_called_once()
    assert len(posts) == 1
    assert posts[0][0] == "/actions/workflows/chain-lots.yml/dispatches"


def test_exam_failure_does_not_abort_sweep_and_comments_merged_pr():
    def rejected(*args):
        raise LifecycleBlocked("EXAM_REQUEST_DUPLICATE")
    result, posts, close = run_handoff(REAL, exam=rejected)
    assert result["status"] == "SWEEP_DISPATCHED"
    assert result["exam"] == "EXAM_CLOSE_NONBLOCKING:EXAM_REQUEST_DUPLICATE"
    assert len(posts) == 2
    assert posts[0][0] == "/issues/777/comments"
    assert "EXAM_REQUEST_DUPLICATE" in posts[0][1]["body"]
    assert posts[1][0] == "/actions/workflows/chain-lots.yml/dispatches"


def test_issue_comment_failure_is_nonblocking_too():
    class CommentFail(API):
        def call(self, method, route, body=None):
            if method == "POST" and route == "/issues/777/comments":
                raise RuntimeError("GitHub comment unavailable")
            return super().call(method, route, body)

    api = CommentFail(REAL)
    with patch.object(train_handoff, "git", return_value=SHA), \
         patch.object(train_handoff, "validate_train_run"), \
         patch.object(train_handoff, "ensure_main_ci", return_value={"status": "MAIN_CI_GREEN"}), \
         patch("pilot.exam_issue_lifecycle.close_registered",
               side_effect=LifecycleBlocked("EXAM_REGISTRATION_NOT_MERGED")):
        mapping = json.loads(Path(__file__).with_name(
            "train_handoff_map_v1.json").read_text("utf-8"))
        result = train_handoff.dispatch(api, 777, SHA, 555, mapping)
    assert result["status"] == "SWEEP_DISPATCHED"
    assert api.posts[0][0] == "/actions/workflows/chain-lots.yml/dispatches"


def test_actual_exam_issue_closure_only_with_matching_registration_and_scope(tmp_path):
    folder = tmp_path / "pilot/runs/req-901"
    folder.mkdir(parents=True)
    (folder / "chain_plan.json").write_text(json.dumps({
        "bindings": [{"task_name": TASK}]}))
    comments = []
    class ExamAPI:
        def call(self, method, path, body=None):
            from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL
            if method == "GET" and (path == "/issues/901" or path == f"/contents/{CONTROL}?ref=main"):
                return fake_api({})(path[1:])
            if method == "GET" and path.startswith("/issues?"):
                return [{
                    "number": 981, "state": "open",
                    "user": {"login": "github-actions[bot]"},
                    "title": f"EXAM_REQUEST: {TASK}",
                    "labels": [{"name": "exam-request"}],
                    "body": f"- Pedido: `req-901`\n- Task ID: `{TASK}`",
                }]
            if method == "GET":
                return fake_api({})(path[1:])
            comments.append((method, path, body))
            return {}
    def git(*parts):
        assert parts[:3] == ("diff", "--name-only", SHA + "^1")
        return f"pilot/worker_v08/native_tasks/{TASK}.json"
    assert close_registered(ExamAPI(), SHA, REAL, git, tmp_path) == "EXAM_ISSUE_CLOSED"
    assert [p for _, p, _ in comments] == ["/issues/981/comments", "/issues/981"]
    comments.clear()
    for branch in AUX:
        assert close_registered(ExamAPI(), SHA, branch, git, tmp_path) == "NO_EXAM_REGISTRATION"
    assert not comments
    with pytest.raises(LifecycleBlocked, match="EXAM_REGISTRATION_NOT_MERGED"):
        close_registered(ExamAPI(), SHA, REAL, lambda *_: "", tmp_path)
    assert not comments
