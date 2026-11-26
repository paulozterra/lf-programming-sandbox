#!/usr/bin/env python3
"""CP3.4: strict adapter between PG-05 selector and pinned native profiles.

Never rewrite selector evidence or manufacture PG-07 authority. Historical
CP3.3 fixtures remain immutable; paths are validated in the actual repo.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config import project_config as _project  # noqa: E402
import json
import re

# Explicit aliases; deliberately NO suffix-stripping or fuzzy matching.
SELECTOR_BINDINGS = {
    "PERFIL-PROG-BACKEND-SPRING-EXP": ("BACKEND", "PERFIL-PROG-BACKEND-EXP", "prog_backend_exp"),
    "PERFIL-PROG-FRONTEND-EXP": ("FRONTEND", "PERFIL-PROG-FRONTEND-EXP", "prog_frontend_exp"),
    "PERFIL-PROG-DATA-EXP": ("DATA", "PERFIL-PROG-DATA-EXP", "prog_data_exp"),
}
# T54 phase 3b: real product roots per area, resolved on access.
REAL_ROOTS = _project.AreaTable(_project.area_project_roots)
FAKE_PREFIXES = ("src/main/java/com/lf/", "web/src/app/")


def _existing_affected_test(root: Path, area: str, path: str) -> bool:
    """T26.3: an existing project test planned into a BACKEND lot ("prueba afectada").

    Same classifier as the planner (affected_tests.is_project_test); only an
    already existing test file qualifies, never a new or invented one.
    """
    from affected_tests import is_project_test
    if area != "BACKEND" or not is_project_test(path):
        return False
    target = root / path
    return target.is_file() and not target.is_symlink()


def _infra_allowed_paths():
    from pilot.orchestrator import infra_lot
    p = infra_lot.policy()
    return set(p["database"]["config_files"]) | {
        item["manifest"] for item in p["targets"].values()
    } | {p["targets"]["npm"]["lockfile"]}


def _project_base(area: str, path: str) -> str:
    """Directory that must already exist for a new file at `path` (T54 3b).

    Precedence (generalizes the former fixed if-chain):
    1. the most specific (longest) configured component root containing the
       path — with nested components the inner project must exist;
    2. otherwise the longest matching project root of the area, cut before a
       conventional "/src/main/java" layout ("backend/src/main/java/" ->
       "backend"), as the old chain did for backend/ and apps/web/.
    For the sandbox this reproduces every branch of the old chain exactly.
    The caller still requires the directory to exist (never invents a project).
    """
    owners = [item["root"] for item in _project.components().values()
              if path.startswith(item["root"] + "/")]
    if owners:
        return max(owners, key=len)
    for prefix in sorted(REAL_ROOTS[area], key=len, reverse=True):
        if path.startswith(prefix):
            bare = prefix.rstrip("/")
            return bare.split("/src/main/java", 1)[0]
    raise NativeLotBlocked("CP34_PROJECT_ROOT_MISSING")


class NativeLotBlocked(ValueError):
    """Fail-closed reason visible to the owner."""


def map_profile(profile_code: str, declared_area: str) -> dict[str, str]:
    binding = SELECTOR_BINDINGS.get(profile_code)
    if binding is None:
        raise NativeLotBlocked("CP34_PROFILE_UNKNOWN")
    area, native_code, pinned_slug = binding
    if declared_area == "CONTRATO":
        rules = json.loads((Path(__file__).with_name("atomize_rules_v1.json")).read_text())
        t2 = rules.get("contract_lot", {})
        mappings = rules.get("profile_resolution", {}).get("area_to_profile", {})
        if (t2.get("schema_version") != "T2_CONTRACT_LOT_POLICY_V1"
                or t2.get("profile_area") != area
                or mappings.get("CONTRATO") != profile_code):
            raise NativeLotBlocked("CP34_CONTRACT_PROFILE_POLICY_INVALID")
    elif declared_area == "INFRA":
        rules = json.loads((Path(__file__).with_name("atomize_rules_v1.json")).read_text())
        policy = rules.get("infra_lot", {})
        mappings = rules.get("profile_resolution", {}).get("area_to_profile", {})
        if (area != "BACKEND" or policy.get("schema_version") != "T3_INFRA_POLICY_V1"
                or policy.get("profile_area") != area
                or mappings.get("INFRA") != profile_code):
            raise NativeLotBlocked("CP34_INFRA_PROFILE_POLICY_INVALID")
    elif area != declared_area:
        raise NativeLotBlocked("CP34_PROFILE_AREA_MISMATCH")
    return {"selector_code": profile_code, "area": area,
            "native_profile_code": native_code, "pinned_profile_slug": pinned_slug}


def _characterization_path(area: str, paths: list[str], lot: dict | None) -> str | None:
    """Only the committed T7 characterization lot may create its own suite."""
    if lot is None or lot.get("lot_kind") != "CHARACTERIZATION":
        return None
    lot_id = lot.get("id")
    if (area != "FRONTEND" or lot.get("area") != area
            or lot.get("producer_route") != "T7_CHARACTERIZATION_NOT_PG04_PG05"
            or not isinstance(lot_id, str)
            or not re.fullmatch(r"SOL-K[0-9a-f]{12}", lot_id)
            or lot.get("write_paths") != paths
            or lot.get("production_authority") is not False
            or lot.get("handoff_allowed") is not False):
        raise NativeLotBlocked("CP34_CHARACTERIZATION_SCOPE_INVALID")
    component = _project.area_component("FRONTEND", "npm")
    suite = component["root"] + "/visible-tests"
    expected = suite + "/" + lot_id.lower() + ".json"
    if suite not in component["test_roots"] or paths != [expected]:
        raise NativeLotBlocked("CP34_CHARACTERIZATION_SCOPE_INVALID")
    return expected


def real_write_paths(root: Path, area: str, paths: list[str], *,
                     lot: dict | None = None) -> list[str]:
    if area not in REAL_ROOTS or not isinstance(paths, list) or not paths:
        raise NativeLotBlocked("CP34_WRITE_SCOPE_INVALID")
    characterization = _characterization_path(area, paths, lot)
    result = []
    for path in paths:
        if (not isinstance(path, str) or not path or path.startswith("/")
                or "\\" in path or str(PurePosixPath(path)) != path
                or any(part in (".", "..") for part in PurePosixPath(path).parts)
                or path.startswith(FAKE_PREFIXES)
                or not (path.startswith(REAL_ROOTS[area])
                        or _existing_affected_test(root, area, path))
                or (area == "INFRA" and path not in _infra_allowed_paths())
                or Path(path).suffix not in ({".yaml"} if area == "CONTRATO"
                                             else {".xml", ".properties", ".example", ".json"} if area == "INFRA"
                                             else {".java", ".ts", ".tsx", ".sql", ".json"} if path == characterization
                                             else {".java", ".ts", ".tsx", ".sql"})):
            raise NativeLotBlocked("CP34_FAKE_OR_UNSAFE_PATH")
        target = root / path
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            raise NativeLotBlocked("CP34_UNSAFE_PATH")
        # A new source file is legitimate, but never invent an absent project.
        project_root = path.split("/", 2)
        base = root / _project_base(area, path)
        if not base.is_dir() or base.is_symlink():
            raise NativeLotBlocked("CP34_PROJECT_ROOT_MISSING")
        result.append(path)
    if len(set(result)) != len(result) or len(result) > 6:
        raise NativeLotBlocked("CP34_WRITE_SCOPE_INVALID")
    return sorted(result)


def next_ready(lots: dict, completed: set[str]) -> list[dict]:
    """Schedule only genuinely dependency-free lots; never imply a merge."""
    if (lots.get("schema_version") != "CP33_LOTS_CANDIDATE_V1"
            or lots.get("production_authority") is not False
            or lots.get("handoff_allowed") is not False
            or lots.get("worker_invoked") is not False):
        raise NativeLotBlocked("CP34_LOTS_NOT_CANDIDATE")
    by_id = {lot["id"]: lot for lot in lots["lots"]}
    if len(by_id) != len(lots["lots"]) or not completed.issubset(by_id):
        raise NativeLotBlocked("CP34_DAG_INVALID")
    for lot in lots["lots"]:
        if lot["area"] not in REAL_ROOTS or any(d not in by_id for d in lot["depends_on"]):
            raise NativeLotBlocked("CP34_DAG_INVALID")
    # completed means explicitly handed off by a verified, merged predecessor,
    # never merely registered or proposed.
    return [lot for lot in lots["lots"] if lot["id"] not in completed
            and set(lot["depends_on"]).issubset(completed)]
