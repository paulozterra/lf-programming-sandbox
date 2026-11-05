from __future__ import annotations

from collections.abc import Mapping
from typing import Any


LEARNING_EFFICIENCY_METRICS_V1: tuple[str, ...] = (
    "eligible_count",
    "retrieved_count",
    "relevant_retrieved",
    "applied_count",
    "retrieval_precision",
    "retrieval_recall",
    "application_rate",
    "repeat_error_rate",
    "context_bytes_or_tokens",
    "supabase_queries",
    "learning_lookup_latency",
)


class LearningMetricsError(ValueError):
    """Raised when the canonical learning-efficiency metric contract is violated."""


def _not_observed() -> dict[str, Any]:
    return {"value": None, "observation_status": "NOT_OBSERVED"}


def build_learning_efficiency_metrics(*, context_bytes_or_tokens: int | None = None) -> dict[str, Any]:
    metrics = {name: _not_observed() for name in LEARNING_EFFICIENCY_METRICS_V1}
    if context_bytes_or_tokens is not None:
        if isinstance(context_bytes_or_tokens, bool) or not isinstance(context_bytes_or_tokens, int) or context_bytes_or_tokens < 0:
            raise LearningMetricsError("context_bytes_or_tokens must be a non-negative integer")
        metrics["context_bytes_or_tokens"] = {
            "value": context_bytes_or_tokens,
            "observation_status": "OBSERVED",
        }
    envelope = {"contract": "LEARNING_EFFICIENCY_METRICS_V1", "metrics": metrics}
    validate_learning_efficiency_metrics(envelope)
    return envelope


def validate_learning_efficiency_metrics(envelope: Any) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise LearningMetricsError("learning metrics envelope must be an object")
    if envelope.get("contract") != "LEARNING_EFFICIENCY_METRICS_V1":
        raise LearningMetricsError("learning metrics contract mismatch")
    metrics = envelope.get("metrics")
    if not isinstance(metrics, Mapping):
        raise LearningMetricsError("learning metrics must be an object")

    expected = set(LEARNING_EFFICIENCY_METRICS_V1)
    actual = set(metrics)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise LearningMetricsError("missing learning metrics: " + ",".join(missing))
    if unexpected:
        raise LearningMetricsError("unexpected learning metrics: " + ",".join(unexpected))

    for name in LEARNING_EFFICIENCY_METRICS_V1:
        record = metrics[name]
        if not isinstance(record, Mapping):
            raise LearningMetricsError(f"{name} must be an object")
        if set(record) != {"value", "observation_status"}:
            raise LearningMetricsError(f"{name} record shape invalid")
        status = record["observation_status"]
        value = record["value"]
        if status == "NOT_OBSERVED":
            if value is not None:
                raise LearningMetricsError(f"{name} NOT_OBSERVED value must be null")
            continue
        if status != "OBSERVED":
            raise LearningMetricsError(f"{name} observation_status invalid")
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise LearningMetricsError(f"{name} OBSERVED value must be numeric")
        if value < 0:
            raise LearningMetricsError(f"{name} OBSERVED value must be non-negative")

    for numerator, denominator, derived in (
        ("relevant_retrieved", "retrieved_count", "retrieval_precision"),
        ("applied_count", "relevant_retrieved", "application_rate"),
    ):
        num = metrics[numerator]
        den = metrics[denominator]
        out = metrics[derived]
        if num["observation_status"] == den["observation_status"] == "OBSERVED" and den["value"] > 0:
            if out["observation_status"] != "OBSERVED":
                raise LearningMetricsError(f"{derived} must be OBSERVED when inputs are observed")
            expected_value = num["value"] / den["value"]
            if abs(out["value"] - expected_value) > 1e-12:
                raise LearningMetricsError(f"{derived} inconsistent with observed inputs")

    return dict(envelope)
