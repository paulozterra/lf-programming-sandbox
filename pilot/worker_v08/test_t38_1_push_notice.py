"""T38.1: push-rejection notice reaches unlabeled request issues and explains PATCH_NOT_APPLICABLE."""
import json
import native_push_failure_notify as n

SHA = "a" * 40


def _run(monkeypatch, code, labels, *, suspend=False):
    calls = []

    from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL
    def fake(*args):
        calls.append(args)
        if args[:2] == ("gh", "api") and args[2].startswith(f"repos/{n.REPO}/"):
            path = args[2].removeprefix(f"repos/{n.REPO}/")
            if path == f"contents/{CONTROL}?ref=main":
                paused = suspend and any("/comments?" in str(x) for x in calls)
                return json.dumps(fake_api({"req-286": {"state":"SUSPENDING","authorization_pr":77}} if paused else {})(path))
            if path.startswith(("contents/", "pulls/", "commits/", "issues/77/events")):
                return json.dumps(fake_api({"req-286": {"state":"SUSPENDING","authorization_pr":77}})(path))
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


def test_late_suspension_prevents_push_notice(monkeypatch):
    out, posted = _run(monkeypatch, "NATIVE_PUSH_PATCH_NOT_APPLICABLE", [], suspend=True)
    assert out == "REQUEST_SUSPENDED" and not posted
