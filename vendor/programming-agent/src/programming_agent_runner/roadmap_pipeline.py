from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_json
from .retrieval import retrieval_quality_passes
from .review_packet_v1 import validate_review_packet_v1
from .structured_test_receipt import successful_test_ids, validate_structured_test_receipt
from .traceability import traceability_graph_from_dict, validate_traceability_graph

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_TEST_SUFFIXES = {
    "retrieval": (
        "RetrievalTests.test_gold_metrics_cover_required_dimensions",
        "RetrievalTests.test_required_source_missing_blocks",
    ),
    "traceability": (
        "TraceabilityTests.test_complete_important_pass_is_valid",
        "TraceabilityTests.test_pass_without_evidence_is_rejected",
    ),
    "human_review_v1": (
        "ReviewPacketV1Tests.test_v1_exposes_retrieved_rule_trace_tests_and_review_order",
        "ReviewPacketV1Tests.test_missing_critical_context_blocks_packet",
    ),
    "playwright": (
        "PlaywrightGateTests.test_clean_execution_passes",
        "PlaywrightGateTests.test_ui_detection_and_web_not_applicable_guard",
    ),
    "learning_loop": (
        "LearningLoopTests.test_builder_cannot_skip_audit_to_activate",
        "LearningLoopTests.test_active_rule_requires_audit_pass_and_human_approval",
    ),
    "integration": ("RoadmapIntegrationTests.test_layers_compose_without_bypassing_governance",),
    "ci_cd": (
        "RoadmapPipelineTests.test_green_technical_pipeline_remains_promotion_blocked",
        "PromotionGateTests.test_valid_independent_audit_and_human_gate_authorize_promotion_only",
        "PromotionGateTests.test_builder_cannot_be_independent_auditor",
    ),
}


class RoadmapPipelineError(ValueError):
    """Raised when v0.9 technical evidence is incomplete or inconsistently bound."""


def _has_suffixes(receipt: dict[str, Any], suffixes: tuple[str, ...]) -> bool:
    successful = successful_test_ids(receipt)
    return all(any(test_id.endswith(suffix) for test_id in successful) for suffix in suffixes)


def promotion_blockers() -> list[str]:
    return ["INDEPENDENT_AUDIT_REQUIRED", "HUMAN_PROMOTION_GATE_REQUIRED"]


def technical_status(stages: dict[str, str]) -> str:
    return "PASS" if stages and all(value == "PASS" for value in stages.values()) else "FAIL"


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RoadmapPipelineError(f"{field} must be lowercase SHA-256")
    return value


def _embedded_digest_valid(value: dict[str, Any], field: str) -> bool:
    digest = value.get(field)
    return isinstance(digest, str) and digest == sha256_json({key: item for key, item in value.items() if key != field})


def retrieval_result_digest_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    digest = value.get("context_sha256")
    payload = {
        "schema_version": 1,
        "status": value.get("status"),
        "query": value.get("query"),
        "selected": value.get("selected"),
        "missing_critical_context": value.get("missing_critical_context"),
        "filtered_counts": value.get("filtered_counts"),
    }
    return isinstance(digest, str) and _SHA256.fullmatch(digest) is not None and digest == sha256_json(payload)


