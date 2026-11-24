#!/usr/bin/env python3
"""Characterization suite coverage: the new case file must name every
requirement it was asked to pin, and only those, with valid cases.

Browser behavior is verified separately by playwright_gate.py --suite
--mutation-check; this command checks the declared coverage only.
"""
from __future__ import annotations

import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import argparse
import json
import re
import sys
from pathlib import Path

REQUIREMENT = re.compile(r"[A-Z][A-Z0-9_.-]{0,127}\Z")


class CoverageBlocked(ValueError):
    pass


def check(root: Path, suite_file: str, required: list[str]) -> int:
    from pilot.worker_v08.playwright_gate import BrowserBlocked, check_case
    rel = Path(suite_file)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".json":
        raise CoverageBlocked("CARACTERIZACION_ARCHIVO_INVALIDO")
    path = root / rel
    if path.is_symlink() or not path.is_file():
        raise CoverageBlocked("CARACTERIZACION_ARCHIVO_AUSENTE")
    if not required or any(not REQUIREMENT.fullmatch(r) for r in required):
        raise CoverageBlocked("CARACTERIZACION_REQUISITOS_INVALIDOS")
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise CoverageBlocked("CARACTERIZACION_ARCHIVO_INVALIDO") from exc
    if not isinstance(data, dict) or set(data) != {"covers", "cases"}:
        raise CoverageBlocked("CARACTERIZACION_ARCHIVO_INVALIDO")
    covers, cases = data["covers"], data["cases"]
    if (not isinstance(covers, list) or len(set(covers)) != len(covers)
            or set(covers) != set(required)):
        missing = sorted(set(required) - set(covers if isinstance(covers, list) else []))
        raise CoverageBlocked("CARACTERIZACION_COBERTURA_INCOMPLETA:" + ",".join(missing))
    if not isinstance(cases, list) or len(cases) < len(required):
        # At least one concrete case per pinned requirement.
        raise CoverageBlocked("CARACTERIZACION_CASOS_INSUFICIENTES")
    try:
        for case in cases:
            check_case(case)
    except BrowserBlocked as exc:
        raise CoverageBlocked(str(exc)) from exc
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--suite-file", required=True)
    parser.add_argument("--requires", required=True)
    args = parser.parse_args()
    try:
        count = check(args.root, args.suite_file,
                      [r for r in args.requires.split(",") if r])
    except CoverageBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("CARACTERIZACION_COBERTURA_OK:" + str(count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
