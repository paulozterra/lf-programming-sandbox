"""T10 same-area reuse and deterministic Markdown on a synthetic screen."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pytest

from pilot.orchestrator.reuse_assessment import assess, index
from pilot.orchestrator import atomize, intake
from pilot.orchestrator.analysis_report import render, write, ReportBlocked, read_rules
from pilot.orchestrator.test_t72_dependencies import _scenario


def test_cross_area_registry_rule_remains_frontend_work(tmp_path):
    package, _, _, backend, _ = _scenario(tmp_path, attested=True)
    content = (tmp_path / backend).read_bytes()
    ref = {"path":backend,"sha256":hashlib.sha256(content).hexdigest()}
    registry = {"schema_version":"T7_IMPLEMENTED_REGISTRY_V1",
                "entries":[{"request":"before","lot":"SOL-OLD",
                            "area":"BACKEND","rule_codes":["SYN-R-1"],
                            "endpoints":[],"files":[ref],
                            "merge_sha":"a"*40,"status":"ATTESTED"}]}
    result = assess(index(tmp_path), package["requirements"],
                    root=tmp_path, registry=registry)
    reqs = {r["requirement_id"]:r for r in package["requirements"]}
    rows = {r["requirement_id"]:r for r in result["obligations"]}
    back = [id for id,r in reqs.items() if r.get("source_requirement_id")=="SYN-R-1"
            and r.get("scope_id","").endswith("-BACKEND")]
    front = [id for id,r in reqs.items() if r.get("source_requirement_id")=="SYN-R-1"
             and r.get("scope_id","").endswith("-FRONTEND")]
    assert back and front
    assert all(rows[id]["decision"]=="REUSE_AS_IS" for id in back)
    for id in front:
        row = rows[id]
        assert row["decision"]=="BUILD_NEW"
        assert row["reason"]=="REUSE_AREA_DISTINTA:BACKEND"
        assert row["path"] is None
        assert row["write_paths"]==[]
        assert row["reuse_context"] == [{**ref,"role":"DEPENDENCIA",
                                          "component_area":"BACKEND"}]
    atoms = atomize.atomize(package,tmp_path,"a"*40,run="t72-after",
                           reuse_assessment=result)
    assert all(not any(b in atom["requirement_ids"] for b in back)
               for atom in atoms["atoms"])
    assert any(atom["area"]=="FRONTEND"
               and any(f in atom["requirement_ids"] for f in front)
               for atom in atoms["atoms"])


def test_synthetic_json_report_stable_and_tampering_blocks(tmp_path):
    package, _, _, _, _ = _scenario(tmp_path, attested=True)
    folder = tmp_path / "pilot/runs/t72-after"
    metadata = {"author":"fixture-author","issue":987654,
                "date":"2026-11-14T00:00:00Z"}
    (folder/"request_meta.json").write_text(json.dumps(metadata),encoding="utf-8")
    reuse=assess(index(tmp_path),package["requirements"],
                 registry={"schema_version":"T7_IMPLEMENTED_REGISTRY_V1",
                           "entries":[]},root=tmp_path)
    (folder/"reuse_assessment.json").write_text(json.dumps(reuse),encoding="utf-8")
    fixture = tmp_path/"analysis/fixtures/other_pinned_screen"
    request=(folder/"request.md").read_bytes()
    lots={"lots":[{"id":"LOT-FE","area":"FRONTEND",
                   "write_paths":["frontend/src/app/catalog-list/page.tsx"],
                   "depends_on":["LOT-BE"]},
                  {"id":"LOT-BE","area":"BACKEND",
                   "write_paths":["apps/time-service/src/main/java/demo/Api.java"],
                   "depends_on":[]}]}
    (folder/"lots.json").write_text(json.dumps(lots),encoding="utf-8")
    actual = render(package,reuse,lots,metadata,request,read_rules(fixture,request))
    first = write(tmp_path,"t72-after",fixture)
    assert first==actual==(folder/"ANALYSIS_REPORT.md").read_bytes()
    assert b"A1" in first and b"FRONTEND" in first
    assert b"fixture-author" in first
    assert write(tmp_path,"t72-after",fixture)==first
    (folder/"ANALYSIS_REPORT.md").write_bytes(first.replace(b"LOT-FE",b"LOT-XX"))
    with pytest.raises(ReportBlocked,match="GENERATED_CONTENT_DRIFT"):
        write(tmp_path,"t72-after",fixture)
