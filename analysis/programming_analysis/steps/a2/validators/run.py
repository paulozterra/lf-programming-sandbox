"""A2 candidate: consume A1 and PROJECT the existing canonical depth policy.

No classifier engine, no Router, LLM, skill activation, source-attestation
or runtime write. Evidence values arrive typed from an external consumer.
A2 itself cannot assert the provenance or independently review the model.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

BASE = Path(__file__).resolve().parents[1]
REPO = BASE.parents[3]
CONTRACT_PATH = REPO / (
    "sandbox/lf_contract_gate_test/programming_agent_four_stage/"
    "wave1_boundary_contracts/analysis_change_classification_contract_v1.json"
)
A1_SCHEMA = REPO / "skills/programming_analysis/steps/a1/schemas/output.schema.json"
REQUEST_SCHEMA = REPO / (
    "sandbox/lf_contract_gate_test/programming_agent_four_stage/"
    "wave1_boundary_contracts/analysis_request_context_v1.schema.json"
)
SCHEMA = "A2_INTERNAL_STEP_CANDIDATE_RESULT_V1"
SKILL = "PROGRAMMING_ANALYSIS_LF"
SIGNAL_SCHEMA = "ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid(value: Any, schema: dict) -> bool:
    return Draft202012Validator(schema).is_valid(value)


def _blocked(code: str) -> dict:
    result = {
        "schema_version": SCHEMA, "skill_code": SKILL, "step_code": "A2",
        "status": "BLOCKED", "blocking_codes": [code], "classification": None,
        "business": None,
        "source_attested": False, "independent_judge_verified": False,
        "operationally_integrated": False, "effects_executed": False,
        "next_step": None,
    }
    # A malformed fail-closed envelope is a hard error, not an admissible result.
    if not _valid(result, _json(BASE / "schemas/output.schema.json")):
        raise ValueError("A2_BLOCKED_OUTPUT_SCHEMA_DRIFT")
    return result


def _signals_valid(signals: Any, policy: dict) -> bool:
    allowed = policy["signals"]
    if not isinstance(signals, dict) or set(signals) != set(allowed):
        return False
    for key, kind in allowed.items():
        value = signals[key]
        if isinstance(kind, list):
            if not isinstance(value, str) or value not in kind:
                return False
        elif kind == "BOOLEAN":
            if type(value) is not bool:
                return False
        elif kind == "BOOLEAN_OR_UNKNOWN":
            if not (type(value) is bool or value == "UNKNOWN"):
                return False
        elif kind == "NON_NEGATIVE_INTEGER":
            if type(value) is not int or value < 0:
                return False
        else:
            return False  # Fail closed if the canonical contract evolves.
    return True


def _literal(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _match(predicate: str, signals: dict) -> bool:
    """Interpret only the simple DSL in A2's existing canonical JSON policy."""
    expr = re.fullmatch(r"([a-z_]+)=([A-Z_]+|true|false|[0-9]+)", predicate)
    if expr:
        key, value = expr.groups()
        if key not in signals:
            raise ValueError("UNKNOWN_CANONICAL_PREDICATE_FIELD")
        return _literal(signals[key]) == value
    expr = re.fullmatch(r"([a-z_]+) in \[([A-Z_,]+)\]", predicate)
    if expr:
        key, values = expr.groups()
        if key not in signals:
            raise ValueError("UNKNOWN_CANONICAL_PREDICATE_FIELD")
        return _literal(signals[key]) in values.split(",")
    expr = re.fullmatch(r"([a-z_]+)>0", predicate)
    if expr:
        key = expr.group(1)
        if key not in signals or type(signals[key]) is not int:
            raise ValueError("UNKNOWN_CANONICAL_PREDICATE_FIELD")
        return signals[key] > 0
    raise ValueError("UNRECOGNIZED_CANONICAL_PREDICATE")


def _depth(signals: dict, policy: dict) -> tuple[str, list[str]]:
    high = [p for p in policy["L3_if_any"] if _match(p, signals)]
    if high:
        return "L3", high
    medium = [p for p in policy["L2_if_no_L3_and_any"] if _match(p, signals)]
    if medium:
        return "L2", medium
    low = policy["L1_requires_all"]
    if low and all(_match(p, signals) for p in low):
        return "L1", list(low)
    raise ValueError("CANONICAL_DEPTH_POLICY_COVERAGE_GAP")


