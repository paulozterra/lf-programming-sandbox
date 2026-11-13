"""T2: two governed examples and a random third scope; no exceptions by code."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

import pytest
import yaml

from analysis.a9.front_bindings import partition
from analysis.a9.area_projection import project
from analysis.a9.test_general_second_screen import second_screen, make_package
from analysis.host.run_a1_a9_fixture import run_f4
from pilot.orchestrator import atomize, intake, package_to_lots
from pilot.orchestrator.contract_validate import (
    ContractBlocked, validate, check_frontend, check_generated,
)

ROOT = Path(__file__).resolve().parents[2]
DB_ONLY = pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="Requires disposable PostgreSQL profile selector",
)


def source_for(target, screen):
    module = atomize._slug(target + "-BACKEND", atomize._rules())
    # Test source has typed operations; production reads them, never infers them.
    return {"schema_version": "T2_API_CONTRACT_SOURCE_V1",
            "fields": deepcopy(screen["fields"]),
            "errors": deepcopy(screen["errors"]),
            "operations": [{
                "method": "post", "path": "/api/" + module,
                "evidence_refs": [f"fixture://t2/{target}/api-operation"],
            }]}


def accept(root, slug, pkg, raw):
    folder = root / "pilot/runs" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder/"request.md").write_bytes(raw)
    (folder/"analysis.json").write_bytes(intake.canonical(pkg))
    (folder/"state.json").unlink(missing_ok=True)
    intake.accept(root, slug)
    return folder


def scenario(root, kind, *, slug):
    if kind == "first":
        # Reuse Analysis's existing test-only compatibility symlink. A1-A5
        # source code and its validators remain byte-exact and unmodified.
        import analysis.conftest
        original = run_f4(root, slug=slug)
        pkg = deepcopy(original["package"])
        raw = (root/"pilot/runs"/slug/"request.md").read_bytes()
        screen = json.loads((ROOT/"analysis/fixtures/sbx_auth_login/screen_contract.json").read_text())["contract"]
    elif kind == "second":
        src = second_screen()
        raw = b"Create an independent typed screen contract from sourced fields and rules\\n"
        pkg = make_package(src, raw)
        screen = src["screen_contract"]
    else:
        token = uuid.uuid4().hex[:9]
        target = "R" + token.upper() + "-EDIT"
        raw = ("Create generated typed screen " + token + "\n").encode()
        screen_ref = "fixture://synthetic/" + token + "/screen#contract/"
        source_a = "fixture://synthetic/" + token + "/rule/a"
        source_b = "fixture://synthetic/" + token + "/rule/b"
        a, b = "FIELD_" + token.upper(), "ERROR_" + token.upper()
        screen = {
            "fields": [{"field_code": "INPUT_" + token.upper(), "status":"VIGENTE",
                        "required":True,"rule_refs":[source_a]}],
            "errors": [{"error_code":"ERROR_RESPONSE_" + token.upper(),
                        "status":"VIGENTE","generic":True,"rule_refs":[source_b]}],
            "visual":{"variants":[{"code":"VARIANT_" + token.upper(),
                                   "status":"VIGENTE","rule_refs":[source_a,source_b]}]},
            "rules": [{"code":a,"source_ref":source_a,"association_ref":source_a+"/assoc"},
                      {"code":b,"source_ref":source_b,"association_ref":source_b+"/assoc"}],
            "context":{}, "metadata":{}, "profiles":[], "analytics":[],
        }
        rules = {
            a: {"source_ref":source_a,"categoria":"workflow","binding_source":"LEGACY_EXPLICIT"},
            b: {"source_ref":source_b,"categoria":"error_states","binding_source":"LEGACY_EXPLICIT"},
        }
        reqs = [
            {"requirement_id":"REQ-"+a.replace("_","-"), "source_requirement_id":a,
             "evidence_refs":[source_a], "outcome":"Validate a supplied field",
             "acceptance_signal":"Field validation", "acceptance_checks":["Field validation"],
             "scope_id":target,"materiality_level":"HIGH",
             "requires_independent_exam":True,"simulation_mode":"SIMULATED_SANDBOX_ONLY"},
            {"requirement_id":"REQ-"+b.replace("_","-"), "source_requirement_id":b,
             "evidence_refs":[source_b], "outcome":"Return a typed error",
             "acceptance_signal":"Error response", "acceptance_checks":["Error response"],
             "scope_id":target,"materiality_level":"HIGH",
             "requires_independent_exam":True,"simulation_mode":"SIMULATED_SANDBOX_ONLY"},
        ]
        def front(ref):
            return {"front_id":"F3-"+hashlib.sha256(ref.encode()).hexdigest()[:16],
                    "candidate_ref":ref,"front_kind":"API_CONTRACT",
                    "evidence_refs":[ref],"obligation_refs":[],
                    "status":"REQUIRED","closure":"CLOSED","blockers":[],
                    "simulation_mode":"SIMULATED_SANDBOX_ONLY"}
        refs=[screen_ref+"fields/0",screen_ref+"errors/0",
              screen_ref+"visual/variants/0",screen_ref+"context",
              screen_ref+"metadata",source_a,source_b]
        fronts=[front(r) for r in refs]
        active,excluded=partition(fronts,reqs,screen,rules,scope=target,
                                   create_empty_inventory=True)
        projected,active,scopes,rule_fronts=project(
            target,reqs,active,readiness="READY_CANDIDATE")
        # Source-neutral synthetic intake wrapper reuses the approved A9 shape.
        src = second_screen()
        pkg = make_package(src, raw)
        pkg["request_context"]["target_ref"] = target
        pkg["requirements"] = projected
        pkg["material_fronts"] = active
        pkg["scope_proposals"] = scopes
        pkg["non_atomized_fronts"] = excluded
        pkg["applicable_rules"] = [
            {"front_id":rule_fronts[r["source_requirement_id"]],
             "requirement_id":r["requirement_id"],
             "rule_code":r["source_requirement_id"],"source_ref":r["evidence_refs"][0]}
            for r in projected if not r.get("derived_from_requirement_id")]
    pkg["api_contract_source"]=source_for(pkg["request_context"]["target_ref"],screen)
    folder=accept(root,slug,pkg,raw)
    return folder,pkg


@pytest.mark.parametrize("kind", ["first","second","synthetic"])
@DB_ONLY
def test_t2_contract_precedes_be_and_fe_and_validates(tmp_path,kind):
    slug="t2-"+kind
    folder,pkg=scenario(tmp_path,kind,slug=slug)
    lots=package_to_lots.prepare(tmp_path,slug,base_head_sha="a"*40)
    assert [lot["area"] for lot in lots["lots"]]==["CONTRATO","BACKEND","FRONTEND"]
    contract,be,fe=lots["lots"]
    assert be["depends_on"]==[contract["id"]]
    assert set(fe["depends_on"])=={be["id"],contract["id"]}
    assert be["contract_context_ref"]==contract["write_paths"][0]
    assert fe["contract_context_ref"]==contract["write_paths"][0]
    assert contract["profile_code"]==be["profile_code"]
    assert len(contract["write_paths"])==1
    assert contract["write_paths"][0].startswith("contracts/")
    module=contract["contract_module"]
    draft=folder/"contract_drafts"/(module+".openapi.yaml")
    context=folder/"contract_context"/(module+".json")
    assert draft.is_file() and context.is_file()
    assert validate(draft,json.loads(context.read_text()),module)
    plan=json.loads((tmp_path/"pilot/orchestrator/chain_plans"/(slug+".json")).read_text())
    assert len(plan["bindings"])==3
    templates=[json.loads((tmp_path/b["template_path"]).read_text())["task_spec"]
               for b in plan["bindings"]]
    assert len(templates[0]["acceptance_commands"])>=1
    assert contract["write_paths"][0] in templates[1]["context_path_patterns"]
    assert contract["write_paths"][0] in templates[2]["context_path_patterns"]
    assert any(x["name"]=="frontend-no-manual-fetch"
               for x in templates[2]["acceptance_commands"])
    assert json.loads((folder/"t1_interventions.json").read_text())["INTERVENCION_MANUAL"]=="NO"
    assert not (folder/"owner_area_decision.json").exists()
    assert not (folder/"planning_fixture.json").exists()
    if os.getenv("T2_ARTIFACT_DIR"):
        shutil.copytree(folder,Path(os.environ["T2_ARTIFACT_DIR"])/kind)


def test_contract_missing_requirement_fails(tmp_path):
    pkg={"atoms":[{"area":"BACKEND","functional_module":"sample","requirement_ids":["REQ-RANDOM-A"]}],
         "api_contract_source":{"errors":[]}}
    path=tmp_path/"sample.openapi.yaml"
    path.write_text(yaml.safe_dump({"openapi":"3.1.0",
        "info":{"title":"sample","version":"1"},
        "paths":{"/something":{"post":{"x-requirement-ids":["REQ-OTHER"],
        "responses":{"200":{"description":"OK"}}}}}}))
    with pytest.raises(ContractBlocked,match="CONTRACT_REQ_COVERAGE_MISSING"):
        validate(path,pkg,"sample")


def test_missing_error_and_secret_examples_block(tmp_path):
    pkg={"atoms":[{"area":"BACKEND","functional_module":"sample","requirement_ids":["REQ-RANDOM-A"]}],
         "api_contract_source":{"errors":[{"error_code":"RANDOM_ERR","status":"VIGENTE"}]}}
    path=tmp_path/"sample.openapi.yaml"
    spec={"openapi":"3.1.0","info":{"title":"sample","version":"1"},
        "paths":{"/sample":{"post":{"x-requirement-ids":["REQ-RANDOM-A"],
        "responses":{"200":{"description":"OK"}}}}}}
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked,match="CONTRACT_ERROR_COVERAGE_MISSING"):
        validate(path,pkg,"sample")
    spec["paths"]["/sample"]["post"]["responses"]["default"]={
        "description":"Error","x-error-codes":["RANDOM_ERR"]}
    spec["paths"]["/sample"]["post"]["requestBody"]={
        "content":{"application/json":{"schema":{"properties":{
            "password":{"type":"string","example":"a-real-password"}}}}}}
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked,match="CONTRACT_SECRET_EXAMPLE"):
        validate(path,pkg,"sample")


def test_manual_fetch_blocks(tmp_path):
    file=tmp_path/"frontend/src/app/page.tsx"
    file.parent.mkdir(parents=True)
    file.write_text('export async function call(){ return fetch("/api/internal"); }')
    with pytest.raises(ContractBlocked,match="CONTRACT_MANUAL_FETCH_FORBIDDEN"):
        check_frontend(tmp_path)


def test_stale_generated_client_blocks(tmp_path,monkeypatch):
    root=tmp_path
    generated=root/"frontend/src/lib/api/generated/index.ts"
    generated.parent.mkdir(parents=True)
    generated.write_text("// initial\n")
    subprocess.run(["git","init","-q"],cwd=root,check=True)
    subprocess.run(["git","add","frontend/src/lib/api/generated/index.ts"],cwd=root,check=True)
    script=root/"npm"
    script.write_text("#!/bin/sh\nprintf '// altered\\n' > frontend/src/lib/api/generated/index.ts\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH",str(root)+os.pathsep+os.environ["PATH"])
    with pytest.raises(ContractBlocked,match="CONTRACT_GENERATED_CLIENT_STALE"):
        check_generated(root)


def test_intervention_report_distinguishes_bot_contract_from_manual_contract():
    from pilot.orchestrator.intervention_report import classify
    path="contracts/functional-unit.openapi.yaml"
    assert classify(path,"BOT","sample")[0]=="AUTOMATIC"
    assert classify(path,"PAULO_O_GPT","sample")[1]=="MANUAL_CONTRACT"
