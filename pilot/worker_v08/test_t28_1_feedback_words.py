"""T28.1: ordinary words in visible output do not hide feedback; real secrets do."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_feedback_delivery as delivery  # noqa: E402


def feedback(text: str) -> bytes:
    return json.dumps({
        "schema_version": delivery.SCHEMA, "attempt": 2, "kind": "VISIBLE_ACCEPTANCE_ONLY",
        "commands": [{name: None for name in delivery.CMD_KEYS} | {
            "name": "std-be-05-spotless-check", "status": "FAIL", "returncode": 1,
            "stdout_excerpt": text}],
    }).encode()


@pytest.mark.parametrize("text", [
    "ReminderController.java had format violations: import RequestHeader order. "
    "Run 'mvn spotless:apply'",
    "AuthService.session(token) returned empty: hidden field, private method, secret rotation",
])
def test_ordinary_auth_words_are_published(text):
    assert delivery.parse_feedback(feedback(text), 2)["commands"][0]["stdout_excerpt"] == text


@pytest.mark.parametrize("text", [
    "Authorization: Bearer AbCdEfGhIjKlMnOpQrStUv123",
    "hash $2a$10$CO5.OM.rZMc1GUEY68j5BuwHRON65SQb7B63Qvnk8",
    "see pilot/holdouts/x.oracle.json.age",
    "holdout_sha256=abc",
    "-----BEGIN RSA PRIVATE KEY-----",
])
def test_exam_material_and_secret_values_stay_blocked(text):
    with pytest.raises(delivery.FeedbackBlocked, match="FEEDBACK_NO_PUBLICO"):
        delivery.parse_feedback(feedback(text), 2)


def test_full_worker_excerpt_length_is_published():
    # The Worker keeps the last 4000 characters of a command's output.
    text = ("[ERROR] src/main/java/demo/GadgetController.java format violation\n" * 80)[-4000:]
    assert len(text) == 4000
    assert delivery.parse_feedback(feedback(text), 2)["commands"][0]["stdout_excerpt"] == text


def test_worker_workspace_path_is_normalized_not_blocked():
    text = ("[ERROR] Failed to execute goal spotless:check on project time-service: "
            "/home/runner/work/_temp/native-private/workspace/apps/time-service/src/main/java/"
            "demo/GadgetController.java had format violations")
    out = delivery.parse_feedback(feedback(text), 2)["commands"][0]["stdout_excerpt"]
    assert "native-private" not in out and "<worker-workspace>/" in out
    assert out.endswith("demo/GadgetController.java had format violations")


def test_exam_file_under_workspace_still_blocked():
    with pytest.raises(delivery.FeedbackBlocked, match="PRIVATE_PATTERN"):
        delivery.parse_feedback(feedback("/home/runner/_temp/native-private/holdout.oracle.json"), 2)
