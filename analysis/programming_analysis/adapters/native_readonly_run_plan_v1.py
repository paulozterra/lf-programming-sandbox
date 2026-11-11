"""Candidate, source-only planner for native READ_ONLY skill RUN.

No DB access, invoker call, permission grant, receipt signing, or A3 dispatch.
All supplied records are UNTRUSTED; a governed host must read and attest them.
"""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy

SKILL = "PROGRAMMING_ANALYSIS_LF"
OP = "EJECUCION_SKILL_LF"
REPO = "cristhianlujan/claude-persona-lf-patch"
PATH = "skills/programming_analysis/SKILL.md"
SCHEMA = "PROGRAMMING_ANALYSIS_NATIVE_READONLY_RUN_PLAN_CANDIDATE_V1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def block(code):
    return dict(schema_version=SCHEMA, status="BLOCKED", blocking_codes=[code],
                reservation_args=None, expected_step0=None,
                host_attested=False, reservation_executed=False,
                step0_recorded=False, readback_authenticated=False, a3_allowed=False)


def _ok_hex(x, pat=HEX64):
    return isinstance(x, str) and pat.fullmatch(x) is not None


def _good_business(x):
    return isinstance(x, str) and 2 <= len(x) <= 32 and x == x.strip()


def plan(parent, catalog, asset, authority, router, source, caller, input_sha256, actor_execution_id):
    """Produce a structural proposal, NEVER authorization to write."""
    if not all(isinstance(x, dict) for x in (parent, catalog, asset, authority, router, source, caller)):
        return block("READBACK_CONTEXT_REQUIRED")
    if (parent.get("operation_code") != "EJECUCION_PERFIL_LF" or parent.get("status") != "IN_PROGRESS"
            or parent.get("execution_id") != actor_execution_id or parent.get("target_type") != "PERFIL"):
        return block("PARENT_SCOPE_NOT_AUTHORIZED")
    pid, prof, req = parent.get("execution_id"), parent.get("target_code"), parent.get("request_sha256")
    if not isinstance(pid, str) or not pid or not isinstance(prof, str) or not prof or not _ok_hex(req):
        return block("PARENT_IDENTITY_INVALID")
    m = parent.get("manifest")
    if not isinstance(m, dict) or not _good_business(m.get("business")):
        return block("PARENT_BUSINESS_MISSING")
    business = m["business"]
    handoff = m.get("router_profile_handoff")
    receipt = handoff.get("router_authorization_receipt") if isinstance(handoff, dict) else None
    if not isinstance(receipt, dict) or not isinstance(handoff, dict):
        return block("PARENT_ROUTER_RECEIPT_MISSING")
    if (handoff.get("business") != business or handoff.get("profile_code") != prof
            or handoff.get("request_sha256") != req or receipt.get("business") != business
            or receipt.get("profile_code") != prof or receipt.get("request_sha256") != req):
        return block("PARENT_ROUTER_SCOPE_CONFLICT")
    if (receipt.get("router") != "ACT-0001" or receipt.get("operation_code") != "EJECUCION_PERFIL_LF"
            or receipt.get("action_code") != "PROFILE_EXECUTION" or receipt.get("asset_type") != "PERFIL"
            or receipt.get("schema_version") != "LF_ROUTER_PROFILE_AUTHORIZATION_RECEIPT_V1"
            or receipt.get("profile_execution_allowed") is not True
            or receipt.get("effect_authority") is not False):
        return block("PARENT_ROUTER_AUTHORIZATION_INVALID")
    if (router.get("asset_type") != "SKILL" or router.get("action_code") != "SKILL_EXECUTION"
            or router.get("operation_code") != OP or router.get("write_allowed") is not False
            or router.get("status") != "ACTIVE"):
        return block("SKILL_ROUTER_ROUTE_INVALID")
    if (catalog.get("skill_code") != SKILL or catalog.get("required_operation") != OP
            or catalog.get("effect") != "READ_ONLY" or catalog.get("status") != "READY"):
        return block("SKILL_CATALOG_NOT_ADMITTED_READONLY")
    if (asset.get("codigo_activo") != SKILL or asset.get("tipo_activo") != "SKILL"
            or asset.get("archived_at") is not None or asset.get("estado_operativo") != "READ_ONLY"
            or not isinstance(asset.get("metadata"), dict)
            or asset["metadata"].get("runtime_binding_enabled") is not True):
        return block("SKILL_ASSET_NOT_ADMITTED")
    if (authority.get("profile_code") != prof or authority.get("operation_code") != OP
            or authority.get("status") != "ACTIVE"):
        return block("PROFILE_SKILL_OPERATION_AUTHORITY_MISSING")
    if (source.get("repository") != REPO or source.get("path") != PATH
            or source.get("ref") != "refs/heads/main"
            or not _ok_hex(source.get("commit_sha"), HEX40)
            or not _ok_hex(source.get("blob_sha"), HEX40)):
        return block("SKILL_MAIN_SOURCE_NOT_ATTESTED")
    if (caller.get("repository") != REPO
            or not isinstance(caller.get("method"), str)
            or not caller["method"].startswith("GITHUB_ACTIONS_OIDC_")
            or not isinstance(caller.get("workflow_ref"), str)
            or not caller["workflow_ref"].startswith(REPO + "/.github/workflows/")
            or not caller["workflow_ref"].endswith("@refs/heads/main")):
        return block("CALLER_OIDC_IDENTITY_INVALID")
    if not _ok_hex(input_sha256):
        return block("SKILL_INPUT_DIGEST_INVALID")
    seed = hashlib.sha256((pid + "|" + SKILL + "|" + input_sha256).encode()).hexdigest()
    skill_run_id = "RUN-" + seed[:20].upper()
    child_id = "EXEC-SKILL-" + seed[:32].upper()
    idem = "SKILL-READONLY-NATIVE-V1:" + seed
    manifest = {
        "business": business, "read_only": True, "no_write": True, "no_promotion": True,
        "profile_handoff": {"source_execution_id": pid, "skill_run_id": skill_run_id,
                            "profile_code": prof, "request_sha256": req,
                            "business": business, "via": "SKILL_INVOKER"},
        "skill_source": {"repository": REPO, "path": PATH,
                         "commit_sha": source["commit_sha"], "blob_sha": source["blob_sha"]},
        "governed_caller_method": caller["method"],
        "caller_repository": caller["repository"],
        "caller_workflow_ref": caller["workflow_ref"],
        "router_action_code": "SKILL_EXECUTION", "skill_input_sha256": input_sha256,
    }
    args = {"p_execution_id": child_id, "p_operation_code": OP,
            "p_target_type": "SKILL", "p_target_code": SKILL,
            "p_idempotency_key": idem, "p_request_sha256": req,
            "p_actor_execution_id": pid, "p_target_repo": REPO,
            "p_target_path": PATH, "p_manifest": manifest}
    return {"schema_version": SCHEMA, "status": "CANDIDATE_PRECONDITIONS_CONSISTENT",
            "blocking_codes": [], "business": business, "profile_code": prof,
            "skill_run_id": skill_run_id, "child_execution_id": child_id,
            "reservation_args": args,
            "expected_step0": {"execution_id": child_id, "step_order": 0,
                               "step_id": "init_execution", "status": "STEP_PASS_WITH_EVIDENCE",
                               "judge_code": "JUDGE-EJECUCION-SKILL-LF-v0.1"},
            "host_attested": False, "reservation_executed": False,
            "step0_recorded": False, "readback_authenticated": False,
            "a3_allowed": False}