def run(a1_result: Any, signal_bundle: Any) -> dict:
    """Return a candidate classification, never an A3 admission."""
    if not isinstance(a1_result, dict) or not _valid(a1_result, _json(A1_SCHEMA)):
        return _blocked("A1_OUTPUT_CONTRACT_INVALID")
    raw_semantic = a1_result.get("interpretation_state") == "SEMANTIC_REVIEWED_CANDIDATE"
    legacy_structured = (
        a1_result.get("interpretation_state") == "PRESTRUCTURED_UNATTESTED"
        and a1_result.get("original_request_sha256") is None
    )
    if (a1_result["status"] != "VALID_OUTPUT"
            or a1_result["semantic_review_required"]
            or a1_result["next_capability"] != "A2"
            or not (legacy_structured or raw_semantic)):
        return _blocked("A1_SEMANTIC_OR_STATUS_GATE_UNRESOLVED")
    if raw_semantic:
        intent = a1_result.get("intent_analysis")
        if (not isinstance(intent, dict)
                or not isinstance(a1_result.get("original_request_sha256"), str)
                or not isinstance(a1_result.get("semantic_candidate_sha256"), str)
                or hashlib.sha256(json.dumps(
                    intent, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest() != a1_result["semantic_candidate_sha256"]
                or not isinstance(a1_result.get("semantic_reviewer_ref"), str)
                or a1_result.get("semantic_review_identity_verified") is not False):
            return _blocked("A1_SEMANTIC_CANDIDATE_BINDING_INVALID")
    business = a1_result.get("business")
    if not isinstance(business, str) or not (2 <= len(business) <= 32) or business != business.strip():
        return _blocked("A1_BUSINESS_SCOPE_INVALID")
    # This is the LF-specific skill. A forged valid-shaped A1 payload cannot
    # turn A2 into a SALY classifier, even when its signal bundle agrees.
    if business != "LF":
        return _blocked("A2_BUSINESS_NOT_ENABLED_FOR_SKILL")
    context = a1_result["payload"]
    if not _valid(context, _json(REQUEST_SCHEMA)):
        return _blocked("A1_CANONICAL_CONTEXT_INVALID")
    if not isinstance(signal_bundle, dict) or not isinstance(signal_bundle.get("business"), str) or not signal_bundle["business"].strip():
        return _blocked("A2_BUSINESS_REQUIRED")
    if not _valid(signal_bundle, _json(BASE / "schemas/input.schema.json")):
        # Preserve actionable diagnostics for nested A2 inputs. The full
        # envelope remains fail-closed; neither case is a source attestation.
        if isinstance(signal_bundle, dict):
            refs = signal_bundle.get("evidence_refs")
            if isinstance(refs, list) and (
                not refs or any(not isinstance(x, str) or len(x.strip()) < 3 for x in refs)
                or len(set(x for x in refs if isinstance(x, str))) != len(refs)
            ):
                return _blocked("A2_EVIDENCE_REFS_REQUIRED")
            supplied_signals = signal_bundle.get("depth_signals")
            if isinstance(supplied_signals, dict):
                depth_spec = _json(CONTRACT_PATH).get("classification", {}).get("depth_policy")
                if (isinstance(depth_spec, dict)
                        and isinstance(depth_spec.get("signals"), dict)
                        and not _signals_valid(supplied_signals, depth_spec)):
                    return _blocked("A2_DEPTH_SIGNALS_NOT_TYPED")
        return _blocked("A2_SIGNAL_ENVELOPE_INVALID")
    if not isinstance(signal_bundle, dict) or set(signal_bundle) != {
        "schema_version", "business", "target_ref", "change_type", "target_granularity",
        "nested_parent_ref", "evidence_refs", "depth_signals",
    } or signal_bundle["schema_version"] != SIGNAL_SCHEMA:
        return _blocked("A2_SIGNAL_ENVELOPE_INVALID")

    if signal_bundle["business"] != business:
        return _blocked("A2_BUSINESS_SCOPE_MISMATCH")
    if raw_semantic:
        intent = a1_result["intent_analysis"]
        if (signal_bundle["change_type"] != intent["operation"]["kind"]
                or signal_bundle["target_granularity"] != intent["target"]["artifact_kind"]):
            return _blocked("A2_SEMANTIC_INTENT_DRIFT")
    for fact in context["provided_facts"]:
        if fact["fact_code"] in {"BUSINESS", "BUSINESS_CODE", "TARGET_BUSINESS"}:
            if fact["value"] != business or fact["source_ref"] not in context["source_refs"]:
                return _blocked("A2_BUSINESS_FACT_CONFLICT")
    target = signal_bundle["target_ref"]
    change_type = signal_bundle["change_type"]
    granularity = signal_bundle["target_granularity"]
    parent = signal_bundle["nested_parent_ref"]
    evidence = signal_bundle["evidence_refs"]
    if not isinstance(target, str) or target not in context["target_hints"]:
        return _blocked("A2_TARGET_NOT_PRESENT_IN_A1")
    if (not isinstance(change_type, str) or not change_type.strip()
            or not isinstance(granularity, str) or not granularity.strip()):
        return _blocked("A2_CLASSIFICATION_NOT_EXPLICIT")
    if parent is not None and (not isinstance(parent, str) or not parent.strip()):
        return _blocked("A2_NESTED_PARENT_INVALID")
    if granularity in {"CONTROL", "SECTION"} and parent is None:
        return _blocked("A2_NESTED_PARENT_REQUIRED")
    if parent is not None and (parent == target or parent not in context["target_hints"]):
        return _blocked("A2_NESTED_PARENT_NOT_IN_A1")
    if (not isinstance(evidence, list) or not evidence
            or any(not isinstance(ref, str) or len(ref.strip()) < 3 for ref in evidence)
            or len(set(evidence)) != len(evidence)):
        return _blocked("A2_EVIDENCE_REFS_REQUIRED")

    contract = _json(CONTRACT_PATH)
    if (contract.get("unit") != "A2"
            or contract.get("input_contract") != "REQUEST_CONTEXT_V1"
            or contract.get("output_contract") != "ANALYSIS_CHANGE_CLASSIFICATION_V1"):
        return _blocked("A2_CANONICAL_CONTRACT_DRIFT")
    policy = contract["classification"]["depth_policy"]
    signals = signal_bundle["depth_signals"]
    if not _signals_valid(signals, policy):
        return _blocked("A2_DEPTH_SIGNALS_NOT_TYPED")
    try:
        depth, reasons = _depth(signals, policy)
    except ValueError:
        return _blocked("A2_DEPTH_POLICY_DRIFT")
    if depth == "L1" and any(
        signals[key] in ("UNKNOWN", "UNRESOLVED", "UNKNOWN_FAIL_CLOSED")
        for key in ("materiality_level", "scope_bounded", "authority_state",
                    "reversibility_state", "currentness_decision")
    ):
        return _blocked("A2_UNKNOWN_MATERIAL_CANNOT_BE_L1")
    signal_digest = hashlib.sha256(json.dumps(
        signal_bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    unresolved = (
        signals["materiality_level"] == "UNKNOWN"
        or signals["scope_bounded"] == "UNKNOWN"
        or signals["authority_state"] != "SUFFICIENT"
        or signals["reversibility_state"] == "UNKNOWN"
        or signals["currentness_decision"] not in ("CURRENT", "CURRENT_REBOUND")
        or signals["known_cross_scope_impact"] == "UNKNOWN"
        or signals["unresolved_material_signal_count"] > 0
        or signals["required_specialist_count"] > 0
    )
    # References and signals are supplied, not authenticated by this module.
    result = {
        "schema_version": SCHEMA, "skill_code": SKILL, "step_code": "A2",
        "business": business,
        "status": "NEED_MORE_EVIDENCE" if unresolved else "CANDIDATE_UNATTESTED",
        "blocking_codes": ["A2_TYPED_EVIDENCE_CURRENTNESS_OR_SPECIALIST_PENDING"] if unresolved else [],
        "classification": {
            "schema_version": "ANALYSIS_CHANGE_CLASSIFICATION_V1",
            "change_type": change_type.strip(),
            "target_ref": target,
            "target_granularity": granularity.strip(),
            "nested_parent_ref": parent,
            "depth_level": depth,
            "depth_reason_predicates": reasons,
            "evidence_refs": copy.deepcopy(evidence),
            "signals_sha256": signal_digest,
            "specialist_resolution": "PENDING" if signals["required_specialist_count"] else "NOT_REQUESTED",
        },
        "source_attested": False, "independent_judge_verified": False,
        "operationally_integrated": False, "effects_executed": False,
        "next_step": None,
    }
    # Validate every non-blocked response before exposing the candidate result.
    if not _valid(result, _json(BASE / "schemas/output.schema.json")):
        return _blocked("A2_CANDIDATE_OUTPUT_SCHEMA_DRIFT")
    return result
