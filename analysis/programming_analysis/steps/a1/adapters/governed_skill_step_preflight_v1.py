"""A1 transport envelope preflight; NO model, network, RPC, or write authority.

Consumers may use this on both sides of the already-governed transport.
A successful result is a structural candidate, NEVER a step receipt.
"""
from __future__ import annotations

import copy
import re

OPERATION = "EJECUCION_SKILL_LF"
SKILL = "PROGRAMMING_ANALYSIS_LF"
STEPS = {
    "init_execution": ("execution_id_created",),
    "router": ("router_read", "action"),
    "skill_resolve": ("exact_skill_resolved", "codigo_activo", "skill_identity"),
    "skill_source_read": ("skill_source_ref", "source_revision", "source_authority"),
    "input_validate": ("input_scope", "activation_trigger_match"),
    "execute_skill": ("skill_output", "source_refs"),
    "output_validate": ("output_contract_result", "deterministic_validation"),
    "semantic_judge": ("semantic_judge_result", "unsupported_claims"),
    "report_output": ("result", "skill_code", "execution_id", "no_write_performed"),
}
FIELDS = {
    "schema_version", "operation_code", "target_type", "target_code",
    "execution_id", "step_id", "evidence_ref", "evidence_payload",
    "actor_execution_id",
}
FORBIDDEN = {
    "service_role", "service_role_key", "SUPABASE_SERVICE_ROLE_KEY",
    "trust_validation", "server_trust_context", "authority_approved",
    "step_status", "step_result", "recorded_by_rpc", "mini_judge_result",
    "receipt_verified", "caller_oidc_verified",
}
HASH = re.compile(r"^[0-9a-f]{64}$")
EXECUTION = re.compile(r"^[A-Za-z0-9_.:-]{8,180}$")


def _blocked(code: str) -> dict:
    return {
        "status": "BLOCKED",
        "code": code,
        "authority_verified": False,
        "readback_verified": False,
        "writes_performed": False,
    }


