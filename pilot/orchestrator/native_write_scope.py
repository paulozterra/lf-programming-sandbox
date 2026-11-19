"""T24 single trusted write-scope authority shared across LF areas.

No glob, traversal, symlink or control-plane writes may ever enter a task
write scope. A task must fit at least one complete area: paths from unrelated
areas cannot be joined to exploit an allowlist union.
"""
from __future__ import annotations

from pathlib import PurePosixPath
import sys as _project_sys
from pathlib import Path as _project_Path

_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config import project_config as _project  # noqa: E402

# T54 phase 3b: area write prefixes come from the project configuration,
# resolved on access (importing this module reads no configuration).
AREA_ROOTS = _project.AreaTable(_project.area_write_prefixes)
AREAS = _project.AREAS
PRODUCT_ROOTS = _project.ProductRoots()
FORBIDDEN_ROOTS = (".github/", "vendor/", "pilot/", "standards/")
MAX_PATHS = 6


class WriteScopeError(ValueError):
    pass


def _safe_path(path: object) -> bool:
    if not isinstance(path, str) or not path or len(path) > 512:
        return False
    if (path.startswith(("/", "\\")) or "\\" in path
            or "*" in path or "?" in path or "[" in path or "]" in path
            or path.startswith(FORBIDDEN_ROOTS)):
        return False
    parts = path.split("/")
    if (len(parts) < 2 or any(p in ("", ".", "..") for p in parts)
            or ":" in parts[0] or PurePosixPath(path).as_posix() != path):
        return False
    return True


def validate_write_paths(paths: object, *, area: str | None = None) -> set[str]:
    """Return exactly the given paths or fail closed; no inferred scope expansion."""
    if (not isinstance(paths, list) or not 1 <= len(paths) <= MAX_PATHS
            or any(not _safe_path(p) for p in paths)
            or len(set(paths)) != len(paths)):
        raise WriteScopeError("TASK_SCOPE_UNSAFE")
    candidates = (area,) if area is not None else tuple(sorted(AREAS))
    if area is not None and area not in AREAS:
        raise WriteScopeError("TASK_SCOPE_AREA_UNKNOWN")
    if not any(all(any(path.startswith(root) for root in AREA_ROOTS[a])
                   for path in paths) for a in candidates):
        raise WriteScopeError("TASK_SCOPE_UNSAFE")
    return set(paths)


def area_candidates(paths: object) -> frozenset[str]:
    """For diagnostics only; registration must never guess a unique area."""
    return frozenset(area for area in AREAS
                     if _accepts_area(paths, area))


def _accepts_area(paths: object, area: str) -> bool:
    try:
        validate_write_paths(paths, area=area)
        return True
    except WriteScopeError:
        return False
