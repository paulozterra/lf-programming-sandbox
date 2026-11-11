"""A1 / Intake Normalize. Internal analysis step: no Router, RUN, SQL, or profile dependency.

Canonical functional payload: REQUEST_CONTEXT_V1, schema kept only in its
source-of-truth path under sandbox/lf_contract_gate_test/... .
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
CANONICAL_SCHEMA = ROOT / "sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_request_context_v1.schema.json"


def _schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _problems(value: Any, schema: dict) -> list[str]:
    return ["/".join(map(str, error.absolute_path)) or "ROOT"
            for error in sorted(Draft202012Validator(schema).iter_errors(value),
                                key=lambda error: (list(map(str, error.absolute_path)), error.message))]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values))


def _explicit_other_business_source(ref: str) -> bool:
    """Only deny explicit known cross-business namespaces, never guess authority."""
    return bool(re.match(r"(?i)^(?:saly(?=[:./]|$)|supabase://saly(?=[:./]|$))", ref))


def _normalized_prompt(payload: dict) -> str:
    objective = payload["objective"]
    lines = [
        "Solicitud: " + objective["problem_statement"],
        "Resultado esperado: " + objective["desired_outcome"],
    ]
    if payload["target_hints"]:
        lines.append("Identificadores o referencias recibidas (sin verificar): " + ", ".join(payload["target_hints"]))
    if payload["provided_facts"]:
        lines.append("Datos recibidos (declarados, no verificados): " + "; ".join(
            fact["fact_code"] + "=" + (
                fact["value"] if isinstance(fact["value"], str)
                else json.dumps(fact["value"], ensure_ascii=False, sort_keys=True)
            ) + " [fuente: " + fact["source_ref"] + "]"
            for fact in payload["provided_facts"]
        ))
    if payload["constraints"]:
        lines.append("Restricciones recibidas: " + "; ".join(payload["constraints"]))
    return "\n".join(lines)


def _guard_check(data: dict, result: dict) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "a1_deterministic_guard", BASE / "judges/semantic_guard.py"
    )
    if spec is None or spec.loader is None:
        return ["GUARD_UNAVAILABLE"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check(data, result)


def run(data: Any, *, business: str | None = None,
        semantic_producer: Any = None, semantic_reviewer: Any = None) -> dict:
    """Normalize a prestructured request or semantically reviewed raw input.

    Text-only inputs require two separate callbacks. In their absence the
    request is NOT pretended to be interpreted; no keyword fallback exists.
    This remains a local SOURCE_CANDIDATE, not operational attestation.
    """
    is_raw_envelope = isinstance(data, dict) and "raw_prompt" in data
    if isinstance(data, str) or is_raw_envelope:
        raw = data if isinstance(data, str) else data.get("raw_prompt")
        if is_raw_envelope and business is not None and "business" in data and data["business"] != business:
            return _run_semantic(raw, None, None, None, business_conflict=True)
        declared_business = business if business is not None else (
            data.get("business") if is_raw_envelope else None
        )
        return _run_semantic(raw, declared_business, semantic_producer, semantic_reviewer)
    base = {
        "schema_version": "A1_INTERNAL_STEP_CANDIDATE_RESULT_V1",
        "skill_code": "PROGRAMMING_ANALYSIS_LF",
        "step_code": "A1",
        "business": data.get("business") if isinstance(data, dict) else None,
        "status": "BLOCKED",
        "payload": None,
        "declared_intent_kind": None,
        "normalized_prompt": None,
        "original_request_sha256": None,
        "semantic_review_required": False,
        "interpretation_state": "NO_VALID_INTERPRETATION",
        "blocking_codes": [],
        "next_capability": None,
        "external_authority_verified": False,
        "operationally_integrated": False,
        "effects_executed": False,
    }
    if not isinstance(data, dict):
        base["blocking_codes"] = ["INPUT_NOT_OBJECT"]
        return base
    errors = _problems(data, _schema(BASE / "schemas/input.schema.json"))
    original = data.get("original_request")
    mode = data.get("input_mode", "STRUCTURED")
    if isinstance(original, str) and original.strip():
        base["original_request_sha256"] = sha256(original.encode("utf-8")).hexdigest()
        base["semantic_review_required"] = True
    if mode == "SEMANTIC_CANDIDATE" and not isinstance(original, str):
        errors.append("ORIGINAL_LITERAL_REQUIRED_FOR_SEMANTIC_CANDIDATE")
    if isinstance(original, str) and not original.strip():
        errors.append("ORIGINAL_LITERAL_EMPTY")
    if data.get("business") != "LF":
        errors.append("BUSINESS_BINDING_NOT_QUALIFIED")
    if errors:
        base["blocking_codes"] = sorted(set("INPUT_SCHEMA:" + x for x in errors))
        return base
    normalized = copy.deepcopy(data)
    for section in ("request_identity", "objective"):
        normalized[section] = {k: v.strip() if isinstance(v, str) else v
                               for k, v in normalized[section].items()}
    for k in ("target_hints", "source_refs", "constraints"):
        normalized[k] = _unique(normalized[k])
    facts = []
    for item in normalized["provided_facts"]:
        facts.append({**item,
                      "fact_code": item["fact_code"].strip(),
                      "source_ref": item["source_ref"].strip()})
    normalized["provided_facts"] = facts
    normalized["ambiguities"] = [
        {**item, "code": item["code"].strip(), "statement": item["statement"].strip()}
        for item in normalized["ambiguities"]
    ]
    if any(not normalized["objective"][k] for k in ("problem_statement", "desired_outcome")):
        base["blocking_codes"] = ["ESSENTIAL_OBJECTIVE_MISSING"]
        return base
    if any(not v for k in ("target_hints", "source_refs", "constraints") for v in normalized[k]):
        base["blocking_codes"] = ["BLANK_REFERENCE_OR_CONSTRAINT"]
        return base
    if any(x["source_ref"] not in normalized["source_refs"] for x in facts):
        base["blocking_codes"] = ["UNSUPPORTED_PROVIDED_FACT_REF"]
        return base
    if any(_explicit_other_business_source(ref) for ref in normalized["source_refs"]):
        base["blocking_codes"] = ["CROSS_BUSINESS_SOURCE_REQUIRES_QUALIFIED_BINDING"]
        return base
    payload = {k: normalized[k] for k in (
        "request_identity", "objective", "target_hints", "source_refs",
        "provided_facts", "constraints", "ambiguities"
    )}
    payload.update(schema_version="REQUEST_CONTEXT_V1", no_solution_inferred=True)
    defects = _problems(payload, _schema(CANONICAL_SCHEMA))
    if defects:
        base["blocking_codes"] = ["CANONICAL_OUTPUT_INVALID:" + x for x in defects]
        return base
    base["payload"] = payload
    base["declared_intent_kind"] = normalized["declared_intent_kind"]
    base["normalized_prompt"] = _normalized_prompt(payload)
    base["interpretation_state"] = (
        "SEMANTIC_CANDIDATE_UNATTESTED"
        if base["semantic_review_required"]
        else "PRESTRUCTURED_UNATTESTED"
    )
    if any(a["resolution_state"] == "OPEN" and a["materiality"] in ("MATERIAL", "UNKNOWN")
           for a in payload["ambiguities"]):
        base["status"] = "REQUIRES_DECISION"
        base["blocking_codes"] = ["MATERIAL_INTENT_AMBIGUITY"]
    elif not payload["target_hints"]:
        base["status"] = "NEED_MORE_EVIDENCE"
        base["blocking_codes"] = ["TARGET_HINT_MISSING"]
    else:
        base["status"] = "REQUIRES_SEMANTIC_REVIEW" if base["semantic_review_required"] else "VALID_OUTPUT"
        base["next_capability"] = None if base["semantic_review_required"] else "A2"
    if _problems(base, _schema(BASE / "schemas/output.schema.json")):
        raise ValueError("A1_INTERNAL_OUTPUT_SCHEMA_FAILURE")
    faults = _guard_check(data, base)
    if faults:
        base["status"] = "BLOCKED"
        base["payload"] = None
        base["normalized_prompt"] = None
        base["next_capability"] = None
        base["interpretation_state"] = "NO_VALID_INTERPRETATION"
        base["blocking_codes"] = sorted(set(faults))
    return base


def _run_semantic(raw_text: Any, business: Any, producer: Any, reviewer: Any,
                  *, business_conflict: bool = False) -> dict:
    """Provider-neutral callback seam; canonical REQUEST_CONTEXT_V1 unchanged."""
    base = {
        "schema_version": "A1_INTERNAL_STEP_CANDIDATE_RESULT_V1",
        "skill_code": "PROGRAMMING_ANALYSIS_LF",
        "step_code": "A1",
        "business": business if isinstance(business, str) else None,
        "status": "BLOCKED",
        "payload": None,
        "declared_intent_kind": None,
        "normalized_prompt": None,
        "original_request_sha256": sha256(raw_text.encode("utf-8")).hexdigest()
            if isinstance(raw_text, str) and raw_text.strip() else None,
        "semantic_review_required": True,
        "interpretation_state": "NO_VALID_INTERPRETATION",
        "blocking_codes": [],
        "next_capability": None,
        "external_authority_verified": False,
        "operationally_integrated": False,
        "effects_executed": False,
    }
    if business_conflict:
        base["blocking_codes"] = ["RAW_ENVELOPE_BUSINESS_CONFLICT"]
        return base
    if business != "LF":
        base["blocking_codes"] = ["BUSINESS_SCOPE_NOT_PROVIDED_OR_NOT_LF"]
        return base
    spec = importlib.util.spec_from_file_location(
        "a1_semantic_intake_candidate", BASE / "semantic_intake_candidate_v1.py"
    )
    if spec is None or spec.loader is None:
        base["blocking_codes"] = ["SEMANTIC_ADAPTER_UNAVAILABLE"]
        return base
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    reviewed = adapter.extract(raw_text, producer, reviewer)
    if reviewed["status"] != "REVIEWED_CANDIDATE":
        base["status"] = (
            "REQUIRES_SEMANTIC_REVIEW" if reviewed["status"] == "REQUIRES_SEMANTIC_REVIEW"
            else "BLOCKED"
        )
        base["blocking_codes"] = reviewed["blocking_codes"]
        return base
    try:
        structured = adapter.to_structured_input(raw_text, business, reviewed)
    except (TypeError, ValueError, KeyError):
        base["blocking_codes"] = ["SEMANTIC_TO_CANONICAL_MAPPING_INVALID"]
        return base
    result = run(structured)
    if result["status"] not in ("REQUIRES_SEMANTIC_REVIEW", "REQUIRES_DECISION"):
        return result  # preserve canonical material gates
    result["intent_analysis"] = copy.deepcopy(reviewed["intent"])
    result["semantic_candidate_sha256"] = reviewed["candidate_sha256"]
    result["semantic_reviewer_ref"] = reviewed["reviewer_ref"]
    result["semantic_review_identity_verified"] = False
    if result["status"] == "REQUIRES_SEMANTIC_REVIEW":
        result["status"] = "VALID_OUTPUT"
        result["semantic_review_required"] = False
        result["interpretation_state"] = "SEMANTIC_REVIEWED_CANDIDATE"
        result["next_capability"] = "A2"
        result["blocking_codes"] = []
    faults = _problems(result, _schema(BASE / "schemas/output.schema.json"))
    faults.extend(_guard_check(structured, result))
    if faults:
        base["blocking_codes"] = sorted(set(
            ["SEMANTIC_RESULT_CONTRACT_INVALID"] if _problems(
                result, _schema(BASE / "schemas/output.schema.json")) else []
        ) | set(_guard_check(structured, result)))
        return base
    return result
