from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import programming_quality as q
from .hashutil import sha256_bytes, sha256_json, strict_json_loads
from .programming_quality_hardening import evaluate_bound_risk_profile

__all__ = ["evaluate_bound_risk_profile"]

READBACK_SCHEMA_VERSION = 2
EXECUTION_EVIDENCE_SCHEMA_VERSION = 1
SEMANTIC_RISKS = {
    "concurrency", "atomicity", "idempotency", "retries",
    "partial_failures", "external_side_effects",
}
SEMANTIC_HIDDEN_FAMILY = "concurrency_partial_failure"
REQUIRED_TEST007_HOLDOUTS = {
    "test007_concurrent_duplicate_effect",
    "test007_partial_failure_retry",
}
_ALLOWED_TYPES: dict[str, type[Any] | None] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "null": None,
}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,127}\Z")
_SOURCE_FIELDS = {
    "file_json": {"kind", "path", "sha256"},
    "supabase_rest": {"kind", "url_env", "key_env", "schema", "table"},
}


@dataclass(frozen=True)
class ReadbackManifest:
    task_id: str
    checks: tuple[dict[str, Any], ...]
    not_applicable_reason: str | None
    sha256: str


def _short_text(value: Any, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{field} is invalid")
    return value.strip()


def _normalize_source(source: Any, index: int) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError(f"readback checks[{index}].source is invalid")
    kind = source.get("kind")
    if not isinstance(kind, str):
        raise ValueError(f"readback checks[{index}].source.kind is invalid")
    fields = _SOURCE_FIELDS.get(kind)
    if fields is None or set(source) != fields:
        raise ValueError(f"readback checks[{index}].source fields are invalid")
    if kind == "file_json":
        path = _short_text(source["path"], f"readback checks[{index}].source.path", 4096)
        digest = source["sha256"]
        if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
            raise ValueError(f"readback checks[{index}].source.sha256 is invalid")
        return {"kind": kind, "path": path, "sha256": digest}
    url_env = source["url_env"]
    key_env = source["key_env"]
    if not isinstance(url_env, str) or _ENV_NAME.fullmatch(url_env) is None:
        raise ValueError(f"readback checks[{index}].source.url_env is invalid")
    if not isinstance(key_env, str) or _ENV_NAME.fullmatch(key_env) is None:
        raise ValueError(f"readback checks[{index}].source.key_env is invalid")
    return {
        "kind": kind,
        "url_env": url_env,
        "key_env": key_env,
        "schema": _short_text(source["schema"], f"readback checks[{index}].source.schema", 128),
        "table": _short_text(source["table"], f"readback checks[{index}].source.table", 128),
    }


def parse_readback_manifest(value: Any) -> ReadbackManifest:
    top = {"schema_version", "task_id", "checks", "not_applicable_reason"}
    if not isinstance(value, dict) or set(value) != top:
        raise ValueError(f"readback manifest fields must be exactly {sorted(top)}")
    if type(value["schema_version"]) is not int or value["schema_version"] != READBACK_SCHEMA_VERSION:
        raise ValueError(f"readback schema_version must be {READBACK_SCHEMA_VERSION}")
    task_id = _short_text(value["task_id"], "readback task_id", 128)
    checks = value["checks"]
    reason = value["not_applicable_reason"]
    if not isinstance(checks, list):
        raise ValueError("readback checks must be an array")
    if checks and reason is not None:
        raise ValueError("not_applicable_reason must be null when checks exist")
    if not checks and (not isinstance(reason, str) or len(reason.strip()) < 12):
        raise ValueError("empty readback requires an explicit not-applicable reason")
    fields = {
        "entity", "expected_entity", "source", "pk_field", "expected_pk",
        "field", "expected_value", "expected_type", "status_field", "expected_status",
    }
    normalized: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or set(check) != fields:
            raise ValueError(f"readback checks[{index}] fields are invalid")
        if check["expected_type"] not in _ALLOWED_TYPES:
            raise ValueError(f"readback checks[{index}].expected_type is invalid")
        item = dict(check)
        item["source"] = _normalize_source(check["source"], index)
        for field in ("entity", "expected_entity", "pk_field", "field"):
            item[field] = _short_text(check[field], f"readback checks[{index}].{field}")
        if check["status_field"] is not None and not isinstance(check["status_field"], str):
            raise ValueError(f"readback checks[{index}].status_field is invalid")
        normalized.append(item)
    payload = {key: value[key] for key in sorted(top)}
    return ReadbackManifest(
        task_id,
        tuple(normalized),
        None if checks else reason.strip(),
        sha256_json(payload),
    )


def load_readback_manifest(path: Path, expected_sha256: str) -> ReadbackManifest:
    if _HEX64.fullmatch(expected_sha256) is None:
        raise ValueError("readback expected_sha256 is invalid")
    data = path.read_bytes()
    observed = sha256_bytes(data)
    if observed != expected_sha256:
        raise ValueError(f"READBACK_MANIFEST_DIGEST_MISMATCH: expected {expected_sha256}, observed {observed}")
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"readback manifest JSON invalid: {type(exc).__name__}") from exc
    return parse_readback_manifest(value)


