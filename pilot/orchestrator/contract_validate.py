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


def _examples(obj, parents=()):
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ("example", "examples", "default") and any(
                    any(fragment in x.casefold() for fragment in ("password","passwd","secret","token","api_key"))
                    for x in parents):
                if val not in ("[REDACTED]", "<redacted>", "***", None):
                    deny("CONTRACT_SECRET_EXAMPLE")
            if key in ("example", "examples") and isinstance(val, str):
                if "Bearer " in val or val.startswith("sk-"):
                    deny("CONTRACT_SECRET_EXAMPLE")
            _examples(val, parents + (str(key),))
    if isinstance(obj, list):
        for val in obj:
            _examples(val, parents)


def validate(path, package, module):
    spec = load(path)
    atoms = package.get("atoms", [])
    required = {r for a in atoms if a.get("functional_module") == module
                and a.get("area") in ("BACKEND","FRONTEND")
                for r in a.get("requirement_ids", [])}
    errors = package.get("api_contract_source", {}).get("errors")
    if not required:
        deny("CONTRACT_REQUIREMENTS_UNSOURCED")
    if not isinstance(errors, list) or any(not isinstance(e, dict) for e in errors):
        deny("CONTRACT_ERRORS_UNSOURCED")
    wanted_errors = {e["error_code"] for e in errors if e.get("status") in ("VIGENTE","ACTIVE")
                     and isinstance(e.get("error_code"), str)}
    seen, seen_errors = set(), set()
    for _, _, op in operations(spec):
        seen.update(op["x-requirement-ids"])
        for response in op["responses"].values():
            if not isinstance(response, dict) or not isinstance(response.get("x-error-codes", []), list):
                deny("CONTRACT_RESPONSE_INVALID")
            seen_errors.update(response.get("x-error-codes", []))
    if required - seen:
        deny("CONTRACT_REQ_COVERAGE_MISSING:" + ",".join(sorted(required - seen)))
    if wanted_errors - seen_errors:
        deny("CONTRACT_ERROR_COVERAGE_MISSING:" + ",".join(sorted(wanted_errors - seen_errors)))
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
    p.add_argument("--package", type=Path)
    p.add_argument("--module")
    p.add_argument("--compare-live")
    p.add_argument("--check-frontend",type=Path)
    p.add_argument("--check-client",type=Path)
    a=p.parse_args()
    try:
        if a.contract and a.package and a.module:
            validate(a.contract,json.loads(a.package.read_text()),a.module)
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
