"""T48: CP3.6 exam-request idempotence, versioned issue markers, fail closed."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from pilot.orchestrator import chain_lots as chain

REQUEST = "req-286"
TASK = "req286contrato1"
PATH = "pilot/runs/req-286/templates/req286contrato1.task.json"
LOT = {"id": "SOL-001", "area": "CONTRATO", "requirement_ids": ["REQ-T48"],
       "write_paths": ["contracts/demo.openapi.yaml"]}
BINDING = {"task_name": TASK, "template_path": PATH}
CREATED = "https://github.com/paulozterra/lf-programming-sandbox/issues/902"


@pytest.fixture
def env(tmp_path, monkeypatch):
    src = tmp_path / PATH
    src.parent.mkdir(parents=True)
    src.write_text(json.dumps({"task_spec": {"objective": "original"}}))
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    monkeypatch.setattr(chain, "public_exam_request",
                        lambda *args: ("EXAM_REQUEST: " + args[2]["task_name"],
                                      f"Solicitud automática de examen independiente (T4).\\n"
                                      f"- Pedido: `{args[1]}`\\n"
                                      f"- Task ID: `{args[2]['task_name']}`"))
    chain._EXAM_RUN_CACHE.clear()
    yield src
    chain._EXAM_RUN_CACHE.clear()


def issue(key, *, number=902, state="open", reason=None, old=False):
    return {"number": number, "title": "EXAM_REQUEST: " + TASK,
            "body": ("Solicitud automática de examen independiente (T4).\n"
                     f"- Pedido: `{REQUEST}`\n- Task ID: `{TASK}`\n"
                     f"<!-- LF_EXAM_REQUEST_TASK:{TASK} -->\n" +
                     ("" if old else f"<!-- {key} -->")),
            "state": state, "state_reason": reason}


def harness(monkeypatch, *, rows=None, stale=False, bad=False):
    calls = []
    notices = []
    def listing(path, **kw):
        calls.append(("rest", path))
        if bad:
            raise ValueError("GITHUB_LIST_PAGINATION_LIMIT")
        if "comments" in path:
            return []
        return [] if stale else list(rows or [])
    def command(*args, **kw):
        calls.append(args)
        if args[:3] == ("gh", "label", "list"):
            return '[{"name":"exam-request"}]'
        if args[:3] == ("gh", "issue", "create"):
            return CREATED
        return ""
    monkeypatch.setattr(chain, "api_list", listing)
    monkeypatch.setattr(chain, "run", command)
    from pilot.orchestrator.lifecycle_test_support import fake_api
    monkeypatch.setattr(chain, "api", fake_api({}))
    monkeypatch.setattr(chain, "exam_notice",
                        lambda *args: notices.append(args))
    return calls, notices


def creates(calls):
    return [c for c in calls if c[:3] == ("gh", "issue", "create")]


@pytest.mark.parametrize("req_id,task", [
    ("req-275", "req275contrato1"), ("req-286", "req286contrato1"),
])
def test_t48_plan_then_admission_single_publish_even_if_rest_stale(
        env, monkeypatch, req_id, task):
    template = chain.ROOT / f"pilot/runs/{req_id}/templates/{task}.task.json"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(json.dumps({"task_spec": {"objective": "original"}}))
    binding = {"task_name": task, "template_path": str(template.relative_to(chain.ROOT))}
    calls, _ = harness(monkeypatch, stale=True)
    lots = {"lots": [LOT]}
    bindings = {"SOL-001": binding}
    monkeypatch.setattr(chain, "missing_exam", lambda *_: True)
    plan = chain.request_all_lot_exams(req_id, lots, bindings)
    # Re-enter through admission; the same cache entry avoids both REST and POST.
    before = len(calls)
    monkeypatch.setattr(chain, "require_green_base", lambda *args: None)
    monkeypatch.setattr(chain, "protected_test_conflict", lambda *args: None)
    admission = chain.admit_registration(req_id, binding, LOT, "a" * 40)
    assert plan[0]["exam_issue"] == 902
    assert admission["exam_issue"] == 902
    assert len(calls) == before
    assert len(creates(calls)) == 1


def test_t48_rest_open_reuses_without_create(env, monkeypatch):
    key = chain.exam_key(REQUEST, BINDING)
    calls, _ = harness(monkeypatch, rows=[issue(key)])
    assert chain.request_missing_exam(REQUEST, BINDING, LOT)["exam_issue"] == 902
    assert not creates(calls)


def test_t48_closed_discarded_never_recreated_and_notice(env, monkeypatch):
    key = chain.exam_key(REQUEST, BINDING)
    calls, notices = harness(monkeypatch, rows=[
        issue(key, state="closed", reason="not_planned")])
    a = chain.request_missing_exam(REQUEST, BINDING, LOT)
    b = chain.request_missing_exam(REQUEST, BINDING, LOT)
    assert a == b
    assert a["reason_code"] == "EXAM_REQUEST_PREVIOUSLY_DISCARDED"
    assert len(notices) == 1 and not creates(calls)


def test_t48_new_template_version_distinct_from_closed_issue(env, monkeypatch):
    old = chain.exam_key(REQUEST, BINDING)
    env.write_text(json.dumps({"task_spec": {"objective": "changed"}}))
    new = chain.exam_key(REQUEST, BINDING)
    assert old != new
    calls, _ = harness(monkeypatch, rows=[
        issue(old, state="closed", reason="not_planned")])
    assert chain.request_missing_exam(REQUEST, BINDING, LOT)["exam_issue"] == 902
    assert len(creates(calls)) == 1
    assert f"<!-- {new} -->" in creates(calls)[0][creates(calls)[0].index("--body") + 1]


def test_t48_legacy_task_marker_recognized(env, monkeypatch):
    key = chain.exam_key(REQUEST, BINDING)
    calls, _ = harness(monkeypatch, rows=[issue(key, old=True)])
    assert chain.request_missing_exam(REQUEST, BINDING, LOT)["exam_issue"] == 902
    assert not creates(calls)


def test_t48_incomplete_rest_blocks_without_publishing(env, monkeypatch):
    calls, notices = harness(monkeypatch, bad=True)
    result = chain.request_missing_exam(REQUEST, BINDING, LOT)
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "EXAM_REQUEST_LIST_UNTRUSTED"
    assert not creates(calls) and len(notices) == 1


def test_t48_two_open_reconciles_with_comment_and_close(env, monkeypatch):
    key = chain.exam_key(REQUEST, BINDING)
    calls, notices = harness(monkeypatch, rows=[issue(key, number=902),
                                                 issue(key, number=903)])
    result = chain.request_missing_exam(REQUEST, BINDING, LOT)
    assert result["exam_issue"] == 902
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "EXAM_REQUEST_DUPLICATE_OPEN"
    assert ("gh", "api", "-X", "PATCH",
            f"repos/{chain.REPO}/issues/903",
            "-f", "state=closed", "-f", "state_reason=duplicate") in calls
    comments = [c for c in calls if c[:3] == ("gh", "issue", "comment")]
    assert any("#902" in " ".join(c) for c in comments)
    assert not creates(calls)


def test_t48_missing_or_invalid_template_blocks(env, monkeypatch):
    env.unlink()
    calls, notices = harness(monkeypatch)
    result = chain.request_missing_exam(REQUEST, BINDING, LOT)
    assert result["reason_code"] == "EXAM_REQUEST_TEMPLATE_UNRESOLVED"
    assert not creates(calls) and len(notices) == 1


def test_t48_cache_per_template_hash_not_only_task(env, monkeypatch):
    calls, _ = harness(monkeypatch, stale=True)
    chain.request_missing_exam(REQUEST, BINDING, LOT)
    env.write_text(json.dumps({"task_spec": {"objective": "v2"}}))
    chain.request_missing_exam(REQUEST, BINDING, LOT)
    assert len(creates(calls)) == 2


def test_t48_old_native_registration_uses_legacy_version(env):
    native = chain.ROOT / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    native.parent.mkdir(parents=True)
    native.write_text(json.dumps({"task_spec": {"base_head_sha": "a" * 40}}))
    assert chain.exam_key(REQUEST, BINDING) == (
        f"LF_EXAM_REQUEST_KEY:{REQUEST}:{TASK}:legacy")


def test_t48_notice_is_deduped_by_rest_comments(env, monkeypatch):
    key = chain.exam_key(REQUEST, BINDING)
    calls = []
    marker = f"<!-- LF_EXAM_NOTICE:{key}:EXAM_REQUEST_PREVIOUSLY_DISCARDED -->"
    def api(path):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        assert path == "issues/286"
        return {"number": 286, "state": "open"}
    def listing(path, **kw):
        return [{"body": marker}] if path.endswith("/comments") else []
    monkeypatch.setattr(chain, "api", api)
    monkeypatch.setattr(chain, "api_list", listing)
    monkeypatch.setattr(chain, "run", lambda *a: calls.append(a))
    chain.exam_notice(REQUEST, key, "EXAM_REQUEST_PREVIOUSLY_DISCARDED")
    assert calls == []
