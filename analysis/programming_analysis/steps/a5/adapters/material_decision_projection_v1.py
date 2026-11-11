"""Evidence-lossless A3/A4 material-item ledger for A5.

Projection only. Does NOT decide policy, manufacture human questions,
choose ADR or run model/provider. It preserves every typed material row.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

A3_ROWS = (
    ("policy_scope_clear_rule_candidates", "APPROVED_RULE"),
    ("policy_deferred_rule_items", "POLICY_DEFERRED_RULE"),
    ("excluded_rule_items", "EXCLUDED_RULE"),
    ("policy_link_items", "POLICY_BINDING"),
)
A4_ROWS = (
    ("direct_impacts", "DIRECT_IMPACT"),
    ("indirect_impacts", "INDIRECT_IMPACT"),
    ("consumers", "CONSUMER"),
    ("dependency_paths", "DEPENDENCY"),
    ("excluded_pending_obligations", "EXCLUDED_OBLIGATION"),
    ("unresolved_material_impacts", "MATERIAL_EVIDENCE_GAP"),
)


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def _row(section: str, index: int, kind: str, source: str, data: dict,
         *, disposition: str) -> dict:
    ref = (data.get("source_ref") or data.get("affected_ref")
           or data.get("target_ref"))
    code = (data.get("rule_code") or data.get("requirement_code")
            or data.get("impact_id") or data.get("code"))
    # No manufactured labels or business semantics: keep exact material payload.
    return {
        "item_id": f"{source}:{section}:{index}",
        "source_stage": source,
        "source_path": f"{section}[{index}]",
        "kind": kind,
        "subject_ref": ref if isinstance(ref, str) else None,
        "subject_code": code if isinstance(code, str) else None,
        "title": data.get("title") if isinstance(data.get("title"), str) else None,
        "description": data.get("description") if isinstance(data.get("description"), str) else (
            data.get("statement") if isinstance(data.get("statement"), str) else None),
        "requested_action": data.get("change_action") if isinstance(data.get("change_action"), str) else None,
        "definition_action": data.get("definition_action") if isinstance(data.get("definition_action"), str) else None,
        "disposition": disposition,
        "owner_decision_required": False,
        "question": None,
        "next_action": {
            "IMPLEMENTATION_OBLIGATION": "SPECIFY_IN_A6_AFTER_GOVERNED_ADMISSION",
            "EXCLUDED_PENDING": "REPORT_EXCLUSION_NO_SCOPE_BLOCK",
            "EVIDENCE_REQUIRED": "TARGETED_SOURCE_READBACK_ONLY",
            "PRESERVE_CONTEXT": "KEEP_SOURCE_BINDING",
        }[disposition],
        "source_payload": deepcopy(data),
        "payload_sha256": canonical_sha(data),
    }


def project(a3: Any, a4: Any) -> dict:
    """Preserve all known material collections, including missing/empty distinctions.

    Raise ValueError with a stable error code for malformed data. Missing
    collections remain explicit in missing_collections and are never assumed
    empty or not applicable. This is a source-only ledger, not source attestation.
    """
    if not isinstance(a3, dict) or not isinstance(a4, dict):
        raise ValueError("A5_MATERIAL_INPUT_NOT_OBJECT")
    target = a3.get("target_ref")
    if (not isinstance(target, str) or not target
            or a4.get("target_ref") != target):
        raise ValueError("A5_MATERIAL_TARGET_MISMATCH")
    items, missing, counts, sources = [], [], {}, {"A3": a3, "A4": a4}
    collections = {
        "A3": list(A3_ROWS) + [("evidence_items", "EVIDENCE_RULE")],
        "A4": list(A4_ROWS),
    }
    for source, rows in collections.items():
        data = sources[source]
        for section, kind in rows:
            if section not in data:
                missing.append(f"{source}.{section}")
                continue
            collection = data[section]
            if not isinstance(collection, list):
                raise ValueError("A5_MATERIAL_COLLECTION_INVALID:" + source + "." + section)
            counts[f"{source}.{section}"] = len(collection)
            for index, item in enumerate(collection):
                if not isinstance(item, dict):
                    raise ValueError("A5_MATERIAL_ROW_INVALID:" + source + "." + section)
                if kind in ("APPROVED_RULE", "EVIDENCE_RULE"):
                    approved = (item.get("rule_status") == "VIGENTE"
                                and item.get("pending_decision") is False
                                and item.get("policy_dependency_disposition") not in (
                                    "DEFER_UNAPPROVED_OR_UNRESOLVED_POLICY",))
                    disposition = "IMPLEMENTATION_OBLIGATION" if approved else "EXCLUDED_PENDING"
                elif kind in ("POLICY_DEFERRED_RULE", "EXCLUDED_RULE", "EXCLUDED_OBLIGATION"):
                    disposition = "EXCLUDED_PENDING"
                elif kind == "DIRECT_IMPACT" and item.get("impact_class") in (
                    "PLANNED_NEW_IMPLEMENTATION_OBLIGATION",
                    "PLANNED_MATERIAL_DEFINITION",
                ) and item.get("source_status") == "VIGENTE" and item.get("change_action") == "CREATE":
                    disposition = "IMPLEMENTATION_OBLIGATION"
                elif kind in ("DIRECT_IMPACT", "INDIRECT_IMPACT", "CONSUMER",
                              "DEPENDENCY", "MATERIAL_EVIDENCE_GAP"):
                    disposition = "EVIDENCE_REQUIRED"
                else:
                    disposition = "PRESERVE_CONTEXT"
                items.append(_row(section, index, kind, source, item,
                                  disposition=disposition))
    material = a3.get("material_contract_readback")
    if material is None:
        missing.append("A3.material_contract_readback.status_items")
    else:
        if not isinstance(material, dict):
            raise ValueError("A5_MATERIAL_CONTRACT_INVALID")
        statuses = material.get("status_items")
        if not isinstance(statuses, list):
            raise ValueError("A5_MATERIAL_STATUS_ITEMS_INVALID")
        counts["A3.material_contract_readback.status_items"] = len(statuses)
        for index, item in enumerate(statuses):
            if not isinstance(item, dict) or not isinstance(item.get("source_ref"), str):
                raise ValueError("A5_MATERIAL_STATUS_ROW_INVALID")
            disp = ("IMPLEMENTATION_OBLIGATION" if item.get("source_status") == "VIGENTE"
                    else "EXCLUDED_PENDING")
            items.append(_row("material_contract_readback.status_items",index,
                              "MATERIAL_DEFINITION","A3",item,disposition=disp))
    # Preserve structured policy-resolution objects and full material definitions
    # without collapsing content to source URLs. The immutable source copy
    # must remain available to the next consumer; source-only, not CURRENT.
    source_detail = {
        "a3_policy_resolution": deepcopy(a3.get("policy_resolution")),
        "a3_material_contract": deepcopy(material),
        "a3_scope_alerts": deepcopy(a3.get("scope_alerts")),
        "a3_unresolved_material_gaps": deepcopy(a3.get("unresolved_material_gaps")),
        "a4_target_change_action": a4.get("target_change_action"),
        "a4_target_code_destination": a4.get("target_code_destination"),
        "a4_analysis_mode": a4.get("analysis_mode"),
    }
    ledger = {
        "schema_version": "A5_MATERIAL_DECISION_LEDGER_V1",
        "target_ref": target,
        "items": items,
        "source_collection_counts": counts,
        "missing_collections": missing,
        "source_detail": source_detail,
        "upstream_contract_snapshot": {
            "A3": deepcopy(a3),
            "A4": deepcopy(a4),
        },
        "source_digest_sha256": canonical_sha({"a3": a3, "a4": a4}),
        "source_attested": False,
    }
    ledger["coverage"] = {
        "input_item_count": sum(counts.values()),
        "output_item_count": len(items),
        "omitted_material_item_count": sum(counts.values())-len(items),
        "complete_for_provided_collections": (not missing and sum(counts.values()) == len(items)),
        "missing_source_collections": missing.copy(),
    }
    ledger["ledger_fingerprint_sha256"] = canonical_sha(ledger)
    return ledger
