from __future__ import annotations

from pathlib import Path
from typing import Any


def _requirement_is_exactly_pinned(requirement: str) -> bool:
    value = requirement.strip()
    if not value or value.startswith(("-", "http://", "https://", "git+")):
        return False
    return "==" in value and not any(marker in value for marker in (">=", "<=", "~=", "!=", ">", "<"))


def verify_dependencies(root: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    manifests = inventory.get("manifests") or {}
    lockfiles = set(inventory.get("lockfiles") or [])

    package = manifests.get("package.json")
    if package:
        npm_deps = (package.get("dependencies") or []) + (package.get("devDependencies") or [])
        package_manager = package.get("packageManager")
        js_locks = lockfiles & {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"}
        if npm_deps and not js_locks:
            findings.append({"code": "JS_DEPENDENCIES_WITHOUT_LOCKFILE", "severity": "BLOCKED"})
        if len(js_locks) > 1 and not package_manager:
            findings.append({"code": "AMBIGUOUS_JS_PACKAGE_MANAGER", "severity": "BLOCKED", "lockfiles": sorted(js_locks)})

    pyproject = manifests.get("pyproject.toml")
    if pyproject:
        py_deps = pyproject.get("dependencies") or []
        py_locks = lockfiles & {"uv.lock", "poetry.lock", "Pipfile.lock"}
        requirements_manifests = {name for name in manifests if name.startswith("requirements") and name.endswith(".txt")}
        if py_deps and not py_locks and not requirements_manifests:
            findings.append({"code": "PYTHON_DEPENDENCIES_WITHOUT_CANONICAL_RESOLUTION", "severity": "BLOCKED"})

    for manifest_name, manifest in manifests.items():
        if not (manifest_name.startswith("requirements") and manifest_name.endswith(".txt")):
            continue
        dependencies = manifest.get("dependencies") or []
        unpinned = sorted(dep for dep in dependencies if not _requirement_is_exactly_pinned(dep))
        if unpinned:
            findings.append({
                "code": "PYTHON_REQUIREMENTS_NOT_EXACTLY_PINNED",
                "severity": "BLOCKED",
                "manifest": manifest_name,
                "dependencies": unpinned,
            })

    status = "BLOCKED" if findings else "PASS"
    return {
        "status": status,
        "findings": findings,
        "verified_manifests": sorted(manifests.keys()),
        "lockfiles": sorted(lockfiles),
        "policy": "EXISTENCE_AND_RESOLUTION_ONLY_NO_EXTERNAL_INSTALL",
    }
