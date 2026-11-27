"""D22 regression: no external effects, no Worker or real GitHub calls."""
import base64
import json

import pytest

from pilot.orchestrator import request_lifecycle as life

MERGE = "a" * 40
SLUG = "req-123"
OTHER = "req-456"
CONTROL = life.CONTROL_PATH


def content(entries):
    data = json.dumps({"schema_version": life.CONTROL_SCHEMA, "requests": entries}).encode()
    return {"type": "file", "encoding": "base64", "size": len(data),
            "content": base64.b64encode(data).decode()}


def fake_api(entries, *, historical=None, issue_state="open"):
    def api(path):
        if path.startswith("issues/"):
            return {"number": int(path.split("/")[1]), "state": issue_state,
                    "labels": [{"name": "lf-request-blocked"}]}
        if path == f"contents/{CONTROL}?ref=main":
            return content(entries)
        if path == f"contents/{CONTROL}?ref={MERGE}":
            return content(entries if historical is None else historical)
        if path == "pulls/77":
            return {"number": 77, "merged": True, "merge_commit_sha": MERGE,
                    "base": {"ref": "main", "repo": {"full_name": "example/sandbox"}},
                    "head": {"repo": {"full_name": "example/sandbox"}}}
        if path == f"compare/{MERGE}...main":
            return {"status": "ahead", "behind_by": 0}
        raise AssertionError(path)
    return api


@pytest.mark.parametrize("state", [life.SUSPENDING, life.SUSPENDED])
def test_suspension_denies_effects_but_not_unrelated_request(state):
    api = fake_api({SLUG: {"state": state, "authorization_pr": 77}})
    assert life.request_state(SLUG, api) == state
    with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
        life.require_open(SLUG, api)
    assert life.request_state(OTHER, api) == life.OPEN


def test_blocked_label_is_not_suspension():
    assert life.request_state(SLUG, fake_api({})) == life.OPEN


def test_authorized_resume_is_explicit():
    api = fake_api({SLUG: {"state": "ACTIVE", "authorization_pr": 77}})
    assert life.request_state(SLUG, api) == life.OPEN


def test_live_policy_rechecked_after_admission():
    entries = {}
    api = fake_api(entries)
    life.require_open(SLUG, api)
    entries[SLUG] = {"state": life.SUSPENDING, "authorization_pr": 77}
    with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
        life.require_open(SLUG, api)


def test_unverified_authorization_fails_closed():
    api = fake_api({SLUG: {"state": life.SUSPENDED, "authorization_pr": 77}}, historical={})
    with pytest.raises(life.RequestStateError, match=life.CODE):
        life.require_open(SLUG, api)


@pytest.mark.parametrize("raw", [b"{}", b'{"schema_version":"LF_REQUEST_LIFECYCLE_CONTROL_V1","requests":{},"requests":{}}',
                                 b'{"schema_version":"LF_REQUEST_LIFECYCLE_CONTROL_V1","requests":{"req-123":{"state":"ACTIVE","authorization_pr":true}}}'])
def test_malformed_policy_denied(raw):
    with pytest.raises(life.RequestStateError, match=life.CODE):
        life.parse_control(raw)


def test_unavailable_policy_denies_open():
    def api(path):
        if path == "issues/123":
            return {"number": 123, "state": "open"}
        raise OSError("unavailable")
    with pytest.raises(life.RequestStateError, match=life.CODE):
        life.require_open(SLUG, api)


def test_closed_is_not_suspension(monkeypatch):
    monkeypatch.setattr(life, "_finalized", lambda *_: False)
    assert life.request_state(SLUG, fake_api({}, issue_state="closed")) == life.CLOSED_CANCELLED


def test_governed_transition_no_delete_no_shortcut():
    pending = {SLUG: {"state": life.SUSPENDING, "authorization_pr": 77}}
    suspended = {SLUG: {"state": life.SUSPENDED, "authorization_pr": 78}}
    resumed = {SLUG: {"state": "ACTIVE", "authorization_pr": 79}}
    assert life.validate_control_transition({}, pending, 77) == SLUG
    assert life.validate_control_transition(pending, suspended, 78) == SLUG
    assert life.validate_control_transition(suspended, resumed, 79) == SLUG
    for before, after, n in [(pending, {}, 78), ({}, suspended, 78),
                              (pending, resumed, 79), (suspended, resumed, 80)]:
        with pytest.raises(life.RequestStateError, match=life.CODE):
            life.validate_control_transition(before, after, n)
