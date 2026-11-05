from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_evidence_envelope, sha256_json
from .models import Evidence, GateResult, RunnerInput, Status, WorkerTaskSpecV2

_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.v[1-9][0-9]*$")
_FINAL_DEPENDENCY_TYPES = {"TASK_EDGE", "INTERFACE_REF", "CONTEXT_REF", "NOT_APPLICABLE"}
_FORBIDDEN_WORKER_KEYS = {"hidden_oracle_ref", "hidden_oracle_sha256", "oracle_envelope"}
_REQUIRED_KEYS = {
    "schema_version",
    "task_id",
    "objective",
    "expected_change",
    "human_story",
    "functional_contract",
    "scope",
    "cases",
    "dependency_resolution",
    "dependency_task_ids",
    "required_tests",
    "required_evidence",
    "blocked_if",
    "base_head_sha",
    "source_snapshot_sha256",
    "context_path_patterns",
    "write_path_patterns",
    "protected_path_patterns",
    "files_expected",
    "platform_refs",
    "interface_refs",
    "acceptance_commands",
    "max_attempts",
    "max_patch_bytes",
    "max_changed_files",
    "max_context_bytes",
    "allow_deletions",
}


def _string(value: Any, name: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, name: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{name} must be a {'non-empty ' if nonempty else ''}list")
    result = [_string(item, f"{name}[]") for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{name} contains duplicate entries")
    return result


def _object_list(value: Any, name: str, *, nonempty: bool = True) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{name} must be a {'non-empty ' if nonempty else ''}list")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{name} entries must be objects")
    return list(value)


def _codes(items: Any, name: str) -> set[str]:
    rows = _object_list(items, name)
    result = {_string(row.get("code"), f"{name}.code") for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"{name} contains duplicate codes")
    return result


def _parse(value: WorkerTaskSpecV2 | dict[str, Any]) -> WorkerTaskSpecV2:
    if isinstance(value, WorkerTaskSpecV2):
        raw = value.to_dict()
    elif isinstance(value, dict):
        raw = dict(value)
    else:
        raise ValueError("worker_task_spec must be an object")

    forbidden = sorted(_FORBIDDEN_WORKER_KEYS.intersection(raw))
    if forbidden:
        raise ValueError(f"worker_task_spec leaks evaluator-only oracle metadata: {forbidden}")
    missing = sorted(_REQUIRED_KEYS.difference(raw))
    extra = sorted(set(raw).difference(_REQUIRED_KEYS))
    if missing:
        raise ValueError(f"worker_task_spec missing keys: {missing}")
    if extra:
        raise ValueError(f"worker_task_spec has unknown keys: {extra}")

    if raw["schema_version"] != 2:
        raise ValueError("worker_task_spec schema_version must equal 2")
    task_id = _string(raw["task_id"], "task_id")
    if not _TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task_id must be WorkerTaskSpec-compatible and versioned")

    human_story = raw["human_story"]
    if not isinstance(human_story, dict):
        raise ValueError("human_story must be an object")
    for key in ("story_code", "title", "persona", "need", "benefit"):
        _string(human_story.get(key), f"human_story.{key}")
    _string_list(human_story.get("dependencies"), "human_story.dependencies", nonempty=False)
    if not isinstance(human_story.get("technical_notes"), dict):
        raise ValueError("human_story.technical_notes must be an object")

    functional = raw["functional_contract"]
    if not isinstance(functional, dict):
        raise ValueError("functional_contract must be an object")
    ac_codes = _codes(functional.get("acceptance_criteria"), "functional_contract.acceptance_criteria")
    inv_codes = _codes(functional.get("invariants"), "functional_contract.invariants")
    neg_codes = _codes(functional.get("negative_controls"), "functional_contract.negative_controls")
    rule_codes = set(_string_list(functional.get("source_rule_codes"), "functional_contract.source_rule_codes"))
    semantic_codes = ac_codes | inv_codes | neg_codes
    valid_semantic_refs = semantic_codes | rule_codes

    scope = raw["scope"]
    if not isinstance(scope, dict) or set(scope) != {"in_scope", "out_of_scope", "must_not_change"}:
        raise ValueError("scope must contain exactly in_scope, out_of_scope and must_not_change")
    for key in ("in_scope", "out_of_scope", "must_not_change"):
        _string_list(scope[key], f"scope.{key}")

    cases = raw["cases"]
    if not isinstance(cases, dict) or set(cases) != {"positive", "edge", "regression"}:
        raise ValueError("cases must contain exactly positive, edge and regression")
    for family in ("positive", "edge", "regression"):
        rows = _object_list(cases[family], f"cases.{family}")
        seen: set[str] = set()
        for row in rows:
            code = _string(row.get("code"), f"cases.{family}.code")
            _string(row.get("statement"), f"cases.{family}.statement", minimum=10)
            refs = set(_string_list(row.get("source_refs"), f"cases.{family}.source_refs"))
            if not refs.issubset(valid_semantic_refs):
                raise ValueError(f"case {code} references unknown semantic refs: {sorted(refs - valid_semantic_refs)}")
            if code in seen:
                raise ValueError(f"duplicate case code: {code}")
            seen.add(code)

    story_dependencies = set(_string_list(human_story["dependencies"], "human_story.dependencies", nonempty=False))
    dependency_rows = _object_list(raw["dependency_resolution"], "dependency_resolution", nonempty=bool(story_dependencies))
    resolved_names: list[str] = []
    dependency_task_ids = raw["dependency_task_ids"]
    if not isinstance(dependency_task_ids, list) or any(not isinstance(item, int) or item < 1 for item in dependency_task_ids):
        raise ValueError("dependency_task_ids must be a list of positive integers")
    if len(dependency_task_ids) != len(set(dependency_task_ids)):
        raise ValueError("dependency_task_ids contains duplicates")

    interface_refs = _string_list(raw["interface_refs"], "interface_refs", nonempty=False)
    context_refs = _string_list(raw["context_path_patterns"], "context_path_patterns")
    for row in dependency_rows:
        source = _string(row.get("source_dependency"), "dependency_resolution.source_dependency")
        resolution_type = _string(row.get("resolution_type"), "dependency_resolution.resolution_type")
        if resolution_type not in _FINAL_DEPENDENCY_TYPES:
            raise ValueError(f"dependency {source} is not finally resolved: {resolution_type}")
        resolution_ref = row.get("resolution_ref")
        if resolution_type == "TASK_EDGE":
            ref = _string(resolution_ref, "dependency_resolution.resolution_ref")
            match = re.fullmatch(r"agent-task://([1-9][0-9]*)", ref)
            if not match or int(match.group(1)) not in dependency_task_ids:
                raise ValueError(f"TASK_EDGE dependency {source} is not backed by dependency_task_ids")
        elif resolution_type == "INTERFACE_REF":
            ref = _string(resolution_ref, "dependency_resolution.resolution_ref")
            if ref not in interface_refs:
                raise ValueError(f"INTERFACE_REF dependency {source} is not present in interface_refs")
        elif resolution_type == "CONTEXT_REF":
            ref = _string(resolution_ref, "dependency_resolution.resolution_ref")
            if ref not in context_refs:
                raise ValueError(f"CONTEXT_REF dependency {source} is not present in context_path_patterns")
        elif resolution_type == "NOT_APPLICABLE":
            _string(row.get("reason"), "dependency_resolution.reason", minimum=10)
        resolved_names.append(source)
    if len(resolved_names) != len(set(resolved_names)):
        raise ValueError("dependency_resolution contains duplicate source_dependency entries")
    if set(resolved_names) != story_dependencies:
        raise ValueError(
            f"Story dependency resolution mismatch: declared={sorted(story_dependencies)} resolved={sorted(set(resolved_names))}"
        )

    required_tests = _object_list(raw["required_tests"], "required_tests")
    covered: set[str] = set()
    test_refs: set[str] = set()
    for row in required_tests:
        test_ref = _string(row.get("test_ref"), "required_tests.test_ref")
        _string(row.get("purpose"), "required_tests.purpose", minimum=10)
        refs = set(_string_list(row.get("covers_refs"), "required_tests.covers_refs"))
        if not refs.issubset(valid_semantic_refs):
            raise ValueError(f"required test {test_ref} references unknown refs: {sorted(refs - valid_semantic_refs)}")
        if test_ref in test_refs:
            raise ValueError(f"duplicate required test ref: {test_ref}")
        test_refs.add(test_ref)
        covered |= refs
    missing_coverage = sorted(semantic_codes - covered)
    if missing_coverage:
        raise ValueError(f"required_tests do not cover all AC/INV/NEG refs: {missing_coverage}")

    required_evidence = _object_list(raw["required_evidence"], "required_evidence")
    for row in required_evidence:
        _string(row.get("evidence_type"), "required_evidence.evidence_type")
        _string(row.get("source_ref"), "required_evidence.source_ref")
        refs = set(_string_list(row.get("covers_refs"), "required_evidence.covers_refs"))
        if not refs.issubset(valid_semantic_refs):
            raise ValueError(f"required evidence references unknown refs: {sorted(refs - valid_semantic_refs)}")

    blocked_if = _object_list(raw["blocked_if"], "blocked_if")
    for row in blocked_if:
        _string(row.get("code"), "blocked_if.code")
        _string(row.get("condition"), "blocked_if.condition", minimum=10)

    _string_list(raw["write_path_patterns"], "write_path_patterns")
    _string_list(raw["protected_path_patterns"], "protected_path_patterns")
    _string_list(raw["files_expected"], "files_expected")
    _string_list(raw["platform_refs"], "platform_refs", nonempty=False)
    if not isinstance(raw["acceptance_commands"], list):
        raise ValueError("acceptance_commands must be a list")
    for key in ("max_attempts", "max_patch_bytes", "max_changed_files", "max_context_bytes"):
        if not isinstance(raw[key], int) or raw[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if not isinstance(raw["allow_deletions"], bool):
        raise ValueError("allow_deletions must be boolean")

    return WorkerTaskSpecV2(**raw)


def evaluate_worker_task_spec(
    input_: RunnerInput,
    *,
    required: bool,
) -> tuple[WorkerTaskSpecV2 | None, GateResult, Evidence]:
    raw = input_.worker_task_spec
    metadata: dict[str, Any]
    if raw is None:
        missing_status: Status = "BLOCKED" if required else "NOT_APPLICABLE"
        reason = "WORKER_TASK_SPEC_V2_REQUIRED_FOR_COMMAND_EXECUTION" if required else "WorkerTaskSpec not required for read-only reference run"
        metadata = {"required": required}
        evidence = Evidence(
            code="E_WORKER_TASK_SPEC_V2",
            status=missing_status,
            source_system="WORKER_TASK_SPEC",
            source_ref=input_.repo_full_name,
            sha256=sha256_evidence_envelope(
                code="E_WORKER_TASK_SPEC_V2",
                status=missing_status,
                source_system="WORKER_TASK_SPEC",
                source_ref=input_.repo_full_name,
                head_sha=input_.head_sha,
                producer="RUNNER_WORKER_TASK_SPEC_GATE",
                metadata=metadata,
            ),
            head_sha=input_.head_sha,
            producer="RUNNER_WORKER_TASK_SPEC_GATE",
            metadata=metadata,
        )
        return None, GateResult("G_WORKER_TASK_SPEC_V2", missing_status, reason, (evidence.code,), metadata), evidence

    spec: WorkerTaskSpecV2 | None
    status: Status
    try:
        spec = _parse(raw)
        if spec.base_head_sha != input_.head_sha:
            raise ValueError("WORKER_TASK_SPEC_HEAD_MISMATCH")
        if spec.source_snapshot_sha256 != input_.source_snapshot_sha256:
            raise ValueError("WORKER_TASK_SPEC_SOURCE_SNAPSHOT_MISMATCH")
        payload = spec.to_dict()
        metadata = {
            "required": required,
            "task_id": spec.task_id,
            "spec_sha256": sha256_json(payload),
            "story_dependency_count": len(spec.human_story["dependencies"]),
            "required_test_count": len(spec.required_tests),
            "semantic_ref_count": sum(
                len(spec.functional_contract[name])
                for name in ("acceptance_criteria", "invariants", "negative_controls")
            ),
        }
        status = "PASS"
        reason = "WorkerTaskSpec v2 is complete, source-bound and semantically test-covered"
    except (TypeError, ValueError, KeyError) as exc:
        spec = None
        status = "BLOCKED"
        reason = str(exc)
        metadata = {"required": required, "error": reason}

    source_ref = spec.task_id if spec is not None else input_.repo_full_name
    evidence = Evidence(
        code="E_WORKER_TASK_SPEC_V2",
        status=status,
        source_system="WORKER_TASK_SPEC",
        source_ref=source_ref,
        sha256=sha256_evidence_envelope(
            code="E_WORKER_TASK_SPEC_V2",
            status=status,
            source_system="WORKER_TASK_SPEC",
            source_ref=source_ref,
            head_sha=input_.head_sha,
            producer="RUNNER_WORKER_TASK_SPEC_GATE",
            metadata=metadata,
        ),
        head_sha=input_.head_sha,
        producer="RUNNER_WORKER_TASK_SPEC_GATE",
        metadata=metadata,
    )
    return spec, GateResult("G_WORKER_TASK_SPEC_V2", status, reason, (evidence.code,), metadata), evidence
