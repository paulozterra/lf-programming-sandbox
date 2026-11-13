#!/usr/bin/env python3
"""T2: deterministic OpenAPI draft from typed A9 source; no API guesswork."""
from __future__ import annotations

import re
import yaml

from contract_validate import ContractBlocked, METHODS, deny


def generate(module, package, atoms):
    source = package.get("api_contract_source")
    if (not isinstance(source, dict)
            or source.get("schema_version") != "T2_API_CONTRACT_SOURCE_V1"):
        deny("T2_CONTRACT_SOURCE_UNRESOLVED")
    for key in ("fields", "errors", "operations"):
        if not isinstance(source.get(key), list):
            deny("T2_CONTRACT_SOURCE_UNRESOLVED")
    related = [a for a in atoms if a.get("functional_module") == module
               and a.get("area") in ("BACKEND", "FRONTEND")]
    if {a["area"] for a in related} != {"BACKEND", "FRONTEND"}:
        deny("T2_CONTRACT_UNPAIRED")
    ids = sorted({rid for atom in related for rid in atom["requirement_ids"]})
    fields = {}
    required = []
    for field in source["fields"]:
        if (not isinstance(field, dict) or not isinstance(field.get("field_code"), str)
                or not field.get("field_code") or field.get("status") != "VIGENTE"):
            deny("T2_CONTRACT_FIELD_UNSOURCED")
        key = field["field_code"]
        if key in fields:
            deny("T2_CONTRACT_FIELD_DUPLICATE")
        fields[key] = {"type": "string"}
        if field.get("required") is True:
            required.append(key)
    errors = sorted({e["error_code"] for e in source["errors"]
                     if isinstance(e, dict) and e.get("status") == "VIGENTE"
                     and isinstance(e.get("error_code"), str) and e["error_code"]})
    if any(not isinstance(e, dict) or not isinstance(e.get("error_code"), str)
           for e in source["errors"]):
        deny("T2_CONTRACT_ERROR_UNSOURCED")
    paths = {}
    for op in source["operations"]:
        if not isinstance(op, dict):
            deny("T2_CONTRACT_OPERATION_UNSOURCED")
        path, method = op.get("path"), op.get("method")
        if (not isinstance(path, str) or not path.startswith("/")
                or ".." in path or not isinstance(method, str)
                or method.lower() not in METHODS):
            deny("T2_CONTRACT_OPERATION_UNSOURCED")
        method = method.lower()
        if method in paths.setdefault(path, {}):
            deny("T2_CONTRACT_OPERATION_DUPLICATE")
        body = {
            "operationId": re.sub("[^a-zA-Z0-9]+", "_", method + "_" + module),
            "x-requirement-ids": ids,
            "responses": {"200": {"description": "Response"},
                          "default": {"description": "Declared errors",
                                      "x-error-codes": errors}},
        }
        if fields and method in ("post", "put", "patch"):
            schema = {"type": "object", "properties": fields}
            if required:
                schema["required"] = sorted(required)
            body["requestBody"] = {"required": True,
                "content": {"application/json": {"schema": schema}}}
        paths[path][method] = body
    if not paths:
        deny("T2_CONTRACT_OPERATION_UNSOURCED")
    return {
        "openapi": "3.1.0",
        "info": {"title": module, "version": "1.0.0"},
        "paths": dict(sorted(paths.items())),
    }


def render(module, package, atoms):
    return yaml.safe_dump(generate(module, package, atoms),
                          allow_unicode=True, sort_keys=False)
