"""T16: use the real pinned Worker parser for every area and native entrypoint."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pilot.orchestrator import generate_chain
from pilot.orchestrator.worker_template_contract import validate_template_worker
from programming_agent_runner.worker_spec import parse_worker_task, TaskSpecError

AREAS = {
    "CONTRATO": (["contracts/sample.openapi.yaml"], "sample", None),
    "INFRA": (["apps/time-service/pom.xml"], None, []),
    "DATA": (["apps/time-service/src/main/resources/db/migration/V1__sample.sql"], None, None),
    "BACKEND": (["apps/time-service/src/main/java/lf/sandbox/time/Sample.java"], None, None),
    "FRONTEND": (["frontend/src/app/sample/page.tsx"], None, None),
}


def synthetic_template(area: str) -> dict:
    paths, module, infra = AREAS[area]
    commands = generate_chain.acceptance(
        area, paths, run="req-901", module=module,
        skeleton_path="pilot/runs/req-901/templates/sample.skeleton.json"
                      if module else None,
        infra_dependencies=infra, has_contract=area in {"BACKEND", "FRONTEND"})
    return {"task_spec": {
        "schema_version": 1, "task_id": "LF-WORKER-NATIVE-REQ901" + area,
        "base_head_sha": "<FILL_AT_REGISTRATION>",
        "source_snapshot_sha256": "<FILL_AT_REGISTRATION>",
        "max_attempts": 1, "allow_deletions": False, "max_changed_files": len(paths),
        "max_context_bytes": 200000, "max_patch_bytes": 60000,
        "objective": "Implementar lote sintético " + area,
        "write_path_patterns": paths,
        "context_path_patterns": ["pilot/runs/req-901/analysis.json"],
        "protected_path_patterns": ["vendor/**"],
        "acceptance_commands": commands,
    }}


@pytest.mark.parametrize("area", sorted(AREAS))
def test_all_area_templates_pass_real_worker_parser(area):
    generated = synthetic_template(area)
    validate_template_worker(generated, area, pending_shas=True)
    pinned = dict(generated["task_spec"],
                  base_head_sha="a" * 40, source_snapshot_sha256="b" * 64)
    assert parse_worker_task(pinned).to_dict() == pinned
    validate_template_worker({"task_spec": pinned}, area)


@pytest.mark.parametrize("area", sorted(AREAS))
def test_invalid_schema_is_rejected_before_worker(area):
    template = synthetic_template(area)
    template["task_spec"]["context_derivation"] = "pilot/worker_v08/derive_context.py"
    with pytest.raises(ValueError, match="TEMPLATE_WORKER_SCHEMA_INVALID:" + area):
        validate_template_worker(template, area, pending_shas=True)


def test_actual_generate_chain_emits_worker_compatible_tasks_for_all_areas(tmp_path, monkeypatch):
    import contract_generate
    monkeypatch.setattr(contract_generate, "generate",
                        lambda module, package, atoms: {"synthetic": module})
    run = "req-901"
    folder = tmp_path / "pilot/runs" / run
    folder.mkdir(parents=True)
    (folder / "analysis.json").write_text(json.dumps({"requirements": []}))
    (folder / "atomized_inputs.json").write_text(json.dumps({"atoms": []}))
    import hashlib
    lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": False, "handoff_allowed": False,
            "worker_invoked": False, "lots": []}
    profiles = {
        "CONTRATO": "PERFIL-PROG-FRONTEND-EXP",
        "INFRA": "PERFIL-PROG-BACKEND-SPRING-EXP",
        "DATA": "PERFIL-PROG-DATA-EXP",
        "BACKEND": "PERFIL-PROG-BACKEND-SPRING-EXP",
        "FRONTEND": "PERFIL-PROG-FRONTEND-EXP",
    }
    for i, (area, (paths, module, infra)) in enumerate(AREAS.items(), 1):
        item = {"id": "SOL-%03d" % i, "area": area,
                "profile_code": profiles[area], "write_paths": paths,
                "depends_on": [], "requirement_ids": ["REQ-" + area]}
        if module:
            item["contract_module"] = module
        if infra is not None:
            item["infra_missing_dependencies"] = infra
        lots["lots"].append(item)
    plan = generate_chain.generate(tmp_path, run, lots)
    assert len(plan["bindings"]) == 5
    for binding, lot in zip(plan["bindings"], lots["lots"]):
        template = json.loads((tmp_path / binding["template_path"]).read_text())
        assert "context_derivation" not in template["task_spec"]
        validate_template_worker(template, lot["area"], pending_shas=True)


def test_native_registration_and_prepare_use_same_worker_contract():
    import inspect
    from pilot.orchestrator import native_lot_registration, prepare_native_lot
    source = inspect.getsource(native_lot_registration.register_lot)
    sealed = inspect.getsource(native_lot_registration.seal_lot)
    assert "validate_template_worker" in source
    assert "validate_template_worker" in sealed
    assert "register_lot(" in inspect.getsource(prepare_native_lot.run)
    assert "seal_lot(" in inspect.getsource(prepare_native_lot.run)
