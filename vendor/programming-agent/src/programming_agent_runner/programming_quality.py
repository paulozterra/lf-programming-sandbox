from __future__ import annotations

import ast
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .hashutil import sha256_bytes, sha256_file, sha256_json, strict_json_loads
from .security_gate import scan_repository
from .verified_worker import run_verified_worker
from .worker_commands import AcceptanceResult, run_acceptance_suite
from .worker_oracle import HiddenOracle
from .worker_spec import (
    AcceptanceCommand,
    TaskSpecError,
    WorkerTaskSpec,
    _acceptance_commands,
    canonical_relative_path,
)
from .worker_workspace import (
    WorkspaceError,
    create_disposable_workspace,
    replay_cumulative_patch,
    verify_source_repository,
)

QUALITY_PLAN_SCHEMA_VERSION = 1
QUALITY_RECEIPT_SCHEMA_VERSION = 1
BASELINE_SCHEMA_VERSION = 1

RISK_DIMENSIONS = (
    "concurrency",
    "atomicity",
    "idempotency",
    "retries",
    "partial_failures",
    "external_side_effects",
    "security",
    "persistence",
)
COVERAGE_KINDS = {"acceptance_test", "hidden_adversarial_test", "architecture_judge", "security_judge"}
FIXTURE_STAGES = ("parse_compile", "lint_static", "setup_import", "reachability")
BASELINE_FAMILIES = (
    "root_cause_bug",
    "multi_file_feature",
    "concurrency_partial_failure",
    "security",
)
BASELINE_CONTROLS = (
    "risk_profile_pre_exec",
    "fixture_preflight",
    "semantic_post_green_judge",
    "programming_quality_regression",
    "readback_field_binding",
)
BASELINE_THRESHOLD_KEYS = {
    "min_family_count",
    "min_total_adversarial",
    "min_total_hidden_holdouts",
}
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_GENERIC_NA = {"n/a", "na", "not applicable", "none", "no aplica", "no aplica."}

_GET_CALLS = {"get", "load", "lookup", "find", "exists", "is_processed"}
_EFFECT_CALLS = {"charge", "debit", "transfer", "send", "publish", "dispatch", "create_payment"}
_SAVE_CALLS = {"save", "persist", "mark_processed", "update", "insert", "commit", "set_processed"}
_GUARD_CALLS = {
    "claim",
    "claim_once",
    "reserve",
    "acquire",
    "lock",
    "compare_and_set",
    "insert_if_absent",
    "upsert",
    "begin",
    "transaction",
}
_IDEMPOTENCY_TOKENS = {"idempotency_key", "idempotency", "request_key", "dedupe_key"}

_PLAN_FIELDS = {
    "schema_version",
    "task_id",
    "base_head_sha",
    "risk_profile",
    "fixture_preflight_commands",
    "semantic_paths",
}
_RISK_FIELDS = {"dimension", "classification", "justification", "coverage"}
_COVERAGE_FIELDS = {"kind", "ref"}
_BASELINE_FIELDS = {
    "schema_version",
    "baseline_id",
    "decision_ref",
    "families",
    "controls",
    "protected_artifacts",
    "thresholds",
    "change_authorization",
}
_FAMILY_FIELDS = {
    "required_test_suffixes",
    "min_hidden_holdouts",
    "min_adversarial_tests",
    "semantic_required",
}
_AUTH_FIELDS = {"decision_ref", "evidence_ref", "reason"}


@dataclass(frozen=True)
class QualityPlan:
    task_id: str
    base_head_sha: str
    risk_profile: tuple[dict[str, Any], ...]
    fixture_preflight_commands: tuple[AcceptanceCommand, ...]
    semantic_paths: tuple[str, ...]
    sha256: str


@dataclass(frozen=True)
class ProgrammingQualityWorkerResult:
    receipt: dict[str, Any]
    patch: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_timestamp(timestamp: str | None) -> str:
    if timestamp is None:
        return _utc_now()
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("timestamp must be non-empty text")
    return timestamp


