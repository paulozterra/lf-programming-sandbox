"""A1 semantic candidate boundary — NOT a model client or a second profile runtime.

The future consumer supplies genuine model output. This module checks its
provenance, preserves exact received context and calls the existing A1 runner.
No outcome here can prove semantic fidelity or authorize the next skill.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
SCHEMA = "A1_SEMANTIC_CANDIDATE_BOUNDARY_V1"
ALLOWED_INTENTS = {"CREATE", "EVOLVE", "COMBINE", "REPAIR", "UNKNOWN"}


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _load_runner():
    spec = importlib.util.spec_from_file_location("a1_core_runner", BASE / "validators/run.py")
    if spec is None or spec.loader is None:
        raise ValueError("A1_CORE_RUNNER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _blocked(code: str) -> dict:
    return {
        "schema_version": SCHEMA,
        "status": "BLOCKED",
        "blocking_codes": [code],
        "candidate_sha256": None,
        "original_request_sha256": None,
        "observed_actions": [],
        "a1_result": None,
        "semantic_verified": False,
        "operationally_verified": False,
        "next_capability": None,
    }


def _valid_strings(items: Any, allow_empty: bool = True) -> bool:
    return (isinstance(items, list)
            and (allow_empty or bool(items))
            and all(isinstance(item, str) and bool(item.strip()) for item in items))


def prepare(context: Any) -> dict:
    """Prepare the immutable instruction packet for an external model call."""
    if not isinstance(context, dict):
        return _blocked("SEMANTIC_CONTEXT_NOT_OBJECT")
    if set(context) != {
        "business", "original_request", "request_identity",
        "target_hints", "source_refs", "provided_facts", "constraints"
    }:
        return _blocked("SEMANTIC_CONTEXT_KEYS_INVALID")
    literal = context["original_request"]
    rid = context["request_identity"]
    if context["business"] != "LF":
        return _blocked("BUSINESS_BINDING_NOT_QUALIFIED")
    if not isinstance(literal, str) or not literal.strip():
        return _blocked("ORIGINAL_LITERAL_MISSING")
    if not isinstance(rid, dict) or not isinstance(rid.get("request_ref"), str) or not rid["request_ref"]:
        return _blocked("REQUEST_IDENTITY_MISSING")
    if not all(_valid_strings(context[key]) for key in ("target_hints", "source_refs", "constraints")):
        return _blocked("CONTEXT_COLLECTION_INVALID")
    refs = context["source_refs"]
    if not isinstance(context["provided_facts"], list):
        return _blocked("PROVIDED_FACTS_INVALID")
    for item in context["provided_facts"]:
        if (not isinstance(item, dict) or set(item) != {"fact_code", "value", "source_ref"}
                or not isinstance(item["fact_code"], str) or not item["fact_code"]
                or not isinstance(item["source_ref"], str) or item["source_ref"] not in refs):
            return _blocked("PROVIDED_FACTS_PROVENANCE_INVALID")
    if rid["request_ref"] not in refs:
        return _blocked("ORIGINAL_REQUEST_SOURCE_REF_MISSING")
    packet = copy.deepcopy(context)
    packet["schema_version"] = "A1_SEMANTIC_MODEL_INPUT_V1"
    packet["original_request_sha256"] = hashlib.sha256(literal.encode("utf-8")).hexdigest()
    packet["semantic_instruction_ref"] = "skills/programming_analysis/steps/a1/prompts/semantic_interpretation_v1.md"
    packet["task"] = "EXTRACT_REQUEST_CONTEXT_CANDIDATE"
    return packet


def evaluate_model_candidate(packet: Any, proposed: Any) -> dict:
    """Validate *external model* candidate against the original and received refs."""
    if not isinstance(packet, dict) or packet.get("schema_version") != "A1_SEMANTIC_MODEL_INPUT_V1":
        return _blocked("PREPARED_TASK_REQUIRED")
    if (not isinstance(packet.get("original_request"), str)
            or packet.get("original_request_sha256") != hashlib.sha256(
                packet["original_request"].encode("utf-8")
            ).hexdigest()):
        return _blocked("PREPARED_LITERAL_HASH_INVALID")
    if not isinstance(proposed, dict):
        return _blocked("MODEL_CANDIDATE_NOT_OBJECT")
    required = {
        "schema_version", "original_request_sha256", "objective", "target_hints",
        "source_refs", "provided_facts", "constraints", "ambiguities",
        "declared_intent_kind", "observed_actions"
    }
    if set(proposed) != required or proposed["schema_version"] != "A1_SEMANTIC_MODEL_RESULT_V1":
        return _blocked("MODEL_CANDIDATE_CONTRACT_INVALID")
    if proposed["original_request_sha256"] != packet["original_request_sha256"]:
        return _blocked("MODEL_LITERAL_BINDING_MISMATCH")
    if not all(_valid_strings(proposed[key]) for key in ("target_hints", "source_refs", "constraints")):
        return _blocked("MODEL_COLLECTIONS_INVALID")
    if not isinstance(proposed["objective"], dict) or any(
        not isinstance(proposed["objective"].get(k), str) or not proposed["objective"][k].strip()
        for k in ("problem_statement", "desired_outcome")
    ):
        return _blocked("MODEL_OBJECTIVE_INVALID")
    if (not isinstance(proposed["declared_intent_kind"], str)
            or proposed["declared_intent_kind"] not in ALLOWED_INTENTS):
        return _blocked("MODEL_INTENT_INVALID")
    # The interpreter may improve wording, but cannot discard received data.
    for key in ("target_hints", "source_refs", "constraints"):
        if not set(packet[key]).issubset(set(proposed[key])):
            return _blocked("RECEIVED_CONTEXT_DROPPED_" + key.upper())
    # New identifiers or authority refs may never be inferred by the model.
    if set(proposed["source_refs"]) != set(packet["source_refs"]):
        return _blocked("SOURCE_REF_INVENTED")
    unexpected_targets = set(proposed["target_hints"]) - set(packet["target_hints"])
    if any(not isinstance(target, str) or target.casefold() not in packet["original_request"].casefold()
           for target in unexpected_targets):
        return _blocked("TARGET_IDENTIFIER_INVENTED")
    if not isinstance(proposed["provided_facts"], list):
        return _blocked("MODEL_FACTS_INVALID")
    if any(not isinstance(fact, dict) or set(fact) != {"fact_code", "value", "source_ref"}
           for fact in proposed["provided_facts"]):
        return _blocked("MODEL_FACTS_INVALID")
    have_facts = {digest(fact) for fact in proposed["provided_facts"]}
    if not {digest(fact) for fact in packet["provided_facts"]}.issubset(have_facts):
        return _blocked("RECEIVED_FACTS_DROPPED")
    if any(fact["source_ref"] not in proposed["source_refs"] for fact in proposed["provided_facts"]):
        return _blocked("MODEL_FACT_SOURCE_NOT_DECLARED")
    # No new externally sourced facts from the producer.
    if len(have_facts) != len({digest(fact) for fact in packet["provided_facts"]}):
        return _blocked("UNATTESTED_FACT_INVENTED")
    literal = packet["original_request"]
    mentions = proposed["observed_actions"]
    if not isinstance(mentions, list) or not mentions:
        return _blocked("MODEL_ACTION_EVIDENCE_MISSING")
    seen = set()
    for action in mentions:
        if not isinstance(action, dict) or set(action) != {"id", "literal_span", "normalized_action"}:
            return _blocked("MODEL_ACTION_EVIDENCE_INVALID")
        if any(not isinstance(action[k], str) or not action[k].strip() for k in action):
            return _blocked("MODEL_ACTION_EVIDENCE_INVALID")
        if action["id"] in seen or action["literal_span"].casefold() not in literal.casefold():
            return _blocked("MODEL_ACTION_SPAN_NOT_GROUNDED")
        seen.add(action["id"])
    if not isinstance(proposed["ambiguities"], list):
        return _blocked("MODEL_AMBIGUITIES_INVALID")
    a1_input = {
        "business": packet["business"],
        "original_request": literal,
        "input_mode": "SEMANTIC_CANDIDATE",
        "request_identity": packet["request_identity"],
        "objective": proposed["objective"],
        "target_hints": proposed["target_hints"],
        "source_refs": proposed["source_refs"],
        "provided_facts": proposed["provided_facts"],
        "constraints": proposed["constraints"],
        "ambiguities": proposed["ambiguities"],
        "declared_intent_kind": proposed["declared_intent_kind"],
    }
    result = _load_runner().run(a1_input)
    if result["status"] != "REQUIRES_SEMANTIC_REVIEW":
        if result["status"] in {"NEED_MORE_EVIDENCE", "REQUIRES_DECISION"}:
            return {
                "schema_version": SCHEMA,
                "status": result["status"],
                "blocking_codes": list(result["blocking_codes"]),
                "candidate_sha256": digest(proposed),
                "original_request_sha256": packet["original_request_sha256"],
                "observed_actions": copy.deepcopy(mentions),
                "a1_result": result,
                "semantic_verified": False,
                "operationally_verified": False,
                "next_capability": None,
            }
        return _blocked("A1_CORE_REQUIRES_ATTENTION_" + result["status"])
    return {
        "schema_version": SCHEMA,
        "status": "REQUIRES_INDEPENDENT_SEMANTIC_REVIEW",
        "blocking_codes": [],
        "candidate_sha256": digest(proposed),
        "original_request_sha256": packet["original_request_sha256"],
        "observed_actions": copy.deepcopy(mentions),
        "original_request": literal,
        "a1_result": result,
        "semantic_verified": False,
        "operationally_verified": False,
        "next_capability": None,
    }


def validate_review(candidate: Any, review: Any) -> dict:
    """Check judge *claims* only; it NEVER attests actual judge independence."""
    if not isinstance(candidate, dict) or candidate.get("status") != "REQUIRES_INDEPENDENT_SEMANTIC_REVIEW":
        return {"status": "BLOCKED", "blocking_codes": ["SEMANTIC_CANDIDATE_REQUIRED"],
                "independence_verified": False, "next_capability": None}
    if not isinstance(review, dict) or set(review) != {
        "candidate_sha256", "original_request_sha256", "status", "covered_action_ids",
        "unsupported_claims", "omitted_actions", "scope_expansions", "review_ref",
        "independently_observed_actions"
    }:
        return {"status": "BLOCKED", "blocking_codes": ["REVIEW_CONTRACT_INVALID"],
                "independence_verified": False, "next_capability": None}
    errors = []
    if review["candidate_sha256"] != candidate["candidate_sha256"]:
        errors.append("REVIEW_CANDIDATE_SHA_MISMATCH")
    if review["original_request_sha256"] != candidate["original_request_sha256"]:
        errors.append("REVIEW_LITERAL_SHA_MISMATCH")
    expected = {row["id"] for row in candidate["observed_actions"]}
    covered = review["covered_action_ids"]
    if not _valid_strings(covered) or set(covered) != expected or len(covered) != len(set(covered)):
        errors.append("REVIEW_ACTION_COVERAGE_MISMATCH")
    if any(not isinstance(review[key], list) for key in
           ("unsupported_claims", "omitted_actions", "scope_expansions")):
        errors.append("REVIEW_FINDINGS_INVALID")
    elif any(review[key] for key in ("unsupported_claims", "omitted_actions", "scope_expansions")):
        errors.append("REVIEW_HAS_MATERIAL_FINDINGS")
    independent = review["independently_observed_actions"]
    if not isinstance(independent, list) or not independent:
        errors.append("INDEPENDENT_ACTIONS_MISSING")
    else:
        actual = set()
        for row in independent:
            if (not isinstance(row, dict)
                    or set(row) != {"literal_span", "normalized_action"}
                    or any(not isinstance(v, str) or not v.strip() for v in row.values())
                    or row["literal_span"].casefold() not in candidate["original_request"].casefold()):
                errors.append("INDEPENDENT_ACTION_EVIDENCE_INVALID")
                break
            actual.add((row["literal_span"].casefold(), row["normalized_action"].casefold()))
        produced = {
            (row["literal_span"].casefold(), row["normalized_action"].casefold())
            for row in candidate["observed_actions"]
        }
        if actual != produced:
            errors.append("INDEPENDENT_ACTION_RECONCILIATION_MISMATCH")
    if review["status"] != "PASS":
        errors.append("REVIEW_VERDICT_NOT_PASS")
    if not isinstance(review["review_ref"], str) or not review["review_ref"].strip():
        errors.append("REVIEW_REF_MISSING")
    return {
        "status": "BLOCKED" if errors else "REVIEW_STRUCTURAL_PASS_ONLY",
        "blocking_codes": sorted(set(errors)),
        "candidate_sha256": candidate["candidate_sha256"],
        "original_request_sha256": candidate["original_request_sha256"],
        "independence_verified": False,
        "operationally_verified": False,
        "next_capability": None,
    }
