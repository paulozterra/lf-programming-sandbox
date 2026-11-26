"""Characterization lots on synthetic inputs: planning, coverage check."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_lots  # noqa: E402
from pilot.worker_v08 import characterization_covers as cov  # noqa: E402

PKG = {"classification": {"implementation_state": "EXISTING"},
       "non_atomized_fronts": [{"obligation_mode": "MODIFY_SCOPE",
                                "candidate_ref": "repo://frontend/src/app/x/page.tsx@" + "a" * 64}]}


def _lots():
    return [{"id": "SOL-001", "area": "FRONTEND", "profile_code": "P", "depends_on": [],
             "requirement_ids": ["REQ-NEW"],
             "write_paths": ["frontend/src/app/x/page.tsx", "frontend/src/app/y/page.tsx"]},
            {"id": "SOL-002", "area": "BACKEND", "profile_code": "B", "depends_on": [],
             "requirement_ids": ["REQ-B"], "write_paths": ["apps/s/src/main/java/A.java"]}]


def _folder(tmp_path, rows):
    (tmp_path / "reuse_assessment.json").write_text(json.dumps({"obligations": rows}))
    return tmp_path


def _row(rid, decision, *paths):
    return {"requirement_id": rid, "decision": decision,
            "reuse_context": [{"path": p, "sha256": "a" * 64} for p in paths]}


def test_frontend_lot_rewriting_reused_files_gets_a_characterization_first(tmp_path):
    folder = _folder(tmp_path, [
        _row("REQ-KEEP-1", "REUSE_AS_IS", "frontend/src/app/x/page.tsx"),
        _row("REQ-KEEP-2", "REUSE_AS_IS", "frontend/src/app/y/page.tsx"),   # declared extension point
        _row("REQ-JAVA", "REUSE_AS_IS", "apps/s/src/main/java/A.java"),     # has Java tests
        _row("REQ-NEW", "BUILD_NEW")])
    out = plan_lots._characterization_lots(PKG, folder, _lots())
    char = [x for x in out if x.get("lot_kind") == "CHARACTERIZATION"]
    assert len(char) == 1
    char = char[0]
    assert char["requirement_ids"] == []
    assert char["characterized_requirement_ids"] == ["REQ-KEEP-1", "REQ-KEEP-2"]
    assert char["characterized_files"] == ["frontend/src/app/x/page.tsx", "frontend/src/app/y/page.tsx"]
    assert len(char["write_paths"]) == 1 and char["write_paths"][0].startswith("frontend/visible-tests/")
    modify = next(x for x in out if x["id"] == "SOL-001")
    assert char["id"] in modify["depends_on"] and modify["characterized_by"] == char["id"]
    assert [x["id"] for x in out].index(char["id"]) < [x["id"] for x in out].index("SOL-001")


def test_new_build_or_nothing_reused_needs_no_characterization(tmp_path):
    folder = _folder(tmp_path, [_row("REQ-NEW", "BUILD_NEW")])
    assert plan_lots._characterization_lots(PKG, folder, _lots()) == _lots()
    new = dict(PKG, classification={"implementation_state": "NEW"})
    folder = _folder(tmp_path, [_row("REQ-KEEP-1", "REUSE_AS_IS", "frontend/src/app/x/page.tsx")])
    assert plan_lots._characterization_lots(new, folder, _lots()) == _lots()


def _suite(tmp_path, data):
    f = tmp_path / "frontend/visible-tests/s.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))
    return "frontend/visible-tests/s.json"


CASE = {"id": "c1", "selector": "#a", "css": {"color": "rgb(0, 0, 0)"}}


def test_covers_must_be_exactly_the_requested_requirements(tmp_path):
    rel = _suite(tmp_path, {"covers": ["REQ-A", "REQ-B"], "cases": [CASE, dict(CASE, id="c2")]})
    assert cov.check(tmp_path, rel, ["REQ-A", "REQ-B"]) == 2
    with pytest.raises(cov.CoverageBlocked, match="COBERTURA_INCOMPLETA:REQ-C"):
        cov.check(tmp_path, rel, ["REQ-A", "REQ-B", "REQ-C"])
    with pytest.raises(cov.CoverageBlocked, match="COBERTURA_INCOMPLETA"):
        cov.check(tmp_path, rel, ["REQ-A"])


def test_covers_needs_a_case_per_requirement_and_valid_cases(tmp_path):
    rel = _suite(tmp_path, {"covers": ["REQ-A", "REQ-B"], "cases": [CASE]})
    with pytest.raises(cov.CoverageBlocked, match="CASOS_INSUFICIENTES"):
        cov.check(tmp_path, rel, ["REQ-A", "REQ-B"])
    rel = _suite(tmp_path, {"covers": ["REQ-A"], "cases": [{"id": "v", "selector": "main"}]})
    with pytest.raises(cov.CoverageBlocked, match="WITHOUT_ASSERTION"):
        cov.check(tmp_path, rel, ["REQ-A"])
    with pytest.raises(cov.CoverageBlocked, match="ARCHIVO_AUSENTE"):
        cov.check(tmp_path, "frontend/visible-tests/none.json", ["REQ-A"])


CHAR_LOT = {"id": "SOL-KX", "area": "FRONTEND", "lot_kind": "CHARACTERIZATION",
            "requirement_ids": [], "characterized_requirement_ids": ["REQ-KEEP-1"],
            "characterized_files": ["frontend/src/app/x/page.tsx"],
            "write_paths": ["frontend/visible-tests/sol-kx.json"]}


def test_characterization_exam_and_context_bind_to_pinned_requirements():
    from t4_admission import examinable_requirements
    assert examinable_requirements(CHAR_LOT) == ["REQ-KEEP-1"]
    assert examinable_requirements({"requirement_ids": ["REQ-A"]}) == ["REQ-A"]


def test_characterization_exam_trace_may_cite_only_pinned_rules(tmp_path, monkeypatch):
    import publish_exam
    folder = tmp_path / "pilot/runs/req-1"
    (folder / "templates").mkdir(parents=True)
    (folder / "templates/t1.task.json").write_text(json.dumps(
        {"task_spec": {"write_path_patterns": CHAR_LOT["write_paths"]}}))
    (folder / "lots.json").write_text(json.dumps({"lots": [CHAR_LOT]}))
    # H4 requires the characterization lot's obligations to resolve against
    # the same pinned, historical A9 source as an implementation lot.
    fixture = tmp_path / "analysis/fixtures/characterization_demo"
    fixture.mkdir(parents=True)
    target = "DEMO-CHARACTERIZATION"
    rules = [
        {"code": "KEEP-1", "source_ref": "supabase://lf_ops.reglas/1",
         "title": "Conservar comportamiento", "status": "VIGENTE"},
        {"code": "OTHER", "source_ref": "supabase://lf_ops.reglas/2",
         "title": "Regla de otro lote", "status": "VIGENTE"},
    ]
    effective = fixture / "effective_rules.json"
    effective.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    digest = hashlib.sha256(effective.read_bytes()).hexdigest()
    (fixture / "SOURCE_PIN.json").write_text(json.dumps({
        "schema_version": "SBX_FIXTURE_PIN_V1", "fixture_id": target,
        "files": [{"file": effective.name, "sha256": digest}],
    }), encoding="utf-8")
    analysis = folder / "analysis.json"
    analysis.write_text(json.dumps({
        "request_context": {"target_ref": target, "intent": "modifica " + target},
        "programming_context_snapshot": {"target": target, "source_snapshot_inputs": {
            "rule_fixture_provenance": {"effective_rules.json":
                f"fixture://{fixture.name}/{effective.name}@{digest}"}}},
        "requirements": [
            {"requirement_id": "REQ-" + rule["code"],
             "source_requirement_id": rule["code"],
             "evidence_refs": [rule["source_ref"]]} for rule in rules
        ],
    }), encoding="utf-8")
    standards = tmp_path / "standards"
    standards.mkdir()
    (standards / "catalog.json").write_text(
        json.dumps({"rules": [{"id": "STD-X"}]}), encoding="utf-8")
    monkeypatch.setattr(publish_exam, "storage_path",
                        lambda key, root: Path(root) / "pilot/runs")
    monkeypatch.setattr(publish_exam, "ROOT", tmp_path)
    trace = {"E1": "rule:KEEP-1", "E2": "rule:STD-X"}
    publish_exam.check_trace('fail("E1")\nfail("E2")', trace, tmp_path, tmp_path, "req-1")
    publish_exam.check_trace_lot(tmp_path, "req-1", "t1", trace)
    # A rule from the same A9 source but outside the characterization lot
    # remains inadmissible, even though its own provenance is valid.
    publish_exam.check_trace('fail("E1")', {"E1": "rule:OTHER"},
                             tmp_path, tmp_path, "req-1")
    with pytest.raises(publish_exam.ExamBlocked, match="EXAM_TRACE_RULE_NOT_IN_LOT"):
        publish_exam.check_trace_lot(tmp_path, "req-1", "t1", {"E1": "rule:OTHER"})
    # Losing historical A9 evidence must also block non-rule traces (H4).
    analysis.unlink()
    with pytest.raises(publish_exam.ExamBlocked, match="EXAM_LOT_RULE_UNRESOLVED:KEEP-1=INVALID"):
        publish_exam.check_trace_lot(tmp_path, "req-1", "t1", {"E1": "env:build"})
