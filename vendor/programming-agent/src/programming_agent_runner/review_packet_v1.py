from __future__ import annotations

import json
from typing import Any

from .hashutil import sha256_json
from .traceability import TraceabilityGraph, traceability_graph_from_dict, validate_traceability_graph

_RISK_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


class ReviewPacketV1Error(ValueError):
    """Raised when v1 enrichment is not bound to valid upstream evidence."""


def _impact_surface(files: list[str]) -> dict[str, Any]:
    lowered = [path.lower() for path in files]
    ui_tokens = ("frontend/", "ui/", "web/", ".tsx", ".jsx", ".vue", ".svelte")
    db_tokens = ("migration", ".sql", "supabase", "database", "/db/")
    api_tokens = ("api", "cli", "worker", "runner")
    security_tokens = ("auth", "security", "permission", "oracle", "secret")
    return {
        "ui": any(any(token in path for token in ui_tokens) for path in lowered),
        "database": any(any(token in path for token in db_tokens) for path in lowered),
        "api_or_runtime": any(any(token in path for token in api_tokens) for path in lowered),
        "security": any(any(token in path for token in security_tokens) for path in lowered),
        "files": files,
    }


def _retrieved_context(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in retrieval.get("selected", []):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "source": item.get("source"),
                "record_id": item.get("record_id"),
                "title": item.get("title"),
                "score": item.get("score"),
                "why_selected": item.get("reasons", []),
                "provenance": item.get("provenance"),
                "content_sha256": item.get("content_sha256"),
            }
        )
    return result


def _tests_by_file(graph: TraceabilityGraph) -> dict[str, list[str]]:
    by_id = {node.node_id: node for node in graph.nodes}
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.relation == "verified_by":
            outgoing.setdefault(edge.source, []).append(edge.target)
    result: dict[str, list[str]] = {}
    for node in graph.nodes:
        if node.kind != "FILE":
            continue
        tests = [by_id[target].label for target in outgoing.get(node.node_id, []) if target in by_id]
        result[node.label] = sorted(set(tests))
    return result


def _risk_by_file_symbol(base_packet: dict[str, Any]) -> list[dict[str, Any]]:
    heatmap = base_packet.get("risk_heatmap", {})
    global_levels = [value.get("level", "LOW") for value in heatmap.values() if isinstance(value, dict)]
    level = min(global_levels, key=lambda item: _RISK_ORDER.get(item, 3)) if global_levels else "LOW"
    result: list[dict[str, Any]] = []
    for item in base_packet.get("change_map", []):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "file": item.get("file"),
                "symbols": item.get("symbols", []),
                "level": level,
                "basis": "v0 risk heatmap + changed-symbol inventory; reviewer must inspect domain-specific semantics",
            }
        )
    return result


