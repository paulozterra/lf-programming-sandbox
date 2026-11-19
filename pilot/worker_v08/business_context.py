"""T33: business rules and screen material travel inside every lot's context.

Before T33 the builder received only requirement IDs plus the OpenAPI
contract; rule texts, values, screen copy, validations and visual tokens
stayed in pilot/runs/<slug>/analysis.json. This module projects, for one
lot, exactly the A9 requirements of that lot and the A3 screen contract
sections that its area consumes. It never invents content: everything is
copied from the run's own A9 package, and a missing or ambiguous source
fails closed.
"""
from __future__ import annotations
from pilot.config.project_config import storage_path, storage

import json
from pathlib import Path
import re

RUN = re.compile(r"pilot/runs/([a-z][a-z0-9_-]{0,63})/reuse_assessment[.]json\Z")
REQ = re.compile(r"REQ-[A-Za-z0-9_-]+\Z")

# Screen sections each area needs; values are copied verbatim.
SECTIONS = {
    "FRONTEND": ("fields", "errors", "visual", "context"),
    "BACKEND": ("fields", "errors"),
    "CONTRATO": ("fields", "errors"),
    "DATA": (),
}
CONTRACT_PATH = ("programming_context_snapshot", "decision_context",
                 "material_ledger", "source_detail", "a3_material_contract",
                 "contract_sections")


class BusinessContextBlocked(ValueError):
    pass


def _fail(code: str):
    raise BusinessContextBlocked(code)


def run_slug(context_paths) -> str | None:
    slugs = {m.group(1) for p in context_paths if isinstance(p, str)
             for m in [RUN.fullmatch(p)] if m}
    if len(slugs) > 1:
        _fail("CONTEXTO_NEGOCIO_RUN_AMBIGUO")
    return next(iter(slugs), None)


def _contract_sections(package: dict) -> dict:
    node = package
    for key in CONTRACT_PATH:
        if not isinstance(node, dict) or key not in node:
            return {}
        node = node[key]
    if not isinstance(node, dict):
        _fail("CONTEXTO_NEGOCIO_PANTALLA_INVALIDA")
    return node


def material(root: Path, slug: str, requirement_ids: list[str], area: str) -> dict:
    """Return {name: bytes} for the lot, or {} when the run has no A9 package."""
    if area not in SECTIONS:
        _fail("CONTEXTO_NEGOCIO_AREA_INVALIDA")
    if (not isinstance(requirement_ids, list) or not requirement_ids
            or any(not isinstance(r, str) or not REQ.fullmatch(r) for r in requirement_ids)):
        _fail("CONTEXTO_NEGOCIO_REQUISITOS_INVALIDOS")
    file = storage_path("requests_root", root=Path(root)) / slug / "analysis.json"
    if not file.exists():
        return {}
    if file.is_symlink() or not file.is_file():
        _fail("CONTEXTO_NEGOCIO_PAQUETE_INVALIDO")
    package = json.loads(file.read_text("utf-8"))
    requirements = package.get("requirements")
    rules = package.get("applicable_rules", [])
    if not isinstance(requirements, list) or not isinstance(rules, list):
        _fail("CONTEXTO_NEGOCIO_PAQUETE_INVALIDO")
    by_id = {}
    for row in requirements:
        if isinstance(row, dict) and isinstance(row.get("requirement_id"), str):
            if row["requirement_id"] in by_id:
                _fail("CONTEXTO_NEGOCIO_REQUISITO_DUPLICADO")
            by_id[row["requirement_id"]] = row
    items = []
    for rid in requirement_ids:
        req = by_id.get(rid)
        if req is None:
            _fail("CONTEXTO_NEGOCIO_REQUISITO_AUSENTE:" + rid)
        source = req.get("source_requirement_id")
        linked = [r for r in rules if isinstance(r, dict)
                  and (r.get("requirement_id") == rid
                       or (source and r.get("rule_code") == source))]
        items.append({
            "requirement_id": rid,
            "rule_code": source,
            "outcome": req.get("outcome"),
            "acceptance_checks": req.get("acceptance_checks", []),
            "evidence_refs": req.get("evidence_refs", []),
            "rules": [{k: r.get(k) for k in ("rule_code", "titulo", "categoria",
                                             "valor_config", "source_ref", "source_status")}
                      for r in linked],
        })
    out = {"reglas_negocio.json": {
        "schema_version": "LF_LOT_BUSINESS_RULES_V1",
        "note": ("Reglas de negocio del lote copiadas del paquete A9 del pedido. "
                 "Son obligatorias y prevalecen sobre cualquier suposición; "
                 "las reglas técnicas (STD-*) están en lf_rules.md."),
        "run": slug, "area": area, "requirements": items}}
    sections = _contract_sections(package)
    wanted = {k: sections[k] for k in SECTIONS[area] if k in sections}
    if wanted:
        out["pantalla.json"] = {
            "schema_version": "LF_LOT_SCREEN_MATERIAL_V1",
            "note": ("Ficha de la pantalla (textos, campos, validaciones, errores y, "
                     "en FRONTEND, tokens visuales y variantes) copiada del paquete A9. "
                     "Usar estos textos y valores tal cual; no inventar otros."),
            "run": slug, "area": area, "sections": wanted}
    return {name: (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            for name, doc in out.items()}
