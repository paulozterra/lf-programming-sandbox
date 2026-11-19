"""T10 deterministic Markdown projection of source JSON (no model)."""
from __future__ import annotations
from pilot.config.project_config import storage_path, storage
import json
from pathlib import Path

MEANINGS = Path(__file__).with_name("analysis_stage_meanings_v1.json")


class ReportBlocked(ValueError):
    pass


def text(value):
    if value is None:
        return "No consignado"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip() or "No consignado"


def join(values):
    return ", ".join(map(text, values)) if values else "Ninguno consignado"


def render(package: dict, reuse: dict, lots: dict | None, meta: dict,
           request: bytes, direct: dict, *, meanings=None) -> bytes:
    meanings = meanings or json.loads(MEANINGS.read_text("utf-8"))
    if (meanings.get("schema_version") != "T10_ANALYSIS_STAGE_MEANINGS_V1"
            or package.get("schema_version") != "ANALYSIS_IMPLEMENTATION_PACKAGE_V1"
            or reuse.get("schema_version") != "T7_REUSE_ASSESSMENT_V1"
            or not isinstance(direct.get("linked_rules"), list)
            or type(meta.get("issue")) is not int
            or not isinstance(meta.get("author"), str)
            or not isinstance(meta.get("date"), str)):
        raise ReportBlocked("GENERATED_CONTENT_DRIFT")
    try:
        request_text = request.decode("utf-8")
        trace = {r["stage"]: r["status"] for r in package["stage_trace"]}
        if set(trace) != {f"A{i}" for i in range(1, 10)}:
            raise ValueError("A1-A9 incomplete")
        sources = {r["code"]: r for r in direct["linked_rules"]}
    except (KeyError, UnicodeError, TypeError, ValueError) as exc:
        raise ReportBlocked("GENERATED_CONTENT_DRIFT") from exc
    fence = chr(96)*3
    lines = ["# Informe del análisis (candidato simulado)", "",
             "## Pedido literal", "", fence+"text", request_text.rstrip("\n"),
             fence, "",
             f"- Autor: {text(meta['author'])}",
             f"- Issue: #{meta['issue']}",
             f"- Fecha: {text(meta['date'])}",
             f"- Pantalla: {text(package['request_context']['target_ref'])}",
             f"- Modo: {text(package['analysis_mode'])}", "",
             "## Reglas de la ficha", "",
             "| Código | Título | Descripción |", "| --- | --- | --- |"]
    for rule in sorted(package["applicable_rules"], key=lambda r:r["rule_code"]):
        code = rule["rule_code"]
        row = sources.get(code, {})
        lines.append(f"| {text(code)} | {text(row.get('title', rule.get('titulo')))} | "
                     f"{text(row.get('descripcion'))} |")
    lines += ["", "## Etapas A1–A9", "",
              "| Etapa | Estado | Significado |", "| --- | --- | --- |"]
    for i in range(1,10):
        stage = f"A{i}"
        status = trace[stage]
        meaning = meanings.get("stages", {}).get(stage, {}).get(status)
        if not isinstance(meaning, str) or not meaning:
            raise ReportBlocked("GENERATED_CONTENT_DRIFT")
        lines.append(f"| {stage} | {text(status)} | {text(meaning)} |")
    lines += ["", "## Clasificación", "",
              "| Campo | Valor |", "| --- | --- |"]
    for key, value in sorted(package["classification"].items()):
        lines.append(f"| {text(key)} | {text(value)} |")
    for heading, key in (("Desconocidos", "material_unknowns"),
                         ("Decisiones pendientes", "decisions_pending")):
        lines += ["", "## " + heading, ""]
        rows = package.get(key, [])
        lines += [f"- {text(row)}" for row in rows] or ["- Ninguno consignado"]
    lines += ["", "## Requisitos y frentes por área", ""]
    for area in ("DATA", "BACKEND", "FRONTEND"):
        requirements = [r for r in package["requirements"]
                        if r.get("execution_area", r.get("scope_id","").rsplit("-",1)[-1]) == area]
        fronts = [f for f in package["material_fronts"] if f.get("execution_area") == area]
        lines += [f"### {area}", "", "Requisitos:", ""]
        lines += [f"- {text(r['requirement_id'])}: {text(r.get('outcome'))}"
                  for r in requirements] or ["- Ninguno consignado"]
        lines += ["", "Frentes:", ""]
        lines += [f"- {text(f['front_id'])}: {text(f.get('front_kind'))} "
                  f"({text(f.get('closure'))})" for f in fronts] or ["- Ninguno consignado"]
        lines += [""]
    lines += ["## Reutilización", "",
              "| Requisito | Decisión | Archivos | Motivo |",
              "| --- | --- | --- | --- |"]
    for r in reuse["obligations"]:
        paths = sorted({*([r["path"]] if r.get("path") else []),
                        *(item["path"] for item in r.get("reuse_context", []))})
        reason = r.get("reason") or r.get("evidence", {}).get("reason") or r.get("evidence",{}).get("kind")
        lines.append(f"| {text(r['requirement_id'])} | {text(r['decision'])} | "
                     f"{join(paths)} | {text(reason)} |")
    lines += ["", "## Lotes en orden", "",
              "| Lote | Área | Rutas a escribir | Dependencias |",
              "| --- | --- | --- | --- |"]
    for lot in (lots or {}).get("lots", []):
        lines.append(f"| {text(lot.get('id'))} | {text(lot.get('area'))} | "
                     f"{join(lot.get('write_paths', []))} | {join(lot.get('depends_on', []))} |")
    if not (lots or {}).get("lots"):
        lines.append("| Ninguno | — | — | — |")
    lines += ["", "Solo evidencia fuente; no acredita autoridad productiva.", ""]
    return "\n".join(lines).encode("utf-8")


def read_rules(fixtures: Path, request: bytes) -> dict:
    from analysis.host.fixture_readback_host import FixtureHost
    data = FixtureHost(fixtures).read_all(request.decode("utf-8").strip())
    # Effective rules include inherited/global obligations absent from the
    # direct-rule list; every description must be sourced, never guessed.
    effective = {row["code"]: row for row in data["effective_rules.json"]["rules"]}
    direct = {row["code"]: row for row in data["direct_rules.json"]["linked_rules"]}
    return {"linked_rules": [direct.get(code, row)
                             for code, row in sorted(effective.items())]}


def write(root: Path, slug: str, fixtures: Path) -> bytes:
    folder = storage_path("requests_root", root=root) / slug
    request = (folder / "request.md").read_bytes()
    report = render(
        json.loads((folder / "analysis.json").read_text("utf-8")),
        json.loads((folder / "reuse_assessment.json").read_text("utf-8")),
        json.loads((folder / "lots.json").read_text("utf-8"))
        if (folder / "lots.json").is_file() else None,
        json.loads((folder / "request_meta.json").read_text("utf-8")),
        request, read_rules(fixtures, request))
    target = folder / "ANALYSIS_REPORT.md"
    if target.is_symlink() or (target.exists() and target.read_bytes() != report):
        raise ReportBlocked("GENERATED_CONTENT_DRIFT")
    if not target.exists():
        target.write_bytes(report)
    return report
