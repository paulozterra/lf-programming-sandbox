#!/usr/bin/env python3
"""T2: generic fail-closed OpenAPI/source/client checks."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen

import yaml

try:
    from openapi_spec_validator import validate_spec
except ImportError:
    validate_spec = None

METHODS = {"get","post","put","patch","delete","head","options"}


class ContractBlocked(ValueError):
    pass


def deny(code):
    raise ContractBlocked(code)


def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1000000:
        deny("CONTRACT_FILE_INVALID")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        deny("CONTRACT_YAML_INVALID")
    if (not isinstance(value, dict) or not str(value.get("openapi", "")).startswith("3.")
            or not isinstance(value.get("info"), dict)
            or not value["info"].get("title") or not value["info"].get("version")
            or not isinstance(value.get("paths"), dict) or not value["paths"]):
        deny("CONTRACT_OPENAPI_INVALID")
    if validate_spec is None:
        deny("CONTRACT_SPEC_VALIDATOR_UNAVAILABLE")
    try:
        validate_spec(value)
    except Exception as exc:
        deny("CONTRACT_OPENAPI_INVALID:" + type(exc).__name__)
    return value


def operations(spec):
    ops = []
    for route, methods in spec["paths"].items():
        if not isinstance(route, str) or not route.startswith("/") or not isinstance(methods, dict):
            deny("CONTRACT_PATH_INVALID")
        for method, op in methods.items():
            if method not in METHODS:
                continue
            if not isinstance(op, dict) or not isinstance(op.get("responses"), dict):
                deny("CONTRACT_OPERATION_INVALID")
            ids = op.get("x-requirement-ids")
            if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids):
                deny("CONTRACT_REQUIREMENT_EXTENSION_INVALID")
            ops.append((route, method, op))
    if not ops:
        deny("CONTRACT_OPERATIONS_MISSING")
    return ops


def _examples(obj, parents=(), in_example=False):
    """Block unredacted secret examples, including nested JSON payload values."""
    secret_terms = ("password", "passwd", "secret", "token", "api_key",
                    "apikey", "authorization", "private_key")
    placeholders = ("[REDACTED]", "<redacted>", "***", None)
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                deny("CONTRACT_EXAMPLE_INVALID")
            sensitive = any(term in key.casefold() for term in secret_terms)
            if in_example and sensitive and value not in placeholders:
                deny("CONTRACT_SECRET_EXAMPLE")
            next_example = in_example or key in ("example", "examples", "default")
            if next_example and any(
                    any(term in piece.casefold() for term in secret_terms)
                    for piece in parents) and key in ("example", "examples", "default"):
                if value not in placeholders:
                    deny("CONTRACT_SECRET_EXAMPLE")
            if next_example and isinstance(value, str):
                lowered = value.casefold()
                if "bearer " in lowered or value.startswith("sk-"):
                    deny("CONTRACT_SECRET_EXAMPLE")
            _examples(value, parents + (key,), next_example)
    elif isinstance(obj, list):
        for part in obj:
            _examples(part, parents, in_example)


def _field_names(operation):
    """Only schema properties and explicit parameters count as visible API fields."""
    names = set()
    def walk(value):
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                names.update(properties)
            for part in value.values():
                walk(part)
        elif isinstance(value, list):
            for part in value:
                walk(part)
    for parameter in operation.get("parameters", []):
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str):
            names.add(parameter["name"])
    walk(operation.get("requestBody", {}))
    walk(operation.get("responses", {}))
    return names


def _check_skeleton(skeleton, module):
    if (not isinstance(skeleton, dict)
            or skeleton.get("schema_version") != "T2_CONTRACT_SKELETON_V1"
            or skeleton.get("functional_module") != module
            or skeleton.get("production_authority") is not False
            or any(not isinstance(skeleton.get(k), list)
                   for k in ("fields", "errors", "requirement_ids", "rules"))):
        deny("CONTRACT_SKELETON_INVALID")
    field_codes = set()
    for field in skeleton["fields"]:
        if (not isinstance(field, dict) or not isinstance(field.get("field_code"), str)
                or not field["field_code"] or not isinstance(field.get("required"), bool)):
            deny("CONTRACT_SKELETON_FIELD_INVALID")
        field_codes.add(field["field_code"])
    error_codes = set()
    for error in skeleton["errors"]:
        if (not isinstance(error, dict) or not isinstance(error.get("error_code"), str)
                or not error["error_code"]):
            deny("CONTRACT_SKELETON_ERROR_INVALID")
        error_codes.add(error["error_code"])
    requirements = skeleton["requirement_ids"]
    if not requirements or not all(isinstance(r, str) and r.startswith("REQ-") for r in requirements):
        deny("CONTRACT_SKELETON_REQUIREMENTS_INVALID")
    if (len(field_codes) != len(skeleton["fields"])
            or len(error_codes) != len(skeleton["errors"])
            or len(set(requirements)) != len(requirements)):
        deny("CONTRACT_SKELETON_DUPLICATE")
    reused = skeleton.get("reused_endpoints", [])
    if (not isinstance(reused, list) or len(set(reused)) != len(reused)
            or any(not isinstance(op, str) or not re.fullmatch(
                r"(?:GET|POST|PUT|PATCH|DELETE) /[A-Za-z0-9_/{}/.-]*", op)
                for op in reused)):
        deny("REUTILIZACION_INDETERMINADA")
    extended = skeleton.get("extended_endpoints", [])
    if (not isinstance(extended, list) or len(set(extended)) != len(extended)
            or not set(extended).issubset(set(reused))):
        deny("REUTILIZACION_INDETERMINADA")
    return field_codes, error_codes, set(requirements)


def validate(path, skeleton, module):
    spec = load(path)
    fields, errors, required = _check_skeleton(skeleton, module)
    seen_requirements, seen_errors, seen_fields = set(), set(), set()
    reused = set(skeleton.get("reused_endpoints", []))
    extended = set(skeleton.get("extended_endpoints", []))
    seen_extensions = set()
    for route, method, operation in operations(spec):
        identity = method.upper() + " " + route
        if identity in reused and identity not in extended:
            deny("DUPLICA_COMPONENTE_EXISTENTE")
        if identity in extended:
            seen_extensions.add(identity)
        seen_requirements.update(operation["x-requirement-ids"])
        seen_fields.update(_field_names(operation))
        for response in operation["responses"].values():
            if not isinstance(response, dict):
                deny("CONTRACT_RESPONSE_INVALID")
            codes = response.get("x-error-codes", [])
            if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes):
                deny("CONTRACT_RESPONSE_ERROR_CODES_INVALID")
            seen_errors.update(codes)
    if extended - seen_extensions:
        deny("CONTRACT_DECLARED_ENDPOINT_MISSING:" + ",".join(sorted(extended - seen_extensions)))
    if required - seen_requirements:
        deny("CONTRACT_REQ_COVERAGE_MISSING:" + ",".join(sorted(required - seen_requirements)))
    if fields - seen_fields:
        deny("CONTRACT_FIELD_COVERAGE_MISSING:" + ",".join(sorted(fields - seen_fields)))
    if errors - seen_errors:
        deny("CONTRACT_ERROR_COVERAGE_MISSING:" + ",".join(sorted(errors - seen_errors)))
    _examples(spec)
    return True


def compare_live(path, live):
    if not isinstance(live, dict) or not isinstance(live.get("paths"), dict):
        deny("CONTRACT_LIVE_INVALID")
    for route, method, _ in operations(load(path)):
        if method not in live["paths"].get(route, {}):
            deny("CONTRACT_LIVE_OPERATION_MISSING:" + method.upper() + " " + route)
    return True


def check_frontend(root):
    root = Path(root)
    if not (root / "frontend/src").is_dir():
        deny("CONTRACT_FRONTEND_ROOT_MISSING")
    pattern = re.compile(r"(?<![a-zA-Z0-9_])(?:window[.])?fetch[ ]*[(]")
    for path in sorted((root / "frontend/src").rglob("*")):
        if path.is_file() and path.suffix in (".ts", ".tsx") and "generated" not in path.parts:
            if pattern.search(path.read_text(encoding="utf-8")):
                deny("CONTRACT_MANUAL_FETCH_FORBIDDEN:" + str(path.relative_to(root)))
    return True


def check_generated(root):
    root = Path(root)
    subprocess.run(["npm","--prefix","frontend","run","gen:api"], cwd=root, check=True)
    diff = subprocess.run(["git","diff","--exit-code","--","frontend/src/lib/api/generated"],cwd=root)
    untracked = subprocess.run(["git","ls-files","--others","--exclude-standard",
                                "--","frontend/src/lib/api/generated"],cwd=root,check=True,
                               capture_output=True,text=True)
    if diff.returncode != 0 or untracked.stdout.strip():
        deny("CONTRACT_GENERATED_CLIENT_STALE")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--contract", type=Path)
    p.add_argument("--skeleton", type=Path)
    p.add_argument("--module")
    p.add_argument("--compare-live")
    p.add_argument("--check-frontend",type=Path)
    p.add_argument("--check-client",type=Path)
    a=p.parse_args()
    try:
        if a.contract and a.skeleton and a.module:
            validate(a.contract,json.loads(a.skeleton.read_text()),a.module)
        if a.compare_live:
            with urlopen(a.compare_live,timeout=15) as stream:
                live=json.load(stream)
            for spec in sorted(Path("contracts").glob("*.openapi.yaml")):
                compare_live(spec,live)
        if a.check_frontend:
            check_frontend(a.check_frontend)
        if a.check_client:
            check_generated(a.check_client)
    except (ContractBlocked,ValueError,OSError,subprocess.CalledProcessError) as exc:
        print("BLOCKED:"+str(exc),file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
