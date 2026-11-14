#!/usr/bin/env python3
"""T9.5 fail-closed static guard for exact-main CI before green-base stages."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "pilot/train_handoff_map_v1.json"
GATE = ROOT / "pilot/train_main_ci_gate_v1.json"


def check(root: Path = ROOT) -> list[str]:
    failures = []
    try:
        mapping = json.loads((root / "pilot/train_handoff_map_v1.json").read_text())
        policy = json.loads((root / "pilot/train_main_ci_gate_v1.json").read_text())
        handoff = (root / "pilot/train_handoff.py").read_text()
        train = (root / ".github/workflows/train-handoff.yml").read_text()
        chain = (root / ".github/workflows/chain-lots.yml").read_text()
        ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    except (OSError, ValueError, yaml.YAMLError):
        return ["WORKFLOW_BASE_SIN_CI:CONFIG"]
    trigger = ci.get("on", ci.get(True, {})) if isinstance(ci, dict) else {}
    if (not isinstance(trigger, dict) or "workflow_dispatch" not in trigger
            or policy.get("schema_version") != "LF_TRAIN_MAIN_CI_GATE_V1"
            or policy.get("workflow") != "ci.yml"
            or "ensure_main_ci(api, sha, required=item" not in handoff
            or '/actions/workflows/ci.yml/dispatches' not in handoff
            or 'main_ci_run(api, sha, config)' not in handoff
            or "pilot/train_handoff.py" not in train
            or "timeout-minutes: 25" not in train):
        failures.append("WORKFLOW_BASE_SIN_CI:TRAIN_HANDOFF")
    for route in mapping.get("routes", []):
        if route.get("workflow") != "chain-lots.yml":
            continue
        if (route.get("requires_green_base") is not True
                or route.get("correlate_request_slug") is not True
                or route.get("input_kind") not in ("train_run_id", "integration_pr")
                or "base_sha" not in chain or "request_slug" not in chain
                or "inputs.base_sha" not in chain):
            failures.append("WORKFLOW_BASE_SIN_CI:chain-lots.yml")
    # Detect ANY new production consumer of require_green_base (not merely
    # the existing chain_lots.py), and demand an explicit gate route.
    files = (root / "pilot").rglob("*.py")
    consumers = [path for path in files
                 if not path.name.startswith("test_")
                 and path.name != "t4_admission.py"
                 and re.search(r"\brequire_green_base\s*\(",
                               path.read_text(encoding="utf-8"))]
    for file in consumers:
        if file.relative_to(root).as_posix() != "pilot/orchestrator/chain_lots.py":
            failures.append("WORKFLOW_BASE_SIN_CI:" + file.relative_to(root).as_posix())
    if not consumers:
        failures.append("WORKFLOW_BASE_SIN_CI:NO_GUARDED_STAGE")
    return sorted(set(failures))


if __name__ == "__main__":
    failures = check()
    for problem in failures:
        print(problem, file=sys.stderr)
    if failures:
        sys.exit(1)
    print("WORKFLOW_BASE_MAIN_CI_POLICY_PASS")
