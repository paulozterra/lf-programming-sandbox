"""Source-only reconciliation of existing LF profile -> skill -> skill-operation RUN.

Untrusted data, including an exact-looking DB row, NEVER authenticates itself.
A privileged host must fetch these three rows by exact IDs and attest the
readback/actor before the live A2->A3 gate can use the binding. No writes.
"""
from __future__ import annotations

import re
from typing import Any

SKILL = "PROGRAMMING_ANALYSIS_LF"
SCHEMA = "PROGRAMMING_ANALYSIS_RUN_BUSINESS_BINDING_CANDIDATE_V1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")


def _blocked(code: str) -> dict:
    return {"schema_version": SCHEMA, "status": "BLOCKED", "blocking_codes": [code],
            "business": None, "parent_execution_id": None, "profile_code": None,
            "skill_run_id": None, "child_execution_id": None,
            "source_consistent": False, "readback_authenticated": False,
            "operationally_integrated": False, "a3_allowed": False}


def _good_business(value: Any) -> bool:
    return isinstance(value, str) and 2 <= len(value) <= 32 and value == value.strip()


def _hex(value: Any, matcher=HEX64) -> bool:
    return isinstance(value, str) and matcher.fullmatch(value) is not None


def reconcile(parent: Any, invocation: Any, child: Any,
              actor_parent_execution_id: Any) -> dict:
    """Compare *supplied* readback rows; never promote them to authority."""
    # lf_skill_invoke_v1 completes READ_ONLY / PROPOSE_ONLY invocations without
    # creating a governed EJECUCION_SKILL_LF child. An invocation receipt alone
    # must NEVER be promoted to a 9-step RUN or a native-judge PASS.
    if (isinstance(parent, dict) and isinstance(invocation, dict)
            and child is None and invocation.get("skill_code") == SKILL
            and invocation.get("status") == "COMPLETED"
            and invocation.get("child_execution_id") in (None, "")):
        return _blocked("RUN_GOVERNED_CHILD_ABSENT_READ_ONLY_INVOKER")
    if not all(isinstance(x, dict) for x in (parent, invocation, child)):
        return _blocked("RUN_READBACK_ROWS_REQUIRED")
    pid = parent.get("execution_id")
    if not isinstance(pid, str) or not pid or pid != actor_parent_execution_id:
        return _blocked("RUN_PARENT_ACTOR_BINDING_MISMATCH")
    if parent.get("operation_code") != "EJECUCION_PERFIL_LF" or parent.get("status") != "IN_PROGRESS":
        return _blocked("RUN_PARENT_NOT_ACTIVE_PROFILE")
    business = (parent.get("manifest") or {}).get("business") if isinstance(parent.get("manifest"), dict) else None
    if not _good_business(business):
        return _blocked("RUN_BUSINESS_ROOT_MISSING")
    profile = parent.get("target_code")
    if not isinstance(profile, str) or not profile.strip():
        return _blocked("RUN_PROFILE_IDENTITY_MISSING")
    manifest = parent["manifest"]
    handoff = manifest.get("router_profile_handoff")
    if not isinstance(handoff, dict):
        return _blocked("RUN_ROUTER_HANDOFF_MISSING")
    if handoff.get("business") != business or handoff.get("profile_code") != profile:
        return _blocked("RUN_ROUTER_HANDOFF_SCOPE_MISMATCH")
    req = parent.get("request_sha256")
    if not _hex(req) or handoff.get("request_sha256") != req:
        return _blocked("RUN_REQUEST_IDENTITY_MISMATCH")
    receipt = handoff.get("router_authorization_receipt")
    if not isinstance(receipt, dict):
        return _blocked("RUN_ROUTER_RECEIPT_MISSING")
    if (receipt.get("schema_version") != "LF_ROUTER_PROFILE_AUTHORIZATION_RECEIPT_V1"
            or receipt.get("router") != "ACT-0001"
            or receipt.get("operation_code") != "EJECUCION_PERFIL_LF"
            or receipt.get("action_code") != "PROFILE_EXECUTION"
            or receipt.get("asset_type") != "PERFIL"
            or receipt.get("profile_execution_allowed") is not True):
        return _blocked("RUN_ROUTER_RECEIPT_INVALID")
    if (receipt.get("business") != business or receipt.get("profile_code") != profile
            or receipt.get("request_sha256") != req):
        return _blocked("RUN_ROUTER_RECEIPT_SCOPE_MISMATCH")
    if (not _hex(receipt.get("fingerprint_sha256"))
            or not _hex(receipt.get("gate2_semantic_receipt_sha256"))
            or not _hex(receipt.get("operation_revision_sha256"))
            or not _hex(receipt.get("router_source_md5"), HEX32)):
        return _blocked("RUN_ROUTER_RECEIPT_DIGEST_INVALID")
    srid = invocation.get("skill_run_id")
    if (not isinstance(srid, str) or not srid
            or invocation.get("skill_code") != SKILL
            or invocation.get("parent_execution_id") != pid
            or invocation.get("profile_code") != profile
            or invocation.get("status") != "COMPLETED"):
        return _blocked("RUN_SKILL_INVOCATION_MISMATCH")
    child_id = invocation.get("child_execution_id")
    if (not isinstance(child_id, str) or not child_id
            or not _hex(invocation.get("input_sha256"))
            or not isinstance(invocation.get("evidence_ref"), str)
            or re.fullmatch(r"SKILLRUN:" + re.escape(srid) + r":[0-9a-f]{64}", invocation["evidence_ref"]) is None):
        return _blocked("RUN_SKILL_INVOCATION_EVIDENCE_INVALID")
    if (child.get("execution_id") != child_id
            or child.get("operation_code") != "EJECUCION_SKILL_LF"
            or child.get("target_code") != SKILL
            or child.get("created_by_execution_id") != pid
            or child.get("request_sha256") != req
            or child.get("status") not in {"IN_PROGRESS", "COMPLETED"}):
        return _blocked("RUN_SKILL_CHILD_IDENTITY_MISMATCH")
    child_manifest = child.get("manifest")
    linked = child_manifest.get("profile_handoff") if isinstance(child_manifest, dict) else None
    if (not isinstance(linked, dict) or linked.get("source_execution_id") != pid
            or linked.get("skill_run_id") != srid):
        return _blocked("RUN_SKILL_CHILD_HANDOFF_MISMATCH")
    return {"schema_version": SCHEMA, "status": "CANDIDATE_CONSISTENT", "blocking_codes": [],
            "business": business, "parent_execution_id": pid, "profile_code": profile,
            "skill_run_id": srid, "child_execution_id": child_id,
            "source_consistent": True, "readback_authenticated": False,
            "operationally_integrated": False, "a3_allowed": False}
