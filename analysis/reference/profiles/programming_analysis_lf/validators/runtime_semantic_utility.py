#!/usr/bin/env python3
"""Deterministic pre-quality utility (NOT an independent semantic judge)."""


def evaluate(payload, contract_gate):
    if not isinstance(contract_gate, dict) or contract_gate.get("status") != "PASS":
        return {"status": "FAIL", "blocking_codes": ["ANALYSIS_CONTRACT_REQUIRED_FIRST"], "downstream_authorized": False}
    errors = []
    if not isinstance(payload, dict):
        errors.append("ANALYSIS_OUTPUT_NOT_OBJECT")
    else:
        intent = (payload.get("request_context") or {}).get("intent", "").strip()
        requirements = payload.get("requirements") or []
        for item in requirements:
            outcome = str(item.get("outcome", "")).strip()
            signal = str(item.get("acceptance_signal", "")).strip()
            if outcome.lower() == intent.lower():
                errors.append("ANALYSIS_REQUIREMENT_IS_ONLY_RESTATED_INTENT")
            if signal.lower() == outcome.lower():
                errors.append("ANALYSIS_ACCEPTANCE_ONLY_RESTATES_OUTCOME")
        if not payload.get("material_fronts") and not payload.get("material_unknowns"):
            errors.append("ANALYSIS_EMPTY_MATERIAL_ACCOUNTING_WITHOUT_UNKNOWN")
    return {
        "status": "FAIL" if errors else "PASS",
        "blocking_codes": sorted(set(errors)),
        "evaluation_scope": "DETERMINISTIC_UTILITY_FLOOR_ONLY",
        "independent_semantic_judge": "NOT_EXECUTED",
        "downstream_authorized": False,
    }
