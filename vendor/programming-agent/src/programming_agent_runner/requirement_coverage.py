from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_json

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ASSERTION_MAP_SCHEMA = "2"
DENOMINATOR_SOURCE = "programacion.objetivos_ejecucion"


class CoverageInputError(ValueError):
    pass


def _blocked(reason: str, *, universe_name: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "BLOCKED",
        "reason": reason,
        "universe_name": universe_name,
        "unmapped_requirements": [],
        "requirements_without_evidence": [],
        "invalid_mappings": [],
        "invalid_evidence": [],
    }
    payload["artifact_sha256"] = sha256_json(payload)
    return payload


def _assertions(mapping: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(mapping, dict):
        return [], ["mapping_not_object"]
    assertions = mapping.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        return [], ["assertions_missing"]
    accepted: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, assertion in enumerate(assertions):
        prefix = f"assertions[{index}]"
        if not isinstance(assertion, dict):
            problems.append(f"{prefix}:not_object")
            continue
        fields_valid = True
        for field in ("id", "mode", "predicate"):
            if not isinstance(assertion.get(field), str) or not assertion[field]:
                problems.append(f"{prefix}:{field}_missing")
                fields_valid = False
        evidence_types = assertion.get("evidence_types")
        artifact_refs = assertion.get("artifact_refs")
        evidence_types_valid = False
        if not isinstance(evidence_types, list) or not evidence_types:
            problems.append(f"{prefix}:evidence_types_missing")
        elif not all(isinstance(value, str) and value for value in evidence_types):
            problems.append(f"{prefix}:evidence_types_invalid")
        else:
            evidence_types_valid = True
        artifact_refs_valid = False
        if not isinstance(artifact_refs, list) or not artifact_refs:
            problems.append(f"{prefix}:artifact_refs_missing")
        elif not all(isinstance(value, str) and value for value in artifact_refs):
            problems.append(f"{prefix}:artifact_refs_invalid")
        else:
            artifact_refs_valid = True
        if fields_valid and evidence_types_valid and artifact_refs_valid:
            assert isinstance(evidence_types, list)
            assert isinstance(artifact_refs, list)
            accepted.append(
                {
                    "id": assertion["id"],
                    "evidence_types": {value.lower() for value in evidence_types},
                    "artifact_refs": set(artifact_refs),
                }
            )
    return accepted, problems


def _valid_evidence(
    item: Any,
    *,
    objective_id: int,
    head_sha: str,
    assertion: dict[str, Any],
) -> tuple[bool, str | None]:
    if not isinstance(item, dict):
        return False, "not_object"
    if item.get("objective_id") != objective_id:
        return False, "objective_id_mismatch"
    if item.get("head_sha") != head_sha:
        return False, "head_sha_mismatch"
    source_ref = item.get("source_ref")
    if not isinstance(source_ref, str) or not source_ref:
        return False, "source_ref_missing"
    if item.get("assertion_id") != assertion["id"]:
        return False, "assertion_id_mismatch"
    if item.get("artifact_ref") not in assertion["artifact_refs"]:
        return False, "artifact_ref_not_mapped"
    type_ = item.get("type")
    if not isinstance(type_, str) or type_.lower() not in assertion["evidence_types"]:
        return False, "evidence_type_not_mapped"
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return False, "receipt_payload_missing"
    for field in (
        "objective_id",
        "head_sha",
        "assertion_id",
        "artifact_ref",
        "type",
        "source_ref",
    ):
        if payload.get(field) != item.get(field):
            return False, f"receipt_{field}_mismatch"
    if payload.get("result") != "PASS":
        return False, "evidence_result_not_pass"
    sha = item.get("sha256")
    if not isinstance(sha, str) or not HEX64.fullmatch(sha):
        return False, "sha256_invalid"
    if sha256_json(payload) != sha:
        return False, "receipt_sha256_mismatch"
    return True, None


def _required_requirements(
    requirements: Any,
) -> tuple[list[tuple[int, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(requirements, list):
        raise CoverageInputError("REQUIREMENT_COVERAGE_INPUT_INVALID")
    required: list[tuple[int, str]] = []
    seen_ids: set[int] = set()
    seen_codes: set[str] = set()
    unknown_applicability: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for item in requirements:
        if not isinstance(item, dict):
            raise CoverageInputError("CANONICAL_REQUIREMENT_ITEM_INVALID")
        objective_id = item.get("objective_id")
        code = item.get("code")
        applicability = item.get("applicability")
        if not isinstance(objective_id, int) or not isinstance(code, str) or not code:
            raise CoverageInputError("CANONICAL_REQUIREMENT_IDENTITY_INVALID")
        if objective_id in seen_ids or code in seen_codes:
            duplicates.append({"objective_id": objective_id, "code": code})
        seen_ids.add(objective_id)
        seen_codes.add(code)
        if applicability == "REQUIRED":
            required.append((objective_id, code))
        elif applicability != "NOT_APPLICABLE":
            unknown_applicability.append(
                {"objective_id": objective_id, "code": code, "applicability": applicability}
            )
    return required, duplicates, unknown_applicability


def _index_evidence(evidence_catalog: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    for item in evidence_catalog:
        if isinstance(item, dict) and isinstance(item.get("objective_id"), int):
            result.setdefault(item["objective_id"], []).append(item)
    return result


def _evaluate_required(
    required: list[tuple[int, str]],
    mappings: dict[str, Any],
    evidence_by_objective: dict[int, list[dict[str, Any]]],
    head_sha: str,
) -> tuple[list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    unmapped: list[str] = []
    without_evidence: list[str] = []
    invalid_mappings: list[dict[str, Any]] = []
    invalid_evidence: list[dict[str, Any]] = []
    for objective_id, code in required:
        mapping = mappings.get(code)
        assertions, mapping_problems = _assertions(mapping)
        if mapping is None:
            unmapped.append(code)
            continue
        if mapping_problems:
            invalid_mappings.append({"code": code, "problems": mapping_problems})
            continue
        candidates = evidence_by_objective.get(objective_id, [])
        missing_assertions: list[dict[str, Any]] = []
        for assertion in assertions:
            validations = [
                _valid_evidence(
                    item,
                    objective_id=objective_id,
                    head_sha=head_sha,
                    assertion=assertion,
                )
                for item in candidates
            ]
            if any(is_valid for is_valid, _ in validations):
                continue
            problems = sorted({problem for _, problem in validations if problem is not None})
            missing_assertions.append(
                {"assertion_id": assertion["id"], "problems": problems or ["no_candidates"]}
            )
        if missing_assertions:
            without_evidence.append(code)
            invalid_evidence.append({"code": code, "assertions": missing_assertions})
    return unmapped, without_evidence, invalid_mappings, invalid_evidence


def build_requirement_coverage(
    inventory: dict[str, Any],
    assertion_map: dict[str, Any],
    evidence_catalog: list[dict[str, Any]],
    head_sha: str,
) -> dict[str, Any]:
    universe_name = inventory.get("universe_name")
    if inventory.get("status") != "FROZEN":
        return _blocked("CANONICAL_REQUIREMENT_UNIVERSE_NOT_FROZEN", universe_name=universe_name)
    if not isinstance(universe_name, str) or not universe_name:
        return _blocked("CANONICAL_REQUIREMENT_UNIVERSE_UNNAMED", universe_name=universe_name)
    if not HEX40.fullmatch(head_sha) or inventory.get("head_sha") != head_sha:
        return _blocked("CANONICAL_REQUIREMENT_HEAD_MISMATCH", universe_name=universe_name)
    if assertion_map.get("schema_version") != ASSERTION_MAP_SCHEMA:
        return _blocked("ASSERTION_MAP_SCHEMA_UNSUPPORTED", universe_name=universe_name)
    if assertion_map.get("denominator_source") != DENOMINATOR_SOURCE:
        return _blocked("ASSERTION_MAP_DENOMINATOR_INVALID", universe_name=universe_name)
    profile_code = inventory.get("profile_code")
    if not isinstance(profile_code, str) or assertion_map.get("profile_code") != profile_code:
        return _blocked("ASSERTION_MAP_PROFILE_MISMATCH", universe_name=universe_name)
    mappings = assertion_map.get("mappings")
    if not isinstance(mappings, dict):
        return _blocked("REQUIREMENT_COVERAGE_INPUT_INVALID", universe_name=universe_name)

    try:
        required, duplicate_requirements, unknown_applicability = _required_requirements(
            inventory.get("requirements")
        )
    except CoverageInputError as exc:
        return _blocked(str(exc), universe_name=universe_name)
    if duplicate_requirements or unknown_applicability:
        payload = _blocked("CANONICAL_REQUIREMENT_UNIVERSE_INVALID", universe_name=universe_name)
        payload["duplicate_requirements"] = duplicate_requirements
        payload["unknown_applicability"] = unknown_applicability
        payload["artifact_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "artifact_sha256"})
        return payload

    unmapped, without_evidence, invalid_mappings, invalid_evidence = _evaluate_required(
        required,
        mappings,
        _index_evidence(evidence_catalog),
        head_sha,
    )

    status = "PASS" if not (unmapped or without_evidence or invalid_mappings) else "FAIL"
    payload = {
        "status": status,
        "reason": "REQUIREMENT_COVERAGE_COMPLETE" if status == "PASS" else "REQUIREMENT_COVERAGE_INCOMPLETE",
        "universe_name": universe_name,
        "head_sha": head_sha,
        "required_total": len(required),
        "mapped_total": len(required) - len(unmapped) - len(invalid_mappings),
        "requirements_with_evidence": (
            len(required) - len(unmapped) - len(without_evidence) - len(invalid_mappings)
        ),
        "unmapped_requirements": sorted(unmapped),
        "requirements_without_evidence": sorted(without_evidence),
        "invalid_mappings": invalid_mappings,
        "invalid_evidence": invalid_evidence,
        "mapping_sha256": sha256_json(assertion_map),
        "inventory_sha256": sha256_json(inventory),
    }
    payload["artifact_sha256"] = sha256_json(payload)
    return payload
