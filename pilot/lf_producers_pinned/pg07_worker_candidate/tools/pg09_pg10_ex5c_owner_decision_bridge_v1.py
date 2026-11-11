"""Read a pinned, non-authenticating owner decision at PG09 C4 -> PG10.

Never changes PG09/PG10 producers. A user statement is recorded with date,
reference and SHA but is NOT an authenticated runtime decision ledger.
No retry or production authority can be granted.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

DECISION_SHA256 = "19b920bd8b3ae0b643a4d1d4b8967132d8007bdb853780ca295a0d6c7dbe45eb"
DECISION_FILE = (Path(__file__).resolve().parents[1] /
                 "fixtures/ex5c_owner_attempt_decision_v1.json")


class OwnerDecisionBlocked(ValueError):
    pass


def reject(reason: str):
    raise OwnerDecisionBlocked(reason)


def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=True, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_registered_owner_decision(path: Path = DECISION_FILE,
                                   expected_sha256: str = DECISION_SHA256) -> dict:
    if not path.is_file() or path.is_symlink():
        reject("PG10_OWNER_DECISION_RECORD_MISSING_BLOCK")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        reject("PG10_OWNER_DECISION_SHA_MISMATCH_BLOCK")
    obj = json.loads(raw)
    exact = {
        "schema_version": "LF_EX5C_OWNER_ATTEMPT_DECISION_V1",
        "decision_ref": "LF-OWNER-EX5C-ATTEMPT-1-20261106",
        "decision_date": "2026-11-06",
        "decision_maker": "Paulo",
        "decision_text": "aceptar PASS del intento 1; sin nueva iteración",
        "decision_state": "RESOLVED",
        "action": "ACCEPT_PASS_ATTEMPT_1_NO_NEW_ITERATION",
        "reason_code": "BUDGET_DECISION",
        "run_id": 42284754122,
        "worker_model": "claude-sonnet-5-5",
        "cost_reported_usd": "0.070022",
        "attempts_used": 1,
        "max_attempts": 1,
        "budget_cap_usd": "0.35",
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "source_ref": "owner-mandate-ex5c-2026-11-06",
        "receipt_authenticated": False,
        "production_authority": False,
        "retry_authorized": False,
        "worker_invoked": False,
        "decision_authenticated": False
    }
    if obj != exact:
        reject("PG10_OWNER_DECISION_FIELD_DRIFT_BLOCK")
    return obj


def bridge_pg09_c4_owner_decision_to_pg10(*, pg09_c4: dict,
                                          decision_path: Path = DECISION_FILE) -> dict:
    """Report a ledger input; calls to actual PG10 stages remain mandatory."""
    decision = load_registered_owner_decision(decision_path)
    if (pg09_c4.get("schema_version") != "PG09_C4_TYPED_ESCALATION_CANDIDATE_V1" or
        pg09_c4.get("status") != "CANDIDATE_NOT_ADMITTED" or
        pg09_c4.get("production_authority") is not False or
        pg09_c4.get("handoff_allowed") is not False or
        pg09_c4.get("candidate_sha256") != digest({
            k: v for k, v in pg09_c4.items() if k != "candidate_sha256"
        })):
        reject("PG10_PG09_C4_SOURCE_INVALID_BLOCK")
    entries = pg09_c4.get("solutions", [])
    if len(entries) != 1 or entries[0].get("solution_id") != "EX5C" or (
            "BUDGET_DECISION" not in entries[0].get("reason_codes", [])):
        reject("PG10_BUDGET_DECISION_NOT_REFERENCED_BLOCK")
    if pg09_c4.get("run_ref") != "sandbox:run:42284754122":
        reject("PG10_OWNER_RUN_MISMATCH_BLOCK")
    # PG10 lineage producer requires a routed conflict_id; that identity
    # must come from original PG10 C1->C3, never fabricated by this bridge.
    return {
        "decision_ref": decision["decision_ref"],
        "decision_date": decision["decision_date"],
        "decision_state": decision["decision_state"],
        "owner_action": decision["action"],
        "reason_code": "BUDGET_DECISION",
        "decision_file_sha256": DECISION_SHA256,
        "source_pg09_c4_sha256": pg09_c4["candidate_sha256"],
        "owner_decision_authenticated": False,
        "production_authority": False, "retry_authorized": False,
        "next_gate": "ORIGINAL_PG10_C1_TO_C3_CONFLICT_AND_LEDGER_READBACK"
    }
