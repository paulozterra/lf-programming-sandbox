"""Fail-closed business-scoped A2->A3 candidate handoff.

Pure internal contract guard. Does NOT call A3, a model, the judge, Router,
Supabase, or GitHub. Approval requires separate native judge and RUN receipts.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from pathlib import Path
import json
from jsonschema import Draft202012Validator

SCHEMA = "A2_A3_BUSINESS_HANDOFF_CANDIDATE_V1"
IDENTITY_FACTS = {"BUSINESS", "BUSINESS_CODE", "TARGET_BUSINESS"}
PRODUCT_FACTS = {"PRODUCT", "PRODUCT_NAME", "PRODUCT_CODE"}
MODULE_FACTS = {"MODULE", "MODULE_NAME", "MODULE_CODE"}


def _checked(payload: dict) -> dict:
    schema = json.loads(Path(__file__).with_suffix(".schema.json").read_text(encoding="utf-8"))
    if not Draft202012Validator(schema).is_valid(payload):
        raise ValueError("A2_A3_HANDOFF_SCHEMA_DRIFT")
    return payload


def _blocked(code: str) -> dict:
    return _checked({
        "schema_version": SCHEMA,
        "status": "BLOCKED",
        "blocking_codes": [code],
        "business": None,
        "a3_inputs": None,
        "research_brief": None,
        "source_attested": False,
        "judge_verified": False,
        "runtime_qualified": False,
        "a3_allowed": False,
        "next_step": None,
    })


def _exact_business(value: Any) -> bool:
    return (isinstance(value, str) and 2 <= len(value) <= 32
            and value == value.strip() and bool(value.strip()))


def _declared_spec(facts: list[dict], allowed: set[str], refs: set[str]) -> dict:
    matches = [f for f in facts if f.get("fact_code") in allowed]
    if not matches:
        return {"state": "UNKNOWN", "value": None, "source_ref": None}
    by_code = {}
    for fact in matches:
        code = fact.get("fact_code")
        if not isinstance(fact.get("value"), str) or not fact["value"].strip() or fact.get("source_ref") not in refs:
            raise ValueError("SPECIFICATION_SOURCE_INVALID")
        if code in by_code and by_code[code] != (fact["value"], fact["source_ref"]):
            raise ValueError("IDENTITY_FACT_CONFLICT_OR_DUPLICATE")
        by_code[code] = (fact["value"], fact["source_ref"])
    # NAME is the display summary. The paired CODE and all refs survive in declared_facts.
    preferred = next((x for x in ("PRODUCT_NAME", "MODULE_NAME", "PRODUCT", "MODULE", "PRODUCT_CODE", "MODULE_CODE") if x in by_code), None)
    value, ref = by_code[preferred]
    return {"state": "DECLARED_UNATTESTED", "value": value, "source_ref": ref}


def prepare_candidate(a1_result: Any, a2_result: Any, expected_business: Any) -> dict:
    """Cross-check scope; prepare ONLY, never authorize A3 from caller claims."""
    if not isinstance(a1_result, dict) or a1_result.get("schema_version") != "A1_INTERNAL_STEP_CANDIDATE_RESULT_V1" or a1_result.get("status") != "VALID_OUTPUT":
        return _blocked("A1_HANDOFF_INVALID")
    if not isinstance(a2_result, dict) or a2_result.get("schema_version") != "A2_INTERNAL_STEP_CANDIDATE_RESULT_V1" or a2_result.get("status") not in {"CANDIDATE_UNATTESTED", "NEED_MORE_EVIDENCE"}:
        return _blocked("A2_HANDOFF_INVALID")
    business = a1_result.get("business")
    if not _exact_business(business) or not _exact_business(expected_business):
        return _blocked("BUSINESS_SCOPE_UNRESOLVED")
    # Guard direct calls as well: business equality is not admission for SALY
    # under the LF-only skill, even for synthetically shaped A1/A2 payloads.
    if business != "LF":
        return _blocked("BUSINESS_NOT_ENABLED_FOR_LF_SKILL")
    if a2_result.get("business") != business or expected_business != business:
        return _blocked("CROSS_BUSINESS_HANDOFF_FORBIDDEN")
    if a1_result.get("skill_code") != "PROGRAMMING_ANALYSIS_LF" or a2_result.get("skill_code") != "PROGRAMMING_ANALYSIS_LF":
        return _blocked("SKILL_IDENTITY_MISMATCH")
    context = a1_result.get("payload")
    classification = a2_result.get("classification")
    if (not isinstance(context, dict) or context.get("schema_version") != "REQUEST_CONTEXT_V1"
            or not isinstance(classification, dict) or classification.get("schema_version") != "ANALYSIS_CHANGE_CLASSIFICATION_V1"
            or not isinstance(context.get("target_hints"), list) or not isinstance(context.get("source_refs"), list)
            or not isinstance(context.get("provided_facts"), list)):
        return _blocked("A3_CANONICAL_INPUT_INVALID")
    target = classification.get("target_ref")
    if not isinstance(target, str) or target not in context["target_hints"]:
        return _blocked("A3_TARGET_NOT_BOUND_TO_A1")
    if not context["source_refs"] or any(not isinstance(ref, str) or not ref for ref in context["source_refs"]):
        return _blocked("A3_SOURCE_REFS_MISSING")
    refs = set(context["source_refs"])
    facts = context["provided_facts"]
    if any(not isinstance(f, dict) for f in facts):
        return _blocked("A3_FACTS_INVALID")
    for fact in facts:
        if fact.get("fact_code") in IDENTITY_FACTS:
            if fact.get("value") != business or fact.get("source_ref") not in refs:
                return _blocked("BUSINESS_IDENTITY_FACT_CONFLICT")
    try:
        product = _declared_spec(facts, PRODUCT_FACTS, refs)
        module = _declared_spec(facts, MODULE_FACTS, refs)
    except ValueError as exc:
        return _blocked(str(exc))
    # These are research instructions, NOT statements that technical values exist.
    questions = [
        {"kind": "TARGET_IDENTITY", "target_ref": target, "business": business},
        {"kind": "CURRENT_AUTHORITY_AND_POLICIES", "target_ref": target, "business": business},
        {"kind": "CURRENT_IMPLEMENTATION_AND_PARAMETERS", "target_ref": target, "business": business},
        {"kind": "DEPENDENCIES_AND_CONSUMERS", "target_ref": target, "business": business},
    ]
    return _checked({
        "schema_version": SCHEMA,
        "status": "CANDIDATE_PENDING_NATIVE_JUDGE_READBACK",
        "blocking_codes": [],
        "business": business,
        "a3_inputs": {
            "REQUEST_CONTEXT_V1": deepcopy(context),
            "ANALYSIS_CHANGE_CLASSIFICATION_V1": deepcopy(classification),
        },
        "research_brief": {
            "business": business,
            "target_ref": target,
            "product": product,
            "module": module,
            "objective": deepcopy(context.get("objective")),
            "constraints": deepcopy(context.get("constraints", [])),
            "declared_facts": deepcopy(facts),
            "source_refs": deepcopy(context["source_refs"]),
            "research_questions": questions,
            "business_boundary": "SAME_BUSINESS_UNLESS_GROUNDED_DEPENDENCY",
        },
        "source_attested": False,
        "judge_verified": False,
        "runtime_qualified": False,
        "a3_allowed": False,
        "next_step": None,
    })
