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



def test_owner_review_bound_to_exact_head_and_transition():
    api = fake_api({SLUG: {"state": life.SUSPENDING, "authorization_pr": 77}})
    def stale(path):
        rows = api(path)
        if path.startswith("pulls/77/reviews"):
            rows[0]["commit_id"] = "d" * 40
        return rows
    with pytest.raises(life.RequestStateError, match=life.CODE):
        life.require_open(SLUG, stale)


def test_drain_refuses_legacy_run_and_exam_reservation():
    entry = {"state": life.SUSPENDING, "authorization_pr": 77}
    api = fake_api({SLUG: entry})
    life.verify_drain(api, SLUG, entry)
    def legacy(path):
        if path.startswith("actions/runs?status=in_progress"):
            return {"total_count": 1, "workflow_runs": [
                {"id": 99, "path": ".github/workflows/worker-native.yml",
                 "created_at": "2026-11-27T05:00:00Z", "run_attempt": 2, "head_branch": "main"}]}
        return api(path)
    def reserved(path):
        if path.startswith("issues?state=open&labels=examiner-working"):
            return [{"id": 98, "body": "- Pedido: `req-123`"}]
        return api(path)
    for reader in (legacy, reserved):
        with pytest.raises(life.RequestStateError, match="REQUEST_DRAIN_PENDING"):
            life.verify_drain(reader, SLUG, entry)


def test_global_registry_not_a_suspension_bypass():
    api = fake_api({SLUG: {"state": life.SUSPENDED, "authorization_pr": 77}})
    life.require_pr_open("lf/implemented-registry/123456789abc",
                         ["pilot/registry/implemented.json"], api)
    with pytest.raises(life.RequestStateError, match=life.CODE):
        life.require_pr_open("lf/implemented-registry/123456789abc",
                             ["pilot/registry/implemented.json", "pilot/runs/req-123/state.json"], api)


def test_bootstrap_empty_policy_and_trusted_main_train():
    import subprocess
    root = life.ROOT
    subprocess.run(["git", "rev-parse", "--verify", "origin/main"], cwd=root, check=True,
                   capture_output=True)
    tree = subprocess.check_output(["git", "ls-tree", "origin/main", "--", CONTROL], cwd=root)
    if not tree:
        assert life.parse_control((root / CONTROL).read_bytes()) == {}
        old_train = subprocess.check_output(["git", "show", "origin/main:pilot/sandbox_train.py"], cwd=root)
        assert b"guard_request_lifecycle" not in old_train
    workflow = (root / ".github/workflows/sandbox-train.yml").read_text()
    assert "ref: main" in workflow


def test_drain_blocks_old_snapshot_even_if_created_after_cutoff():
    entry = {"state": life.SUSPENDING, "authorization_pr": 77}
    api = fake_api({SLUG: entry})
    def delayed(path):
        if path.startswith("actions/runs?status=in_progress"):
            return {"total_count": 1, "workflow_runs": [
                {"id": 99, "path": ".github/workflows/t7-request.yml",
                 "created_at": "2026-11-27T07:00:00Z", "run_attempt": 1,
                 "head_branch": "main", "head_sha": "d" * 40}]}
        if path.startswith("compare/"):
            return {"status": "behind", "base_commit": {"sha": MERGE},
                    "merge_base_commit": {"sha": "d" * 40}}
        return api(path)
    with pytest.raises(life.RequestStateError, match="REQUEST_DRAIN_PENDING"):
        life.verify_drain(delayed, SLUG, entry)


def test_maintenance_cannot_edit_suspended_task_artifacts(monkeypatch):
    monkeypatch.setattr(life, "request_for_task", lambda *a, **k: SLUG)
    api = fake_api({SLUG: {"state": life.SUSPENDED, "authorization_pr": 77}})
    for path in ("pilot/worker_v08/native_tasks/demo.json", "pilot/holdouts/demo.oracle.json.age",
                 "pilot/orchestrator/chain_plans/req-123.json", "pilot/native_proposals/demo.json"):
        with pytest.raises(life.RequestStateError, match="REQUEST_SUSPENDED"):
            life.require_pr_open("maintenance", [path], api)