def preflight(request: object) -> dict:
    """Accept only structural evidence; actual authorization is EXTERNAL."""
    if not isinstance(request, dict) or set(request) != FIELDS:
        return _blocked("REQUEST_CONTRACT_INVALID")
    if request["schema_version"] != "A1_GOVERNED_STEP_REQUEST_V1":
        return _blocked("REQUEST_SCHEMA_INVALID")
    if request["operation_code"] != OPERATION or request["target_type"] != "SKILL":
        return _blocked("OPERATION_TARGET_MISMATCH")
    if request["target_code"] != SKILL:
        return _blocked("SKILL_TARGET_MISMATCH")
    if not isinstance(request["execution_id"], str) or not EXECUTION.fullmatch(request["execution_id"]):
        return _blocked("EXECUTION_ID_INVALID")
    if (not isinstance(request["actor_execution_id"], str)
            or request["actor_execution_id"] != request["execution_id"]):
        return _blocked("ACTOR_EXECUTION_BINDING_MISMATCH")
    step = request["step_id"]
    if not isinstance(step, str) or step not in STEPS:
        return _blocked("STEP_NOT_IN_CANONICAL_OPERATION")
    if not isinstance(request["evidence_ref"], str) or not request["evidence_ref"].strip():
        return _blocked("EVIDENCE_REF_MISSING")
    payload = request["evidence_payload"]
    if not isinstance(payload, dict) or FORBIDDEN.intersection(payload):
        return _blocked("UNTRUSTED_AUTHORITY_FIELDS")
    missing = [
        key for key in STEPS[step]
        if key not in payload or payload[key] is None or payload[key] == ""
    ]
    if missing:
        return _blocked("CANONICAL_EVIDENCE_MISSING")
    if payload.get("blocking_codes") not in (None, []):
        return _blocked("DECLARED_BLOCKING_CODES")
    if step == "init_execution":
        # No recorder fallback: generic operation core intentionally forbids init.
        return {
            "status": "REQUIRES_CANONICAL_BEGIN",
            "code": "INIT_STEP_OWNED_BY_OPERATION_BEGIN",
            "step_id": step,
            "authority_verified": False,
            "readback_verified": False,
            "writes_performed": False,
        }
    if step == "skill_resolve" and payload["codigo_activo"] != SKILL:
        return _blocked("SKILL_RESOLVE_CODE_MISMATCH")
    if step == "skill_source_read":
        rev = payload["source_revision"]
        if not isinstance(rev, str) or not (HASH.fullmatch(rev) or re.fullmatch(r"[0-9a-f]{40}", rev)):
            return _blocked("SOURCE_REVISION_INVALID")
    if step == "execute_skill":
        if not isinstance(payload["source_refs"], list) or not payload["source_refs"]:
            return _blocked("SOURCE_REFS_REQUIRED")
    if step == "semantic_judge":
        if not isinstance(payload["unsupported_claims"], list):
            return _blocked("UNSUPPORTED_CLAIMS_INVALID")
        if payload["unsupported_claims"]:
            return _blocked("UNSUPPORTED_CLAIMS_PRESENT")
        # Do not accept a self-reported PASS as independent proof.
        return {
            "status": "REQUIRES_SERVER_SIDE_INDEPENDENT_JUDGE",
            "code": "INDEPENDENCE_AND_ENFORCEMENT_NOT_ATTESTED",
            "step_id": step,
            "authority_verified": False,
            "readback_verified": False,
            "writes_performed": False,
        }
    if step == "report_output":
        if payload["skill_code"] != SKILL or payload["execution_id"] != request["execution_id"]:
            return _blocked("REPORT_IDENTITY_MISMATCH")
        if payload["no_write_performed"] is not True:
            return _blocked("REPORT_EXPECTS_READ_ONLY_SKILL")
    return {
        "status": "PREFLIGHT_ONLY",
        "code": "STRUCTURE_ACCEPTED_NOT_AUTHORIZED",
        "step_id": step,
        "execution_id": request["execution_id"],
        "evidence": copy.deepcopy(payload),
        "authority_verified": False,
        "readback_verified": False,
        "writes_performed": False,
    }


def compare_readback(request: object, persisted: object) -> dict:
    """Compare server rows only; does not prove DB origin of caller-supplied data."""
    checked = preflight(request)
    if checked["status"] not in ("PREFLIGHT_ONLY", "REQUIRES_SERVER_SIDE_INDEPENDENT_JUDGE"):
        return _blocked("PREFLIGHT_BLOCKED")
    if not isinstance(persisted, dict):
        return _blocked("PERSISTED_ROW_MISSING")
    if (persisted.get("execution_id") != request["execution_id"]
            or persisted.get("step_id") != request["step_id"]
            or persisted.get("evidence_ref") != request["evidence_ref"]):
        return _blocked("PERSISTED_IDENTITY_MISMATCH")
    if persisted.get("status") != "STEP_PASS_WITH_EVIDENCE":
        return _blocked("PERSISTED_STATUS_NOT_CLEAN")
    if not isinstance(persisted.get("evidence_payload"), dict):
        return _blocked("PERSISTED_PAYLOAD_MISSING")
    # Some recorder-owned keys are appended by the server. Required originals
    # must remain unchanged; no subset match is interpreted as independent proof.
    if any(persisted["evidence_payload"].get(k) != v for k, v in request["evidence_payload"].items()):
        return _blocked("PERSISTED_EVIDENCE_MISMATCH")
    return {
        "status": "READBACK_SHAPE_MATCH_ONLY",
        "code": "VERIFY_SOURCE_ORIGIN_AND_SERVER_RECEIPT",
        "execution_id": request["execution_id"],
        "step_id": request["step_id"],
        "authority_verified": False,
        "readback_verified": False,
        "writes_performed": False,
    }
