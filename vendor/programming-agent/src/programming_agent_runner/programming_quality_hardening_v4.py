from __future__ import annotations

import ast
import re
import tempfile
import urllib.error
from pathlib import Path
from typing import Any, Mapping

from . import programming_quality as q
from . import programming_quality_hardening_v2 as v2
from . import programming_quality_hardening_v3 as v3
from .hashutil import sha256_bytes, sha256_json, strict_json_loads
from .worker_oracle import HiddenOracle
from .worker_spec import AcceptanceCommand, WorkerTaskSpec
from .worker_workspace import WorkspaceError, create_disposable_workspace, replay_cumulative_patch, verify_source_repository

HIDDEN_EXECUTION_SCHEMA_VERSION = 1
EXECUTION_EVIDENCE_SCHEMA_VERSION = 2
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")

ReadbackManifest = v2.ReadbackManifest
parse_readback_manifest = v2.parse_readback_manifest
load_readback_manifest = v2.load_readback_manifest
readback_source_paths = v2.readback_source_paths
load_quality_plan = q.load_quality_plan
conservative_semantic_gate = v3.conservative_semantic_gate


def _semantic_targets(plan: q.QualityPlan) -> tuple[set[str], set[str]]:
    exact: set[str] = set()
    roots: set[str] = set()
    for relative in plan.semantic_paths:
        parts = list(Path(relative).with_suffix("").parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        module = ".".join(parts)
        exact.add(module)
        roots.add(parts[0])
    return exact, roots


def _target_aliases(tree: ast.AST, plan: q.QualityPlan) -> set[str]:
    exact, roots = _semantic_targets(plan)
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                if alias.name in exact or module_root in roots:
                    aliases.add(alias.asname or module_root)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_root = node.module.split(".")[0]
            if node.module in exact or module_root in roots:
                for alias in node.names:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _attribute_on_alias(node: ast.AST | None, aliases: set[str]) -> tuple[str, str] | None:
    if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
        return None
    if node.value.id not in aliases:
        return None
    return node.value.id, node.attr


def _target_calls(node: ast.AST, aliases: set[str]) -> list[tuple[ast.Call, str]]:
    calls: list[tuple[ast.Call, str]] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        bound = _attribute_on_alias(child.func, aliases)
        if bound is not None:
            calls.append((child, bound[1]))
    return calls


def _assert_calls_target(tree: ast.AST, aliases: set[str]) -> bool:
    for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert)):
        if _target_calls(assertion.test, aliases):
            return True
    return False


def _thread_targets_target(tree: ast.AST, aliases: set[str]) -> bool:
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        func_name = v3._call_name(call).lower()
        if func_name == "thread":
            for keyword in call.keywords:
                if keyword.arg == "target" and _attribute_on_alias(keyword.value, aliases) is not None:
                    return True
        if func_name == "submit" and call.args and _attribute_on_alias(call.args[0], aliases) is not None:
            return True
    return False


def _partial_failure_retries_target(tree: ast.AST, aliases: set[str]) -> bool:
    target_calls = _target_calls(tree, aliases)
    for attempt in (node for node in ast.walk(tree) if isinstance(node, ast.Try)):
        if not attempt.handlers:
            continue
        inside_names = {
            name
            for statement in attempt.body
            for _, name in _target_calls(statement, aliases)
        }
        if not inside_names:
            continue
        end_line = getattr(attempt, "end_lineno", getattr(attempt, "lineno", 0))
        later_names = {
            name
            for call, name in target_calls
            if getattr(call, "lineno", 0) > end_line
        }
        if inside_names & later_names:
            return True
    return False


