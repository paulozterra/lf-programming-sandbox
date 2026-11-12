#!/usr/bin/env python3
"""Offline, blocking GitHub Actions YAML syntax and jobs contract.

Walk every .github/workflows/*.yml file, not merely workflows GitHub could
register. GitHub cannot report a normal PR check for unparseable workflows.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml


def verify_workflows(root: Path) -> list[str]:
    directory = root / ".github" / "workflows"
    files = sorted(directory.glob("*.yml"))
    findings: list[str] = []
    if not directory.is_dir() or not files:
        return ["WORKFLOW_YAML_MISSING_DIRECTORY_OR_FILES"]
    for path in files:
        if path.is_symlink() or not path.is_file():
            findings.append(f"{path.name}: WORKFLOW_YAML_NOT_REGULAR")
            continue
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeError, OSError) as exc:
            findings.append(f"{path.name}: WORKFLOW_YAML_PARSE_ERROR: {exc}")
            continue
        if not isinstance(parsed, dict):
            findings.append(f"{path.name}: WORKFLOW_YAML_NOT_MAPPING")
        elif not isinstance(parsed.get("jobs"), dict) or not parsed["jobs"]:
            findings.append(f"{path.name}: WORKFLOW_YAML_JOBS_MISSING_OR_EMPTY")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    findings = verify_workflows(args.root)
    for line in findings:
        print(line, file=sys.stderr)
    if findings:
        return 1
    count = len(list((args.root / ".github" / "workflows").glob("*.yml")))
    print(f"WORKFLOW_YAML_POLICY_PASS files={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
