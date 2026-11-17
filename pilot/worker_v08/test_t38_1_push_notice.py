"""T38.1: push-rejection notice reaches unlabeled request issues and explains PATCH_NOT_APPLICABLE."""
import json
import native_push_failure_notify as n

SHA = "a" * 40


def _run(monkeypatch, code, labels):
    calls = []

    def fake(*args):
        calls.append(args)
        if args[:2] == ("gh", "api") and args[2].endswith("/issues/286"):
            return json.dumps({"number": 286, "state": "open", "labels": labels})
        if args[:2] == ("gh", "api"):
            return "[]"
        return ""
    monkeypatch.setattr(n, "find_issue", lambda c, t: 286)
    monkeypatch.setattr(n, "command", fake)
    out = n.notify(".", "lf/native-proposal/req286backend2", SHA, code)
    return out, [c for c in calls if c[:3] == ("gh", "issue", "comment")]


def test_unlabeled_issue_gets_notice(monkeypatch):
    out, posted = _run(monkeypatch, "NATIVE_PUSH_GUARD_FAILED", [])
    assert out == "NATIVE_PUSH_ALERT_COMMENTED" and len(posted) == 1


def test_patch_not_applicable_says_no_attempt_charged(monkeypatch):
    out, posted = _run(monkeypatch, "NATIVE_PUSH_PATCH_NOT_APPLICABLE", [])
    body = posted[0][-1]
    assert out == "NATIVE_PUSH_ALERT_COMMENTED"
    assert "NO se cobró intento" in body and "git apply --check" in body
