#!/usr/bin/env python3
"""Reject runner context inside job-level env in all GitHub Actions YAML.

No external parser dependency. Tracks indentation of the jobs/job/env mappings
and checks YAML expressions in env values, including multiline values.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RUNNER_EXPRESSION = re.compile(r"\$\{\{[^}]*\brunner\.", re.IGNORECASE)


def violations(text, filename="<memory>"):
    errors = []
    in_jobs = False
    job_indent = None
    env_indent = None
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        token = line.strip()
        if indent == 0:
            in_jobs = token == "jobs:"
            job_indent = None
            env_indent = None
            continue
        if not in_jobs:
            continue
        if indent == 2 and re.match(r"^[\w-]+:\s*(?:#.*)?$", token):
            job_indent = token.split(":", 1)[0]
            env_indent = None
            continue
        if job_indent is None:
            continue
        if indent == 4:
            env_indent = 4 if token == "env:" else None
            continue
        if env_indent is not None and indent > env_indent and RUNNER_EXPRESSION.search(line):
            errors.append(f"{filename}:{lineno}: JOB_ENV_RUNNER_CONTEXT_UNAVAILABLE")
    return errors


def main():
    files = sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))
    if not files:
        raise SystemExit("NO_WORKFLOWS_FOUND")
    failures = []
    for path in files:
        failures.extend(violations(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT))))
    for problem in failures:
        print(problem, file=sys.stderr)
    print(f"WORKFLOW_JOB_ENV_CHECK files={len(files)} violations={len(failures)}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
