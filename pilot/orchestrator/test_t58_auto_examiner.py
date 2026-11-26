"""T58: automatic examiner queue, brief and lot-scoped rule traces."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from analysis.host.fixture_normalize import normalize
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



def _bind(root, target, fixture, reqs, request=REQ):
    folder = root / "pilot/runs" / request
    folder.mkdir(parents=True, exist_ok=True)
    source = root / "analysis" / "fixtures" / fixture
    pin = json.loads((source / "SOURCE_PIN.json").read_text())
    intent = "implementa " + target
    if pin["schema_version"] == "SOURCE_SCREEN_PIN_V1":
        _, _, evidence = normalize(source, intent)
        ref = evidence["effective_rules.json"]
    else:
        digest = hashlib.sha256((source / "effective_rules.json").read_bytes()).hexdigest()
        ref = f"fixture://{fixture}/effective_rules.json@{digest}"
    (folder / "analysis.json").write_text(json.dumps({
        "request_context": {"target_ref": target, "intent": intent},
        "programming_context_snapshot": {"target": target, "source_snapshot_inputs": {
            "rule_fixture_provenance": {"effective_rules.json":
                ref}}},
        "requirements": reqs,
    }))


def _pin_legacy(folder, target):
    digest = hashlib.sha256((folder / "effective_rules.json").read_bytes()).hexdigest()
    (folder / "SOURCE_PIN.json").write_text(json.dumps({
        "schema_version": "SBX_FIXTURE_PIN_V1", "fixture_id": target,
        "files": [{"file": "effective_rules.json", "sha256": digest}],
    }))


def _pin_second(folder, target):
    digest = hashlib.sha256((folder / "source.json").read_bytes()).hexdigest()
    (folder / "SOURCE_PIN.json").write_text(json.dumps({
        "schema_version": "SOURCE_SCREEN_PIN_V1", "fixture_id": target,
        "source_file": "source.json", "sha256": digest, "simulation_only": True,
    }))


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
    legacy = fixtures / "effective_rules.json"
    data = json.loads(legacy.read_text())
    for i, rule in enumerate(data["rules"], 1):
        rule["source_ref"] = "supabase://lf_ops.reglas/" + str(i)
    legacy.write_text(json.dumps(data))
    _pin_legacy(fixtures, "SBX-DEMO")
    _bind(root, "SBX-DEMO", "sbx_demo", [
        {"requirement_id": "REQ-" + r["code"], "source_requirement_id": r["code"],
         "evidence_refs": [r["source_ref"]]} for r in data["rules"]])
    (root / "standards").mkdir()
    (root / "standards/catalog.json").write_text(json.dumps({"rules": [{"id": "STD-BE-05"}]}))
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
    brief = eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-SBX-R-ONE"], 50)
    assert set(brief["rules"]) == {"SBX-R-ONE"}
    assert brief["rules_without_text"] == []
    # A non-lot lookup may be absent without weakening the valid lot.
    assert eb.resolve_fiche_rule(tmp_path, REQ, "SBX-R-GONE")["status"] == "MISSING"
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
    with pytest.raises(eb.BriefBlocked, match="REQUIREMENTS_MISMATCH"):
        eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-SBX-R-TWO"])


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

def _second_source(root, fixture="sbx_demo", *, source_code="PUBLIC_RULE_X",
                   canonical="PUBLIC-RULE-X", evidence=True, duplicate=False,
                   target="SBX-DEMO", bind=True, request=REQ):
    folder = root / "analysis" / "fixtures" / fixture
    folder.mkdir(parents=True, exist_ok=True)
    ref = "fixture://" + fixture + "/rules/1"
    rule = {"code": source_code, "source_ref": ref, "title": "Regla pública",
            "descripcion": "Descripción de prueba", "status": "VIGENTE",
            "association_ref": "fixture://" + fixture + "/assoc/1"}
    req = {"requirement_id": "REQ-" + canonical, "source_requirement_id": source_code,
           "evidence_refs": [ref if evidence else "fixture://unrelated"]}
    (folder / "source.json").write_text(json.dumps({
        "schema_version": "SECOND_SCREEN_SOURCE_V1", "target_ref": target,
        "screen_contract": {"rules": [rule], "fields": [], "errors": [],
                            "visual": {}, "context": {}, "metadata": {}},
        "effective_rules": {source_code: {"code": source_code, "source_ref": ref,
                                          "categoria": "security"}},
        "inventory": {"objects": [], "impacts": [], "dependencies": []},
        "requirements": [req, req] if duplicate else [req],
    }), encoding="utf-8")
    _pin_second(folder, target)
    if bind:
        _bind(root, target, fixture, [{"requirement_id": req["requirement_id"],
                                      "source_requirement_id": canonical,
                                      "evidence_refs": ["supabase://lf_ops.reglas/1"]}],
              request=request)
    return folder


def _check_trace(root, monkeypatch, code, request=REQ):
    monkeypatch.setattr(pe, "ROOT", root)
    pe.check_trace('fail("FAIL")', {"FAIL": "rule:" + code}, root, root, request)


def test_second_screen_brief_and_publish_use_same_canonical_trace(tmp_path, monkeypatch):
    _repo(tmp_path, reqs=("REQ-PUBLIC-RULE-X",))
    _second_source(tmp_path)
    brief = eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-PUBLIC-RULE-X"])
    assert brief["rules_without_text"] == []
    assert brief["rule_resolution"] == {"PUBLIC-RULE-X": "VALID"}
    rule = brief["rules"]["PUBLIC-RULE-X"]
    assert rule["code"] == "PUBLIC-RULE-X"
    assert rule["source_rule_code"] == "PUBLIC_RULE_X"
    assert rule["descripcion"] == "Descripción de prueba"
    _check_trace(tmp_path, monkeypatch, "PUBLIC-RULE-X")
    pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:PUBLIC-RULE-X"})
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:PUBLIC_RULE_X"})
    # A rule valid for another request never becomes valid for this request.
    _second_source(tmp_path, fixture="unrelated", source_code="OTHER_RULE",
                   canonical="OTHER-RULE", target="OTHER", request="req-10")
    _check_trace(tmp_path, monkeypatch, "OTHER-RULE", request="req-10")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_UNKNOWN"):
        _check_trace(tmp_path, monkeypatch, "OTHER-RULE")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:OTHER-RULE"})


@pytest.mark.parametrize("defect,state", [
    ("evidence", "INVALID"), ("duplicate", "AMBIGUOUS"),
    ("cross_fixture", "AMBIGUOUS"), ("missing_rule", "INVALID"),
    ("missing_association", "INVALID"), ("wrong_analysis_ref", "INVALID"),
    ("tampered_pin", "INVALID"),
])
def test_second_screen_cannot_be_rescued_by_global_text_or_legacy(tmp_path, monkeypatch, defect, state):
    _repo(tmp_path, reqs=("REQ-PUBLIC-RULE-X",))
    folder = _second_source(tmp_path, evidence=defect != "evidence", duplicate=defect == "duplicate")
    # Both bypasses from the original review: a textual hit and a legacy rule
    # with the same canonical code, even in the selected fixture.
    (folder / "noise.json").write_text(json.dumps({"text": "PUBLIC-RULE-X"}))
    (folder / "effective_rules.json").write_text(json.dumps({"rules": [
        {"code": "PUBLIC-RULE-X", "source_ref": "supabase://lf_ops.reglas/1"}]}))
    _second_source(tmp_path, fixture="other_screen", target="OTHER", bind=False)
    if defect == "cross_fixture":
        _second_source(tmp_path, fixture="other_screen", bind=False)
    if defect in ("missing_rule", "missing_association", "tampered_pin"):
        path = folder / "source.json"
        data = json.loads(path.read_text("utf-8"))
        if defect == "missing_rule":
            data["screen_contract"]["rules"] = []
        elif defect == "missing_association":
            data["requirements"] = []
        else:
            data["extra"] = True
        path.write_text(json.dumps(data), encoding="utf-8")
        if defect != "tampered_pin":
            _pin_second(folder, "SBX-DEMO")
    if defect == "wrong_analysis_ref":
        _bind(tmp_path, "SBX-DEMO", "sbx_demo", [{"requirement_id": "REQ-PUBLIC-RULE-X",
                "source_requirement_id": "PUBLIC-RULE-X", "evidence_refs": ["wrong"]}])
    assert eb.resolve_fiche_rule(tmp_path, REQ, "PUBLIC-RULE-X")["status"] == state
    with pytest.raises(eb.BriefBlocked, match="EXAM_LOT_RULE_UNRESOLVED:PUBLIC-RULE-X=" + state):
        eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-PUBLIC-RULE-X"])
    with pytest.raises(pe.ExamBlocked, match="EXAM_LOT_RULE_UNRESOLVED:PUBLIC-RULE-X=" + state):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "env:build"})
    reason = "UNKNOWN" if state == "MISSING" else state
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_" + reason):
        _check_trace(tmp_path, monkeypatch, "PUBLIC-RULE-X")


def test_colliding_rule_codes_are_bound_to_the_request_source(tmp_path, monkeypatch):
    _repo(tmp_path, reqs=("REQ-PUBLIC-RULE-X",))
    _second_source(tmp_path)
    other = _second_source(tmp_path, fixture="other_screen", source_code="OTHER_RULE",
                           target="OTHER", request="req-10")
    # Same canonical REQ, different source code. Neither can leak into the other.
    assert eb.resolve_fiche_rule(tmp_path, REQ, "PUBLIC-RULE-X")["rule"]["source_rule_code"] == "PUBLIC_RULE_X"
    assert eb.resolve_fiche_rule(tmp_path, "req-10", "PUBLIC-RULE-X")["rule"]["source_rule_code"] == "OTHER_RULE"
    _check_trace(tmp_path, monkeypatch, "PUBLIC-RULE-X")
    _check_trace(tmp_path, monkeypatch, "PUBLIC-RULE-X", request="req-10")
    _bind(tmp_path, "SBX-DEMO", other.name, [{"requirement_id": "REQ-PUBLIC-RULE-X",
          "source_requirement_id": "PUBLIC-RULE-X", "evidence_refs": ["supabase://lf_ops.reglas/1"]}])
    assert eb.resolve_fiche_rule(tmp_path, REQ, "PUBLIC-RULE-X")["status"] == "INVALID"
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_INVALID"):
        _check_trace(tmp_path, monkeypatch, "PUBLIC-RULE-X")


def test_legacy_and_std_structured_lookup_and_lot_scope(tmp_path, monkeypatch):
    _repo(tmp_path)
    _second_source(tmp_path, fixture="other_screen", canonical="SBX-R-ONE",
                   target="OTHER", bind=False)
    assert eb.resolve_fiche_rule(tmp_path, REQ, "SBX-R-ONE")["rule"]["fixture"] == "sbx_demo"
    _check_trace(tmp_path, monkeypatch, "SBX-R-ONE")
    _check_trace(tmp_path, monkeypatch, "STD-BE-05")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_UNKNOWN"):
        _check_trace(tmp_path, monkeypatch, "STD-DOES-NOT-EXIST")
    _check_trace(tmp_path, monkeypatch, "SBX-R-TWO")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:SBX-R-TWO"})


@pytest.mark.parametrize("second,code", [(False, "SBX-R-ONE"), (True, "PUBLIC-RULE-X")])
def test_historical_projection_rejects_consistently_repinned_rule(tmp_path, monkeypatch, second, code):
    _repo(tmp_path, reqs=("REQ-" + code,))
    folder = _second_source(tmp_path) if second else tmp_path / "analysis/fixtures/sbx_demo"
    analysis_path = tmp_path / "pilot/runs" / REQ / "analysis.json"
    original_analysis = analysis_path.read_bytes()
    assert eb.resolve_fiche_rule(tmp_path, REQ, code)["status"] == "VALID"
    filename = "source.json" if second else "effective_rules.json"
    path = folder / filename
    data = json.loads(path.read_text())
    rules = data["screen_contract"]["rules"] if second else data["rules"]
    rules[0]["descripcion"] = "Descripción modificada después de A9"
    path.write_text(json.dumps(data), encoding="utf-8")
    if second:
        _pin_second(folder, "SBX-DEMO")
    else:
        _pin_legacy(folder, "SBX-DEMO")
    assert analysis_path.read_bytes() == original_analysis
    assert eb.resolve_fiche_rule(tmp_path, REQ, code)["status"] == "INVALID"
    with pytest.raises(eb.BriefBlocked, match="EXAM_LOT_RULE_UNRESOLVED:" + code + "=INVALID"):
        eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-" + code])
    with pytest.raises(pe.ExamBlocked, match="EXAM_LOT_RULE_UNRESOLVED:" + code + "=INVALID"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "env:build"})
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_INVALID"):
        _check_trace(tmp_path, monkeypatch, code)


@pytest.mark.parametrize("second,code", [(False, "SBX-R-ONE"), (True, "PUBLIC-RULE-X")])
def test_unrelated_source_maintenance_preserves_historical_binding(tmp_path, monkeypatch, second, code):
    _repo(tmp_path, reqs=("REQ-" + code,))
    if second:
        _second_source(tmp_path)
    other = _second_source(tmp_path, fixture="unrelated", target="OTHER", bind=False)
    before = eb.resolve_fiche_rule(tmp_path, REQ, code)
    assert before["status"] == "VALID"
    path = other / "source.json"
    data = json.loads(path.read_text())
    data["screen_contract"]["rules"][0]["descripcion"] = "Otra ficha actualizada"
    path.write_text(json.dumps(data), encoding="utf-8")
    _pin_second(other, "OTHER")
    assert eb.resolve_fiche_rule(tmp_path, REQ, code) == before
    _check_trace(tmp_path, monkeypatch, code)


def test_historical_second_screen_missing_rule_remains_missing(tmp_path, monkeypatch):
    _repo(tmp_path, reqs=("REQ-PUBLIC-RULE-X",))
    folder = _second_source(tmp_path)
    path = folder / "source.json"
    data = json.loads(path.read_text())
    data["requirements"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    _pin_second(folder, "SBX-DEMO")
    _bind(tmp_path, "SBX-DEMO", "sbx_demo", [{"requirement_id": "REQ-PUBLIC-RULE-X",
          "source_requirement_id": "PUBLIC-RULE-X", "evidence_refs": ["supabase://lf_ops.reglas/1"]}])
    assert eb.resolve_fiche_rule(tmp_path, REQ, "PUBLIC-RULE-X")["status"] == "MISSING"
    with pytest.raises(eb.BriefBlocked, match="EXAM_LOT_RULE_UNRESOLVED:PUBLIC-RULE-X=MISSING"):
        eb.build_brief(tmp_path, REQ, TASK, WRITE, ["REQ-PUBLIC-RULE-X"])
    with pytest.raises(pe.ExamBlocked, match="EXAM_LOT_RULE_UNRESOLVED:PUBLIC-RULE-X=MISSING"):
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "request:req-9 decision"})
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_UNKNOWN"):
        _check_trace(tmp_path, monkeypatch, "PUBLIC-RULE-X")


@pytest.mark.parametrize("request_id,code", [
    ("req-825", "FORMAT-CANARY-VALIDATION"),
    ("req-186", "SBX-R-LOG"),
    ("req-186", "SBX-R-ERR-FRONTEND"),
    ("req-652", "SBX-B2B-R-DATA-ATTEMPTS-BACKEND"),
    ("req-286", "SBX-B2B-R-AUTH-GENERIC"),
    ("req-391", "SBX-B2B-R-AUTH-GENERIC"),
    ("req-652", "SBX-B2B-R-AUTH-GENERIC"),
])
def test_public_historical_requests_read_only(request_id, code, monkeypatch):
    """Compatibility readback only: no regeneration, holdout or live service.

    Expected state follows the recorded A9 identity and current source bytes,
    not a hard-coded assumption that the moving fixture has never changed.
    The adversarial guarantees themselves are covered by isolated tests above.
    """
    root = Path(__file__).resolve().parents[2]
    analysis_path = root / "pilot/runs" / request_id / "analysis.json"
    if not analysis_path.is_file():
        pytest.skip("public historical request not present in this checkout")
    raw = analysis_path.read_bytes()
    analysis = json.loads(raw)
    history = analysis["programming_context_snapshot"]["source_snapshot_inputs"]["rule_fixture_provenance"]
    ref = history["effective_rules.json"]
    fixture = ref.split("/")[2]
    folder = root / "analysis/fixtures" / fixture
    pin = json.loads((folder / "SOURCE_PIN.json").read_text())
    if pin["schema_version"] == "SOURCE_SCREEN_PIN_V1":
        _, _, evidence = normalize(folder, analysis["request_context"]["intent"])
        current = evidence["effective_rules.json"]
    else:
        digest = hashlib.sha256((folder / "effective_rules.json").read_bytes()).hexdigest()
        assert digest == next(x["sha256"] for x in pin["files"] if x["file"] == "effective_rules.json")
        current = f"fixture://{fixture}/effective_rules.json@{digest}"
    result = eb.resolve_fiche_rule(root, request_id, code)
    expected = "VALID" if current == ref else "INVALID"
    assert result["status"] == expected, (request_id, ref, current, result)
    if expected == "VALID":
        _check_trace(root, monkeypatch, code, request=request_id)
    else:
        with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_INVALID"):
            _check_trace(root, monkeypatch, code, request=request_id)
    assert analysis_path.read_bytes() == raw


@pytest.mark.parametrize("second,base", [(False, "SBX-R-ONE"), (True, "PUBLIC-RULE-X")])
@pytest.mark.parametrize("bad", [False, True])
def test_area_derived_lot_obligation_uses_explicit_a9_parent(tmp_path, second, base, bad):
    rid = "REQ-" + base
    derived = rid + "-BACKEND"
    _repo(tmp_path, reqs=(derived,))
    if second:
        _second_source(tmp_path)
    path = tmp_path / "pilot/runs" / REQ / "analysis.json"
    analysis = json.loads(path.read_text())
    parent = next(q for q in analysis["requirements"] if q["requirement_id"] == rid)
    clone = {**parent, "requirement_id": derived, "execution_area": "BACKEND",
             "derived_from_requirement_id": rid}
    if bad:
        clone["evidence_refs"] = ["unrelated"]
    analysis["requirements"].append(clone)
    path.write_text(json.dumps(analysis))
    code = derived[4:]
    if bad:
        with pytest.raises(eb.BriefBlocked, match="EXAM_LOT_RULE_UNRESOLVED:" + code + "=INVALID"):
            eb.build_brief(tmp_path, REQ, TASK, WRITE, [derived])
        with pytest.raises(pe.ExamBlocked, match="EXAM_LOT_RULE_UNRESOLVED:" + code + "=INVALID"):
            pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "env:build"})
    else:
        brief = eb.build_brief(tmp_path, REQ, TASK, WRITE, [derived])
        assert brief["rule_resolution"] == {code: "VALID"}
        assert brief["rules"][code]["code"] == code
        pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:" + code})
        with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
            pe.check_trace_lot(tmp_path, REQ, TASK, {"FAIL": "rule:" + base})


def test_missing_bound_requirement_blocks_brief_cli_and_all_non_fiche_traces(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    reqs = ["REQ-SBX-R-ONE", "REQ-SBX-R-GONE"]
    _repo(root, reqs=reqs)
    out = tmp_path / "brief"
    monkeypatch.setattr("sys.argv", ["examiner_brief.py", "--request", REQ, "--task", TASK,
                                     "--write-paths", json.dumps(WRITE),
                                     "--requirement-ids", json.dumps(reqs),
                                     "--root", str(root), "--out", str(out)])
    assert eb.main() == 2
    assert "EXAM_LOT_RULE_UNRESOLVED:SBX-R-GONE=MISSING" in capsys.readouterr().out
    assert not out.exists()
    for target in ("env:build", "request:req-9 decision", "contract:contracts/x.yaml", "rule:STD-BE-05"):
        with pytest.raises(pe.ExamBlocked, match="EXAM_LOT_RULE_UNRESOLVED:SBX-R-GONE=MISSING"):
            pe.check_trace_lot(root, REQ, TASK, {"FAIL": target})

    # Exercise the real publisher entry point up to its public preflight.
    # No encrypted files, private oracles or builds are involved.
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    script = scratch / "check.py"
    script.write_text('fail("FAIL")\n')
    trace = scratch / "trace.json"
    trace.write_text(json.dumps({"FAIL": "env:build"}))
    monkeypatch.setattr(pe, "ROOT", root)
    monkeypatch.setattr(pe, "worker_load", lambda *args: None)
    monkeypatch.setattr(pe, "lint_overlay_scope", lambda *args: pytest.fail("must block before overlay"))
    monkeypatch.setattr(pe, "exercise", lambda *args: pytest.fail("must block before exercise"))
    monkeypatch.setattr("sys.argv", ["publish_exam.py", "--request", REQ, "--task", TASK,
                                     "--script", str(script), "--trace", str(trace),
                                     "--family", "backend", "--version", "v1",
                                     "--worktree", str(scratch), "--reference", str(scratch),
                                     "--mutants", str(scratch), "--derived-from", "synthetic"])
    assert pe.main() == 1
    assert "EXAM_LOT_RULE_UNRESOLVED:SBX-R-GONE=MISSING" in capsys.readouterr().out
    assert not list((root / "pilot/holdouts").iterdir())
