"""T36: a valid OpenAPI that uses $ref for request schemas covers its fields."""
import pytest
import yaml

import contract_validate as cv

SK = {"schema_version": "T2_CONTRACT_SKELETON_V1", "functional_module": "m",
      "production_authority": False,
      "fields": [{"field_code": "F1", "required": True, "api_name": "email"},
                 {"field_code": "F2", "required": True, "api_name": "password"}],
      "errors": [{"error_code": "E-1", "generic": True}],
      "requirement_ids": ["REQ-A"], "rules": [],
      "reused_endpoints": [], "extended_endpoints": []}


def _spec(schema, comps):
    return {"openapi": "3.0.3", "info": {"title": "x", "version": "1"},
            "paths": {"/api/x": {"post": {
                "x-requirement-ids": ["REQ-A"],
                "requestBody": {"content": {"application/json": {"schema": schema}}},
                "responses": {"401": {"description": "x", "x-error-codes": ["E-1"]}}}}},
            "components": {"schemas": comps}}


def _write(tmp_path, spec):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(spec), "utf-8")
    return p


def test_ref_request_schema_counts(tmp_path):
    spec = _spec({"$ref": "#/components/schemas/Req"},
                 {"Req": {"allOf": [{"$ref": "#/components/schemas/Base"}],
                          "properties": {"password": {"type": "string"}}},
                  "Base": {"properties": {"email": {"type": "string"}}}})
    assert cv.validate(_write(tmp_path, spec), SK, "m") is True


def test_missing_field_still_blocks(tmp_path):
    spec = _spec({"$ref": "#/components/schemas/A"},
                 {"A": {"properties": {"email": {"type": "string"}}}})
    with pytest.raises(cv.ContractBlocked, match="CONTRACT_FIELD_COVERAGE_MISSING:password"):
        cv.validate(_write(tmp_path, spec), SK, "m")


def test_cycle_terminates():
    spec = {"components": {"schemas": {"A": {"properties": {"email": {}},
                                              "allOf": [{"$ref": "#/components/schemas/A"}]}}}}
    op = {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/A"}}}}}
    assert cv._field_names(op, spec) == {"email"}


def test_external_ref_is_not_followed(tmp_path):
    spec = _spec({"$ref": "http://evil.example/x.yaml#/Req"}, {})
    with pytest.raises(cv.ContractBlocked, match="CONTRACT_FIELD_COVERAGE_MISSING"):
        cv.validate(_write(tmp_path, spec), SK, "m")
