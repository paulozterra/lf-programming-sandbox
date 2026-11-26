"""T58: automatic examiner queue, brief and lot-scoped rule traces."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pilot.orchestrator import examiner_brief as eb
from pilot.orchestrator import examiner_queue as eq
from pilot.orchestrator import publish_exam as pe

REQ = "req-9"
TASK = "req9backend2"
WRITE = ["apps/x/Service.java"]


def _issue(task=TASK, slug=REQ, number=50, labels=("exam-request",), user=eq.BOT,
           write=WRITE, reqs=("REQ-SBX-R-ONE",)):
    body = ("Solicitud automática de examen independiente (T4).\n\n"
            f"- Pedido: `{slug}`\n- Lote: `SOL-002`\n- Task ID: `{task}`\n"
            f"- Rutas de escritura: `{json.dumps(write)}`\n"
            f"- REQ: `{json.dumps(list(reqs))}`\n\n"
            f"<!-- LF_EXAM_REQUEST_TASK:{task} -->\n")
    return {"number": number, "state": "open", "title": f"EXAM_REQUEST: {task}",
            "user": {"login": user}, "labels": [{"name": n} for n in labels], "body": body}


def _repo(root: Path, task=TASK, write=WRITE, reqs=("REQ-SBX-R-ONE",)):
    folder = root / "pilot" / "runs" / REQ
    (folder / "templates").mkdir(parents=True)
    (folder / "templates" / f"{task}.task.json").write_text(json.dumps({"task_spec": {
        "objective": "Implementar BACKEND", "base_head_sha": "<FILL_AT_REGISTRATION>",
        "write_path_patterns": write, "context_path_patterns": ["contracts/x.yaml"],
        "acceptance_commands": [{"name": "visible", "argv": ["true"]}]}}))
    (folder / "lots.json").write_text(json.dumps({"lots": [
        {"id": "SOL-002", "area": "BACKEND", "depends_on": ["SOL-001"],
         "write_paths": write, "requirement_ids": list(reqs)},
        {"id": "SOL-003", "area": "FRONTEND", "depends_on": [],
         "write_paths": ["apps/web/page.tsx"], "requirement_ids": ["REQ-SBX-R-TWO"]}]}))
    fixtures = root / "analysis" / "fixtures" / "sbx_demo"
    fixtures.mkdir(parents=True)
    (fixtures / "effective_rules.json").write_text(json.dumps({"rules": [
        {"code": "SBX-R-ONE", "title": "Uno", "descripcion": "regla del lote"},
        {"code": "SBX-R-TWO", "title": "Dos", "descripcion": "regla de otro lote"}]}))
    (root / "contracts").mkdir()
    (root / "contracts" / "x.yaml").write_text("openapi: 3.1.0\n")
    (root / "pilot" / "holdouts").mkdir(parents=True)


# --- queue -----------------------------------------------------------------

def test_queue_lists_only_planned_requests_without_exam(tmp_path):
    _repo(tmp_path)
    q = eq.build_queue([_issue()], [], tmp_path, open_requests={9})
    assert [r["task"] for r in q["pending"]] == [TASK]
    assert q["pending"][0]["requirement_ids"] == ["REQ-SBX-R-ONE"]


def test_queue_skips_published_in_flight_and_blocked(tmp_path):
    _repo(tmp_path)
    assert eq.build_queue([_issue()], [{"head": {"ref": f"exam/{TASK}"}}],
                          tmp_path, {9})["in_flight"][0]["task"] == TASK
    assert eq.build_queue([_issue(labels=("exam-request", "examiner-working"))], [],
                          tmp_path, {9})["in_flight"][0]["task"] == TASK
    assert eq.build_queue([_issue(labels=("exam-request", "examiner-blocked"))], [],
                          tmp_path, {9})["blocked"][0]["task"] == TASK
    (tmp_path / "pilot/holdouts" / f"{TASK}.oracle.json.age").write_text("x")
    q = eq.build_queue([_issue()], [], tmp_path, {9})
    assert q["pending"] == q["in_flight"] == q["blocked"] == q["stale"] == []


def test_queue_marks_stale_when_not_planned_or_request_closed(tmp_path):
    _repo(tmp_path)
    # re-planned task (no template), different scope, closed request
    assert eq.build_queue([_issue(task="req9backend22")], [], tmp_path, {9})["stale"]
    assert eq.build_queue([_issue(write=["other.java"])], [], tmp_path, {9})["stale"]
    assert eq.build_queue([_issue()], [], tmp_path, set())["stale"]


def test_queue_ignores_untrusted_or_malformed_issues(tmp_path):
    _repo(tmp_path)
    bad = [_issue(user="someone"), _issue(labels=()),
           {**_issue(), "title": "EXAM_REQUEST: other"},
           {**_issue(), "pull_request": {}}, "junk"]
    q = eq.build_queue(bad, [], tmp_path, {9})
    assert q["pending"] == q["stale"] == []
    dup = eq.build_queue([_issue(), _issue(number=51)], [], tmp_path, {9})
    assert dup["duplicates"] == [TASK] and len(dup["pending"]) == 1


# --- brief -----------------------------------------------------------------

def test_brief_carries_only_the_lot_rules_and_context(tmp_path):
    _repo(tmp_path)
    (tmp_path / WRITE[0]).parent.mkdir(parents=True)
    (tmp_path / WRITE[0]).write_text("class Service {}")
    brief = eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-SBX-R-ONE", "REQ-SBX-R-GONE"], 50)
    assert set(brief["rules"]) == {"SBX-R-ONE"}
    assert brief["rules_without_text"] == ["SBX-R-GONE"]
    assert brief["area"] == "BACKEND" and brief["depends_on"] == ["SOL-001"]
    assert brief["base_head_sha"] == "main actual"
    assert brief["context_files"] == {"contracts/x.yaml": "openapi: 3.1.0\n"}
    assert brief["existing_write_path_content"] == {WRITE[0]: "class Service {}"}
    assert brief["publish"]["branch"] == f"exam/{TASK}"
    assert "SBX-R-ONE" in eb.render_md(brief)


def test_brief_blocks_on_scope_mismatch_or_missing_template(tmp_path):
    _repo(tmp_path)
    with pytest.raises(eb.BriefBlocked, match="SCOPE_MISMATCH"):
        eb.build_brief(tmp_path, REQ, TASK, ["other.java"], ["REQ-SBX-R-ONE"])
    with pytest.raises(eb.BriefBlocked, match="MISSING"):
        eb.build_brief(tmp_path, REQ, "req9backend9", WRITE, ["REQ-SBX-R-ONE"])
    with pytest.raises(eb.BriefBlocked, match="IDENTITY"):
        eb.build_brief(tmp_path, "nope", TASK, WRITE, [])


def test_brief_cli_refuses_output_inside_repository(tmp_path, monkeypatch, capsys):
    _repo(tmp_path)
    monkeypatch.setattr("sys.argv", ["examiner_brief.py", "--request", REQ, "--task", TASK,
                                     "--write-paths", json.dumps(WRITE),
                                     "--requirement-ids", '["REQ-SBX-R-ONE"]',
                                     "--root", str(tmp_path), "--out", str(tmp_path / "x")])
    assert eb.main() == 2
    assert "OUT_INSIDE_REPO" in capsys.readouterr().out


# --- publish_exam: rule traces scoped to the lot ---------------------------

def test_trace_rule_must_belong_to_lot(tmp_path):
    _repo(tmp_path)
    pe.check_trace_lot(tmp_path, REQ, TASK, {"A": "rule:SBX-R-ONE", "B": "rule:STD-BE-05",
                                            "C": "env:build", "D": "contract:contracts/x.yaml"})
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT:A=SBX-R-TWO"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"A": "rule:SBX-R-TWO"})
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_LOT_UNRESOLVED"):
        pe.check_trace_lot(tmp_path, REQ, "req9backend9", {"A": "env:x"})


def test_procedure_document_names_the_tools():
    doc = (Path(__file__).parent / "EXAMINADOR_AUTOMATICO.md").read_text("utf-8")
    for needle in ("examiner_queue.py", "examiner_brief.py", "publish_exam.py",
                   "examiner-blocked", "exam/<task>", "ready-to-merge"):
        assert needle in doc

# --- second-screen public source trace --------------------------------------

def _second_source(root, fixture="second_screen", *, source_code="PUBLIC_RULE_X",
                   canonical="PUBLIC-RULE-X", evidence=True, duplicate=False):
    folder = root / "analysis" / "fixtures" / fixture
    folder.mkdir(parents=True, exist_ok=True)
    ref = "fixture://" + fixture + "/rules/1"
    rule = {"code": source_code, "source_ref": ref, "title": "Regla pública",
            "descripcion": "Descripción de prueba"}
    req = {"requirement_id": "REQ-" + canonical, "source_requirement_id": source_code,
           "evidence_refs": [ref if evidence else "fixture://unrelated"]}
    (folder / "source.json").write_text(json.dumps({
        "schema_version": "SECOND_SCREEN_SOURCE_V1",
        "screen_contract": {"rules": [rule]},
        "effective_rules": {source_code: {"code": source_code, "source_ref": ref}},
        "requirements": [req, req] if duplicate else [req],
    }), encoding="utf-8")


def test_second_screen_brief_and_publish_use_same_canonical_trace(tmp_path, monkeypatch):
    _repo(tmp_path, reqs=("REQ-PUBLIC-RULE-X",))
    _second_source(tmp_path)
    brief = eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-PUBLIC-RULE-X"])
    assert brief["rules_without_text"] == []
    rule = brief["rules"]["PUBLIC-RULE-X"]
    assert rule["code"] == "PUBLIC-RULE-X"
    assert rule["source_rule_code"] == "PUBLIC_RULE_X"
    assert rule["descripcion"] == "Descripción de prueba"
    monkeypatch.setattr(pe, "ROOT", tmp_path)
    trace = {"FAIL": "rule:PUBLIC-RULE-X"}
    pe.check_trace('fail("FAIL")', trace, tmp_path, tmp_path, REQ)
    pe.check_trace_lot(tmp_path, REQ, TASK, trace)
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:PUBLIC_RULE_X"})
    _second_source(tmp_path, fixture="unrelated", source_code="OTHER_RULE",
                   canonical="OTHER-RULE")
    other = {"FAIL": "rule:OTHER-RULE"}
    pe.check_trace('fail("FAIL")', other, tmp_path, tmp_path, REQ)
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
        pe.check_trace_lot(tmp_path, REQ, TASK, other)


@pytest.mark.parametrize("defect", ["evidence", "duplicate", "cross_fixture", "missing_rule"])
def test_second_screen_does_not_guess_or_accept_ambiguous_alias(tmp_path, monkeypatch, defect):
    _repo(tmp_path, reqs=("REQ-PUBLIC-RULE-X",))
    _second_source(tmp_path, evidence=defect != "evidence", duplicate=defect == "duplicate")
    if defect == "cross_fixture":
        _second_source(tmp_path, fixture="other_screen")
    if defect == "missing_rule":
        path = tmp_path / "analysis/fixtures/second_screen/source.json"
        data = json.loads(path.read_text("utf-8"))
        data["screen_contract"]["rules"] = []
        path.write_text(json.dumps(data), encoding="utf-8")
    brief = eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-PUBLIC-RULE-X"])
    assert brief["rules_without_text"] == ["PUBLIC-RULE-X"]
    monkeypatch.setattr(pe, "ROOT", tmp_path)
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_UNKNOWN"):
        pe.check_trace('fail("FAIL")', {"FAIL": "rule:PUBLIC-RULE-X"}, tmp_path, tmp_path, REQ)
