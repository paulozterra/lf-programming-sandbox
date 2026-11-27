"""T20 offline: one red bot PR HEAD -> exactly one CI dispatch, watchdog."""
from __future__ import annotations

import base64
from pathlib import Path
import json
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator import bot_ci_retry as retry
from pilot import request_failure_notify as notify

REPO = "paulozterra/lf-programming-sandbox"
SHA = "a" * 40
HEAD = "b" * 40
BRANCH = "lf/native-registration/envelope-req901contract-aabbccddeeff"
BOT = "github-actions[bot]"


def pr(number=901, sha=SHA, branch=BRANCH):
    return {"number": number, "headRefName": branch, "headRefOid": sha,
            "author": {"login": BOT}}


def details(number=901, sha=SHA, branch=BRANCH):
    return {"number": number, "state": "open", "user": {"login": BOT},
            "head": {"sha": sha, "ref": branch, "repo": {"full_name": REPO}},
            "base": {"ref": "main", "repo": {"full_name": REPO}}}


def ci(id=200, *, conclusion="failure", status="completed", sha=SHA,
       branch=BRANCH, event="pull_request"):
    return {"id": id, "head_sha": sha, "head_branch": branch,
            "status": status, "conclusion": conclusion,
            "created_at": "2026-11-15T20:00:%02dZ" % (id % 60),
            "event": event, "path": ".github/workflows/ci.yml"}


def harness(runs, *, sha=SHA, branch=BRANCH, number=901, changed=False):
    ledger = []
    calls = []
    def run(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "comment"):
            ledger.append({"user": {"login": BOT},
                           "body": args[-1]})
        return ""
    def api(path):
        if path == f"pulls/{number}":
            return details(number, "c" * 40 if changed else sha, branch)
        if path == f"actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100":
            return {"workflow_runs": runs, "total_count": len(runs)}
        raise AssertionError(path)
    return run, api, ledger, calls


def run_retries(runs, *, ledger=None, changed=False, bot=True):
    run, api, comments, calls = harness(runs, changed=changed)
    if ledger is not None:
        comments.extend(ledger)
    with patch.object(retry, "_listed", return_value=[
            pr() if bot else {**pr(), "author": {"login": "a-human"}}]), \
         patch.object(retry, "_comment_rows", side_effect=lambda *_: comments):
        results = retry.retry_failed_bot_prs(HEAD, run, api, REPO, [], lambda _: True)
    return results, calls, comments


def test_red_bot_pr_dispatch_once_and_same_sha_never_retries_again():
    rows, actions, comments = run_retries([ci()])
    assert rows[0]["status"] == "CI_RETRY_DISPATCHED"
    assert sum(x[:3] == ("gh", "workflow", "run") for x in actions) == 1
    assert sum(x[:3] == ("gh", "pr", "comment") for x in actions) == 1
    assert f"<!-- LF_T20_CI_RETRY:901:{SHA}:200 -->" in comments[0]["body"]
    # Same HEAD, same failed original: another sweep cannot dispatch.
    rows2, actions2, _ = run_retries([ci()], ledger=comments)
    assert rows2[0]["status"] == "CI_RETRY_ALREADY_RECORDED"
    assert not any(x[:3] == ("gh", "workflow", "run") for x in actions2)


def test_latest_executed_must_be_failed_not_latest_action_required_or_success():
    # action_required is never an executed CI and cannot hide failure.
    rows, calls, _ = run_retries([ci(), ci(201, conclusion="action_required",
                                         status="completed", event="workflow_dispatch")])
    assert rows[0]["status"] == "CI_RETRY_DISPATCHED"
    assert any(c[:3] == ("gh", "workflow", "run") for c in calls)
    for newer in [ci(201, conclusion="success"), ci(201, status="in_progress",
                  conclusion=None)]:
        rows, calls, _ = run_retries([ci(), newer])
        assert rows == []
        assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


def test_head_mismatch_and_human_pr_do_not_dispatch():
    rows, calls, _ = run_retries([ci()], changed=True)
    assert rows == []
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)
    rows, calls, _ = run_retries([ci()], bot=False)
    assert rows == [] and not calls