def _control_receipt(
    control_id: str,
    *,
    task_id: str,
    execution_id: str,
    head_sha: str,
    input_digest: str,
    outcome: str,
    reason_code: str,
    evidence_refs: Iterable[str] = (),
    details: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if outcome not in {"PASS", "FAIL", "BLOCKED", "N/A"}:
        raise ValueError(f"invalid control outcome: {outcome}")
    if _HEX40.fullmatch(head_sha) is None or _HEX64.fullmatch(input_digest) is None:
        raise ValueError("control receipt requires canonical head/input digest")
    value: dict[str, Any] = {
        "schema_version": QUALITY_RECEIPT_SCHEMA_VERSION,
        "control_id": control_id,
        "task_id": task_id,
        "execution_id": execution_id,
        "exact_head": head_sha,
        "timestamp": _safe_timestamp(timestamp),
        "input_digest": input_digest,
        "outcome": outcome,
        "reason_code": reason_code,
        "evidence_refs": sorted(set(evidence_refs)),
        "details": dict(details or {}),
    }
    value["output_digest"] = sha256_json(value)
    return value


def validate_control_receipt(receipt: Any) -> list[str]:
    if not isinstance(receipt, dict):
        return ["RECEIPT_NOT_OBJECT"]
    errors: list[str] = []
    expected = {
        "schema_version",
        "control_id",
        "task_id",
        "execution_id",
        "exact_head",
        "timestamp",
        "input_digest",
        "outcome",
        "reason_code",
        "evidence_refs",
        "details",
        "output_digest",
    }
    if set(receipt) != expected:
        errors.append("RECEIPT_FIELDS_MISMATCH")
    if receipt.get("schema_version") != QUALITY_RECEIPT_SCHEMA_VERSION:
        errors.append("RECEIPT_SCHEMA_INVALID")
    if receipt.get("outcome") not in {"PASS", "FAIL", "BLOCKED", "N/A"}:
        errors.append("RECEIPT_OUTCOME_INVALID")
    if not isinstance(receipt.get("exact_head"), str) or _HEX40.fullmatch(receipt["exact_head"]) is None:
        errors.append("RECEIPT_HEAD_INVALID")
    if not isinstance(receipt.get("input_digest"), str) or _HEX64.fullmatch(receipt["input_digest"]) is None:
        errors.append("RECEIPT_INPUT_DIGEST_INVALID")
    digest = receipt.get("output_digest")
    if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        errors.append("RECEIPT_OUTPUT_DIGEST_INVALID")
    elif sha256_json({key: value for key, value in receipt.items() if key != "output_digest"}) != digest:
        errors.append("RECEIPT_OUTPUT_DIGEST_MISMATCH")
    refs = receipt.get("evidence_refs")
    if not isinstance(refs, list) or refs != sorted(set(refs)) or not all(isinstance(ref, str) and ref for ref in refs):
        errors.append("RECEIPT_EVIDENCE_REFS_INVALID")
    if not isinstance(receipt.get("details"), dict):
        errors.append("RECEIPT_DETAILS_INVALID")
    return sorted(set(errors))


def _quality_plan_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": value["schema_version"],
        "task_id": value["task_id"],
        "base_head_sha": value["base_head_sha"],
        "risk_profile": value["risk_profile"],
        "fixture_preflight_commands": value["fixture_preflight_commands"],
        "semantic_paths": value["semantic_paths"],
    }


def parse_quality_plan(value: Any) -> QualityPlan:
    if not isinstance(value, dict) or set(value) != _PLAN_FIELDS:
        raise ValueError(f"quality plan fields must be exactly {sorted(_PLAN_FIELDS)}")
    if type(value["schema_version"]) is not int or value["schema_version"] != QUALITY_PLAN_SCHEMA_VERSION:
        raise ValueError(f"quality plan schema_version must be {QUALITY_PLAN_SCHEMA_VERSION}")
    task_id = value["task_id"]
    if not isinstance(task_id, str) or not task_id or len(task_id.encode("utf-8")) > 128:
        raise ValueError("quality plan task_id is invalid")
    head_sha = value["base_head_sha"]
    if not isinstance(head_sha, str) or _HEX40.fullmatch(head_sha) is None:
        raise ValueError("quality plan base_head_sha is invalid")

    profile = value["risk_profile"]
    if not isinstance(profile, list) or len(profile) != len(RISK_DIMENSIONS):
        raise ValueError("risk_profile must explicitly classify every required dimension")
    normalized_profile: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in profile:
        if not isinstance(entry, dict) or set(entry) != _RISK_FIELDS:
            raise ValueError(f"risk profile fields must be exactly {sorted(_RISK_FIELDS)}")
        dimension = entry["dimension"]
        if dimension not in RISK_DIMENSIONS or dimension in seen:
            raise ValueError(f"risk profile dimension is invalid or duplicated: {dimension!r}")
        classification = entry["classification"]
        if classification not in {"APPLIES", "N/A"}:
            raise ValueError(f"risk profile classification invalid for {dimension}")
        justification = entry["justification"]
        if (
            not isinstance(justification, str)
            or len(justification.strip()) < 12
            or justification.strip().lower() in _GENERIC_NA
        ):
            raise ValueError(f"risk profile justification is too weak for {dimension}")
        coverage = entry["coverage"]
        if not isinstance(coverage, list):
            raise ValueError(f"risk profile coverage must be an array for {dimension}")
        normalized_coverage: list[dict[str, str]] = []
        for binding in coverage:
            if not isinstance(binding, dict) or set(binding) != _COVERAGE_FIELDS:
                raise ValueError(f"coverage binding fields must be exactly {sorted(_COVERAGE_FIELDS)}")
            kind = binding["kind"]
            ref = binding["ref"]
            if kind not in COVERAGE_KINDS or not isinstance(ref, str) or not ref.strip():
                raise ValueError(f"coverage binding invalid for {dimension}")
            normalized_coverage.append({"kind": kind, "ref": ref})
        if classification == "APPLIES" and not normalized_coverage:
            raise ValueError(f"APPLIES risk lacks bound coverage: {dimension}")
        if classification == "N/A" and normalized_coverage:
            raise ValueError(f"N/A risk must not bind coverage: {dimension}")
        normalized_profile.append(
            {
                "dimension": dimension,
                "classification": classification,
                "justification": justification.strip(),
                "coverage": normalized_coverage,
            }
        )
        seen.add(dimension)
    if seen != set(RISK_DIMENSIONS):
        raise ValueError("risk_profile does not cover every required dimension")

    try:
        fixture_commands = _acceptance_commands(value["fixture_preflight_commands"])
    except TaskSpecError as exc:
        raise ValueError(f"fixture preflight commands invalid: {exc}") from exc
    if tuple(command.name for command in fixture_commands) != FIXTURE_STAGES:
        raise ValueError(f"fixture preflight stages must be exactly {FIXTURE_STAGES}")

    semantic_paths_raw = value["semantic_paths"]
    if not isinstance(semantic_paths_raw, list):
        raise ValueError("semantic_paths must be an array")
    semantic_paths = tuple(canonical_relative_path(path, "semantic_paths[]") for path in semantic_paths_raw)
    if len(set(semantic_paths)) != len(semantic_paths):
        raise ValueError("semantic_paths contains duplicates")

    payload = _quality_plan_payload(value)
    return QualityPlan(
        task_id=task_id,
        base_head_sha=head_sha,
        risk_profile=tuple(normalized_profile),
        fixture_preflight_commands=fixture_commands,
        semantic_paths=semantic_paths,
        sha256=sha256_json(payload),
    )


