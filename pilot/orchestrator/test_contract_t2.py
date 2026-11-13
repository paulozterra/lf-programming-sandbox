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


def attach_screen_readback(package, screen):
    """Represent typed screen source in a simulated A9 package, never API operations."""
    if "programming_context_snapshot" not in package:
        package["programming_context_snapshot"] = {
            "decision_context": {"material_ledger": {"source_detail": {
                "a3_material_contract": {"contract_sections": {
                    "fields": deepcopy(screen["fields"]),
                    "errors": deepcopy(screen["errors"]),
                }}
            }}}
        }
    return package


def constructor_proposal(skeleton):
    """Fixture-only candidate: constructor chooses path/method, not Analysis."""
    module = skeleton["functional_module"]
    properties = {f["field_code"]: {"type": "string"} for f in skeleton["fields"]}
    return {
        "openapi": "3.1.0", "info": {"title": module, "version": "1.0.0"},
        "paths": {"/api/" + module: {"post": {
            "operationId": "propose_" + module.replace("-", "_"),
            "x-requirement-ids": skeleton["requirement_ids"],
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {
                    "type": "object", "properties": properties
                }}}},
            "responses": {
                "200": {"description": "Success"},
                "400": {"description": "Declared errors",
                        "x-error-codes": [e["error_code"] for e in skeleton["errors"]]}
            },
        }}},
    }


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
    attach_screen_readback(pkg,screen)
    folder=accept(root,slug,pkg,raw)
    return folder,pkg


@pytest.mark.parametrize("kind", ["first", "second", "synthetic"])
@DB_ONLY
def test_t2_contract_precedes_be_and_fe_and_validates(tmp_path, kind):
    slug = "t2-" + kind
    folder, package = scenario(tmp_path, kind, slug=slug)
    assert "api_contract_source" not in package
    lots = package_to_lots.prepare(tmp_path, slug, base_head_sha="a" * 40)
    assert [lot["area"] for lot in lots["lots"]] == ["CONTRATO", "BACKEND", "FRONTEND"]
    contract, be, fe = lots["lots"]
    assert contract["depends_on"] == []
    assert be["depends_on"] == [contract["id"]]
    assert set(fe["depends_on"]) == {be["id"], contract["id"]}
    assert be["contract_context_ref"] == contract["write_paths"][0]
    assert fe["contract_context_ref"] == contract["write_paths"][0]
    assert contract["profile_code"] == be["profile_code"]
    module = contract["contract_module"]
    skeleton_path = tmp_path / "contracts" / (module + ".skeleton.json")
    assert skeleton_path.is_file()
    skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
    assert skeleton["schema_version"] == "T2_CONTRACT_SKELETON_V1"
    assert skeleton["functional_module"] == module
    assert skeleton["production_authority"] is False
    assert skeleton["fields"] and skeleton["errors"]
    assert not any(key in skeleton for key in ("paths", "operations", "api_contract_source"))
    assert set(skeleton["requirement_ids"]) == set(contract["requirement_ids"])
    assert skeleton["rules"]
    assert sorted(skeleton["fields"], key=lambda x: x["field_code"]) == sorted([
        {"field_code": f["field_code"], "required": f["required"]}
        for f in package["programming_context_snapshot"]["decision_context"][
            "material_ledger"]["source_detail"]["a3_material_contract"][
                "contract_sections"]["fields"] if f["status"] == "VIGENTE"],
        key=lambda x: x["field_code"])

    assert not (tmp_path / contract["write_paths"][0]).exists()
    proposed = tmp_path / "candidate.openapi.yaml"
    spec = constructor_proposal(skeleton)
    proposed.write_text(yaml.safe_dump(spec), encoding="utf-8")
    assert validate(proposed, skeleton, module)

    plan = json.loads((tmp_path / "pilot/orchestrator/chain_plans" /
                       (slug + ".json")).read_text())
    assert len(plan["bindings"]) == 3
    templates = [json.loads((tmp_path / row["template_path"]).read_text())["task_spec"]
                 for row in plan["bindings"]]
    assert templates[0]["write_path_patterns"] == [contract["write_paths"][0]]
    assert "contracts/" + module + ".skeleton.json" in templates[0]["context_path_patterns"]
    assert "contracts/*.skeleton.json" in templates[0]["protected_path_patterns"]
    assert "--skeleton" in templates[0]["acceptance_commands"][0]["argv"]
    assert contract["write_paths"][0] in templates[1]["context_path_patterns"]
    assert contract["write_paths"][0] in templates[2]["context_path_patterns"]
    assert any(x["name"] == "backend-contract-operations"
               for x in templates[1]["acceptance_commands"])
    assert any(x["name"] == "frontend-no-manual-fetch"
               for x in templates[2]["acceptance_commands"])
    report = json.loads((folder / "t1_interventions.json").read_text())
    assert report["INTERVENCION_MANUAL"] == "NO"
    assert "MANUAL_CONTRACT" not in report["interventions"]
    assert not (folder / "owner_area_decision.json").exists()
    assert not (folder / "planning_fixture.json").exists()
    if os.getenv("T2_ARTIFACT_DIR"):
        out = Path(os.environ["T2_ARTIFACT_DIR"]) / kind
        shutil.copytree(folder, out)
        (out / "contract_skeleton.json").write_bytes(skeleton_path.read_bytes())
        (out / "constructor_example.openapi.yaml").write_bytes(proposed.read_bytes())


