"""A2 source-only guard for an A1 semantic candidate; never authorizes A3.

Pure deterministic binding check; independent judge identity and source
CURRENTNESS remain the responsibility of the governed host.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def check(a1: Any, a2: Any, signals: Any) -> dict:
    def blocked(code: str) -> dict:
        return {"status": "BLOCKED", "blocking_codes": [code],
                "source_attested": False, "independent_judge_verified": False,
                "a3_allowed": False}

    if not all(isinstance(x, dict) for x in (a1, a2, signals)):
        return blocked("SEMANTIC_BINDING_INPUT_INVALID")
    if (a1.get("schema_version") != "A1_INTERNAL_STEP_CANDIDATE_RESULT_V1"
            or a1.get("skill_code") != "PROGRAMMING_ANALYSIS_LF"
            or a1.get("step_code") != "A1"
            or a2.get("schema_version") != "A2_INTERNAL_STEP_CANDIDATE_RESULT_V1"
            or a2.get("skill_code") != "PROGRAMMING_ANALYSIS_LF"
            or a2.get("step_code") != "A2"
            or signals.get("schema_version") != "ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1"
            or a1.get("business") != "LF" or a2.get("business") != "LF"
            or signals.get("business") != "LF"):
        return blocked("SEMANTIC_BINDING_BUSINESS_INVALID")
    if (a1.get("external_authority_verified") is not False
            or a1.get("operationally_integrated") is not False
            or a1.get("effects_executed") is not False
            or a2.get("operationally_integrated") is not False
            or a2.get("effects_executed") is not False
            or a1.get("status") != "VALID_OUTPUT"
            or a1.get("interpretation_state") != "SEMANTIC_REVIEWED_CANDIDATE"
            or a1.get("semantic_review_required") is not False
            or a1.get("next_capability") != "A2"
            or a1.get("semantic_review_identity_verified") is not False
            or not isinstance(a1.get("semantic_reviewer_ref"), str)
            or not a1["semantic_reviewer_ref"].strip()
            or a2.get("status") not in ("CANDIDATE_UNATTESTED", "NEED_MORE_EVIDENCE")
            or a2.get("source_attested") is not False
            or a2.get("independent_judge_verified") is not False
            or a2.get("next_step") is not None):
        return blocked("SEMANTIC_BINDING_GATE_INVALID")
    intent, context, classification = (a1.get("intent_analysis"),
                                       a1.get("payload"), a2.get("classification"))
    if not all(isinstance(x, dict) for x in (intent, context, classification)):
        return blocked("SEMANTIC_BINDING_CONTEXT_INVALID")
    if (intent.get("schema_version") != "A1_INTENT_ANALYSIS_CANDIDATE_V1"
            or context.get("schema_version") != "REQUEST_CONTEXT_V1"
            or classification.get("schema_version") != "ANALYSIS_CHANGE_CLASSIFICATION_V1"):
        return blocked("SEMANTIC_BINDING_CONTEXT_INVALID")
    raw = context.get("objective", {}).get("problem_statement") if isinstance(
        context.get("objective"), dict) else None
    if (not isinstance(raw, str) or not raw.strip()
            or a1.get("original_request_sha256") != hashlib.sha256(raw.encode("utf-8")).hexdigest()
            or a1.get("semantic_candidate_sha256") != _digest(intent)
            or context["objective"].get("desired_outcome") != intent.get("desired_outcome")):
        return blocked("SEMANTIC_BINDING_CONTENT_DIGEST_INVALID")
    target, operation = intent.get("target"), intent.get("operation")
    if not isinstance(target, dict) or not isinstance(operation, dict):
        return blocked("SEMANTIC_BINDING_INTENT_INVALID")
    mentions, hints = target.get("raw_mentions"), context.get("target_hints")
    if (not isinstance(mentions, list) or not mentions
            or not isinstance(hints, list) or hints != mentions[:1]
            or any(not isinstance(x, str) or x not in raw for x in mentions)
            or classification.get("target_ref") != hints[0]
            or signals.get("target_ref") != hints[0]
            or classification.get("change_type") != operation.get("kind")
            or classification.get("target_granularity") != target.get("artifact_kind")):
        return blocked("SEMANTIC_BINDING_TARGET_OR_OPERATION_DRIFT")
    declared = intent.get("explicit_constraints")
    actual = context.get("constraints")
    spans = intent.get("evidence_spans")
    if (not isinstance(declared, list) or not isinstance(actual, list)
            or any(not isinstance(c, dict) or not isinstance(c.get("text"), str)
                   or not c["text"].strip() for c in declared)
            or actual != [c["text"] for c in declared]
            or not isinstance(spans, list) or not spans):
        return blocked("SEMANTIC_BINDING_CONSTRAINT_DRIFT")
    for span in spans:
        if (not isinstance(span, dict) or type(span.get("start")) is not int
                or type(span.get("end")) is not int
                or not isinstance(span.get("quote"), str)
                or not 0 <= span["start"] < span["end"] <= len(raw)
                or raw[span["start"]:span["end"]] != span["quote"]):
            return blocked("SEMANTIC_BINDING_SPAN_DRIFT")
    if any(c not in raw or not any(
            s.get("dimension") in ("NEGATION", "CONSTRAINT") and c in s["quote"]
            for s in spans) for c in actual):
        return blocked("SEMANTIC_BINDING_CONSTRAINT_SPAN_MISSING")
    if classification.get("signals_sha256") != _digest(signals):
        return blocked("SEMANTIC_BINDING_SIGNAL_DIGEST_INVALID")
    return {"status": "CHECKED_SOURCE_ONLY", "blocking_codes": [],
            "business": "LF", "request_sha256": a1["original_request_sha256"],
            "semantic_candidate_sha256": a1["semantic_candidate_sha256"],
            "source_attested": False, "independent_judge_verified": False,
            "a3_allowed": False}
