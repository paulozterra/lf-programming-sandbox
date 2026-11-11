"""CP3.3: pinned producers, disposable SQL selector, deterministic DAG and negatives."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"pilot/orchestrator"))
import intake
import plan_lots

THREE="sample-three-area-notes"
ONE="sample-reminder-note"
PREFS={"DATA":"PERFIL-PROG-DATA-EXP",
       "BACKEND":"PERFIL-PROG-BACKEND-SPRING-EXP",
       "FRONTEND":"PERFIL-PROG-FRONTEND-EXP"}


def fixture(temp,slug):
    folder=temp/"pilot/runs"/slug
    folder.mkdir(parents=True)
    source=ROOT/"pilot/runs"/slug
    for name in ("request.md","analysis.json","planning_fixture.json"):
        shutil.copyfile(source/name,folder/name)
    intake.accept(temp,slug)
    return folder


def patch_fixture(folder,mutate):
    path=folder/"planning_fixture.json"
    value=json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value,sort_keys=True),encoding="utf-8")


def test_three_areas_data_then_backend_then_frontend_with_selected_profiles(tmp_path):
    folder=fixture(tmp_path,THREE)
    out=plan_lots.plan(tmp_path,THREE)
    assert out["schema_version"]=="CP33_LOTS_CANDIDATE_V1"
    assert out["pg01_status"]=="FIXTURE_UNATTESTED"
    assert [l["area"] for l in out["lots"]]==["DATA","BACKEND","FRONTEND"]
    assert [l["profile_code"] for l in out["lots"]]==[PREFS[x] for x in
             ("DATA","BACKEND","FRONTEND")]
    assert len(out["lots"])==3
    assert out["topological_order"]==[l["id"] for l in out["lots"]]
    assert out["lots"][0]["depends_on"]==[]
    assert out["lots"][1]["depends_on"]==[out["lots"][0]["id"]]
    assert out["lots"][2]["depends_on"]==[out["lots"][1]["id"]]
    for lot in out["lots"]:
        assert lot["write_paths"]
        assert lot["production_authority"] is False and lot["handoff_allowed"] is False
        assert len(lot["profile_assignment_sha256"])==64
        assert len(lot["profile_currentness_sha256"])==64
    assert all(len(value)==64 for value in out["producer_outputs_sha256"].values())
    assert (folder/"lots.json").read_bytes()==intake.canonical(out)
    state=json.loads((folder/"state.json").read_text())
    assert state["stage"]=="LOTS_PLANNED"
    assert state["lot_count"]==3
    assert state["lots_sha256"]==hashlib.sha256(intake.canonical(out)).hexdigest()
    assert state["production_authority"] is False


def test_notes_sample_planned_with_pinned_sources(tmp_path):
    fixture(tmp_path,ONE)
    out=plan_lots.plan(tmp_path,ONE)
    assert len(out["lots"])==1
    assert out["lots"][0]["area"]=="BACKEND"
    assert out["lots"][0]["profile_code"]==PREFS["BACKEND"]
    assert len(out["producer_outputs_sha256"])>=12


def test_same_input_same_bytes_and_replay(tmp_path):
    a,b=tmp_path/"a",tmp_path/"b"
    first=fixture(a,THREE)
    second=fixture(b,THREE)
    plan_lots.plan(a,THREE)
    original_lots=(first/"lots.json").read_bytes()
    original_state=(first/"state.json").read_bytes()
    plan_lots.plan(b,THREE)
    assert original_lots==(second/"lots.json").read_bytes()
    assert original_state==(second/"state.json").read_bytes()
    plan_lots.plan(a,THREE)
    assert original_lots==(first/"lots.json").read_bytes()
    assert original_state==(first/"state.json").read_bytes()


def test_multiple_areas_in_single_pg04_solution_blocks(tmp_path):
    folder=fixture(tmp_path,THREE)
    def bad(obj):
        backend=next(x for x in obj["atoms"] if x["area"]=="BACKEND")
        backend["paths"].append("db/migration/V999__leak.sql")
    patch_fixture(folder,bad)
    with pytest.raises(plan_lots.PlanningBlocked,match="LOTE_MULTIAREA"):
        plan_lots.plan(tmp_path,THREE)
    assert not (folder/"lots.json").exists()
    assert json.loads((folder/"state.json").read_text())["stage"]=="INTAKE_ACCEPTED"


def test_cycle_in_pg04_dependency_blocks(tmp_path):
    folder=fixture(tmp_path,THREE)
    def bad(obj):
        data=next(x for x in obj["atoms"] if x["area"]=="DATA")
        data["depends_on"]=["ATOM-FRONTEND"]
    patch_fixture(folder,bad)
    with pytest.raises(plan_lots.PlanningBlocked,match="LOTES_CICLO"):
        plan_lots.plan(tmp_path,THREE)
    assert not (folder/"lots.json").exists()


def test_orchestrator_topological_loop_and_unknown_dependency_block():
    lots=[{"id":"A","depends_on":["B"]},{"id":"B","depends_on":["A"]}]
    with pytest.raises(plan_lots.PlanningBlocked,match="LOTES_CICLO"):
        plan_lots.topo(lots)
    with pytest.raises(plan_lots.PlanningBlocked,match="LOTES_DEPENDENCIA_DESCONOCIDA"):
        plan_lots.topo([{"id":"A","depends_on":["UNDEFINED"]}])


def test_missing_selector_never_invents_profile(tmp_path,monkeypatch):
    fixture(tmp_path,THREE)
    monkeypatch.delenv("SELECTOR_EXP_TEST_DSN",raising=False)
    monkeypatch.delenv("SELECTOR_EXP_DISPOSABLE_DB",raising=False)
    with pytest.raises(plan_lots.PlanningBlocked,match="SELECTOR_REQUIERE_ENTORNO"):
        plan_lots.plan(tmp_path,THREE)
    assert not (tmp_path/"pilot/runs"/THREE/"lots.json").exists()


def test_missing_preference_blocks_before_profile_assignment(tmp_path):
    folder=fixture(tmp_path,THREE)
    patch_fixture(folder,lambda obj:obj["profile_choices"].pop("FRONTEND"))
    with pytest.raises(plan_lots.PlanningBlocked,match="SELECTOR_REQUIERE_DECISION"):
        plan_lots.plan(tmp_path,THREE)


def test_stage_not_accepted_blocks(tmp_path):
    folder=fixture(tmp_path,THREE)
    state=json.loads((folder/"state.json").read_text())
    state["stage"]="UNKNOWN"
    (folder/"state.json").write_text(json.dumps(state))
    with pytest.raises(plan_lots.PlanningBlocked,match="LOTES_INTAKE_NO_ACEPTADO"):
        plan_lots.plan(tmp_path,THREE)
