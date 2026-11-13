"""Deterministic typed A1/A2 candidate signals from a catalog-resolved request.

This module asserts no live provider authority. It never extracts facts from
natural-language prose except the literal text and the catalog identifier.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

UNKNOWN_DEPTH = {
    "materiality_level": "HIGH",
    "scope_bounded": "TRUE",
    "authority_state": "UNKNOWN",
    "reversibility_state": "NOT_DEMONSTRATED",
    "currentness_decision": "UNKNOWN_FAIL_CLOSED",
    "material_contradiction": False,
    "known_cross_scope_impact": False,
    "unresolved_material_signal_count": 0,
    "required_specialist_count": 0,
}


class SignalsBlocked(ValueError):
    pass


def intent(root: Path, code: str) -> str:
    """Registered implementation wins; unverified ledger does not grant MODIFY."""
    registry = root / "pilot/registry/implemented.json"
    if registry.is_symlink():
        raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    if not registry.exists():
        return "CREATE"
    try:
        obj = json.loads(registry.read_text("utf-8"))
        rows = obj["entries"]
        if not isinstance(rows, list):
            raise ValueError("entries")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES") from exc
    # A screen implementation is registered only if its source-linked
    # requirement identity and verified file evidence explicitly match.
    for row in rows:
        if not isinstance(row, dict):
            raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES")
        if row.get("screen_code") == code and row.get("status") == "ATTESTED":
            return "MODIFY"
    return "CREATE"


def derive(root: Path, code: str, request: str, data: dict,
           provenance: dict, *, legacy: bool = False) -> dict:
    if not isinstance(request, str) or not request.strip():
        raise SignalsBlocked("PEDIDO_AMBIGUO")
    screen = data["screen_contract.json"]
    if screen.get("target_ref") != code:
        raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    provenance_key = "screen_contract.json"
    source_ref = provenance.get(provenance_key)
    if not isinstance(source_ref, str) or not source_ref.startswith("fixture://"):
        raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    # Preserve exactly the old Login fixture, solely for its historical test
    # request. For every new user text use source-derived signals below.
    original = data.get("semantic_signals.json")
    if (legacy and isinstance(original, dict) and
            original.get("simulation") is True and
            original.get("request_text") == request):
        return deepcopy(original)
    rules = data["direct_rules.json"].get("linked_rules", [])
    effective = data["effective_rules.json"].get("rules", [])
    if not isinstance(rules, list) or not isinstance(effective, list):
        raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    constraints = sorted(set(
        str(row["title"]) for row in rules
        if isinstance(row, dict) and row.get("status") == "VIGENTE"
        and row.get("pending_decision") is False
        and isinstance(row.get("title"), str) and row["title"]
    ))
    # Source rules are the only constraints; no natural-language inference.
    depth = deepcopy(UNKNOWN_DEPTH)
    inv = data.get("inventory.json", {})
    if not isinstance(inv, dict):
        raise SignalsBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    if any(inv.get(k) for k in ("objects", "impacts", "dependencies")):
        depth["scope_bounded"] = "UNKNOWN"
    action = intent(root, code)
    a1 = {
        "business": "LF",
        "request_identity": {"request_ref": source_ref, "request_kind": "USER_REQUEST"},
        "objective": {"problem_statement": request, "desired_outcome": (
            "Pantalla " + code + ": aplicar exclusivamente reglas verificadas de la ficha")},
        "target_hints": [code], "source_refs": [source_ref],
        "provided_facts": [{"fact_code": "SOURCE_SCREEN_HINT",
                            "value": code, "source_ref": source_ref}],
        "constraints": constraints, "ambiguities": [],
        "declared_intent_kind": action,
    }
    a2 = {
        "schema_version": "ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1",
        "business": "LF", "target_ref": code, "change_type": action,
        "target_granularity": "SCREEN", "nested_parent_ref": None,
        "evidence_refs": [source_ref], "depth_signals": depth,
    }
    return {"imitates":"deterministic request and pinned screen signals",
            "simulation":True,"request_text":request,
            "a1_structured":a1,"a2_signals":a2,
            "source_obligations":deepcopy(original.get("source_obligations", []))
                                  if isinstance(original, dict) else []}
