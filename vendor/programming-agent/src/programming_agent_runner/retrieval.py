from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from .hashutil import sha256_json

RetrievalStatus = Literal["PASS", "BLOCKED"]

ALLOWED_SOURCES = (
    "rules",
    "decisions",
    "ekb",
    "preventions",
    "best_practices",
    "documentation",
    "github",
)
_SOURCE_PRIORITY = {source: len(ALLOWED_SOURCES) - index for index, source in enumerate(ALLOWED_SOURCES)}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RetrievalError(ValueError):
    """Raised when a retrieval input is not explicit enough to replay safely."""


@dataclass(frozen=True)
class TaskContextQuery:
    task_id: str
    project: str
    domain: str
    change_type: str
    version: str
    risk: str
    as_of: str
    required_sources: tuple[str, ...]
    shell: str | None = None
    module: str | None = None
    screen: str | None = None
    paths: tuple[str, ...] = ()
    required_record_ids: tuple[str, ...] = ()
    top_k: int = 12
    max_context_bytes: int = 65536

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeRecord:
    source: str
    record_id: str
    title: str
    content: str
    project: str
    domain: str
    active: bool
    approved: bool
    applicable: bool
    effective_at: str
    expires_at: str | None
    provenance: dict[str, Any]
    shell: str | None = None
    module: str | None = None
    screen: str | None = None
    paths: tuple[str, ...] = ()
    change_types: tuple[str, ...] = ()
    versions: tuple[str, ...] = ()
    risk_tags: tuple[str, ...] = ()
    canonical_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievedFragment:
    source: str
    record_id: str
    title: str
    content: str
    score: int
    reasons: tuple[str, ...]
    provenance: dict[str, Any]
    content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalResult:
    status: RetrievalStatus
    query: dict[str, Any]
    selected: tuple[RetrievedFragment, ...]
    missing_critical_context: tuple[str, ...]
    filtered_counts: dict[str, int]
    context_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "selected": [item.to_dict() for item in self.selected],
            "missing_critical_context": list(self.missing_critical_context),
            "filtered_counts": self.filtered_counts,
            "context_sha256": self.context_sha256,
        }


@dataclass(frozen=True)
class GoldCase:
    case_id: str
    query: TaskContextQuery
    records: tuple[KnowledgeRecord, ...]
    expected_record_ids: tuple[str, ...]
    expected_status: RetrievalStatus


