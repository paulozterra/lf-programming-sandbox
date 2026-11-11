"""A1 semantic interpretation adapter (SOURCE CANDIDATE, no model/provider binding).

A semantic producer and a separate semantic reviewer are injected as callables.
A substring check alone NEVER attests semantic meaning. No keyword lexicons,
target IDs, business policies, network calls, Router or RUN creation here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

from pathlib import Path

BASE = Path(__file__).resolve().parent
CONTRACT = BASE / "schemas/intent_analysis_candidate_v1.schema.json"
SCHEMA = "A1_INTENT_ANALYSIS_CANDIDATE_V1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _schema_errors(candidate: Any) -> list[str]:
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return ["/".join(map(str, e.absolute_path)) or "ROOT"
            for e in Draft202012Validator(schema).iter_errors(candidate)]


def _grounding_errors(raw_text: str, candidate: dict) -> list[str]:
    errors = []
    spans = candidate["evidence_spans"]
    present = {s["dimension"] for s in spans}
    unknown_capability = candidate["target"]["canonical_capability"] == "UNKNOWN"
    required_spans = ("OPERATION", "ARTIFACT") if unknown_capability else (
        "OPERATION", "ARTIFACT", "CAPABILITY"
    )
    for required in required_spans:
        if required not in present:
            errors.append("MISSING_EVIDENCE_" + required)
    for s in spans:
        quote, start, end = s["quote"], s["start"], s["end"]
        if raw_text[start:end] != quote:
            errors.append("EVIDENCE_SPAN_MISMATCH")
    for item in candidate["explicit_constraints"]:
        if item["text"] not in raw_text:
            errors.append("EXPLICIT_CONSTRAINT_UNGROUNDED")
        elif not any(
            span["dimension"] in ("CONSTRAINT", "NEGATION")
            and item["text"] in span["quote"] for span in spans
        ):
            errors.append("EXPLICIT_CONSTRAINT_EVIDENCE_MISSING")
    for mention in candidate["target"]["raw_mentions"]:
        if mention not in raw_text:
            errors.append("RAW_MENTION_UNGROUNDED")
    op = candidate["operation"]
    if op["kind"] == "UNKNOWN" or (
        unknown_capability and not any(
            issue["materiality"] in ("MATERIAL", "UNKNOWN")
            for issue in candidate["material_ambiguities"]
        )
    ):
        errors.append("MATERIAL_INTENT_UNRESOLVED")
    if op["user_assumed_state"] != "UNSPECIFIED":
        if not any(s["dimension"] == "ASSUMPTION" for s in spans):
            errors.append("USER_ASSUMED_STATE_UNGROUNDED")
    if candidate["target"]["actor_scope"] != "UNSPECIFIED" and not any(
        s["dimension"] == "ACTOR_SCOPE" for s in spans
    ):
        errors.append("ACTOR_SCOPE_UNGROUNDED")
    return sorted(set(errors))


def extract(raw_text: str, producer: Any, reviewer: Any) -> dict:
    """Separate model-dependent production and independent review callbacks.

    The callback's claimed identity is not authenticated here. All results
    remain SOURCE_CANDIDATE and do not establish source/authority CURRENT.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return {"status": "BLOCKED", "blocking_codes": ["EMPTY_RAW_REQUEST"]}
    if not callable(producer):
        return {"status": "BLOCKED", "blocking_codes": ["SEMANTIC_PRODUCER_UNAVAILABLE"]}
    if not callable(reviewer) or reviewer is producer:
        return {"status": "BLOCKED", "blocking_codes": ["SEPARATE_SEMANTIC_REVIEWER_REQUIRED"]}
    try:
        candidate = producer(raw_text)
    except Exception:
        return {"status": "BLOCKED", "blocking_codes": ["SEMANTIC_PRODUCER_FAILED"]}
    errors = _schema_errors(candidate)
    if errors:
        return {"status": "BLOCKED", "blocking_codes": ["INTENT_SCHEMA:" + x for x in errors]}
    errors = _grounding_errors(raw_text, candidate)
    if errors:
        return {"status": "REQUIRES_SEMANTIC_REVIEW", "blocking_codes": errors}
    fingerprint = _hash(candidate)
    try:
        decision = reviewer(raw_text, candidate)
    except Exception:
        return {"status": "BLOCKED", "blocking_codes": ["SEMANTIC_REVIEWER_FAILED"]}
    if not isinstance(decision, dict) or set(decision) != {
        "verdict", "candidate_sha256", "reviewer_ref", "issues"
    }:
        return {"status": "BLOCKED", "blocking_codes": ["SEMANTIC_REVIEW_FORMAT_INVALID"]}
    if (decision["verdict"] != "PASS" or decision["candidate_sha256"] != fingerprint
            or not isinstance(decision["reviewer_ref"], str) or not decision["reviewer_ref"].strip()
            or not isinstance(decision["issues"], list) or decision["issues"]):
        return {"status": "REQUIRES_SEMANTIC_REVIEW",
                "blocking_codes": ["SEMANTIC_REVIEW_NOT_PASSED"]}
    return {"status": "REVIEWED_CANDIDATE", "intent": candidate,
            "candidate_sha256": fingerprint, "reviewer_ref": decision["reviewer_ref"],
            "blocking_codes": [],
            "external_authority_verified": False,
            "independent_reviewer_identity_verified": False}


def to_structured_input(raw_text: str, business: str, reviewed: dict) -> dict:
    """Populate only the existing canonical REQUEST_CONTEXT_V1 fields."""
    candidate = reviewed["intent"]
    sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    ref = "user://a1-raw-" + sha[:20]  # local request identifier, not an authority
    op = candidate["operation"]["kind"]
    # Intent to implement is NOT proof that creation from zero is required.
    legacy = {"MODIFY": "EVOLVE", "REBUILD": "EVOLVE", "REPAIR": "REPAIR",
              "CREATE": "CREATE"}.get(op, "UNKNOWN")
    mentioned = candidate["target"]["raw_mentions"]
    if not mentioned:
        # No fabricated repository target ID or guessed screen name.
        raise ValueError("TARGET_MENTION_REQUIRED")
    return {
        "business": business,
        "original_request": raw_text,
        "input_mode": "SEMANTIC_CANDIDATE",
        "request_identity": {"request_ref": ref, "request_kind": "USER_REQUEST"},
        "objective": {"problem_statement": raw_text,
                      "desired_outcome": candidate["desired_outcome"]},
        "target_hints": mentioned[:1],
        "source_refs": [ref],
        "provided_facts": [],
        "constraints": [x["text"] for x in candidate["explicit_constraints"]],
        "ambiguities": [{"code": item["code"], "statement": item["statement"],
                         "materiality": item["materiality"], "resolution_state": "OPEN"}
                        for item in candidate["material_ambiguities"]],
        "declared_intent_kind": legacy,
    }
