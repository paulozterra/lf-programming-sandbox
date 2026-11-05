from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

CATEGORIES = ("build", "lint", "typecheck", "test", "negative_test")
MAKE_TARGET_BY_CATEGORY = {
    "build": "build",
    "lint": "lint",
    "typecheck": "typecheck",
    "test": "test",
    "negative_test": "test-negative",
}


@dataclass(frozen=True)
class DiscoveredCommand:
    category: str
    command: tuple[str, ...]
    source: str
    confidence: str = "EXPLICIT"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        return value


def _package_manager(root: Path, package_json: dict[str, Any]) -> str | None:
    declared = package_json.get("packageManager")
    if isinstance(declared, str) and "@" in declared:
        name = declared.split("@", 1)[0]
        if name in {"npm", "pnpm", "yarn", "bun"}:
            return name
    lock_map = {
        "package-lock.json": "npm",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lockb": "bun",
    }
    found = [manager for lock, manager in lock_map.items() if (root / lock).exists()]
    return found[0] if len(found) == 1 else None


def _script_command(manager: str, name: str) -> tuple[str, ...]:
    if manager == "yarn":
        return ("yarn", name)
    if manager == "bun":
        return ("bun", "run", name)
    return (manager, "run", name)


def discover_commands(root: Path) -> list[DiscoveredCommand]:
    commands: list[DiscoveredCommand] = []
    package_json = root / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
        scripts = data.get("scripts") or {}
        manager = _package_manager(root, data)
        if manager:
            package_names = {"negative_test": "test:negative", **{c: c for c in ("build", "lint", "typecheck", "test")}}
            for category, script_name in package_names.items():
                if script_name in scripts:
                    commands.append(DiscoveredCommand(category, _script_command(manager, script_name), "package.json"))

    makefile = root / "Makefile"
    if makefile.exists():
        targets = set()
        for line in makefile.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+):(?:\s|$)", line)
            if match and not match.group(1).startswith("."):
                targets.add(match.group(1))
        for category, target in MAKE_TARGET_BY_CATEGORY.items():
            if target in targets:
                commands.append(DiscoveredCommand(category, ("make", target), "Makefile"))

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        scripts = ((data.get("project") or {}).get("scripts") or {})
        for category in CATEGORIES:
            script_name = "test-negative" if category == "negative_test" else category
            if script_name in scripts:
                commands.append(DiscoveredCommand(category, ("python-project-script", script_name), "pyproject.toml"))

    unique: dict[tuple[str, tuple[str, ...]], DiscoveredCommand] = {}
    for command in commands:
        unique[(command.category, command.command)] = command
    return sorted(unique.values(), key=lambda c: (c.category, c.source, c.command))