def build_roadmap_manifest(
    *,
    repository: str,
    head_sha: str,
    tree_sha: str,
    source_snapshot_sha256: str,
    run_id: int,
    run_attempt: int,
    job_name: str,
    test_receipt: dict[str, Any],
    retrieval_metrics: dict[str, Any],
    retrieval_result: dict[str, Any],
    traceability: dict[str, Any],
    playwright: dict[str, Any],
    human_review_v1: dict[str, Any],
    security: dict[str, Any],
) -> dict[str, Any]:
    if _SHA40.fullmatch(head_sha) is None or _SHA40.fullmatch(tree_sha) is None:
        raise RoadmapPipelineError("head/tree must be lowercase 40-hex")
    _require_digest(source_snapshot_sha256, "source_snapshot_sha256")
    if run_id <= 0 or run_attempt <= 0 or not job_name:
        raise RoadmapPipelineError("GitHub execution identity invalid")
    receipt_problems = validate_structured_test_receipt(
        test_receipt,
        expected_repository=repository,
        expected_head_sha=head_sha,
        expected_run_id=run_id,
        expected_run_attempt=run_attempt,
        expected_job_name=job_name,
    )
    if receipt_problems:
        raise RoadmapPipelineError(f"test receipt invalid: {receipt_problems}")
    if test_receipt.get("source_snapshot_sha256") != source_snapshot_sha256:
        raise RoadmapPipelineError("test receipt source snapshot mismatch")
    if not retrieval_result_digest_valid(retrieval_result):
        raise RoadmapPipelineError("retrieval result digest mismatch")
    graph = traceability_graph_from_dict(traceability)
    if validate_traceability_graph(graph):
        raise RoadmapPipelineError("traceability graph invalid")
    if not _embedded_digest_valid(playwright, "evidence_sha256"):
        raise RoadmapPipelineError("Playwright evidence digest mismatch")
    if not _embedded_digest_valid(security, "evidence_sha256"):
        raise RoadmapPipelineError("security evidence digest mismatch")
    review_problems = validate_review_packet_v1(human_review_v1)
    if review_problems:
        raise RoadmapPipelineError(f"Human Review v1 invalid: {review_problems}")

    stage_tests = {name: _has_suffixes(test_receipt, suffixes) for name, suffixes in _REQUIRED_TEST_SUFFIXES.items()}
    summary = test_receipt.get("summary", {})
    stages = {
        "build_lint_typecheck_unit_negative": "PASS" if summary.get("overall_status") == "PASS" else "FAIL",
        "retrieval": "PASS"
        if stage_tests["retrieval"] and retrieval_quality_passes(retrieval_metrics) and retrieval_result.get("status") == "PASS"
        else "FAIL",
        "traceability": "PASS" if stage_tests["traceability"] else "FAIL",
        "human_review_v1": "PASS"
        if stage_tests["human_review_v1"] and human_review_v1.get("status") == "PASS"
        else "FAIL",
        "playwright": "PASS"
        if stage_tests["playwright"] and playwright.get("status") in {"PASS", "NOT_APPLICABLE"}
        else "FAIL",
        "security": "PASS" if security.get("status") == "PASS" else "FAIL",
        "learning_loop": "PASS" if stage_tests["learning_loop"] else "FAIL",
        "integration": "PASS" if stage_tests["integration"] else "FAIL",
        "ci_cd_evidence_seal": "PASS" if stage_tests["ci_cd"] else "FAIL",
    }
    technical = technical_status(stages)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source": "programming-agent-v09-roadmap-manifest",
        "repository": repository,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "source_snapshot_sha256": source_snapshot_sha256,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "job_name": job_name,
        "stages": stages,
        "technical_status": technical,
        "promotion_status": "BLOCKED",
        "promotion_blockers": promotion_blockers(),
        "independent_auditor_verdict_included": False,
        "human_promotion_included": False,
        "production_deployment_included": False,
        "bindings": {
            "test_receipt_sha256": _require_digest(test_receipt.get("receipt_sha256"), "test_receipt_sha256"),
            "retrieval_metrics_sha256": _require_digest(retrieval_metrics.get("metrics_sha256"), "retrieval_metrics_sha256"),
            "retrieval_context_sha256": _require_digest(retrieval_result.get("context_sha256"), "retrieval_context_sha256"),
            "traceability_graph_sha256": graph.graph_sha256,
            "playwright_evidence_sha256": playwright["evidence_sha256"],
            "human_review_v1_sha256": _require_digest(human_review_v1.get("packet_sha256"), "human_review_v1_sha256"),
            "security_evidence_sha256": security["evidence_sha256"],
        },
        "artifact_policy": "PRIMARY_STRUCTURED_EVIDENCE_WITH_ARCHIVAL_ZIP_FALLBACK",
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    return manifest
