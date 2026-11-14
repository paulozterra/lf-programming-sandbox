#!/usr/bin/env python3
"""T9.3 enforce a single selector bootstrap recipe across ALL workflow jobs."""
from __future__ import annotations

from pathlib import Path
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
SHARED = "pilot/orchestrator/prepare_selector.sh"
SELECTOR = "pilot/orchestrator/selector_db.py"


def check_workflow(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        return [f"WORKFLOW_YAML_INVALIDO:{path.name}"]
    errors = []
    for job in doc["jobs"].values():
        if not isinstance(job, dict):
            continue
        scripts = [str(s.get("run", "")) for s in job.get("steps", [])
                   if isinstance(s, dict)]
        direct = any(re.search(r"(?:python3?|/python)\s+" + re.escape(SELECTOR)
                               + r"(?:\s|$)", code) for code in scripts)
        shared_steps = [i for i, code in enumerate(scripts)
                        if re.search(r"\bbash\s+" + re.escape(SHARED) + r"(?:\s|$)", code)]
        # No independent bootstraps, even if one shared invocation is also present.
        if direct or (any("selector_db.py" in code for code in scripts)
                      and not shared_steps):
            errors.append(f"WORKFLOW_ENTORNO_SELECTOR_DUPLICADO:{path.name}")
        # If a job invokes the common recipe and then invokes the selector
        # separately, the earlier rule rejects that drift as well.
        if shared_steps and any("docker run" in code and "postgres:17" in code
                                for code in scripts):
            errors.append(f"WORKFLOW_ENTORNO_SELECTOR_DUPLICADO:{path.name}")
    return sorted(set(errors))


def scan(root: Path = ROOT) -> list[str]:
    return sorted({error for path in (root / ".github/workflows").glob("*.yml")
                   for error in check_workflow(path)})


if __name__ == "__main__":
    failures = scan()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        sys.exit(1)
    print("WORKFLOW_SHARED_SELECTOR_POLICY_PASS")