def validate_test007_command_semantics(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    if oracle.family != v2.SEMANTIC_HIDDEN_FAMILY:
        return []
    commands = {command.name: command for command in oracle.commands}
    findings: list[str] = []
    for required in sorted(v2.REQUIRED_TEST007_HOLDOUTS):
        command = commands.get(required)
        if command is None:
            findings.append(f"HIDDEN_HOLDOUT_MISSING:{required}")
            continue
        tree = v3._inline_python(command)
        if tree is None:
            findings.append(f"HIDDEN_HOLDOUT_SOURCE_NOT_PINNED_INLINE:{required}")
            continue
        aliases = _target_aliases(tree, plan)
        if not aliases:
            findings.append(f"HIDDEN_HOLDOUT_NOT_BOUND_TO_SEMANTIC_TARGET:{required}")
            continue
        if not _assert_calls_target(tree, aliases):
            findings.append(f"HIDDEN_HOLDOUT_TARGET_ASSERTION_MISSING:{required}")
        if required == "test007_concurrent_duplicate_effect":
            if not _thread_targets_target(tree, aliases):
                findings.append("HIDDEN_HOLDOUT_CONCURRENCY_TARGET_NOT_EXECUTED")
        elif not _partial_failure_retries_target(tree, aliases):
            findings.append("HIDDEN_HOLDOUT_PARTIAL_FAILURE_TARGET_NOT_RETRIED")
    return sorted(set(findings))


def validate_hidden_holdout_contract(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    baseline: Mapping[str, Any],
) -> list[str]:
    families = baseline.get("families", {})
    if oracle.family not in families:
        return ["HIDDEN_ORACLE_FAMILY_NOT_BASELINED"]
    findings: list[str] = []
    if len(oracle.commands) < families[oracle.family]["min_hidden_holdouts"]:
        findings.append("HIDDEN_HOLDOUT_COUNT_BELOW_BASELINE")
    applies = {
        entry["dimension"]
        for entry in plan.risk_profile
        if entry["classification"] == "APPLIES"
    }
    if applies & v2.SEMANTIC_RISKS:
        if oracle.family != v2.SEMANTIC_HIDDEN_FAMILY:
            findings.append("TEST007_HIDDEN_FAMILY_REQUIRED")
        if not plan.semantic_paths:
            findings.append("SEMANTIC_TARGETS_REQUIRED")
        findings.extend(validate_test007_command_semantics(plan, oracle))
    return sorted(set(findings))


def hidden_contract_receipt(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    baseline: Mapping[str, Any],
    *,
    execution_id: str,
) -> dict[str, Any]:
    findings = validate_hidden_holdout_contract(plan, oracle, baseline)
    return q._control_receipt(
        "HIDDEN_HOLDOUT_CAUSAL_CONTRACT",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({
            "baseline": baseline["baseline_id"],
            "oracle_manifest": oracle.manifest_sha256,
            "commands": [sha256_json(command.to_dict()) for command in oracle.commands],
            "semantic_paths": list(plan.semantic_paths),
        }),
        outcome="FAIL" if findings else "PASS",
        reason_code="HIDDEN_HOLDOUT_CAUSALITY_UNPROVEN" if findings else "HIDDEN_HOLDOUT_CAUSALITY_PROVEN",
        evidence_refs=[f"oracle:{oracle.family}:{oracle.version}:{oracle.manifest_sha256}"],
        details={"findings": findings, "command_count": len(oracle.commands)},
    )


def _fixture_target_aliases(tree: ast.AST, plan: q.QualityPlan) -> set[str]:
    return _target_aliases(tree, plan)


def _strict_fixture_stage(command: AcceptanceCommand, stage: str, plan: q.QualityPlan) -> tuple[bool, str]:
    tree = v3._inline_python(command)
    if tree is None:
        return False, "FIXTURE_STAGE_CANONICAL_INLINE_PYTHON_REQUIRED"
    aliases = _fixture_target_aliases(tree, plan)
    if not aliases:
        return False, "FIXTURE_STAGE_NOT_BOUND_TO_DECLARED_TARGET"
    if stage == "setup_import":
        return True, "FIXTURE_SETUP_BOUND_TO_DECLARED_TARGET"
    if not _assert_calls_target(tree, aliases):
        return False, "FIXTURE_REACHABILITY_TARGET_CALL_REQUIRED"
    return True, "FIXTURE_REACHABILITY_BOUND_TO_DECLARED_TARGET"


def run_canonical_fixture_preflight(
    workspace: Path,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    if not plan.semantic_paths:
        return q._control_receipt(
            "FIXTURE_PREFLIGHT_CAUSAL",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="FAIL",
            reason_code="FIXTURE_TARGETS_REQUIRED",
        )
    base = v3.run_canonical_fixture_preflight(workspace, plan, execution_id=execution_id)
    if base["outcome"] != "PASS":
        return base
    details = dict(base.get("details", {}))
    bindings: list[dict[str, str]] = []
    for index, stage in ((2, "setup_import"), (3, "reachability")):
        ok, reason = _strict_fixture_stage(plan.fixture_preflight_commands[index], stage, plan)
        bindings.append({"stage": stage, "status": "PASS" if ok else "FAIL", "reason": reason})
    passed = all(item["status"] == "PASS" for item in bindings)
    details["declared_target_bindings"] = bindings
    return q._control_receipt(
        "FIXTURE_PREFLIGHT_CAUSAL",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({"base": base["output_digest"], "semantic_paths": list(plan.semantic_paths)}),
        outcome="PASS" if passed else "FAIL",
        reason_code="FIXTURE_VALID" if passed else "FIXTURE_TARGET_BINDING_INVALID",
        evidence_refs=[f"fixture-target:{item['stage']}:{item['status']}" for item in bindings],
        details=details,
    )


def _source_entity_bound(check: Mapping[str, Any]) -> bool:
    source = check["source"]
    return (
        source["kind"] == "supabase_rest"
        and check["entity"] == check["expected_entity"]
        and source["table"] == check["expected_entity"]
    )


def capture_readback_prestate(
    manifest: ReadbackManifest,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    persistence = v3._persistence_applies(plan)
    if manifest.task_id != plan.task_id:
        return q._control_receipt(
            "READBACK_PRESTATE",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL",
            reason_code="READBACK_TASK_BINDING_MISMATCH",
        )
    if persistence and not manifest.checks:
        return q._control_receipt(
            "READBACK_PRESTATE",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL",
            reason_code="READBACK_REQUIRED_FOR_PERSISTENCE",
        )
    states: list[dict[str, Any]] = []
    for index, check in enumerate(manifest.checks):
        if persistence and not _source_entity_bound(check):
            return q._control_receipt(
                "READBACK_PRESTATE",
                task_id=plan.task_id,
                execution_id=execution_id,
                head_sha=plan.base_head_sha,
                input_digest=manifest.sha256,
                outcome="FAIL",
                reason_code="READBACK_SOURCE_ENTITY_BINDING_MISMATCH",
                details={"check_index": index},
            )
        try:
            row, source_digest = v2._observed_row(check)
            states.append({
                "index": index,
                "state": "PRESENT",
                "row_digest": sha256_json(row),
                "source_digest": source_digest,
            })
        except ValueError as exc:
            if str(exc) == "READBACK_SUPABASE_EXPECTED_EXACTLY_ONE_ROW":
                states.append({"index": index, "state": "MISSING_OR_NONUNIQUE"})
            else:
                return q._control_receipt(
                    "READBACK_PRESTATE",
                    task_id=plan.task_id,
                    execution_id=execution_id,
                    head_sha=plan.base_head_sha,
                    input_digest=manifest.sha256,
                    outcome="BLOCKED",
                    reason_code=f"READBACK_PRESTATE_BLOCKED:{type(exc).__name__}",
                    details={"check_index": index},
                )
        except (OSError, UnicodeError, urllib.error.URLError) as exc:
            return q._control_receipt(
                "READBACK_PRESTATE",
                task_id=plan.task_id,
                execution_id=execution_id,
                head_sha=plan.base_head_sha,
                input_digest=manifest.sha256,
                outcome="BLOCKED",
                reason_code=f"READBACK_PRESTATE_BLOCKED:{type(exc).__name__}",
                details={"check_index": index},
            )
    return q._control_receipt(
        "READBACK_PRESTATE",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=manifest.sha256,
        outcome="PASS",
        reason_code="READBACK_PRESTATE_CAPTURED",
        details={"states": states, "persistence_applies": persistence},
    )


def run_readback_gate(
    manifest: ReadbackManifest,
    plan: q.QualityPlan,
    prestate: Mapping[str, Any],
    *,
    operation_receipt_sha256: str,
    execution_id: str,
) -> dict[str, Any]:
    persistence = v3._persistence_applies(plan)
    if _HEX64.fullmatch(operation_receipt_sha256) is None:
        return q._control_receipt(
            "READBACK_FIELD_BINDING_CAUSAL",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL",
            reason_code="READBACK_OPERATION_RECEIPT_INVALID",
        )
    if prestate.get("outcome") != "PASS":
        return q._control_receipt(
            "READBACK_FIELD_BINDING_CAUSAL",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL",
            reason_code="READBACK_PRESTATE_NOT_VERIFIED",
        )
    states = {item["index"]: item for item in prestate.get("details", {}).get("states", [])}
    children: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    refs = [f"operation:{operation_receipt_sha256}", f"prestate:{prestate['output_digest']}"]
    for index, check in enumerate(manifest.checks):
        if persistence and not _source_entity_bound(check):
            return q._control_receipt(
                "READBACK_FIELD_BINDING_CAUSAL",
                task_id=plan.task_id,
                execution_id=execution_id,
                head_sha=plan.base_head_sha,
                input_digest=manifest.sha256,
                outcome="FAIL",
                reason_code="READBACK_SOURCE_ENTITY_BINDING_MISMATCH",
                details={"check_index": index},
            )
        try:
            row, source_digest = v2._observed_row(check)
            refs.append(f"readback-source:{check['source']['kind']}:{source_digest}")
            child = q.readback_field_binding(
                entity=check["entity"],
                expected_entity=check["expected_entity"],
                row=row,
                pk_field=check["pk_field"],
                expected_pk=check["expected_pk"],
                field=check["field"],
                expected_value=check["expected_value"],
                expected_type=v2._ALLOWED_TYPES[check["expected_type"]],
                status_field=check["status_field"],
                expected_status=check["expected_status"],
                task_id=plan.task_id,
                execution_id=f"{execution_id}:readback:{index}",
                head_sha=plan.base_head_sha,
            )
            previous = states.get(index, {"state": "UNKNOWN"})
            changed = previous.get("state") != "PRESENT" or previous.get("row_digest") != sha256_json(row)
            changes.append({"index": index, "changed_since_prestate": changed})
        except (OSError, UnicodeError, ValueError, urllib.error.URLError) as exc:
            child = q._control_receipt(
                "READBACK_OBSERVATION",
                task_id=plan.task_id,
                execution_id=f"{execution_id}:readback:{index}",
                head_sha=plan.base_head_sha,
                input_digest=manifest.sha256,
                outcome="BLOCKED",
                reason_code=f"READBACK_OBSERVATION_BLOCKED:{type(exc).__name__}",
                details={"check_index": index},
            )
            changes.append({"index": index, "changed_since_prestate": False})
        children.append(child)
    failed = [item for item in children if item["outcome"] != "PASS"]
    unchanged = [item for item in changes if persistence and not item["changed_since_prestate"]]
    if failed:
        outcome = "FAIL"
        reason = "READBACK_SOURCE_OF_TRUTH_MISMATCH"
    elif unchanged:
        outcome = "FAIL"
        reason = "READBACK_NO_POST_OPERATION_CHANGE"
    elif persistence and not children:
        outcome = "FAIL"
        reason = "READBACK_REQUIRED_FOR_PERSISTENCE"
    else:
        outcome = "PASS" if children else "N/A"
        reason = "READBACK_CAUSALLY_VERIFIED" if children else "READBACK_NOT_APPLICABLE"
    return q._control_receipt(
        "READBACK_FIELD_BINDING_CAUSAL",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({
            "manifest": manifest.sha256,
            "prestate": prestate["output_digest"],
            "operation": operation_receipt_sha256,
        }),
        outcome=outcome,
        reason_code=reason,
        evidence_refs=refs + [f"readback:{item['output_digest']}" for item in children],
        details={
            "check_count": len(children),
            "failed_count": len(failed),
            "changes": changes,
            "persistence_applies": persistence,
        },
    )


def load_execution_evidence_config(path: Path) -> dict[str, Any]:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"schema_version", "families"}:
        raise ValueError("execution evidence config fields invalid")
    if value["schema_version"] != EXECUTION_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f"execution evidence schema_version must be {EXECUTION_EVIDENCE_SCHEMA_VERSION}")
    if not isinstance(value["families"], dict) or set(value["families"]) != set(q.BASELINE_FAMILIES):
        raise ValueError("execution evidence families invalid")
    for family, item in value["families"].items():
        if not isinstance(item, dict) or set(item) != {"adversarial_test_suffixes"}:
            raise ValueError(f"execution evidence family fields invalid:{family}")
        suffixes = item["adversarial_test_suffixes"]
        if not isinstance(suffixes, list) or len(suffixes) != len(set(suffixes)):
            raise ValueError(f"execution evidence suffixes invalid:{family}")
        if not all(isinstance(suffix, str) and suffix for suffix in suffixes):
            raise ValueError(f"execution evidence suffix invalid:{family}")
    return value


def validate_hidden_execution_receipt(value: Any, *, expected_head: str) -> list[str]:
    errors: list[str] = []
    fields = {"schema_version", "control_id", "exact_head", "families", "outcome", "reason_code", "output_digest"}
    if not isinstance(value, dict) or set(value) != fields:
        return ["HIDDEN_EXECUTION_RECEIPT_FIELDS_INVALID"]
    if value.get("schema_version") != HIDDEN_EXECUTION_SCHEMA_VERSION:
        errors.append("HIDDEN_EXECUTION_SCHEMA_INVALID")
    if value.get("control_id") != "RUNTIME_HIDDEN_HOLDOUT_EVIDENCE":
        errors.append("HIDDEN_EXECUTION_CONTROL_INVALID")
    if value.get("exact_head") != expected_head:
        errors.append("HIDDEN_EXECUTION_HEAD_MISMATCH")
    families = value.get("families")
    if not isinstance(families, dict) or set(families) != set(q.BASELINE_FAMILIES):
        errors.append("HIDDEN_EXECUTION_FAMILIES_INVALID")
    else:
        for family, item in families.items():
            required = {"status", "command_ids", "command_count", "passed_count", "manifest_sha256", "result_sha256"}
            if not isinstance(item, dict) or set(item) != required:
                errors.append(f"HIDDEN_EXECUTION_FAMILY_FIELDS_INVALID:{family}")
                continue
            if item.get("status") != "PASS":
                errors.append(f"HIDDEN_EXECUTION_FAMILY_NOT_PASS:{family}")
            ids = item.get("command_ids")
            if not isinstance(ids, list) or len(ids) != len(set(ids)) or not all(isinstance(item_id, str) and item_id for item_id in ids):
                errors.append(f"HIDDEN_EXECUTION_IDS_INVALID:{family}")
            if item.get("command_count") != len(ids or []):
                errors.append(f"HIDDEN_EXECUTION_COUNT_MISMATCH:{family}")
            if item.get("passed_count") != item.get("command_count"):
                errors.append(f"HIDDEN_EXECUTION_NOT_ALL_PASSED:{family}")
            for digest_field in ("manifest_sha256", "result_sha256"):
                if not isinstance(item.get(digest_field), str) or _HEX64.fullmatch(item[digest_field]) is None:
                    errors.append(f"HIDDEN_EXECUTION_DIGEST_INVALID:{family}:{digest_field}")
    if value.get("outcome") != "PASS":
        errors.append("HIDDEN_EXECUTION_OUTCOME_NOT_PASS")
    digest = value.get("output_digest")
    if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        errors.append("HIDDEN_EXECUTION_OUTPUT_DIGEST_INVALID")
    elif sha256_json({key: value[key] for key in value if key != "output_digest"}) != digest:
        errors.append("HIDDEN_EXECUTION_OUTPUT_DIGEST_MISMATCH")
    return errors


def evaluate_ci_execution_evidence(
    baseline: Mapping[str, Any],
    config: Mapping[str, Any],
    successful_test_ids: set[str],
    hidden_receipt: Mapping[str, Any],
    *,
    head_sha: str,
    test_receipt_sha256: str,
) -> dict[str, Any]:
    receipt_errors = validate_hidden_execution_receipt(hidden_receipt, expected_head=head_sha)
    families: dict[str, Any] = {}
    findings = list(receipt_errors)
    for family in q.BASELINE_FAMILIES:
        suffixes = config["families"][family]["adversarial_test_suffixes"]
        adversarial = sorted(
            suffix
            for suffix in suffixes
            if any(test_id.endswith(suffix) for test_id in successful_test_ids)
        )
        hidden_family = hidden_receipt.get("families", {}).get(family, {})
        hidden_ids = hidden_family.get("command_ids", []) if isinstance(hidden_family, dict) else []
        required_hidden = baseline["families"][family]["min_hidden_holdouts"]
        required_adversarial = baseline["families"][family]["min_adversarial_tests"]
        if len(hidden_ids) < required_hidden:
            findings.append(f"HIDDEN_EXECUTION_EVIDENCE_BELOW_BASELINE:{family}")
        if len(adversarial) < required_adversarial:
            findings.append(f"ADVERSARIAL_EXECUTION_EVIDENCE_BELOW_BASELINE:{family}")
        families[family] = {
            "hidden_receipt_ids": list(hidden_ids),
            "hidden_count": len(hidden_ids),
            "required_hidden_count": required_hidden,
            "adversarial_test_ids": adversarial,
            "adversarial_count": len(adversarial),
            "required_adversarial_count": required_adversarial,
        }
    value: dict[str, Any] = {
        "schema_version": 2,
        "control_id": "PROGRAMMING_QUALITY_EXECUTION_EVIDENCE",
        "exact_head": head_sha,
        "test_receipt_sha256": test_receipt_sha256,
        "hidden_execution_receipt_sha256": hidden_receipt.get("output_digest"),
        "families": families,
        "findings": sorted(set(findings)),
        "outcome": "FAIL" if findings else "PASS",
        "reason_code": "EXECUTION_EVIDENCE_INSUFFICIENT" if findings else "EXECUTION_EVIDENCE_BOUND_AND_SUFFICIENT",
    }
    value["output_digest"] = sha256_json(value)
    return value


def _outer_receipt(
    plan: q.QualityPlan,
    spec: WorkerTaskSpec,
    controls: list[dict[str, Any]],
    legacy: q.ProgrammingQualityWorkerResult | None,
    *,
    status: str,
    reason: str,
    patch: str,
) -> q.ProgrammingQualityWorkerResult:
    value: dict[str, Any] = {
        "schema_version": 5,
        "task_id": plan.task_id,
        "task_sha256": spec.sha256,
        "base_head_sha": plan.base_head_sha,
        "source_snapshot_sha256": spec.source_snapshot_sha256,
        "quality_plan_sha256": plan.sha256,
        "controls": [
            {
                "control_id": item["control_id"],
                "outcome": item["outcome"],
                "reason_code": item["reason_code"],
                "output_digest": item["output_digest"],
            }
            for item in controls
        ],
        "legacy_quality_receipt_sha256": None if legacy is None else legacy.receipt["receipt_sha256"],
        "status": status,
        "reason": reason,
        "patch_sha256": sha256_bytes(patch.encode("utf-8")) if patch else None,
        "patch_delivered": status == "PASS",
        "commit_allowed": False,
        "push_allowed": False,
        "merge_allowed": False,
        "production_allowed": False,
        "independent_audit_required": True,
    }
    value["receipt_sha256"] = sha256_json(value)
    return q.ProgrammingQualityWorkerResult(value, patch if status == "PASS" else "")


def run_programming_quality_worker_hardened(
    repo_path: Path,
    spec: WorkerTaskSpec,
    client: Any,
    oracle: HiddenOracle,
    plan: q.QualityPlan,
    readback_manifest: ReadbackManifest,
    *,
    work_parent: Path | None = None,
) -> q.ProgrammingQualityWorkerResult:
    execution = plan.task_id
    if plan.task_id != spec.task_id or plan.base_head_sha != spec.base_head_sha:
        return _outer_receipt(plan, spec, [], None, status="BLOCKED", reason="QUALITY_PLAN_TASK_BINDING_MISMATCH", patch="")
    try:
        baseline = q.load_baseline(repo_path / "quality/programming_quality/baseline_v1.json")
    except ValueError as exc:
        return _outer_receipt(plan, spec, [], None, status="BLOCKED", reason=f"BASELINE_INVALID:{exc}", patch="")
    controls = [
        v2.evaluate_bound_risk_profile(plan, spec, oracle, execution_id=execution),
        hidden_contract_receipt(plan, oracle, baseline, execution_id=execution),
    ]
    failed = next((item for item in controls if item["outcome"] in {"FAIL", "BLOCKED"}), None)
    if failed is not None:
        return _outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=failed["reason_code"], patch="")
    prestate = capture_readback_prestate(readback_manifest, plan, execution_id=execution)
    controls.append(prestate)
    if prestate["outcome"] in {"FAIL", "BLOCKED"}:
        return _outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=prestate["reason_code"], patch="")
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-aud23-preflight-", dir=parent) as temporary:
            workspace = Path(temporary) / "fixture"
            create_disposable_workspace(repo_path, workspace, identity)
            fixture = run_canonical_fixture_preflight(workspace, plan, execution_id=execution)
    except WorkspaceError as exc:
        fixture = q._control_receipt(
            "FIXTURE_PREFLIGHT_CAUSAL",
            task_id=plan.task_id,
            execution_id=execution,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="BLOCKED",
            reason_code=str(exc),
        )
    controls.append(fixture)
    if fixture["outcome"] != "PASS":
        return _outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=fixture["reason_code"], patch="")
    legacy = q.run_programming_quality_worker(
        repo_path,
        spec,
        client,
        oracle,
        plan,
        work_parent=work_parent,
        execution_id=execution,
    )
    if legacy.receipt["status"] != "PASS":
        return _outer_receipt(plan, spec, controls, legacy, status=legacy.receipt["status"], reason=legacy.receipt["reason"], patch="")
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-aud23-postgreen-", dir=parent) as temporary:
            candidate = Path(temporary) / "candidate"
            create_disposable_workspace(repo_path, candidate, identity)
            replay_cumulative_patch(candidate, legacy.patch)
            semantic = conservative_semantic_gate(candidate, plan, execution_id=execution)
    except WorkspaceError as exc:
        semantic = q._control_receipt(
            "SEMANTIC_BEHAVIORAL_GUARD",
            task_id=plan.task_id,
            execution_id=execution,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="BLOCKED",
            reason_code=str(exc),
        )
    controls.append(semantic)
    if semantic["outcome"] in {"FAIL", "BLOCKED"}:
        return _outer_receipt(plan, spec, controls, legacy, status=semantic["outcome"], reason=semantic["reason_code"], patch="")
    readback = run_readback_gate(
        readback_manifest,
        plan,
        prestate,
        operation_receipt_sha256=legacy.receipt["receipt_sha256"],
        execution_id=execution,
    )
    controls.append(readback)
    if readback["outcome"] in {"FAIL", "BLOCKED"}:
        return _outer_receipt(plan, spec, controls, legacy, status=readback["outcome"], reason=readback["reason_code"], patch="")
    return _outer_receipt(
        plan,
        spec,
        controls,
        legacy,
        status="PASS",
        reason="AUD23_CAUSAL_PROGRAMMING_QUALITY_GATE_PASSED",
        patch=legacy.patch,
    )
