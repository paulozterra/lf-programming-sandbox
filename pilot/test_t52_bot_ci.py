"""T52 A: the Train approves an action_required bot CI before any fallback.

An approvable pull_request run of the exact SHA suppresses the fallback
dispatch; the Train dispatches once only if nothing is usable or approvable,
or an approved run never starts within CI_APPROVAL_GRACE_SECONDS.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sandbox_train as train  # noqa: E402

SHA = "c" * 40
REPO = "paulozterra/lf-programming-sandbox"


def pr():
    return {"number": 91, "state": "open", "draft": False,
            "head": {"sha": SHA, "ref": "lf/native-integration/x-run-1",
                     "repo": {"full_name": REPO}},
            "base": {"ref": "main"}, "labels": [{"name": "ready-to-merge"}],
            "user": {"login": "github-actions[bot]"}}


def ci_run(run_id, status, sha=SHA, event="pull_request", repo=REPO,
           path=".github/workflows/ci.yml"):
    return {"id": run_id, "head_sha": sha, "event": event, "status": status,
            "conclusion": None, "head_repository": {"full_name": repo}, "path": path}


class Clock:
    def __init__(self, first_sleep=None):
        self.now = 0
        self.first_sleep = first_sleep

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        if self.first_sleep is not None:
            seconds, self.first_sleep = self.first_sleep, None  # one slow poll
        self.now += seconds


class GitHub:
    """`timeline(now)` returns the ci.yml runs visible at that moment."""

    def __init__(self, clock, timeline, green_at=None, on_dispatch=None):
        self.clock, self.timeline, self.green_at = clock, timeline, green_at
        self.on_dispatch = on_dispatch
        self.posts, self.order = [], []

    def api(self, method, path, body=None, expected=(200,)):
        if method == "POST" and path.endswith("/ci.yml/dispatches") and self.on_dispatch:
            self.on_dispatch(self.clock.now)
        if method == "POST":
            self.posts.append(path)
            self.order.append(("POST", path))
            return {}
        if path.startswith("/actions/runs?head_sha="):
            self.order.append(("APPROVE_LIST", path))
            rows = [r for r in self.timeline(self.clock.now)
                    if r["status"] == "action_required"]
            return {"workflow_runs": rows}
        if path.startswith("/actions/workflows/ci.yml/runs?"):
            self.order.append(("CI_LIST", path))
            return {"workflow_runs": self.timeline(self.clock.now)}
        raise AssertionError((method, path))

    def checks(self, sha):
        if self.green_at is not None and self.clock.now >= self.green_at:
            return {n: {"id": 1, "status": "completed", "conclusion": "success"}
                    for n in train.REQUIRED}
        return {}


def run(timeline, green_at=None, first_sleep=None, on_dispatch=None):
    clock = Clock(first_sleep)
    gh = GitHub(clock, timeline, green_at, on_dispatch)
    with patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO}), \
         patch.object(train, "api", side_effect=gh.api), \
         patch.object(train, "pr_data", return_value=pr()), \
         patch.object(train, "check_pr"), \
         patch.object(train, "needs_rehearsal", return_value=False), \
         patch.object(train, "checks_for_head", side_effect=gh.checks), \
         patch.object(train.time, "monotonic", side_effect=clock.monotonic), \
         patch.object(train.time, "sleep", side_effect=clock.sleep):
        try:
            result = train.await_checks(91, SHA, set())
        except train.TrainError as exc:
            result = str(exc)
    return result, gh


def dispatches(gh):
    return [p for p in gh.posts if p == "/actions/workflows/ci.yml/dispatches"]


def test_action_required_run_is_approved_and_no_second_ci_is_dispatched():
    # Waits in action_required until approved, then runs and goes green.
    def timeline(now):
        return [ci_run(10, "action_required" if now < 120 else "in_progress")]
    result, gh = run(timeline, green_at=200)
    assert set(result) == set(train.REQUIRED)
    assert "/actions/runs/10/approve" in gh.posts
    assert dispatches(gh) == []


def test_approval_happens_before_any_fallback_evaluation():
    result, gh = run(lambda now: [ci_run(10, "action_required")], green_at=None)
    first_approve = next(i for i, (k, p) in enumerate(gh.order)
                         if k == "POST" and p.endswith("/approve"))
    first_dispatch = next((i for i, (k, p) in enumerate(gh.order)
                           if p == "/actions/workflows/ci.yml/dispatches"), None)
    assert first_dispatch is None or first_approve < first_dispatch


def test_no_run_at_all_dispatches_once_after_grace():
    result, gh = run(lambda now: [], green_at=400)
    assert set(result) == set(train.REQUIRED)
    assert dispatches(gh) == ["/actions/workflows/ci.yml/dispatches"]


def test_approved_run_that_never_starts_gets_one_bounded_fallback():
    result, gh = run(lambda now: [ci_run(10, "action_required")], green_at=None)
    assert result == "CHECK_WAIT_TIMEOUT"
    assert dispatches(gh) == ["/actions/workflows/ci.yml/dispatches"]
    approve = next(i for i, (k, p) in enumerate(gh.order) if p.endswith("/approve"))
    dispatch = next(i for i, (k, p) in enumerate(gh.order)
                    if p == "/actions/workflows/ci.yml/dispatches")
    assert approve < dispatch


def test_pending_run_of_another_sha_or_fork_does_not_suppress_fallback():
    for foreign in (ci_run(11, "action_required", sha="d" * 40),
                    ci_run(12, "action_required", repo="evil/fork")):
        result, gh = run(lambda now, f=foreign: [f], green_at=400)
        assert set(result) == set(train.REQUIRED)
        assert dispatches(gh) == ["/actions/workflows/ci.yml/dispatches"]


def test_usable_run_suppresses_dispatch_as_before():
    result, gh = run(lambda now: [ci_run(13, "in_progress")], green_at=300)
    assert set(result) == set(train.REQUIRED)
    assert dispatches(gh) == []


def test_pending_approval_listing_is_exact_and_same_repo_only():
    rows = [ci_run(1, "action_required"), ci_run(2, "action_required", sha="e" * 40),
            ci_run(3, "action_required", repo="evil/fork"),
            ci_run(4, "action_required", event="workflow_dispatch"),
            ci_run(5, "completed")]
    with patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO}), \
         patch.object(train, "api", return_value={"workflow_runs": rows}):
        assert [r["id"] for r in train.ci_workflow_runs_for_head(SHA, pending_approval=True)] == [1]
        assert [r["id"] for r in train.ci_workflow_runs_for_head(SHA)] == [5]


def test_pending_first_seen_late_gets_full_approval_grace():
    """Review H1: if the first look after the 60s grace happens late (slow API,
    t=300) and finds a pending run, the Train must still wait
    CI_APPROVAL_GRACE_SECONDS from that sighting, not dispatch at once."""
    def timeline(now):
        return [ci_run(20, "action_required" if now < 400 else "in_progress")]
    result, gh = run(timeline, green_at=450, first_sleep=300)
    assert set(result) == set(train.REQUIRED)
    assert dispatches(gh) == []


def test_pending_never_starting_dispatches_after_grace_from_first_sight():
    def timeline(now):
        return [ci_run(21, "action_required")]
    clock_at_dispatch = []
    result, gh = run(timeline, green_at=None, first_sleep=300,
                     on_dispatch=clock_at_dispatch.append)
    assert dispatches(gh) == ["/actions/workflows/ci.yml/dispatches"]
    assert clock_at_dispatch[0] >= 300 + train.CI_APPROVAL_GRACE_SECONDS


def test_only_required_workflows_are_approved():
    rows = [ci_run(30, "action_required"),
            ci_run(31, "action_required", path=".github/workflows/exam-rehearsal.yml"),
            ci_run(32, "action_required", path=".github/workflows/analysis-f0.yml")]
    posts = []

    def api(method, path, body=None, expected=(200,)):
        if method == "POST":
            posts.append(path)
            return {}
        return {"workflow_runs": rows}
    with patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO}), \
         patch.object(train, "api", side_effect=api):
        train.approve_pending_runs(SHA)
    assert posts == ["/actions/runs/30/approve", "/actions/runs/31/approve"]
