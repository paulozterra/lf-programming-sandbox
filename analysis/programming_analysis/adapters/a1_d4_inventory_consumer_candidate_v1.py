"""Source-only A1 research -> existing D4 canonical metadata preparation.

This is NOT a worker, Router, model executor, authority, or A2 runner.
The governed consumer must supply its own authorized psycopg cursor and
binding receipts. The database ACL decides whether the canonical D4 SELECT
is available; no credentials or privileged role are created here.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
D4_SOURCE = (
    REPO / "services/profile_runtime_api/profile_runtime_api/"
    "source_investigation_preparation.py"
)
SCHEMA = "A1_D4_SOURCE_RESEARCH_TRANSPORT_CANDIDATE_V1"


def _blocked(code: str) -> dict:
    return {
        "schema_version": SCHEMA,
        "status": "BLOCKED",
        "blocking_code": code,
        "a2_result": None,
        "a2_allowed": False,
        "source_attested": False,
        "runtime_integrated": False,
        "no_run_created": True,
    }


def _load_existing_d4():
    spec = importlib.util.spec_from_file_location(
        "lf_existing_d4_metadata_prepare", D4_SOURCE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("CANONICAL_D4_SOURCE_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prepare_a1_research_with_governed_cursor(
    a1_transport: Any, cursor: Any, *, business: str = "LF",
    max_candidates: int = 12,
) -> dict:
    """Use the existing D4 adapter ONLY after A1 produces a material handoff.

    The cursor must originate from the existing governed executor. This
    module never authenticates the cursor, caller or source provenance.
    A successful D4 metadata preparation NEVER resolves A1 ambiguity or
    permits A2 automatically; source-bound reconciliation is still needed.
    """
    if not isinstance(a1_transport, dict) or a1_transport.get(
        "schema_version"
    ) != "A1_A2_SEMANTIC_TRANSPORT_CANDIDATE_V1":
        return _blocked("A1_D4_TRANSPORT_CONTRACT_INVALID")
    if (a1_transport.get("status") != "HALTED_AT_A1"
            or a1_transport.get("a2_result") is not None
            or a1_transport.get("a2_signal_bundle") is not None
            or a1_transport.get("no_run_created") is not True):
        return _blocked("A1_D4_A2_GATE_NOT_HALTED")
    a1 = a1_transport.get("a1_result")
    handoff = a1_transport.get("inventory_research_handoff")
    if not isinstance(a1, dict) or not isinstance(handoff, dict):
        return _blocked("A1_D4_RESEARCH_HANDOFF_REQUIRED")
    if (a1.get("status") != "REQUIRES_DECISION"
            or handoff.get("schema_version") != "A1_INVENTORY_RESEARCH_HANDOFF_CANDIDATE_V1"
            or a1.get("business") != business
            or business != "LF"
            or handoff.get("business") != business
            or handoff.get("allow_a2") is not False
            or handoff.get("inventory_source_verified") is not False
            or handoff.get("inventory_lookup_executed") is not False):
        return _blocked("A1_D4_SCOPE_OR_AUTHORITY_INVALID")
    raw = handoff.get("original_request")
    if not isinstance(raw, str) or not 3 <= len(raw.strip()) <= 1000:
        return _blocked("A1_D4_RAW_REQUEST_INVALID")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if (handoff.get("request_sha256") != digest
            or a1.get("original_request_sha256") != digest):
        return _blocked("A1_D4_RAW_REQUEST_HASH_DRIFT")
    payload = a1.get("payload")
    intent = a1.get("intent_analysis")
    if not isinstance(payload, dict) or not isinstance(intent, dict):
        return _blocked("A1_D4_CONTEXT_REQUIRED")
    pending = [
        item for item in payload.get("ambiguities", [])
        if isinstance(item, dict)
        and item.get("resolution_state") == "OPEN"
        and item.get("materiality") in ("MATERIAL", "UNKNOWN")
    ]
    if (not pending or handoff.get("open_ambiguities") != pending
            or handoff.get("constraints") != payload.get("constraints")
            or handoff.get("target_hints") != payload.get("target_hints")
            or handoff.get("source_refs") != payload.get("source_refs")
            or handoff.get("operation_kind") != intent.get("operation", {}).get("kind")
            or handoff.get("artifact_kind") != intent.get("target", {}).get("artifact_kind")
            or handoff.get("dimensions_to_investigate") != intent.get(
                "dimensions_to_investigate"
            )):
        return _blocked("A1_D4_RESEARCH_CONTEXT_DRIFT")
    if cursor is None:
        return _blocked("A1_D4_GOVERNED_CURSOR_REQUIRED")
    try:
        existing = _load_existing_d4()
        plan = existing.prepare_source_investigation(cursor, raw, max_candidates)
    except Exception:
        # Do not leak DB credentials/errors or claim a negative inventory match.
        return _blocked("A1_D4_CANONICAL_PREPARATION_FAILED")
    action = plan.get("next_action")
    if not isinstance(action, str) or action.startswith("BLOCK_"):
        return _blocked("A1_D4_CANONICAL_PREPARATION_BLOCKED")
    return {
        "schema_version": SCHEMA,
        "status": "METADATA_PREPARED_AMBIGUITIES_OPEN",
        "business": business,
        "request_sha256": digest,
        "operation_kind": handoff["operation_kind"],
        "constraints": list(handoff["constraints"]),
        "open_ambiguities": pending,
        "target_hints": list(handoff["target_hints"]),
        "dimensions_to_investigate": list(handoff["dimensions_to_investigate"]),
        "source_refs": list(handoff["source_refs"]),
        "d4_metadata_preparation": plan,
        "next_required_action": action,
        "a2_result": None,
        "a2_allowed": False,
        "source_attested": False,
        "runtime_integrated": False,
        "no_run_created": True,
    }
