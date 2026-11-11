"""A5 source-only item-level decision projection on top of canonical ADR logic.

Keeps A5's existing ADR resolver and status guards unchanged. No standalone
decision engine; this is a lossless field-level output adapter.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def _material(a3: dict, a4: dict) -> dict:
    spec = importlib.util.spec_from_file_location(
        "a5_material_projection_v1", ROOT / "material_decision_projection_v1.py")
    if spec is None or spec.loader is None:
        raise ValueError("A5_MATERIAL_ADAPTER_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.project(a3, a4)


def _blocked(code: str, base: dict) -> dict:
    return {
        "schema_version": "ANALYSIS_DECISION_CONTEXT_V1",
        "status": "BLOCKED",
        "target_ref": base.get("target_ref"),
        "blocking_codes": [code],
        "decisions": [],
        "unresolved_material_questions": [code],
        "source_attested": False,
        "independent_judge_verified": False,
        "a6_allowed": False,
        "no_write_performed": True,
    }


def enrich(base: Any, inputs: Any, readback: Any = None) -> dict:
    if not isinstance(base, dict) or base.get("status") == "BLOCKED":
        return base
    if not isinstance(inputs, dict):
        return _blocked("A5_ENRICHMENT_INPUTS_INVALID", base)
    a3 = inputs.get("TARGETED_EVIDENCE_SET_V1")
    a4 = inputs.get("SHARED_CHANGE_IMPACT_ANALYSIS")
    if not isinstance(a3, dict) or not isinstance(a4, dict):
        return _blocked("A5_ENRICHMENT_CANONICAL_INPUTS_MISSING", base)
    try:
        ledger = _material(a3, a4)
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        code = str(exc) if str(exc).startswith("A5_") else "A5_MATERIAL_PROJECTION_FAILED"
        return _blocked(code, base)
    items = []
    for item in ledger["items"]:
        state = {
            "IMPLEMENTATION_OBLIGATION": "NO_NEW_DECISION_REQUIRED_SOURCE_CANDIDATE",
            "EXCLUDED_PENDING": "EXCLUDED_FROM_APPROVED_SCOPE",
            "EVIDENCE_REQUIRED": "TARGETED_EVIDENCE_REQUIRED",
            "PRESERVE_CONTEXT": "CANONICAL_CONTEXT_PRESERVED",
        }[item["disposition"]]
        items.append({
            "decision_item_id": item["item_id"],
            "source_stage": item["source_stage"],
            "source_path": item["source_path"],
            "kind": item["kind"],
            "subject_ref": item["subject_ref"],
            "subject_code": item["subject_code"],
            "title": item["title"],
            "description": item["description"],
            "requested_action": item["requested_action"],
            "definition_action": item["definition_action"],
            "decision_classification": state,
            "owner_decision_required": False,
            "material_question": None,
            "owner_role": None,
            "next_action": item["next_action"],
            "source_payload": deepcopy(item["source_payload"]),
            "source_payload_sha256": item["payload_sha256"],
            "source_attested": False,
        })
    by_id = {x["decision_item_id"]: x for x in items}
    if len(by_id) != len(items):
        return _blocked("A5_MATERIAL_DUPLICATE_ITEM_ID", base)
    candidates = readback.get("material_decisions", []) if isinstance(readback, dict) else []
    if not isinstance(candidates, list):
        return _blocked("A5_MATERIAL_DECISION_CANDIDATES_INVALID", base)
    owner, seen = [], set()
    a3_refs = a3.get("source_refs", [])
    a4_refs = a4.get("evidence_refs", [])
    if not isinstance(a3_refs, list) or not isinstance(a4_refs, list):
        return _blocked("A5_MATERIAL_DECISION_SOURCE_REFS_INVALID", base)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return _blocked("A5_MATERIAL_DECISION_CANDIDATE_INVALID", base)
        identity = candidate.get("source_item_id")
        question = candidate.get("material_question")
        source_ref = candidate.get("evidence_ref")
        role = candidate.get("owner_role")
        if (not isinstance(identity, str) or identity not in by_id
                or identity in seen or not isinstance(question, str)
                or len(question.strip()) < 20 or not question.strip().endswith("?")
                or not isinstance(source_ref, str)
                or source_ref not in a3_refs + a4_refs
                or not isinstance(role, str) or not role.strip()
                or candidate.get("source_attested") is not False):
            return _blocked("A5_OWNER_DECISION_MISSING_MATERIAL_BINDING", base)
        row = by_id[identity]
        if row["decision_classification"] == "EXCLUDED_FROM_APPROVED_SCOPE":
            return _blocked("A5_EXCLUDED_RULE_CANNOT_TRIGGER_OWNER_DECISION", base)
        if row["decision_classification"] == "TARGETED_EVIDENCE_REQUIRED":
            return _blocked("A5_MISSING_EVIDENCE_NOT_OWNER_DECISION", base)
        if source_ref not in (
                row["subject_ref"], a3.get("source_refs", [None])[0],
                a4.get("target_ref")) and source_ref not in a3_refs:
            return _blocked("A5_OWNER_DECISION_SOURCE_UNBOUND", base)
        seen.add(identity)
        row["decision_classification"] = "REQUIRES_OWNER_DECISION"
        row["owner_decision_required"] = True
        row["material_question"] = question
        row["owner_role"] = role
        row["next_action"] = "WAIT_GOVERNED_OWNER_DECISION"
        owner.append({
            "decision_id": "A5:OWNER:" + identity,
            "source_item_id": identity,
            "subject_ref": row["subject_ref"],
            "question": question,
            "owner_role": role,
            "evidence_ref": source_ref,
            "selected_option_ref": None,
            "persistence_ref": None,
            "status": "REQUIRES_DECISION",
            "source_attested": False,
        })
    out = deepcopy(base)
    # A canonical ADR trigger is not itself a fully grounded owner question.
    # Distinguish missing question evidence from an actual human decision.
    architecture = []
    flags = out.get("material_adr_triggers_true", [])
    if not isinstance(flags, list):
        flags = []
    disposition = out.get("decision_context", {}).get("adr_disposition")
    trigger_review = (
        readback.get("adr_trigger_review", {})
        if isinstance(readback, dict) else {}
    )
    detail = trigger_review.get("material_detail", {}) if isinstance(trigger_review, dict) else {}
    if not isinstance(detail, dict):
        return _blocked("A5_ADR_MATERIAL_DETAIL_INVALID", base)
    for flag in flags:
        provided = detail.get(flag)
        question = None
        evidence_ref = None
        if provided is not None:
            if not isinstance(provided, dict):
                return _blocked("A5_ADR_MATERIAL_DETAIL_ROW_INVALID", base)
            q = provided.get("material_question")
            ref = provided.get("evidence_ref")
            if (not isinstance(q, str) or len(q.strip()) < 20
                    or not q.strip().endswith("?")
                    or not isinstance(ref, str) or ref not in a3_refs+a4_refs):
                return _blocked("A5_ADR_QUESTION_NOT_SOURCE_BOUND", base)
            question, evidence_ref = q, ref
        need_decision = disposition == "NEW_ADR_REQUIRED"
        architecture.append({
            "trigger": flag,
            "material_question": question,
            "evidence_ref": evidence_ref,
            "decision_required": need_decision,
            "semantic_review_needed": need_decision and question is None,
            "status": (
                "REQUIRES_OWNER_DECISION_CANDIDATE" if need_decision and question
                else "MATERIAL_QUESTION_EVIDENCE_REQUIRED" if need_decision
                else "REUSE_CURRENT_ADR_OR_UNRESOLVED"
            ),
            "selected_option_ref": None,
            "authority_currentness_attested": False,
        })
    # Consolidate A3 approved, deferred and excluded rule identities exactly
    # once. Optional host-supplied layer readback does not self-attest.
    helper=ROOT / "rule_layer_consolidation_v1.py"
    spec=importlib.util.spec_from_file_location("a5_rule_layer_consumer",helper)
    if spec is None or spec.loader is None:
        return _blocked("A5_RULE_LAYER_ADAPTER_UNAVAILABLE",base)
    adapter=importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(adapter)
        rule_profiles=adapter.consolidate(a3,a4,items,readback)
    except (ValueError,TypeError,AttributeError,RecursionError,OSError) as exc:
        code=str(exc) if str(exc).startswith("A5_") else "A5_RULE_LAYER_PROJECTION_FAILED"
        return _blocked(code,base)
    out["rule_profiles"] = rule_profiles
    out["material_ledger"] = ledger
    out["decision_items"] = items
    out["architecture_decision_items"] = architecture
    out["pending_owner_decisions"] = owner
    out["pending_evidence_items"] = [
        {"decision_item_id": x["decision_item_id"],
         "subject_ref": x["subject_ref"], "source_path": x["source_path"],
         "next_action": x["next_action"]}
        for x in items if x["decision_classification"] == "TARGETED_EVIDENCE_REQUIRED"
    ]
    out["material_coverage"] = deepcopy(ledger["coverage"])
    out["scope_disposition"] = (
        "OWNER_DECISION_REQUIRED" if owner
        else "NO_NEW_OWNER_DECISION_DEMONSTRATED_SOURCE_CANDIDATE"
    )
    out["candidate_independent_scope_available"] = (
        not owner and any(x["decision_classification"] ==
            "NO_NEW_DECISION_REQUIRED_SOURCE_CANDIDATE" for x in items)
    )
    if owner and out.get("status") == "UNRESOLVED":
        out["status"] = "REQUIRES_DECISION"
        if isinstance(out.get("decision_context"), dict):
            dc = out["decision_context"]
            dc["status"] = "REQUIRES_DECISION"
            dc["unresolved_questions"].extend(x["question"] for x in owner)
            # Refresh fingerprint using same canonical A5 helper. The caller
            # recomputes in outer wrapper after this source-only projection.
        out.setdefault("unresolved_material_questions", []).extend(x["question"] for x in owner)
    if ledger["missing_collections"]:
        out.setdefault("unresolved_material_questions", []).append(
            "A5_MATERIAL_SOURCE_COLLECTIONS_NOT_SUPPLIED")
    out["a6_allowed"] = False
    out["source_attested"] = False
    out["independent_judge_verified"] = False
    out["no_write_performed"] = True
    return out
