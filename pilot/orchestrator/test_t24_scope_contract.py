"""T24 contract: every generated area must be acceptable to CP3.5.

Uses the actual deterministic generate_chain and vendor Worker parser, not a
copied fake validator. CP3.5 sees the exact generated paths and fixed base.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pilot.orchestrator import generate_chain
from pilot.orchestrator.native_verified_integration import allowed_paths, IntegrationBlocked
from pilot.orchestrator.native_write_scope import (
    AREA_ROOTS, AREAS, WriteScopeError, validate_write_paths, area_candidates,
)
from pilot.orchestrator.worker_template_contract import validate_template_worker

PATHS = {
    "CONTRATO": ["contracts/synthetic.openapi.yaml"],
    "INFRA": ["apps/time-service/pom.xml", "frontend/package.json"],
    "DATA": ["db/migration/V1__synthetic.sql"],
    "BACKEND": ["apps/time-service/src/main/java/lf/sandbox/time/Synthetic.java"],
    "FRONTEND": ["frontend/src/app/synthetic/page.tsx"],
}
PROFILES = {
    "CONTRATO": "PERFIL-PROG-FRONTEND-EXP",
    "INFRA": "PERFIL-PROG-BACKEND-SPRING-EXP",
    "DATA": "PERFIL-PROG-DATA-EXP",
    "BACKEND": "PERFIL-PROG-BACKEND-SPRING-EXP",
    "FRONTEND": "PERFIL-PROG-FRONTEND-EXP",
}
BASE = "a" * 40


@pytest.mark.parametrize("area", sorted(AREAS))
def test_actual_generated_synthetic_area_template_passes_cp35(area, tmp_path):
    from pilot.orchestrator.test_t16_worker_schema import synthetic_template
    assert set(PATHS) == AREAS == set(AREA_ROOTS)
    template = synthetic_template(area)
    template["task_spec"]["write_path_patterns"] = PATHS[area]
    template["task_spec"]["max_changed_files"] = len(PATHS[area])
    validate_template_worker(template, area, pending_shas=True)
    registered = json.loads(json.dumps(template))
    registered["task_spec"]["base_head_sha"] = BASE
    registered["task_spec"]["source_snapshot_sha256"] = "b" * 64
    assert allowed_paths(registered) == (BASE, set(PATHS[area]))
    assert validate_write_paths(PATHS[area], area=area) == set(PATHS[area])


def test_actual_generate_chain_five_lots_paths_pass_cp35(tmp_path, monkeypatch):
    import contract_generate
    monkeypatch.setattr(contract_generate, "generate",
                        lambda module, package, atoms: {"synthetic": module})
    folder = tmp_path / "pilot/runs/req-901"
    folder.mkdir(parents=True)
    (folder / "analysis.json").write_text(json.dumps({"requirements": []}))
    (folder / "atomized_inputs.json").write_text(json.dumps({"atoms": []}))
    lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": False, "handoff_allowed": False,
            "worker_invoked": False, "lots": []}
    for i, (area, paths) in enumerate(PATHS.items(), start=1):
        lot = {"id": f"SOL-{i:03d}", "area": area,
               "profile_code": PROFILES[area],
               "write_paths": paths, "depends_on": [],
               "requirement_ids": [f"REQ-{area}"]}
        if area == "CONTRATO":
            lot["contract_module"] = "synthetic"
        if area == "INFRA":
            lot["infra_missing_dependencies"] = []
        lots["lots"].append(lot)
    plan = generate_chain.generate(tmp_path, "req-901", lots)
    assert len(plan["bindings"]) == len(AREAS)
    for item, lot in zip(plan["bindings"], lots["lots"]):
        template = json.loads((tmp_path / item["template_path"]).read_text("utf-8"))
        template["task_spec"]["base_head_sha"] = BASE
        template["task_spec"]["source_snapshot_sha256"] = "b" * 64
        try:
            actual_base, accepted = allowed_paths(template)
            assert accepted == set(lot["write_paths"]) and actual_base == BASE
        except IntegrationBlocked as exc:
            pytest.fail("SCOPE_GENERACION_INTEGRACION_DIVERGE:" + lot["area"] + ":" + str(exc))


@pytest.mark.parametrize("area,bad", [
    ("CONTRATO", ["frontend/src/app/other/page.tsx"]),
    ("INFRA", ["contracts/forbidden.openapi.yaml"]),
    ("DATA", ["frontend/src/app/other/page.tsx"]),
    ("BACKEND", ["contracts/forbidden.openapi.yaml"]),
    ("FRONTEND", ["apps/time-service/pom.xml"]),
])
def test_mismatched_generation_fails_with_exact_area_code(area, bad):
    with pytest.raises(ValueError, match="SCOPE_GENERACION_INTEGRACION_DIVERGE:" + area):
        generate_chain.enforce_generated_scope(area, bad)
    assert area not in area_candidates(bad)


@pytest.mark.parametrize("bad", [
    ".github/workflows/action.yml", "vendor/secret.py",
    "pilot/holdouts/hidden.age", "standards/changes/CHG-0001.json",
    "/tmp/absolute", "../escape", "contracts/../.github/forbidden.yml",
    "contracts//double.yaml", "contracts/./dot.yaml",
    "contracts/*.openapi.yaml", "C:/windows/drive", "contracts/evil\\file",
    "contracts/test.yaml/", "contracts/%00/../bad.yaml",
])
def test_cp35_and_generator_reject_security_boundaries(bad):
    with pytest.raises(WriteScopeError):
        validate_write_paths([bad])
    with pytest.raises(IntegrationBlocked, match="CP35_TASK_SCOPE_UNSAFE"):
        allowed_paths({"task_spec": {"base_head_sha": BASE,
                                    "write_path_patterns": [bad]}})


def test_mixed_areas_cannot_escape_policy():
    paths = ["contracts/x.openapi.yaml", "frontend/src/page.tsx"]
    with pytest.raises(WriteScopeError):
        validate_write_paths(paths)
    with pytest.raises(IntegrationBlocked, match="CP35_TASK_SCOPE_UNSAFE"):
        allowed_paths({"task_spec": {"base_head_sha": BASE,
                                    "write_path_patterns": paths}})


def test_real_req186_contract_path_is_accepted():
    assert allowed_paths({"task_spec": {
        "base_head_sha": BASE,
        "write_path_patterns": ["contracts/sbx-rem-list.openapi.yaml"],
    }}) == (BASE, {"contracts/sbx-rem-list.openapi.yaml"})


@pytest.mark.parametrize("area,root", sorted(
    (area, root) for area, roots in AREA_ROOTS.items() for root in roots))
def test_every_authorized_root_per_area_is_accepted_by_integration(area, root):
    path = root + "t24_probe.txt"
    assert validate_write_paths([path], area=area) == {path}
    assert allowed_paths({"task_spec": {"base_head_sha": BASE,
                                       "write_path_patterns": [path]}}) == (BASE, {path})