def _text(value: Any, field: str, maximum: int = 200_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise RetrievalError(f"{field} must be a non-empty UTF-8 string <= {maximum} bytes")
    return value


def _strings(value: Any, field: str, *, required: bool = False, maximum: int = 256) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum or (required and not value):
        raise RetrievalError(f"{field} must be an array with 1..{maximum} values" if required else f"{field} invalid")
    result = tuple(_text(item, f"{field}[]", 4096) for item in value)
    if len(set(result)) != len(result):
        raise RetrievalError(f"{field} contains duplicates")
    return result


def _time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RetrievalError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise RetrievalError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RetrievalError("provenance must be an object")
    required = {"source_ref", "snapshot_sha256", "observed_at"}
    if not required.issubset(value):
        raise RetrievalError(f"provenance must include {sorted(required)}")
    _text(value["source_ref"], "provenance.source_ref", 8192)
    digest = value["snapshot_sha256"]
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise RetrievalError("provenance.snapshot_sha256 must be lowercase SHA-256")
    _time(_text(value["observed_at"], "provenance.observed_at", 128), "provenance.observed_at")
    return dict(value)


def task_context_query_from_dict(value: Any) -> TaskContextQuery:
    if not isinstance(value, dict):
        raise RetrievalError("query must be an object")
    required = {"task_id", "project", "domain", "change_type", "version", "risk", "as_of", "required_sources"}
    missing = sorted(required - set(value))
    if missing:
        raise RetrievalError(f"query missing fields: {missing}")
    sources = _strings(value["required_sources"], "required_sources", required=True, maximum=7)
    unknown = sorted(set(sources) - set(ALLOWED_SOURCES))
    if unknown:
        raise RetrievalError(f"unsupported required_sources: {unknown}")
    top_k = value.get("top_k", 12)
    max_bytes = value.get("max_context_bytes", 65536)
    if type(top_k) is not int or not 1 <= top_k <= 100 or top_k < len(sources):
        raise RetrievalError("top_k must be in [1,100] and cover every required source")
    if type(max_bytes) is not int or not 1024 <= max_bytes <= 2_000_000:
        raise RetrievalError("max_context_bytes must be in [1024,2000000]")
    as_of = _text(value["as_of"], "as_of", 128)
    _time(as_of, "as_of")
    optional = {}
    for field in ("shell", "module", "screen"):
        item = value.get(field)
        optional[field] = None if item is None else _text(item, field, 4096)
    return TaskContextQuery(
        task_id=_text(value["task_id"], "task_id", 256),
        project=_text(value["project"], "project", 4096),
        domain=_text(value["domain"], "domain", 4096),
        change_type=_text(value["change_type"], "change_type", 4096),
        version=_text(value["version"], "version", 4096),
        risk=_text(value["risk"], "risk", 4096),
        as_of=as_of,
        required_sources=sources,
        shell=optional["shell"],
        module=optional["module"],
        screen=optional["screen"],
        paths=_strings(value.get("paths", []), "paths"),
        required_record_ids=_strings(value.get("required_record_ids", []), "required_record_ids"),
        top_k=top_k,
        max_context_bytes=max_bytes,
    )


def knowledge_record_from_dict(value: Any) -> KnowledgeRecord:
    if not isinstance(value, dict):
        raise RetrievalError("knowledge record must be an object")
    required = {
        "source", "record_id", "title", "content", "project", "domain", "active", "approved",
        "applicable", "effective_at", "provenance",
    }
    missing = sorted(required - set(value))
    if missing:
        raise RetrievalError(f"knowledge record missing fields: {missing}")
    source = _text(value["source"], "source", 128)
    if source not in ALLOWED_SOURCES:
        raise RetrievalError(f"unsupported source: {source}")
    for field in ("active", "approved", "applicable"):
        if type(value[field]) is not bool:
            raise RetrievalError(f"{field} must be boolean")
    effective = _text(value["effective_at"], "effective_at", 128)
    _time(effective, "effective_at")
    expires = value.get("expires_at")
    if expires is not None:
        expires = _text(expires, "expires_at", 128)
        _time(expires, "expires_at")
    optional: dict[str, str | None] = {}
    for field in ("shell", "module", "screen", "canonical_key"):
        item = value.get(field)
        optional[field] = None if item is None else _text(item, field, 4096)
    return KnowledgeRecord(
        source=source,
        record_id=_text(value["record_id"], "record_id", 512),
        title=_text(value["title"], "title", 8192),
        content=_text(value["content"], "content"),
        project=_text(value["project"], "project", 4096),
        domain=_text(value["domain"], "domain", 4096),
        active=value["active"], approved=value["approved"], applicable=value["applicable"],
        effective_at=effective, expires_at=expires, provenance=_provenance(value["provenance"]),
        shell=optional["shell"], module=optional["module"], screen=optional["screen"],
        paths=_strings(value.get("paths", []), "paths"),
        change_types=_strings(value.get("change_types", []), "change_types"),
        versions=_strings(value.get("versions", []), "versions"),
        risk_tags=_strings(value.get("risk_tags", []), "risk_tags"),
        canonical_key=optional["canonical_key"],
    )


def _fresh(query: TaskContextQuery, record: KnowledgeRecord) -> bool:
    as_of = _time(query.as_of, "as_of")
    if _time(record.effective_at, "effective_at") > as_of:
        return False
    return record.expires_at is None or _time(record.expires_at, "expires_at") > as_of


def _match(query: TaskContextQuery, record: KnowledgeRecord) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if record.project != query.project:
        return False, reasons
    reasons.append("project")
    for field in ("shell", "module", "screen"):
        record_value = getattr(record, field)
        if record_value is not None:
            if getattr(query, field) != record_value:
                return False, reasons
            reasons.append(field)
    if record.domain not in {query.domain, "transversal"}:
        return False, reasons
    reasons.append("domain")
    if record.paths:
        overlap = sorted(set(record.paths) & set(query.paths))
        if not overlap:
            return False, reasons
        reasons.extend(f"path:{item}" for item in overlap)
    if record.change_types and query.change_type not in record.change_types:
        return False, reasons
    if record.change_types:
        reasons.append("change_type")
    if record.versions and query.version not in record.versions:
        return False, reasons
    if record.versions:
        reasons.append("version")
    if query.risk in record.risk_tags:
        reasons.append("risk")
    return True, reasons


def _score(query: TaskContextQuery, record: KnowledgeRecord, reasons: list[str]) -> tuple[int, tuple[str, ...]]:
    weights = {"project": 40, "shell": 50, "module": 80, "screen": 120, "domain": 30, "change_type": 20,
               "version": 20, "risk": 10}
    score = _SOURCE_PRIORITY[record.source]
    for reason in reasons:
        score += 25 if reason.startswith("path:") else weights.get(reason, 0)
    extra = list(reasons)
    if record.source in query.required_sources:
        score += 100
        extra.append("required_source")
    if record.record_id in query.required_record_ids:
        score += 1000
        extra.append("required_record")
    return score, tuple(sorted(set(extra)))


def _fragment(record: KnowledgeRecord, score: int, reasons: tuple[str, ...]) -> RetrievedFragment:
    content_sha256 = sha256_json({"source": record.source, "record_id": record.record_id, "title": record.title,
                                  "content": record.content, "provenance": record.provenance})
    return RetrievedFragment(record.source, record.record_id, record.title, record.content, score, reasons,
                             record.provenance, content_sha256)


def retrieve_context(query: TaskContextQuery, records: Iterable[KnowledgeRecord]) -> RetrievalResult:
    counts = {"inactive_or_unapproved": 0, "stale": 0, "scope": 0, "deduplicated": 0, "eligible": 0}
    candidates: list[tuple[KnowledgeRecord, int, tuple[str, ...]]] = []
    for record in records:
        if not (record.active and record.approved and record.applicable):
            counts["inactive_or_unapproved"] += 1
            continue
        if not _fresh(query, record):
            counts["stale"] += 1
            continue
        matched, reasons = _match(query, record)
        if not matched:
            counts["scope"] += 1
            continue
        score, why = _score(query, record, reasons)
        candidates.append((record, score, why))
    candidates.sort(key=lambda item: (-item[1], -_SOURCE_PRIORITY[item[0].source], item[0].record_id))

    unique: list[tuple[KnowledgeRecord, int, tuple[str, ...]]] = []
    keys: set[str] = set()
    for item in candidates:
        key = item[0].canonical_key or f"{item[0].source}:{item[0].record_id}"
        if key in keys:
            counts["deduplicated"] += 1
            continue
        keys.add(key)
        unique.append(item)
    counts["eligible"] = len(unique)

    selected: list[tuple[KnowledgeRecord, int, tuple[str, ...]]] = []
    selected_ids: set[str] = set()

    def add(item: tuple[KnowledgeRecord, int, tuple[str, ...]]) -> None:
        if item[0].record_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item[0].record_id)

    for record_id in query.required_record_ids:
        match = next((item for item in unique if item[0].record_id == record_id), None)
        if match is not None:
            add(match)
    for source in query.required_sources:
        match = next((item for item in unique if item[0].source == source), None)
        if match is not None:
            add(match)
    for item in unique:
        if len(selected) >= query.top_k:
            break
        add(item)

    missing: list[str] = []
    if len(selected) > query.top_k:
        missing.append("top_k_budget_cannot_satisfy_required_context")
    present_sources = {item[0].source for item in selected[: query.top_k]}
    for source in query.required_sources:
        if source not in present_sources:
            missing.append(f"required_source:{source}")
    for record_id in query.required_record_ids:
        if record_id not in selected_ids:
            missing.append(f"required_record:{record_id}")

    fragments = tuple(_fragment(*item) for item in selected[: query.top_k])
    total_bytes = sum(len(item.content.encode("utf-8")) + len(item.title.encode("utf-8")) + 256 for item in fragments)
    if total_bytes > query.max_context_bytes:
        missing.append(f"context_byte_budget_exceeded:{total_bytes}>{query.max_context_bytes}")
        fragments = ()
    status: RetrievalStatus = "PASS" if not missing else "BLOCKED"
    payload = {"schema_version": 1, "status": status, "query": query.to_dict(),
               "selected": [item.to_dict() for item in fragments], "missing_critical_context": sorted(set(missing)),
               "filtered_counts": counts}
    return RetrievalResult(status, query.to_dict(), fragments, tuple(sorted(set(missing))), counts, sha256_json(payload))


