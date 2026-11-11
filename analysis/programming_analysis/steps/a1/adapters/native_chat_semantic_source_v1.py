"""A1 GPT_NATIVE / CLAUDE_NATIVE source-only handoff and capture.

Reuses the repository's established native-chat mode/provider pairs and same-chat
capture pattern. This module NEVER invokes a model, API, Router, profile, RUN or
Supabase. The current chat authors a semantic candidate separately.

Canonical precedents:
- skills/profile_creator/validators/profile_updater_same_chat_v02.py
- supabase/functions/lf-profiles-governance-caller-v1/profile_continuation.ts

A stored native-chat capture is an untrusted proposal, NOT provider attestation,
and never proves semantic reviewer independence.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

A1 = Path(__file__).resolve().parents[1]
CONTRACT = A1 / "schemas/intent_analysis_candidate_v1.schema.json"
PROTOCOL = A1 / "semantic_model_protocol_candidate_v1.md"
ROUTE = A1 / "contracts/a1_native_semantic_route_v1.json"
ROUTE_CONTRACT_CODE = "A1_NATIVE_SEMANTIC_ROUTE_V1"
ROUTE_CODE = "PROGRAMMING_ANALYSIS_LF/A1/SEMANTIC_NATIVE_AUTHORING"
OWNER_SKILL = "PROGRAMMING_ANALYSIS_LF"
OWNER_STEP = "A1"
MODE_BINDINGS = {
    "GPT_NATIVE": ("OPENAI_CHATGPT_NATIVE", "CHATGPT_CURRENT_CONVERSATION"),
    "CLAUDE_NATIVE": ("ANTHROPIC_CLAUDE_NATIVE", "CLAUDE_CURRENT_CONVERSATION"),
}
HANDOFF_SCHEMA = "A1_NATIVE_CHAT_SEMANTIC_HANDOFF_CANDIDATE_V1"
CAPTURE_SCHEMA = "A1_NATIVE_CHAT_SEMANTIC_CAPTURE_CANDIDATE_V1"
HANDOFF_KEYS = frozenset({
    "schema_version", "route_contract_code", "route_code", "owner_skill_code",
    "owner_step_code", "route_contract_sha256", "business", "executor_mode",
    "executor_provider", "current_surface", "conversation_scope",
    "session_creation", "api_invocation", "raw_request", "input_sha256",
    "semantic_contract_sha256", "semantic_protocol_sha256",
    "reviewer_independence_verified", "source_authority_verified",
    "runtime_qualified", "handoff_sha256",
})
CAPTURE_KEYS = frozenset({
    "schema_version", "route_contract_code", "route_code", "owner_skill_code",
    "owner_step_code", "route_contract_sha256", "handoff_sha256",
    "input_sha256", "executor_mode", "executor_provider", "current_surface",
    "intent_analysis", "intent_sha256", "capture_state",
    "runtime_provider_attested", "reviewer_independence_verified",
    "next_authority", "no_run_created", "capture_sha256",
})


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_sha(value: Any) -> str:
    return _text_sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _require(value: bool, code: str) -> None:
    if not value:
        raise ValueError(code)




def _route_contract() -> dict:
    """Read the A1-specific versioned route, not the Profile Updater contract."""
    _require(ROUTE.is_file(), "NATIVE_A1_ROUTE_CONTRACT_MISSING")
    route = json.loads(ROUTE.read_text(encoding="utf-8"))
    _require(route.get("contract_code") == ROUTE_CONTRACT_CODE
             and route.get("route_code") == ROUTE_CODE
             and route.get("contract_owner") == {
                 "skill_code": OWNER_SKILL,
                 "step_code": OWNER_STEP,
                 "scope": "INTERNAL_A1_SEMANTIC_SOURCE_ONLY"
             }, "NATIVE_A1_ROUTE_CONTRACT_DRIFT")
    boundaries = route.get("operation_boundary") or {}
    _require(boundaries.get("runtime_operation_code") is None
             and all(boundaries.get(key) is False for key in (
                 "updater_operation_allowed", "profile_operation_allowed",
                 "skill_child_run_allowed", "supabase_write_allowed",
                 "router_dispatch_allowed")),
             "NATIVE_A1_OPERATION_BOUNDARY_DRIFT")
    transport = route.get("native_transport") or {}
    expected = [{"executor_mode": mode, "executor_provider": provider,
                 "current_surface": surface} for mode, (provider, surface) in MODE_BINDINGS.items()]
    _require(transport.get("transport_kind") == "EXISTING_CONVERSATION_NATIVE_AUTHORING"
             and transport.get("allowed_bindings") == expected
             and all(transport.get(key) is False for key in (
                 "remote_api_allowed", "llama_allowed", "session_creation_allowed")),
             "NATIVE_A1_PROVIDER_ROUTE_DRIFT")
    artifacts = route.get("artifacts") or {}
    _require(artifacts.get("intent_candidate_schema") == "A1_INTENT_ANALYSIS_CANDIDATE_V1"
             and artifacts.get("canonical_context_schema") == "REQUEST_CONTEXT_V1"
             and artifacts.get("a1_output_schema") == "A1_INTERNAL_STEP_CANDIDATE_RESULT_V1"
             and artifacts.get("a2_depth_signals") == "EVIDENCE_DERIVED_NINE_DEPTH_SIGNALS_REQUIRED",
             "NATIVE_A1_ARTIFACT_CONTRACT_DRIFT")
    envelope = route.get("envelope_contract") or {}
    _require(envelope.get("handoff_required_fields") == sorted(HANDOFF_KEYS)
             and envelope.get("capture_required_fields") == sorted(CAPTURE_KEYS)
             and envelope.get("unknown_fields") == "REJECT_EVEN_IF_SHA_RESIGNED",
             "NATIVE_A1_ENVELOPE_CONTRACT_DRIFT")
    return route


def _require_a1_route(handoff: dict) -> None:
    """Reject Updater and foreign skill routes even if caller recomputes all SHA hashes."""
    _route_contract()
    _require(handoff.get("schema_version") == HANDOFF_SCHEMA
             and handoff.get("route_contract_code") == ROUTE_CONTRACT_CODE
             and handoff.get("route_code") == ROUTE_CODE
             and handoff.get("owner_skill_code") == OWNER_SKILL
             and handoff.get("owner_step_code") == OWNER_STEP,
             "NATIVE_A1_WRONG_SKILL_OR_ROUTE")
    _require(handoff.get("route_contract_sha256") ==
             _text_sha(ROUTE.read_text(encoding="utf-8")),
             "NATIVE_A1_ROUTE_CONTRACT_SOURCE_DRIFT")
    _require(not any(key in handoff for key in (
        "operation_code", "profile_slug", "profile_code", "profile_plan_sha256",
        "evolution_mode", "selected_method_ids", "run_id", "execution_id",
        "runtime_target", "queue_request_id")),
             "NATIVE_A1_UPDATER_OR_RUNTIME_FIELDS_FORBIDDEN")
    _require(set(handoff) == HANDOFF_KEYS, "NATIVE_A1_HANDOFF_FIELDS_INVALID")
    _require(handoff.get("business") == "LF"
             and handoff.get("conversation_scope") == "EXISTING_CONVERSATION_ONLY"
             and handoff.get("session_creation") is False
             and handoff.get("api_invocation") is False
             and handoff.get("reviewer_independence_verified") is False
             and handoff.get("source_authority_verified") is False
             and handoff.get("runtime_qualified") is False,
             "NATIVE_A1_HANDOFF_FALSE_AUTHORITY")


def _require_a1_capture(handoff: dict, capture: dict) -> None:
    _require(capture.get("schema_version") == CAPTURE_SCHEMA
             and capture.get("route_contract_code") == ROUTE_CONTRACT_CODE
             and capture.get("route_code") == ROUTE_CODE
             and capture.get("owner_skill_code") == OWNER_SKILL
             and capture.get("owner_step_code") == OWNER_STEP
             and capture.get("route_contract_sha256") ==
                 handoff.get("route_contract_sha256"),
             "NATIVE_A1_CAPTURE_WRONG_SKILL_OR_ROUTE")
    _require(not any(key in capture for key in (
        "operation_code", "profile_slug", "profile_code",
        "evolution_mode", "selected_method_ids", "run_id", "execution_id",
        "runtime_target", "queue_request_id")),
             "NATIVE_A1_CAPTURE_UPDATER_FIELDS_FORBIDDEN")
    _require(set(capture) == CAPTURE_KEYS, "NATIVE_A1_CAPTURE_FIELDS_INVALID")
    _require(capture.get("capture_state") == "SOURCE_BOUND_NATIVE_CHAT_RAW_UNATTESTED"
             and capture.get("next_authority") == "INDEPENDENT_SEMANTIC_REVIEW_REQUIRED"
             and capture.get("runtime_provider_attested") is False
             and capture.get("reviewer_independence_verified") is False
             and capture.get("no_run_created") is True,
             "NATIVE_A1_CAPTURE_FALSE_AUTHORITY")


def freeze_handoff(*, raw_request: str, business: str, executor_mode: str,
                   executor_provider: str, current_surface: str) -> dict:
    """Build an immutable source-bound AUTHORING request, not a run or execution."""
    _require(isinstance(raw_request, str) and bool(raw_request.strip()),
             "NATIVE_A1_RAW_REQUEST_REQUIRED")
    _require(business == "LF", "NATIVE_A1_BUSINESS_SCOPE_NOT_LF")
    _require(executor_mode in MODE_BINDINGS, "NATIVE_A1_EXECUTOR_MODE_INVALID")
    expected_provider, expected_surface = MODE_BINDINGS[executor_mode]
    _require(executor_provider == expected_provider, "NATIVE_A1_PROVIDER_MODE_MISMATCH")
    _require(current_surface == expected_surface, "NATIVE_A1_CURRENT_SURFACE_MISMATCH")
    _require(CONTRACT.is_file() and PROTOCOL.is_file(),
             "NATIVE_A1_CONTRACT_OR_PROTOCOL_MISSING")
    _route_contract()
    frozen = {
        "route_contract_code": ROUTE_CONTRACT_CODE,
        "route_code": ROUTE_CODE,
        "owner_skill_code": OWNER_SKILL,
        "owner_step_code": OWNER_STEP,
        "route_contract_sha256": _text_sha(ROUTE.read_text(encoding="utf-8")),
        "schema_version": HANDOFF_SCHEMA,
        "business": business,
        "executor_mode": executor_mode,
        "executor_provider": executor_provider,
        "current_surface": current_surface,
        "conversation_scope": "EXISTING_CONVERSATION_ONLY",
        "session_creation": False,
        "api_invocation": False,
        "raw_request": raw_request,
        "input_sha256": _text_sha(raw_request),
        "semantic_contract_sha256": _text_sha(CONTRACT.read_text(encoding="utf-8")),
        "semantic_protocol_sha256": _text_sha(PROTOCOL.read_text(encoding="utf-8")),
        "reviewer_independence_verified": False,
        "source_authority_verified": False,
        "runtime_qualified": False,
    }
    frozen["handoff_sha256"] = _json_sha(frozen)
    return frozen


def capture_candidate(*, handoff: dict, proposed_intent: dict,
                      current_surface: str) -> dict:
    """Bind actual native-authored proposal bytes to a frozen source request.

    Does not authenticate which model authored the supplied candidate.
    """
    _require(isinstance(handoff, dict)
             and handoff.get("schema_version") == HANDOFF_SCHEMA,
             "NATIVE_A1_HANDOFF_INVALID")
    _require_a1_route(handoff)
    _require(_json_sha({k: v for k, v in handoff.items()
                        if k != "handoff_sha256"}) == handoff.get("handoff_sha256"),
             "NATIVE_A1_HANDOFF_TAMPERED")
    expected = MODE_BINDINGS.get(handoff.get("executor_mode"))
    _require(expected is not None and
             (handoff.get("executor_provider"), current_surface) == expected and
             handoff.get("current_surface") == current_surface,
             "NATIVE_A1_CROSS_PROVIDER_CAPTURE_FORBIDDEN")
    _require(handoff.get("conversation_scope") == "EXISTING_CONVERSATION_ONLY"
             and handoff.get("session_creation") is False
             and handoff.get("api_invocation") is False,
             "NATIVE_A1_NON_NATIVE_TRANSPORT_FORBIDDEN")
    _require(handoff.get("input_sha256") == _text_sha(handoff.get("raw_request", "")),
             "NATIVE_A1_INPUT_HASH_DRIFT")
    _require(handoff.get("semantic_contract_sha256") ==
             _text_sha(CONTRACT.read_text(encoding="utf-8"))
             and handoff.get("semantic_protocol_sha256") ==
             _text_sha(PROTOCOL.read_text(encoding="utf-8")),
             "NATIVE_A1_SOURCE_PROTOCOL_DRIFT")
    _require(isinstance(proposed_intent, dict), "NATIVE_A1_CANDIDATE_NOT_OBJECT")
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))
    _require(Draft202012Validator(schema).is_valid(proposed_intent),
             "NATIVE_A1_CANDIDATE_SCHEMA_INVALID")
    capture = {
        "schema_version": CAPTURE_SCHEMA,
        "route_contract_code": ROUTE_CONTRACT_CODE,
        "route_code": ROUTE_CODE,
        "owner_skill_code": OWNER_SKILL,
        "owner_step_code": OWNER_STEP,
        "route_contract_sha256": handoff["route_contract_sha256"],
        "handoff_sha256": handoff["handoff_sha256"],
        "input_sha256": handoff["input_sha256"],
        "executor_mode": handoff["executor_mode"],
        "executor_provider": handoff["executor_provider"],
        "current_surface": current_surface,
        "intent_analysis": copy.deepcopy(proposed_intent),
        "intent_sha256": _json_sha(proposed_intent),
        "capture_state": "SOURCE_BOUND_NATIVE_CHAT_RAW_UNATTESTED",
        "runtime_provider_attested": False,
        "reviewer_independence_verified": False,
        "next_authority": "INDEPENDENT_SEMANTIC_REVIEW_REQUIRED",
        "no_run_created": True,
    }
    capture["capture_sha256"] = _json_sha(capture)
    return capture


def producer_from_capture(handoff: dict, capture: dict):
    """Prepare input for the EXISTING A1 semantic validator; no model invocation."""
    _require(isinstance(handoff, dict) and isinstance(capture, dict),
             "NATIVE_A1_CAPTURE_INPUT_INVALID")
    _require_a1_route(handoff)
    _require_a1_capture(handoff, capture)
    _require(capture.get("schema_version") == CAPTURE_SCHEMA
             and capture.get("handoff_sha256") == handoff.get("handoff_sha256")
             and capture.get("input_sha256") == handoff.get("input_sha256")
             and capture.get("executor_mode") == handoff.get("executor_mode")
             and capture.get("executor_provider") == handoff.get("executor_provider"),
             "NATIVE_A1_CAPTURE_BINDING_INVALID")
    expected = MODE_BINDINGS.get(handoff.get("executor_mode"))
    _require(expected is not None
             and handoff.get("executor_provider") == expected[0]
             and handoff.get("current_surface") == expected[1]
             and capture.get("current_surface") == expected[1],
             "NATIVE_A1_MODE_BINDING_INVALID")
    _require(_json_sha({k: v for k, v in handoff.items()
                        if k != "handoff_sha256"}) == handoff.get("handoff_sha256"),
             "NATIVE_A1_HANDOFF_TAMPERED")
    _require(handoff.get("semantic_contract_sha256") ==
             _text_sha(CONTRACT.read_text(encoding="utf-8"))
             and handoff.get("semantic_protocol_sha256") ==
             _text_sha(PROTOCOL.read_text(encoding="utf-8")),
             "NATIVE_A1_SOURCE_PROTOCOL_DRIFT")
    _require(_json_sha({k: v for k, v in capture.items()
                        if k != "capture_sha256"}) == capture.get("capture_sha256")
             and _json_sha(capture.get("intent_analysis")) == capture.get("intent_sha256"),
             "NATIVE_A1_CAPTURE_DIGEST_DRIFT")
    _require(capture.get("runtime_provider_attested") is False
             and capture.get("reviewer_independence_verified") is False
             and capture.get("no_run_created") is True,
             "NATIVE_A1_CAPTURE_FALSE_AUTHORITY")
    _require(handoff.get("input_sha256") == _text_sha(handoff.get("raw_request", "")),
             "NATIVE_A1_HANDOFF_INPUT_DRIFT")
    snapshot = copy.deepcopy(capture["intent_analysis"])

    def producer(raw_text: str) -> dict:
        _require(raw_text == handoff["raw_request"], "NATIVE_A1_RAW_REQUEST_DRIFT")
        return copy.deepcopy(snapshot)

    return producer