def sample_skeleton():
    return {
        "schema_version": "T2_CONTRACT_SKELETON_V1",
        "functional_module": "sample",
        "production_authority": False,
        "requirement_ids": ["REQ-RANDOM-A"],
        "fields": [{"field_code": "SYNTH_FIELD", "required": True}],
        "errors": [{"error_code": "SYNTH_ERROR"}],
        "rules": [{"rule_code": "RANDOM-A", "requirement_id": "REQ-RANDOM-A",
                   "source_ref": "fixture://random/rule"}],
    }


def test_contract_missing_requirement_fails(tmp_path):
    skeleton = sample_skeleton()
    path = tmp_path / "sample.openapi.yaml"
    spec = constructor_proposal(skeleton)
    spec["paths"]["/api/sample"]["post"]["x-requirement-ids"] = ["REQ-OTHER"]
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked, match="CONTRACT_REQ_COVERAGE_MISSING"):
        validate(path, skeleton, "sample")


def test_contract_missing_field_fails(tmp_path):
    skeleton = sample_skeleton()
    path = tmp_path / "sample.openapi.yaml"
    spec = constructor_proposal(skeleton)
    del spec["paths"]["/api/sample"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["properties"]["SYNTH_FIELD"]
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked, match="CONTRACT_FIELD_COVERAGE_MISSING"):
        validate(path, skeleton, "sample")


def test_missing_error_and_secret_examples_block(tmp_path):
    skeleton = sample_skeleton()
    path = tmp_path / "sample.openapi.yaml"
    spec = constructor_proposal(skeleton)
    spec["paths"]["/api/sample"]["post"]["responses"]["400"]["x-error-codes"] = []
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked, match="CONTRACT_ERROR_COVERAGE_MISSING"):
        validate(path, skeleton, "sample")
    spec["paths"]["/api/sample"]["post"]["responses"]["400"]["x-error-codes"] = [
        "SYNTH_ERROR"]
    spec["paths"]["/api/sample"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["properties"]["password"] = {
            "type": "string", "example": "a-real-password"}
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked, match="CONTRACT_SECRET_EXAMPLE"):
        validate(path, skeleton, "sample")


def test_manual_fetch_blocks(tmp_path):
    file = tmp_path / "frontend/src/app/page.tsx"
    file.parent.mkdir(parents=True)
    file.write_text('export async function call(){ return fetch("/api/internal"); }')
    with pytest.raises(ContractBlocked, match="CONTRACT_MANUAL_FETCH_FORBIDDEN"):
        check_frontend(tmp_path)


def test_stale_generated_client_blocks(tmp_path, monkeypatch):
    root = tmp_path
    generated = root / "frontend/src/lib/api/generated/index.ts"
    generated.parent.mkdir(parents=True)
    generated.write_text("// initial\\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "frontend/src/lib/api/generated/index.ts"],
                   cwd=root, check=True)
    real_run = subprocess.run

    def simulated_generation(argv, **kwargs):
        if argv[0] == "npm":
            # Stub only the generator, not git; verify actual index drift.
            generated.write_text("// altered generated client")
            return subprocess.CompletedProcess(argv, 0)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", simulated_generation)
    with pytest.raises(ContractBlocked, match="CONTRACT_GENERATED_CLIENT_STALE"):
        check_generated(root)


def test_intervention_report_distinguishes_bot_contract_from_manual_contract():
    from pilot.orchestrator.intervention_report import classify
    path = "contracts/functional-unit.openapi.yaml"
    assert classify(path, "BOT", "sample")[0] == "AUTOMATIC"
    assert classify(path, "PAULO_O_GPT", "sample")[1] == "MANUAL_CONTRACT"


def test_native_worker_accepts_only_bounded_contract_write(tmp_path):
    from pilot.orchestrator.native_lot_binding import map_profile, real_write_paths
    from pilot.worker_v08.derive_context import denial

    (tmp_path / "contracts").mkdir()
    path = "contracts/case-2030.openapi.yaml"
    assert denial(path) is None
    assert denial("contracts/case-2030.skeleton.json", is_spec=True) is None
    assert denial("contracts/case-2030.skeleton.json") == "DENIED_OUTSIDE_APPS"
    assert denial("contracts/../unsafe.openapi.yaml") is not None
    assert real_write_paths(tmp_path, "CONTRATO", [path]) == [path]
    mapped = map_profile("PERFIL-PROG-BACKEND-SPRING-EXP", "CONTRATO")
    assert mapped["native_profile_code"] == "PERFIL-PROG-BACKEND-EXP"


def test_nested_password_in_example_blocks(tmp_path):
    skeleton = sample_skeleton()
    spec = constructor_proposal(skeleton)
    spec["paths"]["/api/sample"]["post"]["requestBody"]["content"][
        "application/json"]["example"] = {
            "SYNTH_FIELD": "value", "password": "unredacted"
        }
    path = tmp_path / "sample.openapi.yaml"
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractBlocked, match="CONTRACT_SECRET_EXAMPLE"):
        validate(path, skeleton, "sample")
