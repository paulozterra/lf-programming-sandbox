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
