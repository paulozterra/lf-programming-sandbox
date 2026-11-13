"""T2: generic contract lot in two real sources and third random minimal scope."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import random
import subprocess
import sys

import pytest

from pilot.orchestrator import atomize, contract_validate, prepare_t2, plan_lots
from pilot.orchestrator import intake
from analysis.host.run_a1_a9_fixture import run_f4
from analysis.a9.test_general_second_screen import second_screen, make_package

BASE = "a" * 40


def synthetic(seed=941):
    rng = random.Random(seed)
    token = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=9))
    identifier = "TEST-" + token
    scopes = [identifier + "-BACKEND", identifier + "-FRONTEND"]
    fronts = [{
        "front_id": "F-" + str(i) + "-" + token,
        "scope_ids": [scope],
        "execution_area": area,
        "source_ref": "fixture://generated/" + token + "/" + area,
        "requirement_ids": ["REQ-" + token + "-" + area],
        "obligation_mode": "REQUIRED", "closure": "CLOSED",
    } for i, (scope, area) in enumerate(zip(scopes, ("BACKEND", "FRONTEND")))]
    reqs = [{"requirement_id": f["requirement_ids"][0],
             "scope_id": scope, "outcome": "Synthetic source obligation " + scope,
             "acceptance_signal": "Bounded reproducible effect", "evidence_refs": [f["source_ref"]]}
            for f, scope in zip(fronts, scopes)]
    rules = [{"requirement_id": r["requirement_id"], "front_id": f["front_id"]}
             for r, f in zip(reqs, fronts)]
    return {
        "schema_version": "ANALYSIS_IMPLEMENTATION_PACKAGE_V1",
        "analysis_mode": "SIMULATED_ANALYSIS",
        "scope_proposals": [{"scope_id": scope, "material_front_refs": [f["front_id"]],
                             "readiness_candidate": "READY_CANDIDATE"}
                            for scope, f in zip(scopes, fronts)],
        "material_fronts": fronts, "requirements": reqs, "applicable_rules": rules,
    }


@pytest.mark.parametrize("source", ["synthetic", "login", "notes"])
def test_contract_atom_generalizes(tmp_path, source):
    if source == "synthetic":
        package = synthetic()
    elif source == "login":
        package = run_f4(tmp_path, slug="t2-login")["package"]
    else:
        package = make_package(second_screen(), b"Offline notes fixture\n")
    result = atomize.atomize(package, tmp_path, BASE, run="t2-"+source)
    assert len(result["contract_atoms"]) == 1
    contract = result["contract_atoms"][0]
    assert contract["area"] == "CONTRATO"
    assert contract["paths"][0].startswith("contracts/")
    assert contract["profile_code"] == atomize._rules()["profile_resolution"]["area_to_profile"]["BACKEND"]
    assert len(contract["source_scopes"]) == 2


def test_no_contract_for_single_area(tmp_path):
    sample = synthetic()
    sample["scope_proposals"].pop()
    sample["material_fronts"].pop()
    sample["requirements"].pop()
    sample["applicable_rules"].pop()
    result = atomize.atomize(sample, tmp_path, BASE, run="t2-single")
    assert result["contract_atoms"] == []


def test_contract_requirements_and_generic_errors_are_enforced(tmp_path):
    package = synthetic()
    package["applicable_rules"] = [{"valor_config":{"generic_error":True}}]
    result = atomize.atomize(synthetic(), tmp_path, BASE, run="t2-coverage")
    contract_path = result["contract_atoms"][0]["paths"][0]
    lotrows = [{"id":"B","area":"BACKEND","contract_path":contract_path,
                "requirement_ids":[package["requirements"][0]["requirement_id"]]},
               {"id":"F","area":"FRONTEND","contract_path":contract_path,
                "requirement_ids":[package["requirements"][1]["requirement_id"]]}]
    lots={"lots":lotrows}
    requirements=[r["requirement_id"] for r in package["requirements"]]
    doc={"openapi":"3.0.3","info":{"title":"Synthetic","version":"1.0.0"},
         "paths":{"/resource":{"post":{"operationId":"save",
                   "x-requirement-ids":requirements,"responses":{"200":{"description":"OK"},
                    "default":{"description":"Source-declared generic error"}}}}}}
    assert contract_validate.validate(doc,package,lots,contract_path)["status"] == "PASS"
    broken=deepcopy(doc)
    broken["paths"]["/resource"]["post"]["x-requirement-ids"].pop()
    with pytest.raises(contract_validate.ContractBlocked,match="T2_REQUIREMENT_COVERAGE_MISSING"):
        contract_validate.validate(broken,package,lots,contract_path)
    broken=deepcopy(doc)
    broken["paths"]["/resource"]["post"]["responses"].pop("default")
    with pytest.raises(contract_validate.ContractBlocked,match="T2_GENERIC_ERROR_RESPONSE_MISSING"):
        contract_validate.validate(broken,package,lots,contract_path)
    broken=deepcopy(doc)
    broken["paths"]["/resource"]["post"]["requestBody"]={"content":{"application/json":{
        "schema":{"type":"object","properties":{"password":{"type":"string","example":"real-secret"}}}}}}
    with pytest.raises(contract_validate.ContractBlocked,match="T2_SECRET_EXAMPLE_FORBIDDEN"):
        contract_validate.validate(broken,package,lots,contract_path)


def test_stale_generated_client_and_handwritten_fetch_block(tmp_path):
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(["node",str(root/"frontend/scripts/gen-api.mjs"),"--check"],
                          cwd=tmp_path,capture_output=True,text=True)
    # The production generated-client checker detects untracked stale declarations;
    # here it runs against the real repo if npm is available. Also exercise an
    # isolated stale file via copying the generator to a disposable fixture root.
    isolated=tmp_path/"frontend/scripts"
    isolated.mkdir(parents=True)
    (tmp_path/"contracts").mkdir()
    output=tmp_path/"frontend/src/lib/api/generated"
    output.mkdir(parents=True)
    (output/"obsolete.d.ts").write_text("export interface paths {}\n")
    script=(root/"frontend/scripts/gen-api.mjs").read_text()
    (isolated/"gen-api.mjs").write_text(script)
    stale=subprocess.run(["node",str(isolated/"gen-api.mjs"),"--check"],
                         cwd=tmp_path,capture_output=True,text=True)
    assert stale.returncode!=0 and "T2_GENERATED_CLIENT_STALE" in stale.stderr
    source=tmp_path/"frontend/src/pages"
    source.mkdir(parents=True)
    (source/"handwritten.ts").write_text("const x = fetch('/api/resources');\n")
    checker=(root/"frontend/scripts/check-no-manual-fetch.mjs").read_text()
    (isolated/"check-no-manual-fetch.mjs").write_text(checker)
    bad=subprocess.run(["node",str(isolated/"check-no-manual-fetch.mjs")],
                       cwd=tmp_path,capture_output=True,text=True)
    assert bad.returncode!=0 and "T2_MANUAL_FETCH_FORBIDDEN" in bad.stderr


@pytest.mark.skipif(os.getenv("SELECTOR_EXP_DISPOSABLE_DB")!="YES" or
                    not os.getenv("SELECTOR_EXP_TEST_DSN"),
                    reason="Requires disposable PG05 SQL selector")
@pytest.mark.parametrize("name",["login","notes"])
def test_real_source_t2_chain(tmp_path,name):
    if name=="login":
        run_f4(tmp_path,slug="t2-"+name)
    else:
        folder=tmp_path/"pilot/runs/t2-notes"
        folder.mkdir(parents=True)
        raw=b"Synthetic notes editor request\n"
        package=make_package(second_screen(),raw)
        (folder/"request.md").write_bytes(raw)
        (folder/"analysis.json").write_bytes(intake.canonical(package))
        intake.accept(tmp_path,"t2-notes")
    planned=prepare_t2.prepare(tmp_path,"t2-"+name,
                  base_head_sha=BASE)
    assert [lot["area"] for lot in planned["lots"]]==["CONTRATO","BACKEND","FRONTEND"]
    cid=planned["lots"][0]["id"]
    assert cid in planned["lots"][1]["depends_on"]
    assert cid in planned["lots"][2]["depends_on"]
    folder=tmp_path/"pilot/runs"/("t2-"+name)
    report=json.loads((folder/"t1_interventions.json").read_text())
    assert report["INTERVENCION_MANUAL"]=="NO"
    assert "MANUAL_CONTRACT" not in str(report)
    for lot in planned["lots"]:
        template=next((folder/"templates").glob("*"+lot["area"].lower()+"*.task.json"))
        assert template.is_file()
    assert (folder/"lots.json").is_file()
    if os.getenv("T2_ARTIFACT_DIR"):
        import shutil
        shutil.copytree(folder,Path(os.environ["T2_ARTIFACT_DIR"])/name)
