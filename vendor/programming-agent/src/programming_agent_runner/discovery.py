from __future__ import annotations

import ast
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from .hashutil import SKIP_SNAPSHOT_DIRS, is_transient_directory_name

SKIP_DIRS = SKIP_SNAPSHOT_DIRS | {"node_modules", ".next", ".cache"}
CONFIG_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
    "Makefile", "Taskfile.yml", "Taskfile.yaml", ".env.example", ".env.sample",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "requirement_assertions.json",
}
MIGRATION_DIR_NAMES = {"migrations", "migration", "alembic", "supabase"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs"}


def iter_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs if d not in SKIP_DIRS and not is_transient_directory_name(d)
        )
        current_path = Path(current)
        for name in sorted(files):
            yield current_path / name


def relative_files(root: Path) -> list[str]:
    return [str(path.relative_to(root)).replace(os.sep, "/") for path in iter_files(root)]


def _requirements_manifest(path: Path) -> dict[str, Any]:
    deps = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return {"dependencies": deps}


def dependency_inventory(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"manifests": {}, "lockfiles": []}
    package_json = root / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
        result["manifests"]["package.json"] = {
            "dependencies": sorted((data.get("dependencies") or {}).keys()),
            "devDependencies": sorted((data.get("devDependencies") or {}).keys()),
            "packageManager": data.get("packageManager"),
        }
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project") or {}
        result["manifests"]["pyproject.toml"] = {
            "dependencies": sorted(project.get("dependencies") or []),
            "optional_dependencies": sorted((project.get("optional-dependencies") or {}).keys()),
            "requires_python": project.get("requires-python"),
        }
    for req in sorted(root.glob("requirements*.txt")):
        if req.is_file():
            result["manifests"][req.name] = _requirements_manifest(req)
    for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "uv.lock", "poetry.lock", "Pipfile.lock"):
        if (root / name).exists():
            result["lockfiles"].append(name)
    return result


def configuration_inventory(root: Path) -> dict[str, Any]:
    files = relative_files(root)
    configs = [p for p in files if Path(p).name in CONFIG_NAMES or p.startswith(".github/workflows/")]
    env_refs: set[str] = set()
    pattern = re.compile(r"(?:os\.environ\[['\"]|os\.getenv\(['\"]|process\.env\.)([A-Z][A-Z0-9_]*)")
    for rel in files:
        if not rel.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        env_refs.update(pattern.findall(text))
    return {"files": configs, "environment_variables_referenced": sorted(env_refs)}


def architecture_inventory(root: Path) -> dict[str, Any]:
    files = relative_files(root)
    top_dirs = sorted({p.split("/", 1)[0] for p in files if "/" in p})
    markers = [p for p in files if Path(p).name.lower() in {"architecture.md", "adr.md", "contributing.md"} or "/adr/" in f"/{p.lower()}/"]
    return {"top_level_directories": top_dirs, "architecture_markers": markers}


def test_inventory(root: Path) -> dict[str, Any]:
    files = relative_files(root)
    tests = [p for p in files if any(part in TEST_DIR_NAMES for part in Path(p).parts) or Path(p).name.startswith("test_") or Path(p).name.endswith((".test.js", ".test.ts", ".spec.js", ".spec.ts"))]
    return {"files": tests, "count": len(tests)}


def migration_inventory(root: Path) -> dict[str, Any]:
    files = relative_files(root)
    migrations = [p for p in files if any(part.lower() in MIGRATION_DIR_NAMES for part in Path(p).parts)]
    return {"files": migrations, "count": len(migrations)}


def public_api_inventory(root: Path) -> dict[str, Any]:
    exported: list[str] = []
    for path in iter_files(root):
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(root)).replace(os.sep, "/")
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                exported.append(f"{rel}:{node.name}")
    return {"python_symbols": sorted(exported)}