def test_one_failing_pr_does_not_prevent_another_healthy_pr():
    good = dict(pr(902), headRefName="lf/request/req-902",
                headRefOid="d" * 40)
    dispatched = []
    def api(path):
        if path == "pulls/901":
            return details()
        if path == "pulls/902":
            return details(902, "d" * 40, "lf/request/req-902")
        if "head_sha=" in path:
            sha = path.split("head_sha=")[1].split("&")[0]
            row = ci(200 if sha == SHA else 210, sha=sha,
                     branch=BRANCH if sha == SHA else "lf/request/req-902",
                     conclusion="failure" if sha == SHA else "success")
            return {"workflow_runs": [row], "total_count": 1}
        raise AssertionError(path)
    def run(*args):
        dispatched.append(args)
        return ""
    with patch.object(retry, "_listed", return_value=[pr(), good]), \
         patch.object(retry, "_comment_rows", return_value=[]):
        result = retry.retry_failed_bot_prs(HEAD, run, api, REPO, [], lambda _: True)
    assert len(result) == 1 and result[0]["pr"] == 901
    assert sum(x[:3] == ("gh", "workflow", "run") for x in dispatched) == 1


def test_sweep_retries_even_with_zero_active_plans():
    invoked = []
    native_queries = []
    def simulated_api(path):
        native_queries.append(path)
        assert path == "actions/workflows/worker-native.yml/runs?per_page=100"
        return {"total_count": 0, "workflow_runs": []}
    with patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "plans", return_value=[]), \
         patch.object(chain_lots, "api", side_effect=simulated_api), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
          patch.object(chain_lots, "replay_native_integration", return_value=[]), \
         patch.object(chain_lots, "retry_failed_bot_prs", side_effect=lambda *_, **_kw:
                      invoked.append(True) or [{"status": "CI_RETRY_DISPATCHED", "pr": 901}]):
        rows = chain_lots.process(sweep=True, base_sha=HEAD)
    assert invoked == [True]
    assert native_queries == ["actions/workflows/worker-native.yml/runs?per_page=100"] * 2
    assert rows == [{"status": "CI_RETRY_DISPATCHED", "pr": 901}]


class API:
    def __init__(self, *, latest=True, verified=True):
        self.latest = latest
        self.verified = verified
        self.comments = []
        self.calls = []

    def api(self, method, path, body=None):

        from pilot.orchestrator.lifecycle_test_support import content, CONTROL

        if method == "GET" and path == f"/contents/{CONTROL}?ref=main":

            return content({})
        self.calls.append((method, path, body))
        if path.startswith("/pulls?state=open&head="):
            return [details()]
        if path == f"/actions/workflows/ci.yml/runs?head_sha={SHA}&per_page=100":
            newer = ci(201, conclusion="failure", event="workflow_dispatch")
            if not self.latest:
                newer = ci(202, conclusion="success", event="workflow_dispatch")
            return {"workflow_runs": [ci(), newer], "total_count": 2}
        if path == "/pulls/901/files?per_page=100":
            return [{"filename":
                     "pilot/runs/req-901/proposal_requests/req901contract.proposal-request.json"}]
        if path == "/contents/pilot/runs/req-901/request_meta.json?ref=main":
            metadata = {"issue": 901 if self.verified else 902}
            return {"content": base64.b64encode(json.dumps(metadata).encode()).decode()}
        if path == "/issues/901":
            return {"number": 901, "state": "open", "labels": [{"name": "lf-request"}]}
        if method == "POST" and path == "/issues/901/comments":
            self.comments.append({"user": {"login": BOT}, "body": body["body"]})
            return {}
        raise AssertionError((method, path))

    def pages(self, path):
        if path == "/issues/901/comments":
            return [{"user": {"login": BOT},
                     "body": f"<!-- LF_T20_CI_RETRY:901:{SHA}:200 -->"}, *self.comments]
        raise AssertionError(path)


def test_watchdog_after_failed_second_run_comments_original_issue_once():
    api = API()
    second = ci(201, event="workflow_dispatch")
    assert notify.notify_t20_retry_exhaustion(api, second) == "T20_RETRY_EXHAUSTION_NOTIFIED"
    assert len(api.comments) == 1
    assert "CI_RETRY_EXHAUSTED" in api.comments[0]["body"]
    assert "https://github.com/" + REPO + "/actions/runs/201" in api.comments[0]["body"]
    assert notify.notify_t20_retry_exhaustion(api, second) == "T20_RETRY_EXHAUSTION_ALREADY_NOTIFIED"
    posts = [x for x in api.calls if x[0] == "POST"]
    assert len(posts) == 1 and all("/labels" not in row[1] for row in posts)


def test_watchdog_never_notifies_first_failure_or_superseded_or_bad_issue():
    assert notify.notify_t20_retry_exhaustion(API(), ci()) == "T20_NOT_RETRY_EXHAUSTION"
    assert notify.notify_t20_retry_exhaustion(
        API(latest=False), ci(201, event="workflow_dispatch")) == "T20_RETRY_SUPERSEDED"
    assert notify.notify_t20_retry_exhaustion(
        API(verified=False), ci(201, event="workflow_dispatch")) == "T20_RETRY_ISSUE_UNVERIFIED"