def load_quality_plan(path: Path, expected_sha256: str) -> QualityPlan:
    if _HEX64.fullmatch(expected_sha256) is None:
        raise ValueError("quality plan expected_sha256 is invalid")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"quality plan unreadable: {type(exc).__name__}") from exc
    observed = sha256_bytes(data)
    if observed != expected_sha256:
        raise ValueError(f"QUALITY_PLAN_DIGEST_MISMATCH: expected {expected_sha256}, observed {observed}")
    try:
        raw = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"quality plan JSON invalid: {type(exc).__name__}") from exc
    plan = parse_quality_plan(raw)
    if plan.sha256 != sha256_json(_quality_plan_payload(raw)):
        raise ValueError("quality plan canonical digest mismatch")
    return plan


def evaluate_risk_profile(
    plan: QualityPlan,
    *,
    execution_id: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    missing = [
        entry["dimension"]
        for entry in plan.risk_profile
        if entry["classification"] == "APPLIES" and not entry["coverage"]
    ]
    outcome = "FAIL" if missing else "PASS"
    reason = "APPLICABLE_RISK_UNBOUND" if missing else "ALL_APPLICABLE_RISKS_BOUND"
    return _control_receipt(
        "RISK_PROFILE_PRE_EXEC",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=plan.sha256,
        outcome=outcome,
        reason_code=reason,
        evidence_refs=[binding["ref"] for entry in plan.risk_profile for binding in entry["coverage"]],
        details={"risk_profile": list(plan.risk_profile), "unbound_dimensions": missing},
        timestamp=timestamp,
    )


def _command_record(result: AcceptanceResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "status": result.status,
        "reason": result.reason,
        "returncode": result.returncode,
        "stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
        "stderr_sha256": sha256_bytes(result.stderr.encode("utf-8")),
        "duration_ms": result.duration_ms,
    }


def run_fixture_preflight(
    workspace: Path,
    plan: QualityPlan,
    *,
    execution_id: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    results = run_acceptance_suite(workspace, plan.fixture_preflight_commands)
    records = [_command_record(result) for result in results]
    complete = len(results) == len(plan.fixture_preflight_commands)
    passed = complete and all(result.status == "PASS" for result in results)
    if passed:
        outcome = "PASS"
        reason = "FIXTURE_VALID"
        classification = "FIXTURE_VALID"
    else:
        outcome = "FAIL"
        reason = "FIXTURE_INVALID"
        classification = "FIXTURE_INVALID"
    return _control_receipt(
        "FIXTURE_PREFLIGHT",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json(
            {
                "plan_sha256": plan.sha256,
                "stages": [command.to_dict() for command in plan.fixture_preflight_commands],
            }
        ),
        outcome=outcome,
        reason_code=reason,
        evidence_refs=[f"fixture:{record['name']}" for record in records],
        details={
            "classification": classification,
            "stages": records,
            "expected_stage_order": list(FIXTURE_STAGES),
            "complete": complete,
        },
        timestamp=timestamp,
    )


def classify_fixture_and_implementation(fixture_receipt: Mapping[str, Any], implementation_status: str) -> str:
    if fixture_receipt.get("reason_code") == "FIXTURE_INVALID" or fixture_receipt.get("outcome") != "PASS":
        return "FIXTURE_INVALID"
    if implementation_status == "PASS":
        return "PASS"
    if implementation_status == "BLOCKED":
        return "IMPLEMENTATION_BLOCKED"
    return "IMPLEMENTATION_FAIL"


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _call_has_idempotency(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg and any(token in keyword.arg.lower() for token in _IDEMPOTENCY_TOKENS):
            return True
    for argument in call.args:
        if isinstance(argument, ast.Name) and any(token in argument.id.lower() for token in _IDEMPOTENCY_TOKENS):
            return True
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            if any(token in argument.value.lower() for token in _IDEMPOTENCY_TOKENS):
                return True
    return False


def _semantic_findings_for_tree(tree: ast.AST, path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    scopes: list[ast.AST] = [tree]
    scopes.extend(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    seen: set[tuple[str, int, str]] = set()
    for scope in scopes:
        calls = sorted(
            (node for node in ast.walk(scope) if isinstance(node, ast.Call)),
            key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
        )
        names = [_call_name(call) for call in calls]
        for index, call in enumerate(calls):
            name = names[index]
            if name not in _EFFECT_CALLS:
                continue
            prior_names = names[:index]
            later_names = names[index + 1 :]
            prior_get = any(item in _GET_CALLS for item in prior_names)
            prior_guard = any(item in _GUARD_CALLS for item in prior_names)
            later_save = any(item in _SAVE_CALLS for item in later_names)
            if prior_get and later_save and not prior_guard:
                key = (path, getattr(call, "lineno", 0), "RACE_GET_EFFECT_SAVE")
                if key not in seen:
                    findings.append(
                        {
                            "code": "RACE_GET_EFFECT_SAVE",
                            "path": path,
                            "line": getattr(call, "lineno", 0),
                            "detail": "non-atomic read/check precedes external effect and durable save",
                        }
                    )
                    seen.add(key)
            if later_save and not _call_has_idempotency(call):
                key = (path, getattr(call, "lineno", 0), "PARTIAL_FAILURE_EFFECT_BEFORE_DURABLE_STATE")
                if key not in seen:
                    findings.append(
                        {
                            "code": "PARTIAL_FAILURE_EFFECT_BEFORE_DURABLE_STATE",
                            "path": path,
                            "line": getattr(call, "lineno", 0),
                            "detail": "external effect can succeed before durable save without idempotency binding",
                        }
                    )
                    seen.add(key)
    return sorted(findings, key=lambda item: (item["path"], item["line"], item["code"]))


def semantic_post_green_judge(
    sources: Mapping[str, str],
    plan: QualityPlan,
    *,
    execution_id: str,
    tests_green: bool,
    timestamp: str | None = None,
) -> dict[str, Any]:
    applicable = {
        entry["dimension"]
        for entry in plan.risk_profile
        if entry["classification"] == "APPLIES"
    }
    semantic_risks = applicable & {
        "concurrency",
        "atomicity",
        "idempotency",
        "retries",
        "partial_failures",
        "external_side_effects",
    }
    if not semantic_risks:
        return _control_receipt(
            "SEMANTIC_POST_GREEN_JUDGE",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=sha256_json({"plan_sha256": plan.sha256, "sources": sorted(sources)}),
            outcome="N/A",
            reason_code="NO_APPLICABLE_NONFUNCTIONAL_RISK",
            details={"applicable_risks": sorted(applicable)},
            timestamp=timestamp,
        )
    if not tests_green:
        return _control_receipt(
            "SEMANTIC_POST_GREEN_JUDGE",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=sha256_json({"plan_sha256": plan.sha256, "sources": sorted(sources)}),
            outcome="BLOCKED",
            reason_code="POST_GREEN_PRECONDITION_NOT_MET",
            details={"applicable_risks": sorted(semantic_risks)},
            timestamp=timestamp,
        )
    findings: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    for path, text in sorted(sources.items()):
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as exc:
            parse_errors.append({"path": path, "error": f"{exc.msg}:{exc.lineno}"})
            continue
        findings.extend(_semantic_findings_for_tree(tree, path))
    if parse_errors:
        outcome = "BLOCKED"
        reason = "SEMANTIC_SOURCE_PARSE_ERROR"
    elif findings:
        outcome = "FAIL"
        reason = "SEMANTIC_RISK_DETECTED"
    else:
        outcome = "PASS"
        reason = "SEMANTIC_RISKS_COVERED"
    source_digest = sha256_json(
        {path: sha256_bytes(text.encode("utf-8")) for path, text in sorted(sources.items())}
    )
    return _control_receipt(
        "SEMANTIC_POST_GREEN_JUDGE",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({"plan_sha256": plan.sha256, "source_digest": source_digest}),
        outcome=outcome,
        reason_code=reason,
        evidence_refs=[f"semantic:{item['path']}:{item['line']}:{item['code']}" for item in findings],
        details={
            "tests_green": tests_green,
            "applicable_risks": sorted(semantic_risks),
            "findings": findings,
            "parse_errors": parse_errors,
            "source_digest": source_digest,
        },
        timestamp=timestamp,
    )


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def validate_baseline(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["BASELINE_NOT_OBJECT"]
    if set(value) != _BASELINE_FIELDS:
        errors.append("BASELINE_FIELDS_MISMATCH")
    if value.get("schema_version") != BASELINE_SCHEMA_VERSION:
        errors.append("BASELINE_SCHEMA_INVALID")
    if not isinstance(value.get("baseline_id"), str) or not value.get("baseline_id"):
        errors.append("BASELINE_ID_INVALID")
    if value.get("decision_ref") != "ADR-PROG-004":
        errors.append("BASELINE_DECISION_REF_INVALID")
    families = value.get("families")
    if not isinstance(families, dict) or set(families) != set(BASELINE_FAMILIES):
        errors.append("BASELINE_FAMILIES_INVALID")
    else:
        for name in BASELINE_FAMILIES:
            family = families.get(name)
            if not isinstance(family, dict) or set(family) != _FAMILY_FIELDS:
                errors.append(f"BASELINE_FAMILY_FIELDS_INVALID:{name}")
                continue
            suffixes = family.get("required_test_suffixes")
            if (
                not isinstance(suffixes, list)
                or not suffixes
                or len(set(suffixes)) != len(suffixes)
                or not all(isinstance(item, str) and item for item in suffixes)
            ):
                errors.append(f"BASELINE_REQUIRED_TESTS_INVALID:{name}")
            try:
                _positive_int(family.get("min_hidden_holdouts"), f"{name}.min_hidden_holdouts")
                _positive_int(family.get("min_adversarial_tests"), f"{name}.min_adversarial_tests")
            except ValueError:
                errors.append(f"BASELINE_COUNTS_INVALID:{name}")
            if type(family.get("semantic_required")) is not bool:
                errors.append(f"BASELINE_SEMANTIC_FLAG_INVALID:{name}")
    controls = value.get("controls")
    if not isinstance(controls, dict) or set(controls) != set(BASELINE_CONTROLS):
        errors.append("BASELINE_CONTROLS_INVALID")
    elif any(type(controls[name]) is not bool for name in BASELINE_CONTROLS):
        errors.append("BASELINE_CONTROL_VALUE_INVALID")
    protected = value.get("protected_artifacts")
    if not isinstance(protected, dict) or not protected:
        errors.append("BASELINE_PROTECTED_ARTIFACTS_INVALID")
    else:
        for path, digest in protected.items():
            try:
                canonical_relative_path(path, "protected_artifacts")
            except (TaskSpecError, ValueError):
                errors.append(f"BASELINE_PROTECTED_PATH_INVALID:{path}")
            if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
                errors.append(f"BASELINE_PROTECTED_DIGEST_INVALID:{path}")
    thresholds = value.get("thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != BASELINE_THRESHOLD_KEYS:
        errors.append("BASELINE_THRESHOLDS_INVALID")
    elif any(type(item) is not int or item < 0 for item in thresholds.values()):
        errors.append("BASELINE_THRESHOLD_VALUE_INVALID")
    elif isinstance(families, dict) and set(families) == set(BASELINE_FAMILIES):
        valid_family_values = all(
            isinstance(families.get(name), dict)
            and type(families[name].get("min_hidden_holdouts")) is int
            and type(families[name].get("min_adversarial_tests")) is int
            for name in BASELINE_FAMILIES
        )
        if valid_family_values:
            total_hidden = sum(families[name]["min_hidden_holdouts"] for name in BASELINE_FAMILIES)
            total_adversarial = sum(families[name]["min_adversarial_tests"] for name in BASELINE_FAMILIES)
            if thresholds["min_family_count"] > len(BASELINE_FAMILIES):
                errors.append("BASELINE_FAMILY_THRESHOLD_UNSATISFIED")
            if thresholds["min_total_hidden_holdouts"] > total_hidden:
                errors.append("BASELINE_HIDDEN_THRESHOLD_UNSATISFIED")
            if thresholds["min_total_adversarial"] > total_adversarial:
                errors.append("BASELINE_ADVERSARIAL_THRESHOLD_UNSATISFIED")
    authorization = value.get("change_authorization")
    if authorization is not None:
        if not isinstance(authorization, dict) or set(authorization) != _AUTH_FIELDS:
            errors.append("BASELINE_CHANGE_AUTHORIZATION_INVALID")
        elif not all(isinstance(authorization[key], str) and authorization[key].strip() for key in _AUTH_FIELDS):
            errors.append("BASELINE_CHANGE_AUTHORIZATION_INVALID")
    return sorted(set(errors))


def load_baseline(path: Path) -> dict[str, Any]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"baseline unreadable/invalid: {type(exc).__name__}") from exc
    errors = validate_baseline(value)
    if errors:
        raise ValueError(f"baseline invalid: {errors}")
    return value


def _authorization_valid(value: Mapping[str, Any]) -> bool:
    authorization = value.get("change_authorization")
    return (
        isinstance(authorization, dict)
        and set(authorization) == _AUTH_FIELDS
        and all(isinstance(authorization[key], str) and authorization[key].strip() for key in _AUTH_FIELDS)
    )


def _suffix_present(successful_test_ids: set[str], suffix: str) -> bool:
    return any(test_id.endswith(suffix) for test_id in successful_test_ids)


def evaluate_programming_quality_regression(
    current: Mapping[str, Any],
    *,
    prior: Mapping[str, Any] | None,
    successful_test_ids: set[str] | None,
    actual_artifact_digests: Mapping[str, str],
    task_id: str,
    execution_id: str,
    head_sha: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    validation_errors = validate_baseline(current)
    if validation_errors:
        return _control_receipt(
            "PROGRAMMING_QUALITY_REGRESSION",
            task_id=task_id,
            execution_id=execution_id,
            head_sha=head_sha,
            input_digest=sha256_json({"current": current, "prior": prior}),
            outcome="FAIL",
            reason_code="BASELINE_INVALID",
            details={"findings": validation_errors},
            timestamp=timestamp,
        )
    findings: list[str] = []
    authorized_changes: list[str] = []
    protected = current["protected_artifacts"]
    for path, expected in sorted(protected.items()):
        actual = actual_artifact_digests.get(path)
        if actual != expected:
            findings.append(f"PROTECTED_ARTIFACT_DIGEST_MISMATCH:{path}")
    for name in BASELINE_CONTROLS:
        if current["controls"].get(name) is not True:
            findings.append(f"CONTROL_BYPASS:{name}")

    for family_name in BASELINE_FAMILIES:
        family = current["families"][family_name]
        if successful_test_ids is not None:
            for suffix in family["required_test_suffixes"]:
                if not _suffix_present(successful_test_ids, suffix):
                    findings.append(f"REQUIRED_TEST_NOT_GREEN:{family_name}:{suffix}")

    if prior is None:
        if current.get("decision_ref") != "ADR-PROG-004":
            findings.append("BOOTSTRAP_DECISION_MISSING")
        reason = "BASELINE_BOOTSTRAP_VALID" if not findings else "PROGRAMMING_QUALITY_REGRESSION"
    else:
        prior_errors = validate_baseline(prior)
        if prior_errors:
            findings.extend(f"PRIOR_BASELINE_INVALID:{error}" for error in prior_errors)
        else:
            for family_name in BASELINE_FAMILIES:
                previous = prior["families"][family_name]
                candidate = current["families"][family_name]
                removed = sorted(set(previous["required_test_suffixes"]) - set(candidate["required_test_suffixes"]))
                for suffix in removed:
                    findings.append(f"REQUIRED_TEST_REMOVED:{family_name}:{suffix}")
                if candidate["min_hidden_holdouts"] < previous["min_hidden_holdouts"]:
                    findings.append(f"HIDDEN_HOLDOUT_REDUCED:{family_name}")
                if candidate["min_adversarial_tests"] < previous["min_adversarial_tests"]:
                    findings.append(f"ADVERSARIAL_COVERAGE_REDUCED:{family_name}")
                if previous["semantic_required"] and not candidate["semantic_required"]:
                    findings.append(f"SEMANTIC_JUDGE_DISABLED:{family_name}")
            for name in BASELINE_CONTROLS:
                if prior["controls"].get(name) is True and current["controls"].get(name) is not True:
                    findings.append(f"CONTROL_DISABLED:{name}")
            for name, prior_value in prior["thresholds"].items():
                current_value = current["thresholds"].get(name)
                if type(current_value) is not int or current_value < prior_value:
                    findings.append(f"THRESHOLD_REDUCED:{name}")
            for path, prior_digest in prior["protected_artifacts"].items():
                current_digest = current["protected_artifacts"].get(path)
                if current_digest != prior_digest:
                    authorized_changes.append(f"PROTECTED_BASELINE_CHANGED:{path}")
            if authorized_changes and not _authorization_valid(current):
                findings.extend(f"UNAUTHORIZED_{item}" for item in authorized_changes)
                authorized_changes = []
        reason = "BASELINE_PRESERVED" if not findings else "PROGRAMMING_QUALITY_REGRESSION"

    outcome = "PASS" if not findings else "FAIL"
    return _control_receipt(
        "PROGRAMMING_QUALITY_REGRESSION",
        task_id=task_id,
        execution_id=execution_id,
        head_sha=head_sha,
        input_digest=sha256_json({"current": current, "prior": prior}),
        outcome=outcome,
        reason_code=reason,
        evidence_refs=[f"baseline:{current['baseline_id']}", current["decision_ref"]],
        details={
            "findings": sorted(set(findings)),
            "authorized_changes": sorted(set(authorized_changes)),
            "successful_test_count": None if successful_test_ids is None else len(successful_test_ids),
        },
        timestamp=timestamp,
    )


def readback_field_binding(
    *,
    entity: str,
    expected_entity: str,
    row: Mapping[str, Any],
    pk_field: str,
    expected_pk: Any,
    field: str,
    expected_value: Any,
    expected_type: type[Any] | None,
    status_field: str | None,
    expected_status: Any,
    task_id: str,
    execution_id: str,
    head_sha: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append({"check": "entity", "pass": entity == expected_entity})
    checks.append({"check": "pk", "pass": pk_field in row and row.get(pk_field) == expected_pk})
    checks.append({"check": "field", "pass": field in row and row.get(field) == expected_value})
    if expected_type is not None:
        checks.append({"check": "type", "pass": field in row and type(row.get(field)) is expected_type})
    if status_field is not None:
        checks.append(
            {
                "check": "status",
                "pass": status_field in row and row.get(status_field) == expected_status,
            }
        )
    passed = all(item["pass"] for item in checks)
    expectation_digest = sha256_json(
        {
            "expected_entity": expected_entity,
            "pk_field": pk_field,
            "expected_pk": expected_pk,
            "field": field,
            "expected_value": expected_value,
            "expected_type": None if expected_type is None else expected_type.__name__,
            "status_field": status_field,
            "expected_status": expected_status,
        }
    )
    return _control_receipt(
        "READBACK_FIELD_BINDING",
        task_id=task_id,
        execution_id=execution_id,
        head_sha=head_sha,
        input_digest=expectation_digest,
        outcome="PASS" if passed else "FAIL",
        reason_code="READBACK_EXACT_FIELD_MATCH" if passed else "READBACK_EXACT_FIELD_MISMATCH",
        evidence_refs=[f"entity:{entity}", f"pk:{pk_field}={expected_pk!r}", f"field:{field}"],
        details={"checks": checks},
        timestamp=timestamp,
    )


def _security_control(
    root: Path,
    plan: QualityPlan,
    *,
    execution_id: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    security = scan_repository(root)
    status = security.get("status")
    if status == "PASS":
        outcome = "PASS"
        reason = "EXISTING_SECURITY_GATE_PASS"
    else:
        outcome = "FAIL"
        reason = "EXISTING_SECURITY_GATE_FAIL"
    return _control_receipt(
        "EXISTING_SECURITY_GATE",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=security["evidence_sha256"],
        outcome=outcome,
        reason_code=reason,
        evidence_refs=[f"security:{security['evidence_sha256']}"],
        details=security,
        timestamp=timestamp,
    )


def _semantic_sources(root: Path, plan: QualityPlan) -> dict[str, str]:
    sources: dict[str, str] = {}
    for relative in plan.semantic_paths:
        path = root / relative
        if not path.is_file():
            raise WorkspaceError(f"SEMANTIC_TARGET_MISSING:{relative}")
        try:
            sources[relative] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise WorkspaceError(f"SEMANTIC_TARGET_UNREADABLE:{relative}:{type(exc).__name__}") from exc
    return sources


def _artifact_digests(root: Path, baseline: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in baseline["protected_artifacts"]:
        path = root / relative
        if path.is_file():
            result[relative] = sha256_file(path)
    return result


def _quality_final_receipt(
    *,
    plan: QualityPlan,
    spec: WorkerTaskSpec,
    execution_id: str,
    controls: list[dict[str, Any]],
    verified_receipt: Mapping[str, Any] | None,
    status: str,
    reason: str,
    patch: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    delivered_patch = patch if status == "PASS" else ""
    value: dict[str, Any] = {
        "schema_version": QUALITY_RECEIPT_SCHEMA_VERSION,
        "task_id": plan.task_id,
        "task_sha256": spec.sha256,
        "base_head_sha": plan.base_head_sha,
        "source_snapshot_sha256": spec.source_snapshot_sha256,
        "quality_plan_sha256": plan.sha256,
        "execution_id": execution_id,
        "timestamp": _safe_timestamp(timestamp),
        "controls": [
            {
                "control_id": item["control_id"],
                "outcome": item["outcome"],
                "reason_code": item["reason_code"],
                "output_digest": item["output_digest"],
            }
            for item in controls
        ],
        "verified_worker_receipt_sha256": None if verified_receipt is None else verified_receipt.get("receipt_sha256"),
        "status": status,
        "reason": reason,
        "patch_sha256": sha256_bytes(delivered_patch.encode("utf-8")) if delivered_patch else None,
        "patch_delivered": status == "PASS",
        "commit_allowed": False,
        "push_allowed": False,
        "merge_allowed": False,
        "production_allowed": False,
        "independent_audit_required": True,
    }
    value["receipt_sha256"] = sha256_json(value)
    return value


def run_programming_quality_worker(
    repo_path: Path,
    spec: WorkerTaskSpec,
    client: Any,
    oracle: HiddenOracle,
    plan: QualityPlan,
    *,
    work_parent: Path | None = None,
    execution_id: str | None = None,
) -> ProgrammingQualityWorkerResult:
    execution = execution_id or plan.task_id
    if plan.task_id != spec.task_id or plan.base_head_sha != spec.base_head_sha:
        receipt = _quality_final_receipt(
            plan=plan,
            spec=spec,
            execution_id=execution,
            controls=[],
            verified_receipt=None,
            status="BLOCKED",
            reason="QUALITY_PLAN_TASK_BINDING_MISMATCH",
            patch="",
        )
        return ProgrammingQualityWorkerResult(receipt, "")

    controls: list[dict[str, Any]] = []
    risk_receipt = evaluate_risk_profile(plan, execution_id=execution)
    controls.append(risk_receipt)
    if risk_receipt["outcome"] != "PASS":
        receipt = _quality_final_receipt(
            plan=plan,
            spec=spec,
            execution_id=execution,
            controls=controls,
            verified_receipt=None,
            status="BLOCKED",
            reason=risk_receipt["reason_code"],
            patch="",
        )
        return ProgrammingQualityWorkerResult(receipt, "")

    try:
        identity = verify_source_repository(repo_path, spec)
        temporary_parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-quality-preflight-", dir=temporary_parent) as temporary:
            fixture_workspace = Path(temporary) / "fixture"
            create_disposable_workspace(repo_path, fixture_workspace, identity)
            fixture_receipt = run_fixture_preflight(fixture_workspace, plan, execution_id=execution)
    except WorkspaceError as exc:
        fixture_receipt = _control_receipt(
            "FIXTURE_PREFLIGHT",
            task_id=plan.task_id,
            execution_id=execution,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="BLOCKED",
            reason_code=str(exc),
        )
    controls.append(fixture_receipt)
    if fixture_receipt["outcome"] != "PASS":
        receipt = _quality_final_receipt(
            plan=plan,
            spec=spec,
            execution_id=execution,
            controls=controls,
            verified_receipt=None,
            status="BLOCKED",
            reason="FIXTURE_INVALID" if fixture_receipt["reason_code"] == "FIXTURE_INVALID" else fixture_receipt["reason_code"],
            patch="",
        )
        return ProgrammingQualityWorkerResult(receipt, "")

    verified = run_verified_worker(repo_path, spec, client, oracle, work_parent=work_parent)
    implementation_class = classify_fixture_and_implementation(fixture_receipt, verified.receipt["status"])
    if verified.receipt["status"] != "PASS":
        receipt = _quality_final_receipt(
            plan=plan,
            spec=spec,
            execution_id=execution,
            controls=controls,
            verified_receipt=verified.receipt,
            status=verified.receipt["status"],
            reason=implementation_class,
            patch="",
        )
        return ProgrammingQualityWorkerResult(receipt, "")

    try:
        identity = verify_source_repository(repo_path, spec)
        temporary_parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-quality-postgreen-", dir=temporary_parent) as temporary:
            candidate = Path(temporary) / "candidate"
            create_disposable_workspace(repo_path, candidate, identity)
            replay_cumulative_patch(candidate, verified.patch)

            security_receipt = _security_control(candidate, plan, execution_id=execution)
            controls.append(security_receipt)
            if security_receipt["outcome"] != "PASS":
                receipt = _quality_final_receipt(
                    plan=plan,
                    spec=spec,
                    execution_id=execution,
                    controls=controls,
                    verified_receipt=verified.receipt,
                    status="FAIL",
                    reason=security_receipt["reason_code"],
                    patch="",
                )
                return ProgrammingQualityWorkerResult(receipt, "")

            semantic_receipt = semantic_post_green_judge(
                _semantic_sources(candidate, plan),
                plan,
                execution_id=execution,
                tests_green=True,
            )
            controls.append(semantic_receipt)
            if semantic_receipt["outcome"] in {"FAIL", "BLOCKED"}:
                receipt = _quality_final_receipt(
                    plan=plan,
                    spec=spec,
                    execution_id=execution,
                    controls=controls,
                    verified_receipt=verified.receipt,
                    status=semantic_receipt["outcome"],
                    reason=semantic_receipt["reason_code"],
                    patch="",
                )
                return ProgrammingQualityWorkerResult(receipt, "")

            baseline_path = candidate / "quality/programming_quality/baseline_v1.json"
            prior_path = repo_path / "quality/programming_quality/baseline_v1.json"
            current_baseline = load_baseline(baseline_path)
            prior_baseline = load_baseline(prior_path) if prior_path.is_file() else None
            regression_receipt = evaluate_programming_quality_regression(
                current_baseline,
                prior=prior_baseline,
                successful_test_ids=None,
                actual_artifact_digests=_artifact_digests(candidate, current_baseline),
                task_id=plan.task_id,
                execution_id=execution,
                head_sha=plan.base_head_sha,
            )
            controls.append(regression_receipt)
    except (WorkspaceError, ValueError) as exc:
        regression_receipt = _control_receipt(
            "PROGRAMMING_QUALITY_REGRESSION",
            task_id=plan.task_id,
            execution_id=execution,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="BLOCKED",
            reason_code=f"QUALITY_POSTGREEN_BLOCKED:{exc}",
        )
        controls.append(regression_receipt)

    if controls[-1]["outcome"] != "PASS":
        receipt = _quality_final_receipt(
            plan=plan,
            spec=spec,
            execution_id=execution,
            controls=controls,
            verified_receipt=verified.receipt,
            status=controls[-1]["outcome"],
            reason=controls[-1]["reason_code"],
            patch="",
        )
        return ProgrammingQualityWorkerResult(receipt, "")

    receipt = _quality_final_receipt(
        plan=plan,
        spec=spec,
        execution_id=execution,
        controls=controls,
        verified_receipt=verified.receipt,
        status="PASS",
        reason="PROGRAMMING_QUALITY_GATE_PASSED",
        patch=verified.patch,
    )
    return ProgrammingQualityWorkerResult(receipt, verified.patch)
