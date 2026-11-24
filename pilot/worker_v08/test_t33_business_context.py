"""T33: each lot's context carries its A9 business rules and screen material."""
import json
from pathlib import Path

import pytest

import business_context as bc


def _package(tmp: Path, slug="req-77"):
    run = tmp / "pilot/runs" / slug
    run.mkdir(parents=True)
    package = {
        "requirements": [
            {"requirement_id": "REQ-SBX-R-A", "source_requirement_id": "SBX-R-A",
             "outcome": "Texto de la regla A.", "acceptance_checks": ["Texto de la regla A."],
             "evidence_refs": ["supabase://lf_ops.reglas/1"], "scope_id": "S-BACKEND"},
            {"requirement_id": "REQ-SBX-R-B", "source_requirement_id": "SBX-R-B",
             "outcome": "Texto de la regla B.", "acceptance_checks": [],
             "evidence_refs": [], "scope_id": "S-FRONTEND"}],
        "applicable_rules": [
            {"requirement_id": "REQ-SBX-R-A", "rule_code": "SBX-R-A", "titulo": "A",
             "categoria": "SECURITY", "valor_config": {"max": 5},
             "source_ref": "supabase://lf_ops.reglas/1", "source_status": "VIGENTE"}],
        "programming_context_snapshot": {"decision_context": {"material_ledger": {
            "source_detail": {"a3_material_contract": {"contract_sections": {
                "fields": [{"label": "Correo electrónico"}],
                "errors": [{"message": "No pudimos validar tus datos."}],
                "visual": {"colors": [{"token": "green_action", "hex": "#109044"}]},
                "context": {"elements": [{"label_visible": "Acceder"}]},
                "rules": [{"code": "IGNORED"}]}}}}}},
    }
    (run / "analysis.json").write_text(json.dumps(package), "utf-8")
    return slug


def test_run_slug_from_reuse_ref():
    assert bc.run_slug(["x.md", "pilot/runs/req-77/reuse_assessment.json"]) == "req-77"
    assert bc.run_slug(["x.md"]) is None
    with pytest.raises(bc.BusinessContextBlocked):
        bc.run_slug(["pilot/runs/a/reuse_assessment.json", "pilot/runs/b/reuse_assessment.json"])


def test_backend_lot_gets_its_rules_with_values_and_no_visual(tmp_path):
    slug = _package(tmp_path)
    out = bc.material(tmp_path, slug, ["REQ-SBX-R-A"], "BACKEND")
    rules = json.loads(out["reglas_negocio.json"])
    assert [r["requirement_id"] for r in rules["requirements"]] == ["REQ-SBX-R-A"]
    assert rules["requirements"][0]["outcome"] == "Texto de la regla A."
    assert rules["requirements"][0]["rules"][0]["valor_config"] == {"max": 5}
    screen = json.loads(out["pantalla.json"])["sections"]
    assert set(screen) == {"fields", "errors"}



def test_infra_lot_gets_requirements_without_screen_sections(tmp_path):
    slug = _package(tmp_path)
    out = bc.material(tmp_path, slug, ["REQ-SBX-R-A"], "INFRA")
    assert set(out) == {"reglas_negocio.json"}
    requirements = json.loads(out["reglas_negocio.json"])
    assert requirements["area"] == "INFRA"
    assert requirements["run"] == slug
    assert [r["requirement_id"] for r in requirements["requirements"]] == ["REQ-SBX-R-A"]
    rule = requirements["requirements"][0]
    assert rule["outcome"] == "Texto de la regla A."
    assert rule["acceptance_checks"] == ["Texto de la regla A."]
    assert rule["rules"][0]["valor_config"] == {"max": 5}
    assert "pantalla.json" not in out



def test_frontend_lot_gets_copy_validations_and_tokens(tmp_path):
    slug = _package(tmp_path)
    out = bc.material(tmp_path, slug, ["REQ-SBX-R-B"], "FRONTEND")
    screen = json.loads(out["pantalla.json"])["sections"]
    assert set(screen) == {"fields", "errors", "visual", "context"}
    raw = out["pantalla.json"].decode()
    assert "#109044" in raw and "Acceder" in raw and "IGNORED" not in raw
    rules = json.loads(out["reglas_negocio.json"])
    assert [r["requirement_id"] for r in rules["requirements"]] == ["REQ-SBX-R-B"]


def test_unknown_requirement_fails_closed(tmp_path):
    slug = _package(tmp_path)
    with pytest.raises(bc.BusinessContextBlocked, match="REQUISITO_AUSENTE"):
        bc.material(tmp_path, slug, ["REQ-SBX-R-NOPE"], "BACKEND")


def test_invalid_inputs_fail_closed(tmp_path):
    slug = _package(tmp_path)
    for ids, area in ((["bad id"], "BACKEND"), ([], "BACKEND"), (["REQ-SBX-R-A"], "OTRA")):
        with pytest.raises(bc.BusinessContextBlocked):
            bc.material(tmp_path, slug, ids, area)


def test_run_without_package_adds_nothing(tmp_path):
    (tmp_path / "pilot/runs/legacy").mkdir(parents=True)
    assert bc.material(tmp_path, "legacy", ["REQ-X"], "BACKEND") == {}


def test_registration_wires_business_material():
    src = Path(bc.__file__).with_name("register_task_context.py").read_text("utf-8")
    assert "business_material" in src and "requirement_ids" in src
    reg = Path(bc.__file__).parents[1].joinpath(
        "orchestrator/native_lot_registration.py").read_text("utf-8")
    # CHG-0412: own requirements, or the pinned ones of a characterization lot.
    assert reg.count("requirement_ids=examinable_requirements(lot)") == 2
