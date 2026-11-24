"""T33.3: a skeleton that reuses a frontend PAGE (T7) is a valid contract input."""
import pytest

import contract_validate as cv

SPEC = {
    "openapi": "3.0.3", "info": {"title": "x", "version": "1"},
    "paths": {"/api/auth/login": {"post": {
        "x-requirement-ids": ["REQ-A"],
        "requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "properties": {"email": {"type": "string"}}}}}},
        "responses": {"401": {"description": "x", "x-error-codes": ["E-1"]}}}}},
}
SK = {"schema_version": "T2_CONTRACT_SKELETON_V1", "functional_module": "m",
      "production_authority": False,
      "fields": [{"field_code": "F", "required": True, "api_name": "email"}],
      "errors": [{"error_code": "E-1", "generic": True}],
      "requirement_ids": ["REQ-A"], "rules": [],
      "reused_endpoints": ["PAGE /sbx-rem-list", "POST /api/auth/login"],
      "extended_endpoints": ["PAGE /sbx-rem-list", "POST /api/auth/login"]}


def _write(tmp_path, spec):
    import yaml
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(spec), "utf-8")
    return p


def test_page_reuse_is_accepted_and_not_required_in_openapi(tmp_path):
    assert cv.validate(_write(tmp_path, SPEC), SK, "m") is True


def test_api_extension_is_still_required(tmp_path):
    spec = {**SPEC, "paths": {"/api/other": SPEC["paths"]["/api/auth/login"]}}
    with pytest.raises(cv.ContractBlocked, match="CONTRACT_DECLARED_ENDPOINT_MISSING"):
        cv.validate(_write(tmp_path, spec), SK, "m")


def test_unknown_verb_still_blocks(tmp_path):
    bad = {**SK, "reused_endpoints": ["FETCH /x"], "extended_endpoints": []}
    with pytest.raises(cv.ContractBlocked, match="REUTILIZACION_INDETERMINADA"):
        cv.validate(_write(tmp_path, SPEC), bad, "m")


def _session_contract():
    from copy import deepcopy
    spec, sk = deepcopy(SPEC), deepcopy(SK)
    ops = ["GET /api/session", "POST /api/signout"]
    sk["rules"] = [{"requirement_id": "REQ-A",
                    "valor_config": {"required_contract_operations": ops}}]
    sk["required_contract_operations"] = cv.required_contract_operations(sk["rules"])
    sk["reused_endpoints"].append(ops[0])
    for identity in ops:
        method, route = identity.split(" ", 1)
        spec["paths"][route] = {method.lower(): {
            "x-requirement-ids": ["REQ-A"], "responses": {"204": {"description": "OK"}}}}
    return spec, sk


def test_contract_declaration_of_reused_operation_does_not_require_extension(tmp_path):
    spec, sk = _session_contract()
    assert cv.validate(_write(tmp_path, spec), sk, "m")


@pytest.mark.parametrize("route", ["/api/session", "/api/signout"])
def test_each_required_operation_must_be_declared(tmp_path, route):
    spec, sk = _session_contract()
    del spec["paths"][route]
    with pytest.raises(cv.ContractBlocked, match="CONTRACT_DECLARED_ENDPOINT_MISSING"):
        cv.validate(_write(tmp_path, spec), sk, "m")


def test_reused_endpoint_without_explicit_declaration_still_blocks(tmp_path):
    spec, sk = _session_contract()
    sk["rules"] = []
    del sk["required_contract_operations"]
    with pytest.raises(cv.ContractBlocked, match="DUPLICA_COMPONENTE_EXISTENTE"):
        cv.validate(_write(tmp_path, spec), sk, "m")


def test_required_operation_must_trace_to_rule(tmp_path):
    spec, sk = _session_contract()
    spec["paths"]["/api/session"]["get"]["x-requirement-ids"] = ["REQ-OTHER"]
    with pytest.raises(cv.ContractBlocked, match="CONTRACT_DECLARED_ENDPOINT_REQUIREMENT_MISSING"):
        cv.validate(_write(tmp_path, spec), sk, "m")


def test_required_operations_cannot_be_invented_in_skeleton(tmp_path):
    spec, sk = _session_contract()
    sk["required_contract_operations"]["GET /api/other"] = ["REQ-A"]
    with pytest.raises(cv.ContractBlocked, match="CONTRACT_REQUIRED_OPERATIONS_INVALID"):
        cv.validate(_write(tmp_path, spec), sk, "m")


def test_session_fixture_rule_is_effective_and_pinned():
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "analysis/fixtures/sbx_b2b_login"
    pin = json.loads((root / "SOURCE_PIN.json").read_bytes())
    for item in pin["files"]:
        assert hashlib.sha256((root / item["file"]).read_bytes()).hexdigest() == item["sha256"]
    direct = json.loads((root / "direct_rules.json").read_bytes())
    effective = json.loads((root / "effective_rules.json").read_bytes())
    code = "SBX-B2B-R-INT-HOME"
    config = next(x["valor_config"] for x in direct["valor_config"] if x["code"] == code)
    rule = next(x for x in effective["rules"] if x["code"] == code)
    assert rule["config"] == config
    assert config["required_contract_operations"] == [
        "GET /api/auth/session", "POST /api/auth/logout"]
