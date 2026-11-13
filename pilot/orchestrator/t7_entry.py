#!/usr/bin/env python3
"""T7 safe main-request admission, reusing the pinned A1-A9 / T1-T4 stages.

Refuses untyped semantic interpretation, reuse ambiguity and incomplete
catalogue formats. Never fabricates an oracle, selector or code rewrite.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from analysis.host.request_catalog import resolve, CatalogueBlocked
from analysis.host.run_a1_a9_fixture import run_f4
from pilot.orchestrator import atomize, plan_lots, generate_chain, intake
from pilot.orchestrator.reuse_assessment import write_assessment, ReuseBlocked

SAFE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class EntryBlocked(ValueError):
    pass


def process(root: Path, slug: str, base_sha: str) -> dict:
    if not SAFE.fullmatch(slug):
        raise EntryBlocked("PEDIDO_AMBIGUO")
    folder = root / "pilot/runs" / slug
    request = folder / "request.md"
    if folder.is_symlink() or request.is_symlink() or not request.is_file():
        raise EntryBlocked("PEDIDO_AMBIGUO")
    raw = request.read_bytes()
    code, source = resolve(root, raw)
    if source.resolve() != source.absolute() or source.is_symlink():
        raise EntryBlocked("PANTALLA_NO_EN_CATALOGO")
    pin = json.loads((source / "SOURCE_PIN.json").read_text("utf-8"))
    if pin.get("schema_version") not in ("SBX_FIXTURE_PIN_V1",
                                         "SOURCE_SCREEN_PIN_V1"):
        raise EntryBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    try:
        generated = run_f4(root, slug=slug, fixtures=source)
    except ValueError as exc:
        # A1/A2's typed semantic signals are pinned to their original text.
        # A different request cannot silently inherit the old classification.
        if "SBX_SEMANTIC_REQUEST" in str(exc):
            raise EntryBlocked("ANALISIS_SENALES_NO_DERIVABLES") from exc
        raise
    package = generated["package"]
    reuse = write_assessment(root, slug, package)
    decisions = reuse["obligations"]
    if not decisions or len(decisions) != len(package.get("requirements", [])):
        raise EntryBlocked("REUTILIZACION_INDETERMINADA")
    if all(row["decision"] == "REUSE_AS_IS" for row in decisions):
        return {"request": slug, "screen": code, "status": "REUSE_AS_IS",
                "obligations": len(decisions), "lots": 0}
    # Existing planning stages are reused verbatim. No fictional new area,
    # write scope, or implementation route is introduced in this adapter.
    atom = atomize.atomize(package, root, base_sha, run=slug,
                            reuse_assessment=reuse)
    target = folder / "atomized_inputs.json"
    content = intake.canonical(atom)
    if target.is_symlink() or (target.exists() and target.read_bytes() != content):
        raise EntryBlocked("ATOM_OUTPUT_DRIFT")
    if not target.exists():
        target.write_bytes(content)
    lots = plan_lots.plan(root, slug)
    chain = generate_chain.generate(root, slug, lots)
    return {"request": slug, "screen": code, "status": "LOTS_PLANNED",
            "lots": len(lots["lots"]), "tasks": len(chain["bindings"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--base-head-sha", required=True)
    args = parser.parse_args()
    try:
        value = process(args.root.resolve(), args.request_id, args.base_head_sha)
    except (EntryBlocked, CatalogueBlocked, ReuseBlocked, ValueError,
            KeyError, TypeError, OSError) as exc:
        text = str(exc).split(":", 1)[0]
        print("T7_BLOCKED:" + text, file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