def readback_source_paths(manifest: ReadbackManifest) -> tuple[Path, ...]:
    return tuple(
        Path(check["source"]["path"])
        for check in manifest.checks
        if check["source"]["kind"] == "file_json"
    )


def _read_file_json(source: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    path = Path(source["path"])
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != source["sha256"]:
        raise ValueError(f"READBACK_SOURCE_DIGEST_MISMATCH:{path}")
    value = strict_json_loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("READBACK_SOURCE_ROW_NOT_OBJECT")
    return value, digest


def _read_supabase(source: Mapping[str, Any], check: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    base = os.environ.get(source["url_env"], "").rstrip("/")
    key = os.environ.get(source["key_env"], "")
    if not base or not key:
        raise ValueError("READBACK_SUPABASE_CREDENTIALS_MISSING")
    table = urllib.parse.quote(source["table"], safe="")
    pk_field = urllib.parse.quote(check["pk_field"], safe="")
    pk_value = urllib.parse.quote(str(check["expected_pk"]), safe="")
    fields = {check["pk_field"], check["field"]}
    if check["status_field"] is not None:
        fields.add(check["status_field"])
    select = urllib.parse.quote(",".join(sorted(fields)), safe=",")
    url = f"{base}/rest/v1/{table}?{pk_field}=eq.{pk_value}&select={select}"
    request = urllib.request.Request(
        url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept-Profile": source["schema"],
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("READBACK_SUPABASE_RESPONSE_TOO_LARGE")
    value = strict_json_loads(data.decode("utf-8"))
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ValueError("READBACK_SUPABASE_EXPECTED_EXACTLY_ONE_ROW")
    return value[0], sha256_bytes(data)


def _observed_row(check: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    source = check["source"]
    if source["kind"] == "file_json":
        return _read_file_json(source)
    return _read_supabase(source, check)


def load_execution_evidence_config(path: Path) -> dict[str, Any]:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"schema_version", "families"}:
        raise ValueError("execution evidence config fields invalid")
    if value["schema_version"] != EXECUTION_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("execution evidence schema version invalid")
    if not isinstance(value["families"], dict) or set(value["families"]) != set(q.BASELINE_FAMILIES):
        raise ValueError("execution evidence families invalid")
    for family, item in value["families"].items():
        if not isinstance(item, dict) or set(item) != {"hidden_test_suffixes", "adversarial_test_suffixes"}:
            raise ValueError(f"execution evidence family fields invalid:{family}")
        for key in ("hidden_test_suffixes", "adversarial_test_suffixes"):
            items = item[key]
            if not isinstance(items, list) or len(items) != len(set(items)) or not all(isinstance(entry, str) and entry for entry in items):
                raise ValueError(f"execution evidence list invalid:{family}:{key}")
    return value


def _successful_suffixes(successful_test_ids: set[str], suffixes: list[str]) -> list[str]:
    return sorted(
        suffix
        for suffix in suffixes
        if any(test_id.endswith(suffix) for test_id in successful_test_ids)
    )


def evaluate_ci_execution_evidence(
    baseline: Mapping[str, Any],
    config: Mapping[str, Any],
    successful_test_ids: set[str],
    *,
    head_sha: str,
    test_receipt_sha256: str,
) -> dict[str, Any]:
    families: dict[str, Any] = {}
    findings: list[str] = []
    for family in q.BASELINE_FAMILIES:
        mapping = config["families"][family]
        hidden = _successful_suffixes(successful_test_ids, mapping["hidden_test_suffixes"])
        adversarial = _successful_suffixes(successful_test_ids, mapping["adversarial_test_suffixes"])
        required_hidden = baseline["families"][family]["min_hidden_holdouts"]
        required_adversarial = baseline["families"][family]["min_adversarial_tests"]
        if len(hidden) < required_hidden:
            findings.append(f"HIDDEN_EXECUTION_EVIDENCE_BELOW_BASELINE:{family}")
        if len(adversarial) < required_adversarial:
            findings.append(f"ADVERSARIAL_EXECUTION_EVIDENCE_BELOW_BASELINE:{family}")
        families[family] = {
            "hidden_test_ids": hidden,
            "hidden_count": len(hidden),
            "required_hidden_count": required_hidden,
            "adversarial_test_ids": adversarial,
            "adversarial_count": len(adversarial),
            "required_adversarial_count": required_adversarial,
        }
    value: dict[str, Any] = {
        "schema_version": 1,
        "control_id": "PROGRAMMING_QUALITY_EXECUTION_EVIDENCE",
        "exact_head": head_sha,
        "test_receipt_sha256": test_receipt_sha256,
        "families": families,
        "findings": findings,
        "outcome": "FAIL" if findings else "PASS",
        "reason_code": "EXECUTION_EVIDENCE_INSUFFICIENT" if findings else "EXECUTION_EVIDENCE_BOUND_AND_SUFFICIENT",
    }
    value["output_digest"] = sha256_json(value)
    return value
