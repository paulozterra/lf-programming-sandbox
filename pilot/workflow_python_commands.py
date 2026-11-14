#!/usr/bin/env python3
"""T9.4: smoke imports of workflow Python commands in fresh interpreters.

Read YAML run steps, not source-code comments. Each import starts from the
repository root without an inherited PYTHONPATH; no CLI main is invoked.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
PYTHON = re.compile(
    r"(?<![\w.])python(?:3(?:\.\d+)?)?\s+"
    r"(?:-m\s+([a-zA-Z_][a-zA-Z0-9_.]*)|"
    r"((?:\.\./)*[a-zA-Z0-9_./-]+\.py))(?=\s|$|[;|&)])")
SCRIPT = re.compile(r"(?:(?:\.\./)*)?(pilot/|analysis/host/)")
LOCAL = ("pilot", "analysis", "standards")


def steps(path: Path) -> list[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        raise ValueError("WORKFLOW_YAML_INVALIDO")
    return [s for job in doc["jobs"].values() if isinstance(job, dict)
            for s in (job.get("steps") or []) if isinstance(s, dict)]


def commands(path: Path) -> list[tuple[str, str]]:
    found = []
    for step in steps(path):
        run = "\n".join(x for x in str(step.get("run") or "").splitlines()
                        if not x.lstrip().startswith("#"))
        for m in PYTHON.finditer(run):
            module, script = m.groups()
            if module:
                if module.split(".")[0] in LOCAL:
                    found.append(("module", module))
            elif script:
                found.append(("script", script))
    return sorted(set(found))


def target(root: Path, kind: str, value: str) -> Path:
    if kind == "module":
        relative = Path(value.replace(".", "/") + ".py")
    else:
        normalized = value
        while normalized.startswith("../"):
            normalized = normalized[3:]
        relative = Path(normalized)
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("PYTHON_ENTRYPOINT_NO_EXISTE")
    return resolved


def smoke(root: Path, kind: str, value: str, timeout: int = 20) -> tuple[bool, str]:
    try:
        script = target(root, kind, value)
    except ValueError as exc:
        return False, str(exc)
    if kind == "module":
        python = "import importlib; importlib.import_module(" + repr(value) + ")"
    else:
        python = (
            "import importlib.util,sys,pathlib;"
            "p=pathlib.Path(" + repr(str(script)) + ");"
            "sys.path.insert(0,str(p.parent));"
            "s=importlib.util.spec_from_file_location('_workflow_smoke_',p);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)")
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run([sys.executable, "-c", python], cwd=root,
                                env=env, text=True, capture_output=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "IMPORT_TIMEOUT"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()[-1400:]
    return True, ""


def scan(root: Path = ROOT, *, runner=smoke) -> list[str]:
    findings = []
    cached: dict[tuple[str, str], tuple[bool, str]] = {}
    for workflow in sorted((root / ".github/workflows").glob("*.yml")):
        for kind, value in commands(workflow):
            if kind == "script" and SCRIPT.match(value):
                findings.append(f"WORKFLOW_COMANDO_NO_EJECUTABLE:{workflow.name}:{value}")
                continue
            if (kind, value) not in cached:
                cached[kind, value] = runner(root, kind, value)
            passed, _ = cached[kind, value]
            if not passed:
                findings.append(f"WORKFLOW_COMANDO_NO_EJECUTABLE:{workflow.name}:{value}")
                print(f"WORKFLOW_COMMAND_DIAGNOSTIC:{workflow.name}:{value}:{cached[kind,value][1]}", file=sys.stderr)
    return sorted(set(findings))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    findings = scan(args.root.resolve())
    for f in findings:
        print(f, file=sys.stderr)
    if findings:
        return 1
    print("WORKFLOW_PYTHON_COMMANDS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
