#!/usr/bin/env python3
"""T3 INFRA admission: exact allowlist dependencies and environment-only DB config."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import json
import re
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pilot.orchestrator.infra_lot import DependencyBlocked, deny, installed, policy


def check_infra(root):
    root = Path(root)
    config = policy()
    observed = installed(root, config)
    for target, spec in config["targets"].items():
        for item in spec["dependencies"]:
            if item["id"] not in config["requirements_by_area"]["DATA"]:
                continue
            key = ((target, item["group_id"], item["artifact_id"])
                   if target == "maven" else (target, item["name"]))
            if observed.get(key) != item["version"]:
                deny("T3_DEPENDENCY_MISSING_OR_UNPINNED:" + item["id"])
    db = config["database"]
    if len(db["config_files"]) != 3:
        deny("T3_CONFIG_POLICY_INVALID")
    props_path = root / db["config_files"][1]
    env_path = root / db["config_files"][2]
    if any(p.is_symlink() or not p.is_file() for p in (props_path, env_path)):
        deny("T3_CONFIG_MISSING")
    props = props_path.read_text(encoding="utf-8")
    example = env_path.read_text(encoding="utf-8")
    assignments = {}
    for line in props.splitlines():
        value = line.strip()
        if not value or value.startswith(("#","!")):
            continue
        if "=" not in value:
            deny("T3_PROPERTIES_INVALID")
        key, raw = value.split("=",1)
        if key in assignments:
            deny("T3_PROPERTIES_DUPLICATE")
        assignments[key] = raw.strip()
    for key, value in db["properties"].items():
        if assignments.get(key) != value:
            deny("T3_DATABASE_CONFIG_INVALID:" + key)
    for key in db["env_vars"]:
        match = re.search(r"(?m)^" + re.escape(key) + r"=(.*)$", example)
        if not match or match.group(1).strip():
            deny("T3_ENV_EXAMPLE_SECRET_OR_MISSING:" + key)
    if not db["migration_directory"].startswith(
            "apps/time-service/src/main/resources/db/migration/"):
        deny("T3_MIGRATION_LOCATION_INVALID")
    return True


def check_data(root, paths):
    root = Path(root)
    target = policy()["database"]["migration_directory"]
    if not paths:
        deny("T3_DATA_MIGRATIONS_MISSING")
    for name in paths:
        if not (isinstance(name,str) and name.startswith(target)
                and re.fullmatch(r"V[0-9]+__[a-z][a-z0-9_]*[.]sql",
                                 name.removeprefix(target))):
            deny("T3_DATA_MIGRATION_PATH_INVALID")
        p = root / name
        if p.is_symlink() or not p.is_file():
            deny("T3_DATA_MIGRATION_FILE_MISSING")
    return True


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--check-infra",action="store_true")
    p.add_argument("--check-data",nargs="*")
    args=p.parse_args()
    try:
        if args.check_infra:
            check_infra(args.root)
        if args.check_data is not None:
            check_data(args.root,args.check_data)
    except (DependencyBlocked, OSError,ValueError) as exc:
        print("BLOCKED:"+str(exc))
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
