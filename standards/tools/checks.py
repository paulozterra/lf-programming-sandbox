"""Checks propios del catálogo que no cubre una herramienta estándar.

Subcomandos:
  filenames <dir>...      STD-FE-02: archivos de frontend en kebab-case.
  suppressions <dir>...   STD-GEN-05: toda supresión de lint lleva un id WAIVER-.
  branch <nombre>         STD-GIT-01: ramas del agente dentro de lf/**.

Salida: una línea por violación y código 1 si hay alguna.
"""

import re
import datetime as dt
import waivers
import sys
from pathlib import Path

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Archivos que el framework exige con otro nombre o que no son código propio.
FRONTEND_ALLOWED = {"next-env.d.ts"}
FRONTEND_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".css")
SKIP_DIRS = {"node_modules", ".next", "out", "target", ".git"}
SUPPRESSION = re.compile(
    r"eslint-disable|@ts-ignore|@ts-expect-error|@SuppressWarnings|NOSONAR|# noqa|# type: ignore|prettier-ignore"
)
WAIVER = re.compile(r"WAIVER-\d{4,}")
SOURCE_SUFFIXES = (".java", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py")
BRANCH = re.compile(r"^lf/prog-[A-Za-z0-9-]+/[a-z0-9]+(?:-[a-z0-9]+)*$")


def iter_files(roots: list[str], suffixes: tuple[str, ...]):
    for root in roots:
        base = Path(root)
        if base.is_file():
            if base.name.endswith(suffixes):
                yield base
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not SKIP_DIRS.intersection(path.parts) and path.name.endswith(suffixes):
                yield path


def check_filenames(roots: list[str]) -> list[str]:
    violations = []
    for path in iter_files(roots, FRONTEND_SUFFIXES):
        if path.name in FRONTEND_ALLOWED:
            continue
        stem = path.name.split(".")[0]
        if not KEBAB.match(stem):
            violations.append(f"STD-FE-02 {path}: el nombre de archivo debe ir en kebab-case")
    return violations


def check_suppressions(roots: list[str]) -> list[str]:
    """Un solo parser y registro: delega en waivers.py."""
    catalog, registry = waivers.load()
    return waivers.check_refs(catalog, registry, roots, dt.datetime.now(dt.timezone.utc))


def check_branch(name: str) -> list[str]:
    if BRANCH.match(name):
        return []
    return [f"STD-GIT-01 {name}: la rama del agente debe ser lf/prog-<work_code>/<slug>"]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    command, args = argv[1], argv[2:]
    if command == "filenames":
        violations = check_filenames(args)
    elif command == "suppressions":
        violations = check_suppressions(args)
    elif command == "branch" and len(args) == 1:
        violations = check_branch(args[0])
    else:
        print(__doc__)
        return 2
    for violation in violations:
        print(violation)
    if not violations:
        print(f"OK {command}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