def _review_priority(base_packet: dict[str, Any], tests_by_file: dict[str, list[str]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    heatmap = base_packet.get("risk_heatmap", {})
    high_signals = sorted(
        category for category, data in heatmap.items() if isinstance(data, dict) and data.get("level") == "HIGH"
    )
    for index, path in enumerate(base_packet.get("change_summary", {}).get("files", []), 1):
        values.append(
            {
                "priority": index,
                "file": path,
                "risk_signals": high_signals,
                "relevant_tests": tests_by_file.get(path, []),
            }
        )
    return values


def _discrepancies(
    base_packet: dict[str, Any], retrieval: dict[str, Any], graph: TraceabilityGraph, playwright: dict[str, Any] | None
) -> list[str]:
    problems: list[str] = []
    if retrieval.get("status") != "PASS":
        problems.append("RETRIEVAL_NOT_PASS")
    for item in retrieval.get("missing_critical_context", []):
        problems.append(f"MISSING_CRITICAL_CONTEXT:{item}")
    problems.extend(f"TRACEABILITY:{item}" for item in validate_traceability_graph(graph))
    verification = base_packet.get("verification_matrix", {})
    for key, value in verification.items():
        if isinstance(value, dict) and value.get("result") != "PASS":
            problems.append(f"VERIFICATION_NOT_PASS:{key}:{value.get('result')}")
    impact = _impact_surface(list(base_packet.get("change_summary", {}).get("files", [])))
    if impact["ui"]:
        if playwright is None:
            problems.append("UI_CHANGE_WITHOUT_PLAYWRIGHT_EVIDENCE")
        elif playwright.get("status") != "PASS":
            problems.append(f"PLAYWRIGHT_NOT_PASS:{playwright.get('status')}")
    return sorted(set(problems))


def build_review_packet_v1(
    base_packet: dict[str, Any],
    retrieval: dict[str, Any],
    traceability: dict[str, Any] | TraceabilityGraph,
    playwright: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if base_packet.get("schema_version") != 1 or not isinstance(base_packet.get("packet_sha256"), str):
        raise ReviewPacketV1Error("base Human Review Packet v0 is invalid")
    expected_base_digest = sha256_json({key: value for key, value in base_packet.items() if key != "packet_sha256"})
    if base_packet["packet_sha256"] != expected_base_digest:
        raise ReviewPacketV1Error("base Human Review Packet v0 digest mismatch")
    if not isinstance(retrieval, dict) or not isinstance(retrieval.get("context_sha256"), str):
        raise ReviewPacketV1Error("retrieval result is invalid")
    graph = traceability if isinstance(traceability, TraceabilityGraph) else traceability_graph_from_dict(traceability)
    tests_by_file = _tests_by_file(graph)
    base_summary = base_packet.get("change_summary")
    summary: dict[str, Any] = dict(base_summary) if isinstance(base_summary, dict) else {}
    summary["why"] = (
        "v0.9 roadmap: structured retrieval, automatic traceability, Human Review v1, "
        "impact-driven E2E, integrated CI/CD evidence and controlled learning loop"
    )
    files = list(summary.get("files", []))
    discrepancies = _discrepancies(base_packet, retrieval, graph, playwright)
    limitations = [
        base_packet.get("impact_graph", {}).get("callers_note", "Static impact graph may be incomplete."),
        "Risk-by-symbol remains a deterministic aid, not a substitute for domain review.",
        "Retrieved context proves selection/provenance, not correctness of the underlying policy content.",
    ]
    packet: dict[str, Any] = {
        "schema_version": 1,
        "packet_type": "HUMAN_REVIEW_PACKET_V1",
        "base_packet_sha256": base_packet["packet_sha256"],
        "base_ref": base_packet.get("base_ref"),
        "head_ref": base_packet.get("head_ref"),
        "status": "PASS" if not discrepancies else "BLOCKED",
        "change_summary": summary,
        "retrieved_context": _retrieved_context(retrieval),
        "retrieval_context_sha256": retrieval["context_sha256"],
        "traceability_graph_sha256": graph.graph_sha256,
        "behavior_impact": _impact_surface(files),
        "risk_by_file_symbol": _risk_by_file_symbol(base_packet),
        "relevant_tests_by_file": tests_by_file,
        "playwright_evidence": playwright,
        "review_priority": _review_priority(base_packet, tests_by_file),
        "verification_matrix": base_packet.get("verification_matrix"),
        "discrepancies": discrepancies,
        "known_limitations": limitations,
        "auditor_views": [
            "1_change_context_risk",
            "2_rules_decisions_traceability",
            "3_relevant_tests_and_ui_evidence",
            "4_diff_and_code",
        ],
        "diff_command": base_packet.get("diff_command"),
    }
    packet["packet_sha256"] = sha256_json(packet)
    return packet


def validate_review_packet_v1(packet: Any) -> list[str]:
    if not isinstance(packet, dict):
        return ["PACKET_NOT_OBJECT"]
    problems: list[str] = []
    if packet.get("schema_version") != 1 or packet.get("packet_type") != "HUMAN_REVIEW_PACKET_V1":
        problems.append("PACKET_SCHEMA_INVALID")
    digest = packet.get("packet_sha256")
    expected = sha256_json({key: value for key, value in packet.items() if key != "packet_sha256"})
    if not isinstance(digest, str) or digest != expected:
        problems.append("PACKET_SHA256_MISMATCH")
    if packet.get("status") == "PASS" and packet.get("discrepancies"):
        problems.append("PASS_WITH_DISCREPANCIES")
    if not isinstance(packet.get("retrieved_context"), list):
        problems.append("RETRIEVED_CONTEXT_MISSING")
    return sorted(problems)


def packet_v1_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Human Review Packet v1",
        "",
        f"Status: **{packet['status']}**",
        f"Head: `{packet['head_ref']}`",
        f"Packet SHA256: `{packet['packet_sha256']}`",
        f"Retrieval: `{packet['retrieval_context_sha256']}`",
        f"Traceability: `{packet['traceability_graph_sha256']}`",
        "",
        "## 1. Cambio, contexto y riesgo",
        "",
    ]
    summary = packet.get("change_summary") or {}
    lines.append(f"Archivos cambiados: {summary.get('changed_file_count', 0)}")
    lines.append(f"Motivo: {summary.get('why', '')}")
    lines.extend(["", "### Contexto recuperado", ""])
    for item in packet["retrieved_context"]:
        lines.append(
            f"- `{item['source']}:{item['record_id']}` score={item['score']} — {item['title']} — "
            f"why={json.dumps(item['why_selected'], sort_keys=True)}"
        )
    lines.extend(["", "### Riesgo por archivo/símbolo", ""])
    for item in packet["risk_by_file_symbol"]:
        lines.append(f"- `{item['file']}` **{item['level']}** — {', '.join(item['symbols']) or 'sin símbolos top-level'}")
    lines.extend(
        [
            "",
            "## 2. Reglas/decisiones y trazabilidad",
            "",
            f"Graph SHA256: `{packet['traceability_graph_sha256']}`",
            "",
            "## 3. Tests y evidencia UI",
            "",
        ]
    )
    for path, tests in packet["relevant_tests_by_file"].items():
        lines.append(f"- `{path}` → {', '.join(tests) or 'sin test enlazado'}")
    lines.append(f"- Playwright: `{json.dumps(packet['playwright_evidence'], sort_keys=True)}`")
    lines.extend(["", "### Qué revisar primero", ""])
    for item in packet["review_priority"]:
        lines.append(f"{item['priority']}. `{item['file']}` — tests: {', '.join(item['relevant_tests']) or 'ninguno'}")
    lines.extend(["", "### Discrepancias", ""])
    lines.extend(f"- {item}" for item in packet["discrepancies"] or ["ninguna"])
    lines.extend(["", "### Límites conocidos", ""])
    lines.extend(f"- {item}" for item in packet["known_limitations"])
    lines.extend(["", "## 4. Diff/código", "", f"`{packet['diff_command']}`", ""])
    return "\n".join(lines) + "\n"