def gold_case_from_dict(value: Any) -> GoldCase:
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise RetrievalError("gold case must contain records[]")
    status = value.get("expected_status", "PASS")
    if status not in {"PASS", "BLOCKED"}:
        raise RetrievalError("expected_status must be PASS or BLOCKED")
    return GoldCase(
        case_id=_text(value.get("case_id"), "case_id", 256),
        query=task_context_query_from_dict(value.get("query")),
        records=tuple(knowledge_record_from_dict(item) for item in value["records"]),
        expected_record_ids=_strings(value.get("expected_record_ids", []), "expected_record_ids"),
        expected_status=status,
    )


def evaluate_gold_set(cases: Iterable[GoldCase]) -> dict[str, Any]:
    values = list(cases)
    if not values:
        raise RetrievalError("gold set is empty")
    recalls: list[float] = []
    precisions: list[float] = []
    irrelevant = selected_total = provenance_total = provenance_complete = stale = missing_cases = deterministic = status_ok = 0
    per_case: list[dict[str, Any]] = []
    for case in values:
        first = retrieve_context(case.query, case.records)
        replay = retrieve_context(case.query, case.records)
        deterministic += int(first.to_dict() == replay.to_dict())
        status_ok += int(first.status == case.expected_status)
        selected = {item.record_id for item in first.selected}
        expected = set(case.expected_record_ids)
        recalls.append(len(selected & expected) / len(expected) if expected else 1.0)
        precisions.append(len(selected & expected) / len(selected) if selected else 1.0)
        irrelevant += len(selected - expected)
        selected_total += len(selected)
        missing_cases += int(bool(first.missing_critical_context))
        for fragment in first.selected:
            provenance_total += 1
            provenance_complete += int({"source_ref", "snapshot_sha256", "observed_at"}.issubset(fragment.provenance))
            record = next(item for item in case.records if item.record_id == fragment.record_id)
            stale += int(not _fresh(case.query, record))
        per_case.append({"case_id": case.case_id, "status": first.status, "expected_status": case.expected_status,
                         "selected_record_ids": sorted(selected), "expected_record_ids": sorted(expected),
                         "missing_critical_context": list(first.missing_critical_context),
                         "context_sha256": first.context_sha256})
    count = len(values)
    metrics: dict[str, Any] = {
        "schema_version": 1, "cases": count, "recall_at_k": sum(recalls) / count,
        "precision_at_k": sum(precisions) / count,
        "stale_context_rate": stale / selected_total if selected_total else 0.0,
        "missing_critical_context_rate": missing_cases / count,
        "irrelevant_context_rate": irrelevant / selected_total if selected_total else 0.0,
        "citation_provenance_completeness": provenance_complete / provenance_total if provenance_total else 1.0,
        "deterministic_replay_rate": deterministic / count, "expected_status_match_rate": status_ok / count,
        "per_case": per_case,
    }
    metrics["metrics_sha256"] = sha256_json(metrics)
    return metrics


def retrieval_quality_passes(metrics: dict[str, Any]) -> bool:
    return (
        metrics.get("recall_at_k", 0.0) >= 0.95
        and metrics.get("precision_at_k", 0.0) >= 0.90
        and metrics.get("stale_context_rate") == 0.0
        and metrics.get("irrelevant_context_rate", 1.0) <= 0.10
        and metrics.get("citation_provenance_completeness") == 1.0
        and metrics.get("deterministic_replay_rate") == 1.0
        and metrics.get("expected_status_match_rate") == 1.0
    )
