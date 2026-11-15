#!/usr/bin/env python3
"""T13: statically check every generated Python acceptance script's direct imports."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "pilot/worker_v08/python_runtime_requirements.txt"
# Distribution names differ from their importable module names.
DISTRIBUTIONS = {
    "pyyaml": "yaml",
    "openapi-spec-validator": "openapi_spec_validator",
}
AREAS = ("CONTRATO", "BACKEND", "FRONTEND", "INFRA", "DATA")
PYTHON_COMMAND = "lf-python"


def pinned_modules(requirements=REQUIREMENTS):
    modules = set()
    for line in Path(requirements).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;]+)", line)
        if not match:
            raise ValueError("WORKER_REQUIREMENTS_UNPINNED")
        name = match.group(1).lower().replace("_", "-")
        modules.add(DISTRIBUTIONS.get(name, name.replace("-", "_")))
    return modules


def check_commands(commands, root=ROOT, requirements=REQUIREMENTS):
    pinned = pinned_modules(requirements)
    for command in commands:
        argv = command["argv"]
        if not argv or argv[0] not in (PYTHON_COMMAND, "python3"):
            continue
        if len(argv) < 2 or not argv[1].endswith(".py"):
            raise ValueError("WORKER_PYTHON_COMMAND_INVALID")
        script = argv[1]
        path = Path(root) / script
        if path.is_symlink() or not path.is_file():
            raise ValueError("WORKER_PYTHON_SCRIPT_INVALID:" + script)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=script)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.partition(".")[0])
        for name in sorted(imports):
            if name in sys.stdlib_module_names or name == "__future__":
                continue
            if (Path(root, name).exists() or Path(root, name + ".py").exists()
                    or (path.parent / (name + ".py")).is_file()
                    or (path.parent / name).is_dir()):
                continue
            if name not in pinned:
                raise ValueError(f"WORKER_DEPENDENCIA_FALTANTE:{script}:{name}")


def all_generated_commands():
    sys.path.insert(0, str(ROOT / 'pilot/orchestrator'))
    from generate_chain import acceptance
    for area in AREAS:
        paths = (["contracts/example.openapi.yaml"] if area == "CONTRATO"
                 else ["apps/time-service/src/main/resources/db/migration/V1__example.sql"]
                 if area == "DATA" else ["apps/time-service/pom.xml"]
                 if area == "INFRA" else ["frontend/src/app/page.tsx"])
        yield area, acceptance(
            area, paths, run="example", module="example",
            skeleton_path="pilot/runs/example/templates/example.skeleton.json",
            has_contract=area in ("BACKEND", "FRONTEND"),
            infra_dependencies=[])


def verify(root=ROOT, requirements=REQUIREMENTS):
    for _, commands in all_generated_commands():
        check_commands(commands, root=root, requirements=requirements)


if __name__ == "__main__":
    try:
        verify()
    except (ValueError, SyntaxError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print("T13_WORKER_PYTHON_DEPENDENCIES_PASS")
