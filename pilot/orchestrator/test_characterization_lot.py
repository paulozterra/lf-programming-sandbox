"""Characterization lots on synthetic inputs: planning, coverage check."""
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
