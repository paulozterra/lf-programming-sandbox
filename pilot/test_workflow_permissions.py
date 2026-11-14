#!/usr/bin/env python3
"""T9.1: statically enforce effective GitHub token permissions for every workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
MAP = Path(__file__).with_name("workflow_permission_map_v1.json")


def permissions(value):
    if value == "write-all":
        return {"*": "write"}
    if value in ("read-all", None):
        return {}
    return value if isinstance(value, dict) else {}


def effective(doc, job):
    top = permissions(doc.get("permissions"))
    if "permissions" in job:
        return permissions(job["permissions"])  # job-level overrides, not merges
    return top


def check_workflow(path: Path, mapping: dict) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = []
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        return [f"WORKFLOW_YAML_INVALIDO:{path.name}"]
    for job in doc["jobs"].values():
        if not isinstance(job, dict):
            continue
        allowed = effective(doc, job)
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            continue
        # Never count mentions in comments, descriptions or job names as executions.
        scripts = "\n".join(str(s.get("run", "")) for s in steps if isinstance(s, dict))
        scripts = "\n".join(line for line in scripts.splitlines()
                            if not line.lstrip().startswith("#"))
        for rule in mapping["rules"]:
            perm = rule["permission"]
            if any(re.search(pattern, scripts, flags=re.IGNORECASE)
                   for pattern in rule["patterns"]):
                if allowed.get("*") != "write" and allowed.get(perm) != "write":
                    errors.append(f"WORKFLOW_PERMISO_FALTANTE:{path.name}:{perm}")
    return sorted(set(errors))


def scan(root: Path, mapping: dict) -> list[str]:
    return sorted(set(error for path in (root / ".github/workflows").glob("*.yml")
                      for error in check_workflow(path, mapping)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--mapping", type=Path, default=MAP)
    args = parser.parse_args()
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    if mapping.get("schema_version") != "LF_WORKFLOW_PERMISSION_MAP_V1":
        raise SystemExit("WORKFLOW_PERMISSION_MAP_INVALID")
    problems = scan(args.root, mapping)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("WORKFLOW_PERMISSION_POLICY_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
