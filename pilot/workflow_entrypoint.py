#!/usr/bin/env python3
"""T9.4 single entrypoint for workflow-launched repository scripts.

Preserves script-directory imports while also exposing repository packages.
Only literal pilot/ and analysis/host/ files inside this checkout are allowed.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ("pilot/", "analysis/host/")


def resolve(relative: str) -> Path:
    if not relative.startswith(ALLOWED) or not relative.endswith(".py"):
        raise ValueError("WORKFLOW_COMANDO_RUTA_INVALIDA")
    path = (ROOT / relative).resolve()
    if (not path.is_relative_to(ROOT.resolve()) or not path.is_file()
            or relative.startswith(("/", "../"))):
        raise ValueError("WORKFLOW_COMANDO_RUTA_INVALIDA")
    return path


def execute(relative: str, argv: list[str], *, smoke: bool = False) -> None:
    script = resolve(relative)
    previous = sys.argv
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(script.parent))
    try:
        sys.argv = [str(script), *argv]
        # Smoke executes imports and module-level code exactly as a path script
        # would, but never triggers a guarded CLI main().
        runpy.run_path(str(script),
                       run_name="_lf_workflow_import_smoke_" if smoke else "__main__")
    finally:
        sys.argv = previous


def main() -> int:
    args = sys.argv[1:]
    if not args:
        raise SystemExit("WORKFLOW_COMANDO_FALTANTE")
    smoke = args[0] == "--smoke"
    if smoke:
        args = args[1:]
    if not args:
        raise SystemExit("WORKFLOW_COMANDO_FALTANTE")
    execute(args[0], args[1:], smoke=smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
