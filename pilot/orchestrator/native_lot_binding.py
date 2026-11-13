#!/usr/bin/env python3
"""CP3.4: strict adapter between PG-05 selector and pinned native profiles.

Never rewrite selector evidence or manufacture PG-07 authority. Historical
CP3.3 fixtures remain immutable; paths are validated in the actual repo.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

# Explicit aliases; deliberately NO suffix-stripping or fuzzy matching.
SELECTOR_BINDINGS = {
    "PERFIL-PROG-BACKEND-SPRING-EXP": ("BACKEND", "PERFIL-PROG-BACKEND-EXP", "prog_backend_exp"),
    "PERFIL-PROG-FRONTEND-EXP": ("FRONTEND", "PERFIL-PROG-FRONTEND-EXP", "prog_frontend_exp"),
    "PERFIL-PROG-DATA-EXP": ("DATA", "PERFIL-PROG-DATA-EXP", "prog_data_exp"),
}
REAL_ROOTS = {
    "BACKEND": ("apps/time-service/src/main/java/", "backend/src/main/java/"),
    "FRONTEND": ("apps/web/", "frontend/"),
    "DATA": ("db/", "supabase/migrations/"),
    "CONTRATO": ("contracts/",),
}
FAKE_PREFIXES = ("src/main/java/com/lf/", "web/src/app/")


class NativeLotBlocked(ValueError):
    """Fail-closed reason visible to the owner."""


def map_profile(profile_code: str, declared_area: str) -> dict[str, str]:
    binding = SELECTOR_BINDINGS.get(profile_code)
    if binding is None:
        raise NativeLotBlocked("CP34_PROFILE_UNKNOWN")
    area, native_code, pinned_slug = binding
    if area != declared_area and not (declared_area == "CONTRATO" and area == "BACKEND"):
        raise NativeLotBlocked("CP34_PROFILE_AREA_MISMATCH")
    return {"selector_code": profile_code, "area": declared_area,
            "native_profile_code": native_code, "pinned_profile_slug": pinned_slug}


def real_write_paths(root: Path, area: str, paths: list[str]) -> list[str]:
    if area not in REAL_ROOTS or not isinstance(paths, list) or not paths:
        raise NativeLotBlocked("CP34_WRITE_SCOPE_INVALID")
    result = []
    for path in paths:
        if (not isinstance(path, str) or not path or path.startswith("/")
                or "\\" in path or str(PurePosixPath(path)) != path
                or any(part in (".", "..") for part in PurePosixPath(path).parts)
                or path.startswith(FAKE_PREFIXES)
                or not path.startswith(REAL_ROOTS[area])
                or (not path.endswith(".openapi.yaml") if area == "CONTRATO"
                    else Path(path).suffix not in {".java", ".ts", ".tsx", ".sql"})):
            raise NativeLotBlocked("CP34_FAKE_OR_UNSAFE_PATH")
        target = root / path
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            raise NativeLotBlocked("CP34_UNSAFE_PATH")
        # A new source file is legitimate, but never invent an absent project.
        project_root = path.split("/", 2)
        if path.startswith("contracts/"):
            base = root / "contracts"
        elif path.startswith("apps/time-service/"):
            base = root / "apps/time-service"
        elif path.startswith("apps/web/"):
            base = root / "apps/web"
        elif path.startswith("backend/"):
            base = root / "backend"
        elif path.startswith("frontend/"):
            base = root / "frontend"
        elif path.startswith("supabase/migrations/"):
            base = root / "supabase/migrations"
        else:
            base = root / "db"
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
