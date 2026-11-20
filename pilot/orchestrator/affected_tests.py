#!/usr/bin/env python3
"""T26: existing project tests affected by a lot that changes existing behaviour.

A lot that EXTENDs an existing source (reuse_assessment decision EXTEND)
changes the behaviour of the endpoints listed in that obligation. Project
tests that exercise those endpoints, or the paired test of that class, must
be adapted in the same lot; otherwise the lot is impossible to pass (the
acceptance build runs them). Such tests become part of the lot's planned
write scope ("pruebas afectadas"). Every other test stays protected.

Examiner-owned visible checks (``*/visible-tests/*``) are never affected:
they are not project tests and remain protected.
"""
from __future__ import annotations
# Resolve the trusted repository package when executed as a script.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import json
import re
from pathlib import Path

# Project test roots per writable product root (same roots as T24 scope).
def project_test_roots() -> tuple[str, ...]:
    """T54 3c: affected (updatable) test roots of the project's maven components."""
    from pilot.config import project_config as _project
    return _project.affected_test_roots("maven")


def project_test_globs() -> tuple[str, ...]:
    return tuple(root + "/**" for root in project_test_roots())
TEST_SUFFIXES = (".java",)


class AffectedTestsBlocked(ValueError):
    pass


def _blocked() -> None:
    raise AffectedTestsBlocked("LOTE_PRUEBAS_AFECTADAS_INDETERMINADAS")


def project_test_files(root: Path) -> list[Path]:
    found = []
    for name in project_test_roots():
        directory = Path(root) / name
        if directory.is_symlink():
            _blocked()
        if not directory.is_dir():
            continue
        for file in sorted(directory.rglob("*")):
            if file.is_symlink():
                _blocked()
            if file.is_file() and file.suffix in TEST_SUFFIXES:
                found.append(file)
    return found


def is_project_test(path: str) -> bool:
    return any(path.startswith(root + "/") for root in project_test_roots())


def _references_route(text: str, route: str) -> bool:
    """Exact route reference; a longer route sharing the prefix does not count."""
    return re.search(re.escape(route) + r"(?![A-Za-z0-9_/{-])", text) is not None


def affected_behavior_tests(root: Path, source_path: str, endpoints: list) -> set[str]:
    """Project tests that exercise endpoints whose behaviour changes, or the paired test."""
    if not endpoints:
        return set()
    if (not isinstance(endpoints, list)
            or not all(isinstance(ep, str) and " " in ep.strip() for ep in endpoints)):
        _blocked()
    routes = {ep.strip().split(" ", 1)[1].strip() for ep in endpoints}
    if not all(route.startswith("/") for route in routes):
        _blocked()
    stem = Path(source_path).stem
    matched = set()
    for file in project_test_files(root):
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            _blocked()
        paired = file.stem in (stem + "Test", stem + "Tests", stem + "IT")
        if paired or any(_references_route(text, route) for route in routes):
            matched.add(file.relative_to(root).as_posix())
    return matched


def affected_for_lot(root: Path, lot: dict, reuse_rows: list, scope_by_requirement: dict) -> set[str]:
    """Affected tests for one lot from its own EXTEND obligations."""
    if not isinstance(reuse_rows, list):
        _blocked()
    paths = set(lot.get("write_paths", []))
    scopes = {scope_by_requirement[r] for r in lot.get("requirement_ids", [])
              if r in scope_by_requirement}
    result: set[str] = set()
    for row in reuse_rows:
        if not isinstance(row, dict) or row.get("decision") != "EXTEND":
            continue
        if (row.get("requirement_id") not in lot.get("requirement_ids", [])
                and scope_by_requirement.get(row.get("requirement_id")) not in scopes):
            continue
        source = row.get("path")
        if not isinstance(source, str) or source not in paths:
            continue
        result |= affected_behavior_tests(root, source, row.get("reused_endpoints", []))
    return result


def load_reuse(root: Path, run: str) -> tuple[list, dict]:
    folder = storage_path("requests_root", root=Path(root)) / run
    report = folder / "reuse_assessment.json"
    if not report.exists():
        return [], {}
    if report.is_symlink():
        _blocked()
    rows = json.loads(report.read_text(encoding="utf-8")).get("obligations", [])
    package = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    scopes = {r["requirement_id"]: r["scope_id"] for r in package.get("requirements", [])}
    return rows, scopes


def with_affected_tests(root: Path, run: str, lots: list, *, only_ids=None) -> list:
    """Return lots whose write_paths include their affected project tests."""
    rows, scopes = load_reuse(root, run)
    result = []
    for lot in lots:
        if only_ids is not None and lot["id"] not in only_ids:
            result.append(lot)
            continue
        affected = affected_for_lot(root, lot, rows, scopes)
        if affected - set(lot["write_paths"]):
            lot = dict(lot, write_paths=sorted(set(lot["write_paths"]) | affected),
                       affected_tests=sorted(affected))
        result.append(lot)
    return result
