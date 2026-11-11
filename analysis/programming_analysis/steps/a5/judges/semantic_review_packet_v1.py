"""Build a sealed, batchable independent semantic review packet for A5.

This module DOES NOT run a model. Outputs are NOT independent judge
verdicts. It reuses the fixed A5Q GPT-native criterion family without the
old case-specific >=5 pending decisions restriction.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

SCHEMA = "A5_MATERIAL_SEMANTIC_REVIEW_PACKET_V1"
RUBRIC = [
    {
        "check": "SEMANTIC_MEANING_PRESERVED",
        "question": "Does the result preserve the meaning of every supplied source rule, material definition and impact, without inventing requirements?",
    },
    {
        "check": "NO_FALSE_OWNER_ESCALATION",
        "question": "Are evidence gaps and excluded pending definitions kept distinct from genuine material owner questions?",
    },
    {
        "check": "MATERIAL_QUESTION_EVIDENCE_GROUNDED",
        "question": "Is every proposed decision question justified by the literal scope and source evidence, not merely by a URL, flag or generic label?",
    },
    {
        "check": "PROPER_OWNER_AND_AUTHORITY",
        "question": "Does every human decision have a real source-bound owner role, and do unresolved or historical ADRs remain unapproved?",
    },
    {
        "check": "NO_POLICY_PROMOTION",
        "question": "Are CANDIDATO or pending rules excluded from approved implementation obligations?",
    },
    {
        "check": "SCOPE_CONTINUITY",
        "question": "Can unrelated approved items remain specifiable without pretending that runtime or currentness is verified?",
    },
    {
        "check": "A6_IMPLEMENTABILITY_USEFULNESS",
        "question": "For each material item, can A6 read its original content, required action, evidence and unresolved specifics without material reinterpretation?",
    },
    {
        "check": "RULE_IDENTITY_NO_DUPLICATION",
        "question": "Are A3 approved/deferred/excluded rule identities consolidated without losing original occurrences, inherited bindings or policy dependencies?",
    },
    {
        "check": "FRONTEND_BACKEND_RESPONSIBILITY_GROUNDED",
        "question": "Does each rule's Frontend and Backend applicability and responsibility follow explicit source-backed information, without imposing one layer on all rules?",
    },
    {
        "check": "NO_LAYER_GUESS_FROM_RULE_NAME",
        "question": "Does unknown applicability remain UNKNOWN instead of being inferred from rule title, category, screen identity or a guessed code destination?",
    },
]
CITATION_REQUIREMENT = "quote the source item source_payload verbatim and the output decision item field"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def build(inputs: Any, output: Any, *, batch_size: int = 25) -> dict:
    if not isinstance(inputs, dict) or not isinstance(output, dict):
        raise ValueError("A5_SEMANTIC_PACKET_INPUT_INVALID")
    if type(batch_size) is not int or batch_size < 1 or batch_size > 50:
        raise ValueError("A5_SEMANTIC_BATCH_SIZE_INVALID")
    items = output.get("decision_items")
    ledger = output.get("material_ledger")
    if not isinstance(items, list) or not isinstance(ledger, dict):
        raise ValueError("A5_SEMANTIC_DECISION_ITEMS_REQUIRED")
    if len(items) != len(ledger.get("items", [])):
        raise ValueError("A5_SEMANTIC_MATERIAL_CARDINALITY_MISMATCH")
    batches = []
    for start in range(0,len(items),batch_size):
        subset=deepcopy(items[start:start+batch_size])
        batch={
            "batch_index":len(batches),
            "item_count":len(subset),
            "item_ids":[x["decision_item_id"] for x in subset],
            "items":subset,
        }
        batch["batch_sha256"]=_sha(batch)
        batches.append(batch)
    packet={
        "schema_version":SCHEMA,
        "unit":"A5",
        "evidence_tier":"CANDIDATE_SOURCE_ONLY",
        "input_digest_sha256":_sha(inputs),
        "output_digest_sha256":_sha(output),
        "ledger_digest_sha256":ledger.get("ledger_fingerprint_sha256"),
        "total_items":len(items),
        "batches":batches,
        "architecture_decision_items":deepcopy(output.get("architecture_decision_items", [])),
        "rule_profiles":deepcopy(output.get("rule_profiles")),
        "material_question_judgment":"REQUIRES_INDEPENDENT_SEMANTIC_REVIEW",
        "checks":deepcopy(RUBRIC),
        "citation_requirement":CITATION_REQUIREMENT,
        "case_specific_minimum_pending_decisions":None,
        "source_of_criterion":"analysis_qualification_a5q_c2_gpt_native_packet_v1.py",
        "reviewer_verdict":None,
        "reviewer_identity_attested":False,
        "independent_semantic_review":False,
        "real_model_execution_receipt":False,
        "no_write_performed":True,
    }
    packet["packet_sha256"]=_sha(packet)
    return packet


def check_review_shape(packet: dict, review: Any) -> dict:
    """Validate shape and quoted evidence. Not a model or human adjudicator."""
    if (not isinstance(packet,dict) or packet.get("schema_version")!=SCHEMA
            or not isinstance(review,dict)
            or review.get("packet_sha256")!=packet.get("packet_sha256")
            or review.get("schema_version")!="A5_MATERIAL_SEMANTIC_REVIEW_V1"):
        return {"status":"BLOCKED","code":"A5_SEMANTIC_REVIEW_IDENTITY_INVALID"}
    judgments=review.get("items")
    ids=[i for b in packet["batches"] for i in b["item_ids"]]
    if (not isinstance(judgments,list) or
            [x.get("item_id") for x in judgments if isinstance(x,dict)]!=ids
            or len(judgments)!=len(ids)):
        return {"status":"BLOCKED","code":"A5_SEMANTIC_REVIEW_ITEM_COVERAGE_MISSING"}
    for row in judgments:
        checks=row.get("checks")
        if (not isinstance(checks,list)
                or [x.get("check") for x in checks if isinstance(x,dict)]
                    !=[x["check"] for x in RUBRIC]
                or len(checks)!=len(RUBRIC)):
            return {"status":"BLOCKED","code":"A5_SEMANTIC_REVIEW_CHECKS_INCOMPLETE"}
        for x in checks:
            if x.get("verdict") not in ("PASS","FAIL","UNKNOWN"):
                return {"status":"BLOCKED","code":"A5_SEMANTIC_REVIEW_VERDICT_INVALID"}
            if not isinstance(x.get("evidence_quotes"),list):
                return {"status":"BLOCKED","code":"A5_SEMANTIC_REVIEW_EVIDENCE_QUOTES_MISSING"}
    return {
        "status":"SHAPE_VALID_ONLY",
        "independent_semantic_review":False,
        "reviewer_identity_attested":False,
        "no_runtime_activation":True,
    }