def verify_readback(candidate, reservation, child, step0):
    """Reconcile candidate with supplied post-reservation rows; STILL not trusted."""
    if not isinstance(candidate, dict) or candidate.get("status") != "CANDIDATE_PRECONDITIONS_CONSISTENT":
        return block("RESERVATION_PLAN_NOT_ELIGIBLE")
    if not all(isinstance(x, dict) for x in (reservation, child, step0)):
        return block("RESERVATION_READBACK_REQUIRED")
    args = candidate["reservation_args"]
    result = reservation.get("result")
    if result not in {"RESERVED_NEW_EXECUTION", "REPLAY_EXISTING_EXECUTION"}:
        return block("RESERVATION_RESULT_INVALID")
    if (reservation.get("execution_id") != args["p_execution_id"]
            or reservation.get("operation_code") != OP
            or reservation.get("idempotency_key") != args["p_idempotency_key"]
            or reservation.get("request_sha256") != args["p_request_sha256"]):
        return block("RESERVATION_RECEIPT_MISMATCH")
    if reservation.get("dispatch_permitted") is not (result == "RESERVED_NEW_EXECUTION"):
        return block("RESERVATION_REPLAY_DISPATCH_FORBIDDEN")
    if (child.get("execution_id") != args["p_execution_id"]
            or child.get("operation_code") != OP or child.get("target_type") != "SKILL"
            or child.get("target_code") != SKILL or child.get("target_repo") != REPO
            or child.get("target_path") != PATH
            or child.get("created_by_execution_id") != args["p_actor_execution_id"]
            or child.get("idempotency_key") != args["p_idempotency_key"]
            or child.get("request_sha256") != args["p_request_sha256"]
            or child.get("status") != "IN_PROGRESS"):
        return block("RESERVATION_CHILD_IDENTITY_MISMATCH")
    actual_manifest = child.get("manifest")
    expected_manifest = args["p_manifest"]
    if not isinstance(actual_manifest, dict):
        return block("RESERVATION_MANIFEST_DRIFT")
    # Governance triggers may append operation_policy_snapshots. Compare every
    # caller-owned field exactly; do not mistake extra policies for source drift.
    if any(actual_manifest.get(k) != v for k, v in expected_manifest.items()):
        return block("RESERVATION_MANIFEST_DRIFT")
    if any(k not in expected_manifest and k not in {"operation_policy_snapshots"}
           for k in actual_manifest):
        return block("RESERVATION_MANIFEST_UNEXPECTED_FIELDS")
    expected = candidate["expected_step0"]
    if any(step0.get(key) != value for key, value in expected.items() if key != "judge_code"):
        return block("RESERVATION_STEP0_NOT_CLEAN")
    payload = step0.get("evidence_payload")
    if not isinstance(payload, dict) or (payload.get("execution_id_created") is not True
            or payload.get("step_result") != "STEP_PASS_WITH_EVIDENCE"
            or payload.get("mini_judge_code") != expected["judge_code"]
            or payload.get("mini_judge_result") != "STEP_PASS_WITH_EVIDENCE"
            or not isinstance(step0.get("evidence_ref"), str)
            or not step0["evidence_ref"].startswith("supabase://")):
        return block("RESERVATION_STEP0_RECEIPT_INVALID")
    return {"schema_version": SCHEMA, "status": "CANDIDATE_READBACK_CONSISTENT",
            "blocking_codes": [], "business": candidate["business"],
            "child_execution_id": args["p_execution_id"],
            "replay": result == "REPLAY_EXISTING_EXECUTION",
            "host_attested": False, "reservation_executed": False,
            "step0_recorded": False, "readback_authenticated": False, "a3_allowed": False}
