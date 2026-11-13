"""T2 deterministic OpenAPI/contract acceptance. No business-specific heuristics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen

try:
    import yaml
except ImportError:
    yaml = None

HTTP = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
VERSION = re.compile(r"3\\.[01]\\.[0-9]+\Z")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")
SENSITIVE = re.compile(r"password|passwd|secret|api[_-]?key|access[_-]?token|authorization", re.I)


class ContractBlocked(ValueError):
    pass


def block(reason):
    raise ContractBlocked("T2_" + reason)


def load(path):
    if yaml is None:
        block("YAML_DEPENDENCY_MISSING")
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        block("CONTRACT_MISSING")
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError, yaml.YAMLError):
        block("OPENAPI_INVALID")
    if not isinstance(data, dict):
        block("OPENAPI_INVALID")
    return data


def operations(doc):
    if not isinstance(doc, dict) or not VERSION.fullmatch(str(doc.get("openapi", ""))):
        block("OPENAPI_VERSION_INVALID")
    if not isinstance(doc.get("info"), dict) or not doc["info"].get("title") or not doc["info"].get("version"):
        block("OPENAPI_INFO_INVALID")
    paths = doc.get("paths")
    if not isinstance(paths, dict) or not paths:
        block("OPENAPI_PATHS_MISSING")
    result = {}
    for path, value in paths.items():
        if not isinstance(path, str) or not path.startswith("/") or not isinstance(value, dict):
            block("OPENAPI_PATH_INVALID")
        for method, operation in value.items():
            if method not in HTTP:
                continue
            if (not isinstance(operation, dict)
                    or not isinstance(operation.get("responses"), dict)
                    or not operation["responses"]):
                block("OPENAPI_OPERATION_INVALID")
            tags = operation.get("x-requirement-ids")
            if (not isinstance(tags, list) or not tags
                    or any(not isinstance(tag, str) or not tag for tag in tags)
                    or len(tags) != len(set(tags))):
                block("REQUIREMENT_TRACE_MISSING")
            result[(path, method)] = operation
    if not result:
        block("OPENAPI_OPERATIONS_MISSING")
    return result


def _requirements(package, lots, contract_path):
    if not isinstance(package, dict) or not isinstance(lots, dict):
        block("PACKAGE_INVALID")
    rows = lots.get("lots")
    if not isinstance(rows, list):
        block("LOTS_INVALID")
    dependent = [lot for lot in rows if lot.get("area") in ("BACKEND", "FRONTEND")
                 and lot.get("contract_path") == contract_path]
    if {lot["area"] for lot in dependent} != {"BACKEND", "FRONTEND"}:
        block("CONTRACT_DEPENDENCIES_MISSING")
    known = {r["requirement_id"] for r in package.get("requirements", [])}
    required = set().union(*(set(lot.get("requirement_ids", [])) for lot in dependent))
    if not required or not required.issubset(known):
        block("CONTRACT_REQUIREMENTS_INVALID")
    return required


def declared_errors(package):
    errors = set()
    generic = False
    for row in package.get("applicable_rules", []):
        config = row.get("valor_config", {})
        if not isinstance(config, dict):
            block("RULE_CONFIG_INVALID")
        generic |= config.get("generic_error") is True
        for key in ("error_code", "error_codes", "http_error_status", "http_error_statuses"):
            value = config.get(key)
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            if any(not isinstance(v, (str, int)) or not str(v) for v in values):
                block("RULE_ERROR_DECLARATION_INVALID")
            errors.update(map(str, values))
    return generic, errors


def _scan_examples(node, *, parent=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "example" or key == "examples":
                # Examples of any secret-bearing payload are forbidden; no guessing
                # which sample credentials might be real.
                if SENSITIVE.search(parent) or (isinstance(value, dict) and
                     any(SENSITIVE.search(str(k)) for k in value)):
                    block("SECRET_EXAMPLE_FORBIDDEN")
                if isinstance(value, str) and re.search(r"(?:Bearer\s+\S+|sk-[A-Za-z0-9]{12,})", value):
                    block("SECRET_EXAMPLE_FORBIDDEN")
            _scan_examples(value, parent=str(key))
    elif isinstance(node, list):
        for part in node:
            _scan_examples(part, parent=parent)


def validate(doc, package, lots, contract_path):
    ops = operations(doc)
    required = _requirements(package, lots, contract_path)
    covered = {tag for op in ops.values() for tag in op["x-requirement-ids"]}
    if not required.issubset(covered):
        block("REQUIREMENT_COVERAGE_MISSING:" + ",".join(sorted(required - covered)))
    generic, errors = declared_errors(package)
    all_status = set()
    all_codes = set()
    for operation in ops.values():
        all_status.update(map(str, operation["responses"]))
        all_codes.update(map(str, operation.get("x-error-codes", [])))
    if generic and "default" not in all_status and not any(
            status.isdigit() and 400 <= int(status) <= 599 for status in all_status):
        block("GENERIC_ERROR_RESPONSE_MISSING")
    if not errors.issubset(all_status | all_codes):
        block("DECLARED_ERROR_MISSING:" + ",".join(sorted(errors - (all_status | all_codes))))
    _scan_examples(doc)
    return {"status": "PASS", "operations": len(ops),
            "requirements_covered": len(required), "production_authority": False}


def compare_runtime(contract, base_url):
    expected = operations(contract)
    url = base_url.rstrip("/") + "/v3/api-docs"
    try:
        with urlopen(url, timeout=8) as response:
            actual = json.load(response)
    except (OSError, ValueError):
        block("BACKEND_OPENAPI_UNAVAILABLE")
    actual_operations = operations_for_runtime(actual)
    missing = sorted(set(expected) - actual_operations)
    if missing:
        block("BACKEND_ROUTE_MISSING:" + repr(missing))
    return {"status": "PASS", "route_operations_verified": len(expected)}


def operations_for_runtime(doc):
    paths = doc.get("paths", {}) if isinstance(doc, dict) else {}
    if not isinstance(paths, dict):
        block("BACKEND_OPENAPI_INVALID")
    return {(path, method) for path, methods in paths.items()
            if isinstance(methods, dict) for method in methods if method in HTTP}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--lots", type=Path)
    parser.add_argument("--path", default=None)
    parser.add_argument("--api-url", default=None)
    args = parser.parse_args()
    try:
        if args.api_url:
            sources = ([args.contract] if args.contract else
                       sorted(Path("contracts").glob("*.openapi.yaml")))
            if not sources:
                block("NO_CONTRACTS_TO_COMPARE")
            for source in sources:
                compare_runtime(load(source), args.api_url)
            result = {"status": "PASS", "contracts": len(sources)}
        else:
            if not all((args.contract, args.package, args.lots)):
                block("VALIDATION_INPUT_MISSING")
            contract_path = args.path or args.contract.as_posix()
            result = validate(load(args.contract),
                              json.loads(args.package.read_text()),
                              json.loads(args.lots.read_text()), contract_path)
        print(json.dumps(result, sort_keys=True))
    except (ContractBlocked, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
