from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .hashutil import sha256_evidence_envelope, sha256_file, sha256_json
from .models import ContextPack, Evidence, GateResult, RunnerInput, Status
from .structured_test_receipt import successful_test_ids, validate_structured_test_receipt

EKB_GATE_CODE = "G_EKB_EXECUTABLE_REGRESSIONS"
EKB_EVIDENCE_CODE = "E_EKB_EXECUTABLE_REGRESSIONS"
EKB_RECEIPT_SCHEMA_VERSION = 3

CANONICAL_EXECUTION_CHANNEL = "canonical-ci/quality"
SUPABASE_READBACK_CHANNEL = "canonical-supabase/readback"
INDEPENDENT_PROBE_CHANNEL = "independent-audit/probe"

APPLICABILITY_VALUES = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}
EVIDENCE_KINDS = {"UNIT_TEST", "CI_POLICY", "DB_ASSERTION", "AUDIT_PROBE"}
AUTHORITY_ROLES = {"BUILDER", "INDEPENDENT_AUDITOR"}
INDEPENDENT_AUTHORITY_ROLE = "INDEPENDENT_AUDITOR"
CAUSAL_METHODS = {"KNOWN_BAD_HEAD", "CONTROLLED_MUTANT"}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KNOWN_BAD_REF = re.compile(r"^github:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


def prevention_rule_set_sha256(codes: list[str]) -> str:
    return sha256_json({"active_prevention_rule_codes": sorted(codes)})


def prevention_applicability_sha256(classifications: list[dict[str, Any]]) -> str:
    ordered = sorted(classifications, key=lambda value: str(value.get("rule_code", "")))
    return sha256_json({"prevention_applicability": ordered})


def prevention_receipt_sha256(receipt: dict[str, Any]) -> str:
    return sha256_json({key: value for key, value in receipt.items() if key != "sha256"})


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _valid_repository_ref(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and len(path.parts) > 0


def _valid_test_ref(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        _valid_repository_ref(value)
        and len(path.parts) == 2
        and path.parts[0] == "tests"
        and path.name.startswith("test_")
        and path.suffix == ".py"
    )


def _test_id_matches_ref(test_id: str, test_ref: str) -> bool:
    module = PurePosixPath(test_ref).stem
    return test_id.startswith(f"{module}.") or test_id.startswith(f"tests.{module}.")


def _evidence(input_: RunnerInput, status: Status, metadata: dict[str, Any]) -> Evidence:
    source_ref = f"{input_.repo_full_name}@{input_.head_sha}"
    producer = "RUNNER_EKB_REGRESSION"
    return Evidence(
        code=EKB_EVIDENCE_CODE,
        status=status,
        source_system="RUNNER",
        source_ref=source_ref,
        sha256=sha256_evidence_envelope(
            code=EKB_EVIDENCE_CODE,
            status=status,
            source_system="RUNNER",
            source_ref=source_ref,
            head_sha=input_.head_sha,
            producer=producer,
            metadata=metadata,
        ),
        head_sha=input_.head_sha,
        producer=producer,
        metadata=metadata,
    )


def _validate_classification(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "rule_code",
        "applicability",
        "evidence_kind",
        "reason",
        "source_system",
        "source_ref",
        "authority_role",
        "authority_execution_id",
    }
    if set(value) != expected_fields:
        errors.append("classification_fields_mismatch")
    applicability = value.get("applicability")
    if applicability not in APPLICABILITY_VALUES:
        errors.append("applicability_invalid")
    if value.get("evidence_kind") not in EVIDENCE_KINDS:
        errors.append("evidence_kind_invalid")
    if not isinstance(value.get("reason"), str) or not value.get("reason"):
        errors.append("reason_required")
    if value.get("source_system") != "SUPABASE":
        errors.append("source_system_supabase_required")
    if not isinstance(value.get("source_ref"), str) or not value.get("source_ref"):
        errors.append("source_ref_required")
    authority_role = value.get("authority_role")
    if authority_role not in AUTHORITY_ROLES:
        errors.append("authority_role_invalid")
    if not _positive_int(value.get("authority_execution_id")):
        errors.append("authority_execution_id_invalid")
    if applicability == "NOT_APPLICABLE" and authority_role != INDEPENDENT_AUTHORITY_ROLE:
        errors.append("candidate_self_exemption_forbidden")
    return errors


def _validate_causal_proof(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["causal_proof_required"]
    expected_fields = {
        "method",
        "control_ref",
        "control_sha256",
        "expected_outcome",
        "observed_outcome",
        "failure_class",
        "execution_ref",
        "execution_sha256",
    }
    errors: list[str] = []
    if set(value) != expected_fields:
        errors.append("causal_proof_fields_mismatch")
    method = value.get("method")
    if method not in CAUSAL_METHODS:
        errors.append("causal_method_invalid")
    control_ref = value.get("control_ref")
    if not isinstance(control_ref, str) or not control_ref:
        errors.append("causal_control_ref_required")
    elif method == "KNOWN_BAD_HEAD" and _KNOWN_BAD_REF.fullmatch(control_ref) is None:
        errors.append("known_bad_head_ref_invalid")
    if not _valid_sha256(value.get("control_sha256")):
        errors.append("causal_control_sha256_invalid")
    if value.get("expected_outcome") != "FAIL" or value.get("observed_outcome") != "FAIL":
        errors.append("causal_control_must_fail")
    if not isinstance(value.get("failure_class"), str) or not value.get("failure_class"):
        errors.append("causal_failure_class_required")
    if not isinstance(value.get("execution_ref"), str) or not value.get("execution_ref"):
        errors.append("causal_execution_ref_required")
    if not _valid_sha256(value.get("execution_sha256")):
        errors.append("causal_execution_sha256_invalid")
    return errors


def _structured_receipt_index(
    input_: RunnerInput,
    execution_receipt: dict[str, Any] | None,
) -> tuple[str | None, dict[str, dict[str, Any]], list[str]]:
    if not isinstance(execution_receipt, dict):
        return None, {}, []
    status_raw = execution_receipt.get("status")
    status = status_raw if isinstance(status_raw, str) else None
    status_errors = [] if status in {"PRESENT", "INVALID", "UNAVAILABLE", "INCOMPLETE"} else [
        "structured_receipt_status_invalid"
    ]
    wrappers_raw = execution_receipt.get("structured_receipts")
    if not isinstance(wrappers_raw, list):
        return status, {}, status_errors + ["structured_receipts_invalid"]

    index: dict[str, dict[str, Any]] = {}
    errors: list[str] = list(status_errors)
    for position, wrapper in enumerate(wrappers_raw):
        prefix = f"structured_receipt_{position}"
        if not isinstance(wrapper, dict):
            errors.append(f"{prefix}:wrapper_invalid")
            continue
        receipt = wrapper.get("receipt")
        run_id = wrapper.get("run_id")
        run_attempt = wrapper.get("run_attempt")
        job_id = wrapper.get("job_id")
        suite_id = wrapper.get("check_suite_id")
        if not all(_positive_int(value) for value in (run_id, run_attempt, job_id, suite_id)):
            errors.append(f"{prefix}:execution_identity_invalid")
            continue
        validation_errors = validate_structured_test_receipt(
            receipt,
            expected_repository=input_.repo_full_name,
            expected_head_sha=input_.head_sha,
            expected_run_id=run_id,
            expected_run_attempt=run_attempt,
            expected_job_name="quality",
        )
        errors.extend(f"{prefix}:{error}" for error in validation_errors)
        if not isinstance(receipt, dict):
            continue
        if receipt.get("source_snapshot_sha256") != input_.source_snapshot_sha256:
            errors.append(f"{prefix}:source_snapshot_sha256_mismatch")
        receipt_sha = receipt.get("receipt_sha256")
        if wrapper.get("receipt_sha256") != receipt_sha:
            errors.append(f"{prefix}:wrapper_receipt_sha256_mismatch")
        archive_sha = wrapper.get("artifact_archive_sha256")
        artifact_digest = wrapper.get("artifact_digest")
        if not _valid_sha256(archive_sha) or artifact_digest != f"sha256:{archive_sha}":
            errors.append(f"{prefix}:artifact_digest_mismatch")
        if isinstance(receipt_sha, str):
            if receipt_sha in index:
                errors.append(f"{prefix}:duplicate_receipt_sha256")
            else:
                index[receipt_sha] = wrapper
    return status, index, errors


def _common_receipt_errors(
    receipt: dict[str, Any],
    classification: dict[str, Any],
    input_: RunnerInput,
    expected_fields: set[str],
) -> list[str]:
    errors: list[str] = []
    if set(receipt) != expected_fields:
        errors.append("receipt_fields_mismatch")
    if type(receipt.get("schema_version")) is not int or receipt.get("schema_version") != EKB_RECEIPT_SCHEMA_VERSION:
        errors.append("schema_version_invalid")
    if receipt.get("rule_code") != classification.get("rule_code"):
        errors.append("rule_code_mismatch")
    if receipt.get("status") != "PASS":
        errors.append("receipt_nonpass")
    if receipt.get("head_sha") != input_.head_sha:
        errors.append("head_mismatch")
    if receipt.get("source_snapshot_sha256") != input_.source_snapshot_sha256:
        errors.append("source_snapshot_sha256_mismatch")
    evidence_kind = classification.get("evidence_kind")
    if receipt.get("evidence_kind") != evidence_kind:
        errors.append("evidence_kind_mismatch")
    channels = {
        "UNIT_TEST": CANONICAL_EXECUTION_CHANNEL,
        "CI_POLICY": CANONICAL_EXECUTION_CHANNEL,
        "DB_ASSERTION": SUPABASE_READBACK_CHANNEL,
        "AUDIT_PROBE": INDEPENDENT_PROBE_CHANNEL,
    }
    expected_channel = channels.get(evidence_kind) if isinstance(evidence_kind, str) else None
    if receipt.get("execution_channel") != expected_channel:
        errors.append("execution_channel_mismatch")
    if receipt.get("authority_role") != INDEPENDENT_AUTHORITY_ROLE:
        errors.append("independent_authority_required")
    if not _positive_int(receipt.get("authority_execution_id")):
        errors.append("authority_execution_id_invalid")
    errors.extend(_validate_causal_proof(receipt.get("causal_proof")))
    if receipt.get("sha256") != prevention_receipt_sha256(receipt):
        errors.append("receipt_sha256_mismatch")
    return errors


_COMMON_RECEIPT_FIELDS = {
    "schema_version",
    "rule_code",
    "status",
    "head_sha",
    "source_snapshot_sha256",
    "evidence_kind",
    "execution_channel",
    "authority_role",
    "authority_execution_id",
    "causal_proof",
    "sha256",
}


def _validate_unit_receipt(
    receipt: dict[str, Any],
    classification: dict[str, Any],
    input_: RunnerInput,
    context: ContextPack,
    harness: dict[str, Any],
    structured_index: dict[str, dict[str, Any]],
    structured_ready: bool,
) -> list[str]:
    expected_fields = _COMMON_RECEIPT_FIELDS | {
        "test_ref",
        "test_id",
        "test_sha256",
        "harness_ref",
        "harness_sha256",
        "structured_test_receipt_sha256",
    }
    errors = _common_receipt_errors(receipt, classification, input_, expected_fields)
    test_ref = receipt.get("test_ref")
    inventory = set(context.repository_inventory.get("files") or [])
    if not isinstance(test_ref, str) or not _valid_test_ref(test_ref):
        errors.append("test_ref_invalid")
    elif test_ref not in inventory:
        errors.append("test_ref_missing_from_repository")
    else:
        try:
            actual_test_sha = sha256_file(input_.repo_path / PurePosixPath(test_ref))
        except OSError:
            errors.append("test_ref_unreadable")
        else:
            if receipt.get("test_sha256") != actual_test_sha:
                errors.append("test_sha256_mismatch")

    test_id = receipt.get("test_id")
    if not isinstance(test_id, str) or not test_id:
        errors.append("test_id_invalid")
    elif isinstance(test_ref, str) and not _test_id_matches_ref(test_id, test_ref):
        errors.append("test_id_test_ref_mismatch")

    if receipt.get("harness_ref") != harness.get("ref"):
        errors.append("harness_ref_mismatch")
    if receipt.get("harness_sha256") != harness.get("sha256"):
        errors.append("harness_sha256_mismatch")

    structured_sha = receipt.get("structured_test_receipt_sha256")
    if not isinstance(structured_sha, str) or not _valid_sha256(structured_sha):
        errors.append("structured_test_receipt_sha256_invalid")
    elif structured_ready:
        wrapper = structured_index.get(structured_sha)
        if wrapper is None:
            errors.append("structured_test_receipt_not_observed")
        else:
            structured = wrapper.get("receipt")
            if not isinstance(structured, dict):
                errors.append("structured_test_receipt_invalid")
            else:
                if structured.get("harness_ref") != harness.get("ref"):
                    errors.append("structured_harness_ref_mismatch")
                if structured.get("harness_sha256") != harness.get("sha256"):
                    errors.append("structured_harness_sha256_mismatch")
                if isinstance(test_id, str) and test_id not in successful_test_ids(structured):
                    errors.append("test_id_not_observed_as_success")
    return errors


def _validate_ci_policy_receipt(
    receipt: dict[str, Any],
    classification: dict[str, Any],
    input_: RunnerInput,
    context: ContextPack,
    structured_index: dict[str, dict[str, Any]],
) -> list[str]:
    expected_fields = _COMMON_RECEIPT_FIELDS | {
        "policy_ref",
        "policy_sha256",
        "structured_test_receipt_sha256",
        "run_id",
        "job_id",
        "check_suite_id",
        "verification_status",
    }
    errors = _common_receipt_errors(receipt, classification, input_, expected_fields)
    policy_ref = receipt.get("policy_ref")
    inventory = set(context.repository_inventory.get("files") or [])
    if not isinstance(policy_ref, str) or not _valid_repository_ref(policy_ref):
        errors.append("policy_ref_invalid")
    elif policy_ref not in inventory:
        errors.append("policy_ref_missing_from_repository")
    else:
        try:
            actual_policy_sha = sha256_file(input_.repo_path / PurePosixPath(policy_ref))
        except OSError:
            errors.append("policy_ref_unreadable")
        else:
            if receipt.get("policy_sha256") != actual_policy_sha:
                errors.append("policy_sha256_mismatch")
    if receipt.get("verification_status") != "PASS":
        errors.append("verification_status_nonpass")

    wrapper = structured_index.get(str(receipt.get("structured_test_receipt_sha256")))
    if wrapper is None:
        errors.append("structured_test_receipt_not_observed")
    else:
        for key in ("run_id", "job_id", "check_suite_id"):
            if receipt.get(key) != wrapper.get(key):
                errors.append(f"{key}_mismatch")
    return errors


def _validate_external_receipt(
    receipt: dict[str, Any],
    classification: dict[str, Any],
    input_: RunnerInput,
) -> list[str]:
    evidence_kind = classification.get("evidence_kind")
    if evidence_kind == "DB_ASSERTION":
        specific_fields = {
            "assertion_ref",
            "assertion_sha256",
            "readback_ref",
            "readback_sha256",
            "verification_status",
        }
        ref_fields: tuple[str, ...] = ("assertion_ref", "readback_ref")
        sha_fields: tuple[str, ...] = ("assertion_sha256", "readback_sha256")
    else:
        specific_fields = {"probe_ref", "probe_sha256", "probe_result", "verification_status"}
        ref_fields = ("probe_ref",)
        sha_fields = ("probe_sha256",)
    errors = _common_receipt_errors(receipt, classification, input_, _COMMON_RECEIPT_FIELDS | specific_fields)
    for field in ref_fields:
        if not isinstance(receipt.get(field), str) or not receipt.get(field):
            errors.append(f"{field}_required")
    for field in sha_fields:
        if not _valid_sha256(receipt.get(field)):
            errors.append(f"{field}_invalid")
    if receipt.get("verification_status") != "PASS":
        errors.append("verification_status_nonpass")
    if evidence_kind == "AUDIT_PROBE" and receipt.get("probe_result") != "PASS":
        errors.append("probe_result_nonpass")
    return errors


def evaluate_ekb_regressions(
    input_: RunnerInput,
    context: ContextPack,
    *,
    test_execution_receipt: dict[str, Any] | None = None,
) -> tuple[GateResult, Evidence]:
    if not input_.version_code.startswith("v0.6"):
        metadata = {"applicable": False, "reason": "PRE_V06_COMPATIBILITY"}
        evidence = _evidence(input_, "NOT_APPLICABLE", metadata)
        return (
            GateResult(EKB_GATE_CODE, "NOT_APPLICABLE", "PRE_V06_COMPATIBILITY", (EKB_EVIDENCE_CODE,), metadata),
            evidence,
        )

    snapshot = context.ekb_snapshot
    problems: list[str] = []
    tampering: list[str] = []

    if snapshot.get("status") != "FROZEN":
        problems.append("ekb_status_frozen_required")
    if snapshot.get("source_system") is None:
        problems.append("ekb_source_system_supabase_required")
    elif snapshot.get("source_system") != "SUPABASE":
        tampering.append("ekb_source_system_invalid")
    if not isinstance(snapshot.get("source_ref"), str) or not snapshot.get("source_ref"):
        problems.append("ekb_source_ref_required")

    codes_raw = snapshot.get("active_prevention_rule_codes")
    codes: list[str] = []
    if codes_raw is None:
        problems.append("active_prevention_rule_codes_required")
    elif not isinstance(codes_raw, list):
        tampering.append("active_prevention_rule_codes_invalid_type")
    else:
        codes = [value for value in codes_raw if isinstance(value, str) and value]
        if len(codes) != len(codes_raw):
            tampering.append("active_prevention_rule_codes_invalid")
        if len(set(codes)) != len(codes):
            tampering.append("active_prevention_rule_codes_duplicate")
        if not codes:
            problems.append("active_prevention_rule_codes_empty")
    code_set = set(codes)

    count = snapshot.get("active_prevention_rule_count")
    if count is None:
        problems.append("active_prevention_rule_count_required")
    elif type(count) is not int:
        tampering.append("active_prevention_rule_count_invalid")
    elif count != len(codes):
        tampering.append("active_prevention_rule_count_mismatch")
    expected_set_sha = snapshot.get("active_prevention_rule_codes_sha256")
    if expected_set_sha is None:
        problems.append("active_prevention_rule_codes_sha256_required")
    elif not isinstance(expected_set_sha, str):
        tampering.append("active_prevention_rule_codes_sha256_invalid")
    elif expected_set_sha != prevention_rule_set_sha256(codes):
        tampering.append("active_prevention_rule_codes_sha256_mismatch")

    harness_raw = snapshot.get("test_harness")
    harness: dict[str, Any] = harness_raw if isinstance(harness_raw, dict) else {}
    if set(harness) != {"schema_version", "ref", "sha256"}:
        problems.append("test_harness_contract_required")
    else:
        harness_ref = harness.get("ref")
        if type(harness.get("schema_version")) is not int or harness.get("schema_version") != 1:
            tampering.append("test_harness_schema_version_invalid")
        if not isinstance(harness_ref, str) or not _valid_repository_ref(harness_ref):
            tampering.append("test_harness_ref_invalid")
        elif harness_ref not in set(context.repository_inventory.get("files") or []):
            tampering.append("test_harness_ref_missing_from_repository")
        else:
            try:
                actual_harness_sha = sha256_file(input_.repo_path / PurePosixPath(harness_ref))
            except OSError:
                tampering.append("test_harness_ref_unreadable")
            else:
                if harness.get("sha256") != actual_harness_sha:
                    tampering.append("test_harness_sha256_mismatch")

    classifications_raw = snapshot.get("prevention_applicability")
    classifications: list[dict[str, Any]] = []
    if classifications_raw is None:
        problems.append("prevention_applicability_required")
    elif not isinstance(classifications_raw, list):
        tampering.append("prevention_applicability_invalid_type")
    else:
        classifications = [value for value in classifications_raw if isinstance(value, dict)]
        if len(classifications) != len(classifications_raw):
            tampering.append("prevention_applicability_invalid_type")
    applicability_sha = snapshot.get("prevention_applicability_sha256")
    if applicability_sha is None:
        problems.append("prevention_applicability_sha256_required")
    elif not isinstance(applicability_sha, str):
        tampering.append("prevention_applicability_sha256_invalid")
    elif applicability_sha != prevention_applicability_sha256(classifications):
        tampering.append("prevention_applicability_sha256_mismatch")

    classification_by_rule: dict[str, list[dict[str, Any]]] = {}
    for classification in classifications:
        rule_code = classification.get("rule_code")
        if not isinstance(rule_code, str) or not rule_code:
            tampering.append("classification_rule_code_invalid")
            continue
        classification_by_rule.setdefault(rule_code, []).append(classification)
        if rule_code not in code_set:
            tampering.append(f"{rule_code}:unexpected_classification")
        tampering.extend(f"{rule_code}:{error}" for error in _validate_classification(classification))

    receipts_raw = snapshot.get("prevention_receipts")
    receipts: list[dict[str, Any]] = []
    if receipts_raw is None:
        problems.append("prevention_receipts_required")
    elif not isinstance(receipts_raw, list):
        tampering.append("prevention_receipts_invalid_type")
    else:
        receipts = [value for value in receipts_raw if isinstance(value, dict)]
        if len(receipts) != len(receipts_raw):
            tampering.append("prevention_receipt_invalid_type")
    receipt_by_rule: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        rule_code = receipt.get("rule_code")
        if not isinstance(rule_code, str) or not rule_code:
            tampering.append("prevention_receipt_rule_code_invalid")
            continue
        receipt_by_rule.setdefault(rule_code, []).append(receipt)
        if rule_code not in code_set:
            tampering.append(f"{rule_code}:unexpected_prevention_receipt")

    structured_status, structured_index, structured_errors = _structured_receipt_index(
        input_, test_execution_receipt
    )
    required_rules: list[str] = []
    not_applicable_rules: list[str] = []
    blocked_rules: list[str] = []
    verified_rules: list[str] = []
    unit_test_ids: dict[str, str] = {}
    needs_structured = False

    for code in codes:
        rule_classifications = classification_by_rule.get(code, [])
        if not rule_classifications:
            problems.append(f"{code}:classification_missing")
            continue
        if len(rule_classifications) != 1:
            tampering.append(f"{code}:classification_cardinality_mismatch")
            continue
        classification = rule_classifications[0]
        if _validate_classification(classification):
            continue

        applicability = classification["applicability"]
        rule_receipts = receipt_by_rule.get(code, [])
        if applicability == "NOT_APPLICABLE":
            not_applicable_rules.append(code)
            if rule_receipts:
                tampering.append(f"{code}:receipt_for_not_applicable_rule")
            continue
        if applicability == "BLOCKED":
            blocked_rules.append(code)
            problems.append(f"{code}:applicability_blocked")
            if rule_receipts:
                tampering.append(f"{code}:receipt_for_blocked_rule")
            continue

        required_rules.append(code)
        evidence_kind = classification["evidence_kind"]
        if evidence_kind in {"UNIT_TEST", "CI_POLICY"}:
            needs_structured = True
        if not rule_receipts:
            problems.append(f"{code}:prevention_receipt_missing")
            continue
        if len(rule_receipts) != 1:
            tampering.append(f"{code}:prevention_receipt_cardinality_mismatch")
            continue
        receipt = rule_receipts[0]
        if evidence_kind == "UNIT_TEST":
            errors = _validate_unit_receipt(
                receipt,
                classification,
                input_,
                context,
                harness,
                structured_index,
                structured_status == "PRESENT" and not structured_errors,
            )
            test_id = receipt.get("test_id")
            if isinstance(test_id, str):
                previous = unit_test_ids.get(test_id)
                if previous is not None and previous != code:
                    errors.append(f"test_id_reused_by:{previous}")
                else:
                    unit_test_ids[test_id] = code
        elif evidence_kind == "CI_POLICY":
            errors = _validate_ci_policy_receipt(
                receipt, classification, input_, context, structured_index
            )
        else:
            errors = _validate_external_receipt(receipt, classification, input_)
        if errors:
            tampering.extend(f"{code}:{error}" for error in errors)
        else:
            verified_rules.append(code)

    if needs_structured:
        if structured_status == "INVALID":
            tampering.append("structured_test_execution_receipt_invalid")
        elif structured_status != "PRESENT":
            problems.append("structured_test_execution_receipt_required")
        if structured_errors:
            tampering.extend(structured_errors)

    missing_verified = sorted(set(required_rules) - set(verified_rules))
    metadata = {
        "applicable": True,
        "contract_schema_version": EKB_RECEIPT_SCHEMA_VERSION,
        "source_system": snapshot.get("source_system"),
        "source_ref": snapshot.get("source_ref"),
        "structured_test_execution_receipt_status": structured_status,
        "structured_test_receipt_count": len(structured_index),
        "active_prevention_rule_count": len(codes),
        "active_prevention_rule_codes_sha256": prevention_rule_set_sha256(codes),
        "classification_count": len(classifications),
        "prevention_applicability_sha256": prevention_applicability_sha256(classifications),
        "required_rule_codes": sorted(required_rules),
        "not_applicable_rule_codes": sorted(not_applicable_rules),
        "blocked_rule_codes": sorted(blocked_rules),
        "verified_rule_codes": sorted(set(verified_rules)),
        "missing_verified_rule_codes": missing_verified,
        "problems": sorted(set(problems)),
        "tampering": sorted(set(tampering)),
    }

    if tampering:
        status: Status = "FAIL"
        reason = "EKB_REGRESSION_RECEIPT_INVALID"
    elif problems or missing_verified:
        status = "BLOCKED"
        reason = "EKB_REGRESSION_COVERAGE_INCOMPLETE"
    else:
        status = "PASS"
        reason = "EKB_REGRESSION_RECEIPTS_VERIFIED"

    evidence = _evidence(input_, status, metadata)
    return GateResult(EKB_GATE_CODE, status, reason, (EKB_EVIDENCE_CODE,), metadata), evidence
