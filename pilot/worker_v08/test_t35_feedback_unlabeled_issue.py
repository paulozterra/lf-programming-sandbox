"""T35: feedback reaches a request Issue created through the API (no lf-request label)."""
import json

import pytest

from pilot.worker_v08 import native_feedback_delivery as delivery
from pilot.orchestrator.lifecycle_test_support import content, CONTROL
from pilot.worker_v08.test_t22_feedback_delivery import PUBLIC, REPO, SHA, TASK, feedback_file, root


def _run(comments):
    def run(*args):
        if args[:2] == ("gh", "api"):
            return json.dumps(comments)
        if args[:3] == ("gh", "issue", "comment"):
            comments.append({"user": {"login": "github-actions[bot]"}, "body": args[-1]})
            return ""
        raise AssertionError(args)
    return run


def test_unlabeled_request_issue_receives_feedback(tmp_path):
    control = root(tmp_path)
    visible = delivery.read_public(feedback_file(tmp_path), 1)
    comments = []
    assert delivery.publish(_run(comments), lambda r: content({}) if r == f"contents/{CONTROL}?ref=main" else {"number": 901, "state": "open", "labels": []},
                            REPO, control, TASK, SHA, 1, visible,
                            "BLOCKED_OR_FAILED") == "FEEDBACK_PUBLISHED"
    assert delivery.marker(TASK, SHA, 1) in comments[0]["body"]


def test_pull_request_or_other_number_still_denied(tmp_path):
    control = root(tmp_path)
    visible = delivery.read_public(feedback_file(tmp_path), 1)
    for issue in ({"number": 901, "pull_request": {"url": "x"}}, {"number": 902}):
        with pytest.raises(delivery.FeedbackBlocked, match="REQUEST_STATE_UNRESOLVED"):
            delivery.publish(_run([]), lambda r, i=issue: i, REPO, control, TASK, SHA, 1,
                             visible, "BLOCKED_OR_FAILED")
