#!/usr/bin/env python3
"""T9.2: reject bot-written-path workflows reachable only via push/PR events."""
from __future__ import annotations
import argparse
import fnmatch
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path(__file__).with_name("workflow_trigger_policy_v1.json")
NON_BOT_EVENTS = {"workflow_dispatch", "workflow_run", "repository_dispatch",
                  "schedule", "issues", "issue_comment"}


def events(doc: dict) -> dict:
    # PyYAML's YAML 1.1 loader converts the unquoted Actions key 'on' to True.
    value = doc.get("on", doc.get(True))
    if isinstance(value, str):
        return {value: None}
    if isinstance(value, list):
        return {str(item): None for item in value}
    return value if isinstance(value, dict) else {}


def unreachable(path: Path, policy: dict) -> list[str]:
    if policy.get("schema_version") != "LF_BOT_TRIGGER_POLICY_V1":
        raise ValueError("WORKFLOW_DISPARO_MAP_INVALID")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        return []
    triggers = events(doc)
    if not triggers or any(k in triggers for k in NON_BOT_EVENTS):
        return []
    if not set(triggers).issubset({"push", "pull_request", "pull_request_target"}):
        return []
    examples = policy["bot_written_examples"]
    for event in triggers.values():
        if not isinstance(event, dict) or not isinstance(event.get("paths"), list):
            continue
        if any(fnmatch.fnmatchcase(sample, pattern)
               for sample in examples for pattern in event["paths"]
               if isinstance(pattern, str) and not pattern.startswith("!")):
            return [f"WORKFLOW_DISPARO_INALCANZABLE:{path.name}"]
    return []


def scan(root: Path, policy: dict) -> list[str]:
    return sorted({error for path in (root / ".github/workflows").glob("*.yml")
                   for error in unreachable(path, policy)})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    a = p.parse_args()
    mapping = json.loads(POLICY.read_text(encoding="utf-8"))
    findings = scan(a.root, mapping)
    for item in findings:
        print(item, file=sys.stderr)
    if findings:
        return 1
    print("WORKFLOW_BOT_TRIGGER_POLICY_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
