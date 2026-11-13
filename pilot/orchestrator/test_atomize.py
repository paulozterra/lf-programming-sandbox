"""T1: source-constrained deterministic atomizer and fixture-free planning."""
from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

import pytest

from pilot.orchestrator import atomize, intake, package_to_lots

ROOT = Path(__file__).resolve().parents[2]
BASE = "d78d7085a3869fa5630a188f2e6dce6f3138dfd2"


def payload(name):
    return json.loads((ROOT / "pilot/runs" / name / "analysis.json").read_text())


def make_run(temp, name, *, owner=False):
    src = ROOT / "pilot/runs" / name
    dest = temp / "pilot/runs" / name
    dest.mkdir(parents=True)
    for file in ("request.md", "analysis.json"):
        shutil.copyfile(src / file, dest / file)
    if owner:
        shutil.copyfile(src / "owner_area_decision.json", dest / "owner_area_decision.json")
    intake.accept(temp, name)
    return dest


def test_real_login_unresolved_even_when_owner_decision_present(tmp_path):
    folder = make_run(tmp_path, "f5-login", owner=True)
    with pytest.raises(package_to_lots.PackageLotsBlocked,
                       match=r"ATOM_AREA_UNRESOLVED:.*F3-") as failure:
        package_to_lots.prepare(tmp_path, "f5-login", base_head_sha=BASE)
    if os.environ.get("T1_ARTIFACT_DIR"):
        target = Path(os.environ["T1_ARTIFACT_DIR"])/"login-unresolved"
        target.mkdir(parents=True, exist_ok=True)
        code, payload = str(failure.value).split(":", 1)
        (target/"atomization-block.json").write_text(
            json.dumps({"reason_code": code, "unresolved_fronts": json.loads(payload),
                        "lots_generated": False}, indent=2, sort_keys=True) + "\n")
    assert not (folder / "lots.json").exists()
    assert not (folder / "atomized_inputs.json").exists()
    report = json.loads((folder / "t1_interventions.json").read_text())
    assert report["INTERVENCION_MANUAL"] == "SI"
    assert report["interventions"] == ["owner_area_decision.json"]


def test_three_areas_without_fixture_uses_pg02_pg05(tmp_path):
    folder = make_run(tmp_path, "sample-three-area-notes")
    assert not (folder/"planning_fixture.json").exists()
    lots = package_to_lots.prepare(tmp_path, "sample-three-area-notes", base_head_sha=BASE)
    assert [x["area"] for x in lots["lots"]] == ["DATA", "BACKEND", "FRONTEND"]
    assert len(lots["lots"]) == 3
    assert all(len(x["write_paths"]) <= 6 for x in lots["lots"])
    assert lots["lots"][0]["depends_on"] == []
    assert lots["lots"][1]["depends_on"] == [lots["lots"][0]["id"]]
    assert lots["lots"][2]["depends_on"] == [lots["lots"][1]["id"]]
    assert "planning_fixture_sha256" not in lots
    assert "atomized_inputs_sha256" in lots
    assert lots["worker_invoked"] is False
    plan = tmp_path / "pilot/orchestrator/chain_plans/sample-three-area-notes.json"
    assert plan.is_file()
    assert len(json.loads(plan.read_text())["bindings"]) == 3
    for row in json.loads(plan.read_text())["bindings"]:
        template = tmp_path / row["template_path"]
        assert template.is_file()
        task = json.loads(template.read_text())["task_spec"]
        assert task["source_snapshot_sha256"] == "<FILL_AT_REGISTRATION>"
        assert task["base_head_sha"] == "<FILL_AT_REGISTRATION>"
        assert task["acceptance_commands"]
    first = {x: (folder/x).read_bytes() for x in
             ("atomized_inputs.json", "lots.json", "state.json")}
    assert package_to_lots.prepare(tmp_path, "sample-three-area-notes", base_head_sha=BASE) == lots
    assert all((folder/x).read_bytes() == y for x, y in first.items())
    if os.environ.get("T1_ARTIFACT_DIR"):
        output = Path(os.environ["T1_ARTIFACT_DIR"])/"sample-three-area-notes"
        shutil.copytree(folder, output)
        dest = output/"chain_plans"
        dest.mkdir()
        shutil.copyfile(plan, dest/"sample-three-area-notes.json")


def test_same_a9_same_atom_bytes(tmp_path):
    source = payload("sample-three-area-notes")
    a = atomize.atomize(source, tmp_path, BASE, run="sample-three-area-notes")
    b = atomize.atomize(copy.deepcopy(source), tmp_path, BASE, run="sample-three-area-notes")
    assert atomize.canonical(a) == atomize.canonical(b)
    assert "profile_choices" not in a
    assert len(a["provenance"]) == 3


def test_front_without_source_rule_blocks(tmp_path):
    source = payload("sample-three-area-notes")
    source["requirements"][1]["acceptance_signal"] = "Revisar pendiente."
    with pytest.raises(atomize.AtomBlocked, match="ATOM_AREA_UNRESOLVED:.*A7-FRONT-BACKEND"):
        atomize.atomize(source, tmp_path, BASE, run="sample-three-area-notes")


def test_explicit_area_must_carry_source_ref(tmp_path):
    source = payload("sample-three-area-notes")
    source["material_fronts"][0]["execution_area"] = "DATA"
    with pytest.raises(atomize.AtomBlocked, match="ATOM_AREA_UNRESOLVED"):
        atomize.atomize(source, tmp_path, BASE, run="sample-three-area-notes")
    source["material_fronts"][0]["source_ref"] = "fixture://area/data"
    assert atomize.atomize(source, tmp_path, BASE, run="sample-three-area-notes")["atoms"][0]["area"] == "DATA"
