"""D22 regression: no external effects, no Worker or real GitHub calls."""
import pytest

from pilot.orchestrator import request_lifecycle as life

from pilot.orchestrator.lifecycle_test_support import fake_api, content, MERGE, SLUG, OTHER, CONTROL


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


def test_unknown_owner_authorization_fails_closed():
    api = fake_api({SLUG: {"state": life.SUSPENDED, "authorization_pr": 77}})
    def bad(path):
        if path.startswith("issues/77/events"):
            return [{"event": "labeled", "actor": {"login": "github-actions[bot]"},
                     "label": {"name": "ready-to-merge"}}]
        return api(path)
    with pytest.raises(life.RequestStateError, match=life.CODE):
        life.require_open(SLUG, bad)


@pytest.mark.parametrize("branch, paths", [
    ("lf/request/req-123", ["pilot/runs/req-123/request.md"]),
    ("lf/chain-blocked/req-123-123456789abc", ["pilot/runs/req-123/state.json"]),
    ("lf/evidence/req-123-123456789abc", ["pilot/runs/req-123/H_REPORT.md"]),
    ("lf/generated-t7/123456789abc", ["pilot/runs/req-123/lots.json"]),
    ("maintenance", ["pilot/runs/req-123/analysis.json"]),
])
def test_existing_pending_pr_cannot_cross_suspension(branch, paths):
    api = fake_api({SLUG: {"state": life.SUSPENDED, "authorization_pr": 77}})
    with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
        life.require_pr_open(branch, paths, api)


def test_train_guard_resolves_unregistered_task_from_trusted_plan(monkeypatch):
    monkeypatch.setattr(life, "request_for_task", lambda task, **kwargs: SLUG)
    api = fake_api({SLUG: {"state": life.SUSPENDING, "authorization_pr": 77}})
    for branch in ("exam/req123backend1",
                   "lf/native-registration/req123backend1-123456789abc",
                   "lf/native-integration/req123backend1-run-999",
                   "lf/exam-retire/req123backend1-123456789abc"):
        with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
            life.require_pr_open(branch, [], api)
