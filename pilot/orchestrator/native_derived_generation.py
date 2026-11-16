"""T25: deterministic, trusted integration-owned products derived from contracts.

The Worker may only edit its registered lot. The trusted CP3.5 integration
regenerates and stages generated TypeScript from every OpenAPI contract, with
no authority to modify any other source or build infrastructure.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

from native_write_scope import AREA_ROOTS

GENERATOR = "npm run gen:api"
GENERATED_ROOT = "frontend/src/lib/api/generated/"
SOURCE_ROOT = AREA_ROOTS["CONTRATO"][0]
NAME = re.compile(r"frontend/src/lib/api/generated/(?:index|[a-z][a-z0-9-]*)\.ts\Z")


class DerivedGenerationBlocked(ValueError):
    pass


def generated_output(path: str) -> bool:
    return bool(NAME.fullmatch(path))


def needs_contract_derivatives(paths: object) -> bool:
    return isinstance(paths, (set, list, tuple)) and any(
        isinstance(path, str) and path.startswith(SOURCE_ROOT)
        and path.endswith(".openapi.yaml") for path in paths)


def generate(root: Path, worker_paths: set[str], command) -> dict[str, object]:
    """Run the pinned official generator, stage only approved mechanical files.

    Never import or execute sources from a constructor proposal branch.
    Caller owns the exact Git checkout and has already validated its native
    patch against the registered task scope.
    """
    if not needs_contract_derivatives(worker_paths):
        return {"generator": None, "paths": []}
    if not (root / "frontend/scripts/gen-api.mjs").is_file():
        raise DerivedGenerationBlocked("INTEGRATION_DERIVED_GENERATION_FAILED:gen:api")
    try:
        command(["npm", "run", "gen:api"], cwd=root / "frontend")
        raw = command(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root)
        # The staged native patch is already in the index. Check *new*
        # unstaged or untracked paths, including deletions and renames.
        if not isinstance(raw, bytes):
            raise ValueError("STATUS_UNTRUSTED")
        entries = raw.decode("utf-8").split("\0")
        unstaged: set[str] = set()
        for line in entries:
            if not line:
                continue
            if len(line) < 4 or line[2] != " ":
                raise ValueError("STATUS_UNTRUSTED")
            status, path = line[:2], line[3:]
            if status[1] != " " or status == "??":
                if not generated_output(path):
                    raise ValueError("DERIVED_WRITE_OUT_OF_SCOPE:" + path)
                if status[1] not in (" ", "M", "D", "?"):
                    raise ValueError("DERIVED_RENAME_OUT_OF_SCOPE")
                unstaged.add(path)
        command(["git", "add", "-A", "--", GENERATED_ROOT], cwd=root)
        # Only allow files already present in the worker's staged set or
        # newly staged generated TypeScript. No generated file is attributed
        # to the Worker itself.
        changes = command(["git", "diff", "--cached", "--name-only", "-z"],
                          cwd=root).decode("utf-8").split("\0")
        extras = sorted(set(filter(None, changes)) - set(worker_paths))
        if any(not generated_output(path) for path in extras):
            raise ValueError("DERIVED_STAGED_OUT_OF_SCOPE")
        return {"generator": GENERATOR, "paths": extras}
    except (ValueError, OSError, UnicodeError, subprocess.CalledProcessError,
            DerivedGenerationBlocked) as exc:
        raise DerivedGenerationBlocked(
            "INTEGRATION_DERIVED_GENERATION_FAILED:gen:api") from exc
