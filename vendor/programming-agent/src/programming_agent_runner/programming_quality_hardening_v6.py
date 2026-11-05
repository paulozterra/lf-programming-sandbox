from __future__ import annotations

import ast
import re
import tempfile
import urllib.error
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from . import programming_quality as q
from . import programming_quality_hardening_v2 as v2
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v5 as v5
from .hashutil import sha256_json
from .worker_oracle import HiddenOracle
from .worker_spec import AcceptanceCommand, WorkerTaskSpec
from .worker_workspace import WorkspaceError, create_disposable_workspace, replay_cumulative_patch, verify_source_repository

HIDDEN_EXECUTION_SCHEMA_VERSION = 3
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")

ReadbackManifest = v2.ReadbackManifest
parse_readback_manifest = v2.parse_readback_manifest
load_readback_manifest = v2.load_readback_manifest
readback_source_paths = v2.readback_source_paths
load_quality_plan = q.load_quality_plan
load_execution_evidence_config = v5.load_execution_evidence_config
conservative_semantic_gate = v3.conservative_semantic_gate


def _exact_modules(plan: q.QualityPlan) -> set[str]:
    modules: set[str] = set()
    for relative in plan.semantic_paths:
        parts = list(Path(relative).with_suffix("").parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            modules.add(".".join(parts))
    return modules


def _dotted(node: ast.AST | None) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return None if prefix is None else (*prefix, node.attr)
    return None


def _import_bindings(tree: ast.AST, plan: q.QualityPlan) -> tuple[dict[str, tuple[str, ...]], set[str]]:
    targets = _exact_modules(plan)
    bindings: dict[str, tuple[str, ...]] = {}
    explicitly_imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in targets:
                    continue
                explicitly_imported.add(alias.name)
                if alias.asname:
                    bindings[alias.asname] = tuple(alias.name.split("."))
                else:
                    bindings[alias.name.split(".")[0]] = (alias.name.split(".")[0],)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = f"{node.module}.{alias.name}"
                local = alias.asname or alias.name
                if candidate in targets:
                    explicitly_imported.add(candidate)
                    bindings[local] = tuple(candidate.split("."))
                elif node.module in targets:
                    explicitly_imported.add(node.module)
                    bindings[local] = (*node.module.split("."), alias.name)
    return bindings, explicitly_imported


def _canonical_reference(node: ast.AST | None, tree: ast.AST, plan: q.QualityPlan) -> tuple[str, ...] | None:
    parts = _dotted(node)
    if not parts:
        return None
    bindings, explicit = _import_bindings(tree, plan)
    first = bindings.get(parts[0])
    canonical = (*first, *parts[1:]) if first is not None else parts
    targets = _exact_modules(plan)
    for module in targets:
        prefix = tuple(module.split("."))
        if len(canonical) > len(prefix) and canonical[: len(prefix)] == prefix and module in explicit:
            return canonical
    return None


def _target_calls(node: ast.AST, tree: ast.AST, plan: q.QualityPlan) -> list[tuple[ast.Call, str]]:
    calls: list[tuple[ast.Call, str]] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        reference = _canonical_reference(child.func, tree, plan)
        if reference is not None:
            calls.append((child, ".".join(reference)))
    return calls


def _declared_entrypoints(plan: q.QualityPlan) -> set[str]:
    if len(plan.fixture_preflight_commands) < 4:
        return set()
    tree = v3._inline_python(plan.fixture_preflight_commands[3])
    if tree is None:
        return set()
    result: set[str] = set()
    for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert)):
        result.update(name for _, name in _target_calls(assertion.test, tree, plan))
    return result


def _name_set(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _identity_signature(call: ast.Call, *, ignore_failure_flag: bool = False) -> str | None:
    positional = list(call.args)
    keywords = [(item.arg, item.value) for item in call.keywords if item.arg is not None]
    failure_keywords = {"fail", "should_fail", "inject_failure", "fail_after_effect"}
    if ignore_failure_flag:
        keywords = [(name, value) for name, value in keywords if name not in failure_keywords]
        if positional and isinstance(positional[-1], ast.Constant) and isinstance(positional[-1].value, bool):
            positional = positional[:-1]
    if not positional and not keywords:
        return None
    return ast.dump(
        ast.Tuple(
            elts=[*positional, *[ast.Tuple(elts=[ast.Constant(name), value], ctx=ast.Load()) for name, value in keywords]],
            ctx=ast.Load(),
        ),
        include_attributes=False,
    )


def _failure_flag(call: ast.Call) -> bool:
    for item in call.keywords:
        if item.arg in {"fail", "should_fail", "inject_failure", "fail_after_effect"}:
            return isinstance(item.value, ast.Constant) and item.value.value is True
    return bool(call.args and isinstance(call.args[-1], ast.Constant) and call.args[-1].value is True)


def _thread_invocation(call: ast.Call, tree: ast.AST, plan: q.QualityPlan) -> tuple[str, str] | None:
    name = v3._call_name(call).lower()
    target_node: ast.AST | None = None
    args_node: ast.AST | None = None
    if name == "thread":
        for keyword in call.keywords:
            if keyword.arg == "target":
                target_node = keyword.value
            elif keyword.arg == "args":
                args_node = keyword.value
    elif name == "submit" and call.args:
        target_node = call.args[0]
        args_node = ast.Tuple(elts=list(call.args[1:]), ctx=ast.Load())
    else:
        return None
    reference = _canonical_reference(target_node, tree, plan)
    if reference is None:
        return None
    if args_node is None:
        return None
    signature = ast.dump(args_node, include_attributes=False)
    return ".".join(reference), signature


def _comprehension_variables(node: ast.AST) -> set[str]:
    variables: set[str] = set()
    for comp in ast.walk(node):
        if isinstance(comp, ast.comprehension):
            variables.update(_name_set(comp.target))
    return variables


def _iterable_multiplicity(node: ast.AST) -> int:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
        if len(node.args) == 1 and isinstance(node.args[0], ast.Constant) and type(node.args[0].value) is int:
            return max(0, node.args[0].value)
    return 0


def _same_identity_concurrency_proven(tree: ast.AST, plan: q.QualityPlan, entrypoints: set[str]) -> bool:
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        invocation = _thread_invocation(call, tree, plan)
        if invocation is not None and invocation[0] in entrypoints:
            grouped[invocation] += 1
    for comp in (node for node in ast.walk(tree) if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp))):
        if not isinstance(comp.elt, ast.Call):
            continue
        invocation = _thread_invocation(comp.elt, tree, plan)
        if invocation is None or invocation[0] not in entrypoints:
            continue
        variables = _comprehension_variables(comp)
        if variables & _name_set(comp.elt):
            continue
        multiplicity = 1
        for generator in comp.generators:
            multiplicity *= _iterable_multiplicity(generator.iter)
        grouped[invocation] = max(grouped[invocation], multiplicity)
    return any(count >= 2 for count in grouped.values())


def _single_effect_assertion(tree: ast.AST, plan: q.QualityPlan, entrypoints: set[str]) -> bool:
    for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert)):
        test = assertion.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        pairs = ((test.left, test.comparators[0]), (test.comparators[0], test.left))
        for call_node, one_node in pairs:
            if not isinstance(one_node, ast.Constant) or one_node.value != 1 or not isinstance(call_node, ast.Call):
                continue
            reference = _canonical_reference(call_node.func, tree, plan)
            if reference is None:
                continue
            callable_name = ".".join(reference)
            if callable_name not in entrypoints:
                return True
    return False


def _partial_failure_same_identity_proven(tree: ast.AST, plan: q.QualityPlan, entrypoints: set[str]) -> bool:
    all_calls = _target_calls(tree, tree, plan)
    for attempt in (node for node in ast.walk(tree) if isinstance(node, ast.Try)):
        if not attempt.handlers:
            continue
        if any(isinstance(item, ast.Raise) for statement in attempt.body for item in ast.walk(statement)):
            continue
        inside = [
            (call, name)
            for statement in attempt.body
            for call, name in _target_calls(statement, tree, plan)
            if name in entrypoints
        ]
        if len(inside) != 1 or not _failure_flag(inside[0][0]):
            continue
        inside_signature = _identity_signature(inside[0][0], ignore_failure_flag=True)
        if inside_signature is None:
            continue
        end_line = getattr(attempt, "end_lineno", getattr(attempt, "lineno", 0))
        for call, name in all_calls:
            if name != inside[0][1] or getattr(call, "lineno", 0) <= end_line:
                continue
            if _failure_flag(call):
                continue
            if _identity_signature(call, ignore_failure_flag=True) == inside_signature:
                return True
    return False


def validate_test007_command_semantics(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    if oracle.family != v2.SEMANTIC_HIDDEN_FAMILY:
        return []
    entrypoints = _declared_entrypoints(plan)
    findings: list[str] = []
    if not entrypoints:
        findings.append("SEMANTIC_ENTRYPOINT_NOT_DECLARED")
    commands = {item.name: item for item in oracle.commands}
    for required in sorted(v2.REQUIRED_TEST007_HOLDOUTS):
        command = commands.get(required)
        if command is None:
            findings.append(f"HIDDEN_HOLDOUT_MISSING:{required}")
            continue
        tree = v3._inline_python(command)
        if tree is None:
            findings.append(f"HIDDEN_HOLDOUT_SOURCE_NOT_PINNED_INLINE:{required}")
            continue
        if required == "test007_concurrent_duplicate_effect":
            if not _same_identity_concurrency_proven(tree, plan, entrypoints):
                findings.append("HIDDEN_HOLDOUT_SAME_IDENTITY_CONCURRENCY_UNPROVEN")
            if not _single_effect_assertion(tree, plan, entrypoints):
                findings.append("HIDDEN_HOLDOUT_SINGLE_EFFECT_ASSERTION_MISSING")
        else:
            if not _partial_failure_same_identity_proven(tree, plan, entrypoints):
                findings.append("HIDDEN_HOLDOUT_PARTIAL_FAILURE_SAME_IDENTITY_UNPROVEN")
            if not _single_effect_assertion(tree, plan, entrypoints):
                findings.append("HIDDEN_HOLDOUT_SINGLE_EFFECT_ASSERTION_MISSING")
    return sorted(set(findings))


def hidden_contract_receipt(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    baseline: Mapping[str, Any],
    *,
    execution_id: str,
) -> dict[str, Any]:
    findings: list[str] = []
    families = baseline.get("families", {})
    if oracle.family not in families:
        findings.append("HIDDEN_ORACLE_FAMILY_NOT_BASELINED")
    elif len(oracle.commands) < families[oracle.family]["min_hidden_holdouts"]:
        findings.append("HIDDEN_HOLDOUT_COUNT_BELOW_BASELINE")
    applies = {
        item["dimension"]
        for item in plan.risk_profile
        if item["classification"] == "APPLIES"
    }
    if applies & v2.SEMANTIC_RISKS:
        if oracle.family != v2.SEMANTIC_HIDDEN_FAMILY:
            findings.append("TEST007_HIDDEN_FAMILY_REQUIRED")
        if not plan.semantic_paths:
            findings.append("SEMANTIC_TARGETS_REQUIRED")
        findings.extend(validate_test007_command_semantics(plan, oracle))
    return q._control_receipt(
        "HIDDEN_HOLDOUT_SAME_IDENTITY_EFFECT_CONTRACT",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({
            "baseline": baseline.get("baseline_id"),
            "oracle_manifest": oracle.manifest_sha256,
            "semantic_paths": list(plan.semantic_paths),
            "entrypoints": sorted(_declared_entrypoints(plan)),
        }),
        outcome="FAIL" if findings else "PASS",
        reason_code="HIDDEN_HOLDOUT_BEHAVIOR_CONTRACT_INVALID" if findings else "HIDDEN_HOLDOUT_BEHAVIOR_CONTRACT_VALID",
        evidence_refs=[f"oracle:{oracle.family}:{oracle.version}:{oracle.manifest_sha256}"],
        details={"findings": sorted(set(findings)), "entrypoints": sorted(_declared_entrypoints(plan))},
    )


def _strict_fixture_stage(command: AcceptanceCommand, stage: str, plan: q.QualityPlan) -> tuple[bool, str]:
    tree = v3._inline_python(command)
    if tree is None:
        return False, "FIXTURE_STAGE_CANONICAL_INLINE_PYTHON_REQUIRED"
    calls = _target_calls(tree, tree, plan)
    imported = _import_bindings(tree, plan)[1]
    if not imported:
        return False, "FIXTURE_STAGE_NOT_BOUND_TO_EXACT_TARGET"
    if stage == "setup_import":
        return True, "FIXTURE_SETUP_BOUND_TO_EXACT_TARGET"
    entrypoints = _declared_entrypoints(plan)
    if not entrypoints or not any(name in entrypoints for _, name in calls):
        return False, "FIXTURE_REACHABILITY_EXACT_ENTRYPOINT_REQUIRED"
    return True, "FIXTURE_REACHABILITY_BOUND_TO_EXACT_ENTRYPOINT"


def run_canonical_fixture_preflight(
    workspace: Path,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    base = v3.run_canonical_fixture_preflight(workspace, plan, execution_id=execution_id)
    if base["outcome"] != "PASS":
        return base
    bindings: list[dict[str, str]] = []
    for index, stage in ((2, "setup_import"), (3, "reachability")):
        ok, reason = _strict_fixture_stage(plan.fixture_preflight_commands[index], stage, plan)
        bindings.append({"stage": stage, "status": "PASS" if ok else "FAIL", "reason": reason})
    passed = bool(plan.semantic_paths) and all(item["status"] == "PASS" for item in bindings)
    return q._control_receipt(
        "FIXTURE_PREFLIGHT_EXACT_MODULE_V6",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({"base": base["output_digest"], "semantic_paths": list(plan.semantic_paths)}),
        outcome="PASS" if passed else "FAIL",
        reason_code="FIXTURE_VALID" if passed else "FIXTURE_EXACT_MODULE_BINDING_INVALID",
        details={"bindings": bindings},
    )


def _source_entity_bound(check: Mapping[str, Any]) -> bool:
    source = check["source"]
    return (
        source["kind"] == "supabase_rest"
        and check["entity"] == check["expected_entity"]
        and source["table"] == check["expected_entity"]
    )


def _value_digest(value: Any) -> str:
    return sha256_json({"value": value})


def capture_readback_prestate(
    manifest: ReadbackManifest,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    persistence = v3._persistence_applies(plan)
    if manifest.task_id != plan.task_id:
        return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_TASK_BINDING_MISMATCH")
    if persistence and not manifest.checks:
        return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_REQUIRED_FOR_PERSISTENCE")
    states: list[dict[str, Any]] = []
    for index, check in enumerate(manifest.checks):
        if persistence and not _source_entity_bound(check):
            return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_SOURCE_ENTITY_BINDING_MISMATCH", details={"check_index": index})
        try:
            row, source_digest = v2._observed_row(check)
            if row.get(check["pk_field"]) != check["expected_pk"]:
                return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_PRESTATE_PK_MISMATCH", details={"check_index": index})
            if check["field"] not in row:
                return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_PRESTATE_FIELD_MISSING", details={"check_index": index})
            states.append({
                "index": index,
                "state": "PRESENT",
                "pk_digest": _value_digest(row[check["pk_field"]]),
                "field_digest": _value_digest(row[check["field"]]),
                "expected_field_digest": _value_digest(check["expected_value"]),
                "source_digest": source_digest,
            })
        except ValueError as exc:
            if str(exc) == "READBACK_SUPABASE_EXPECTED_EXACTLY_ONE_ROW":
                states.append({"index": index, "state": "MISSING_OR_NONUNIQUE"})
            else:
                return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="BLOCKED", reason_code=f"READBACK_PRESTATE_BLOCKED:{type(exc).__name__}", details={"check_index": index})
        except (OSError, UnicodeError, urllib.error.URLError) as exc:
            return q._control_receipt("READBACK_PRESTATE_FIELD_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="BLOCKED", reason_code=f"READBACK_PRESTATE_BLOCKED:{type(exc).__name__}", details={"check_index": index})
    missing = [item for item in states if item["state"] != "PRESENT"]
    pre_satisfied = [item for item in states if item.get("field_digest") == item.get("expected_field_digest")]
    outcome = "FAIL" if persistence and (missing or pre_satisfied) else "PASS"
    reason = "READBACK_PRESTATE_ROW_REQUIRED_FOR_UPDATE" if missing else "READBACK_EXPECTED_VALUE_ALREADY_PRESENT_PRESTATE" if pre_satisfied else "READBACK_FIELD_PRESTATE_CAPTURED"
    return q._control_receipt(
        "READBACK_PRESTATE_FIELD_V6",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=manifest.sha256,
        outcome=outcome,
        reason_code=reason,
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
        return q._control_receipt("READBACK_FIELD_TRANSITION_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_OPERATION_RECEIPT_INVALID")
    if prestate.get("outcome") != "PASS":
        return q._control_receipt("READBACK_FIELD_TRANSITION_V6", task_id=plan.task_id, execution_id=execution_id, head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL", reason_code="READBACK_PRESTATE_NOT_VERIFIED")
    states = {item["index"]: item for item in prestate.get("details", {}).get("states", [])}
    children: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    refs = [f"operation:{operation_receipt_sha256}", f"prestate:{prestate['output_digest']}"]
    for index, check in enumerate(manifest.checks):
        previous = states.get(index)
        if persistence and (previous is None or previous.get("state") != "PRESENT"):
            transitions.append({"index": index, "specific_transition": False, "reason": "PRESTATE_NOT_PRESENT"})
            continue
        try:
            row, source_digest = v2._observed_row(check)
            refs.append(f"readback-source:{check['source']['kind']}:{source_digest}")
            child = q.readback_field_binding(
                entity=check["entity"], expected_entity=check["expected_entity"], row=row,
                pk_field=check["pk_field"], expected_pk=check["expected_pk"], field=check["field"],
                expected_value=check["expected_value"], expected_type=v2._ALLOWED_TYPES[check["expected_type"]],
                status_field=check["status_field"], expected_status=check["expected_status"],
                task_id=plan.task_id, execution_id=f"{execution_id}:readback:{index}", head_sha=plan.base_head_sha,
            )
            post_digest = _value_digest(row.get(check["field"]))
            changed_to_expected = (
                previous is not None
                and previous.get("field_digest") != previous.get("expected_field_digest")
                and post_digest == previous.get("expected_field_digest")
            )
            transitions.append({"index": index, "specific_transition": changed_to_expected, "reason": "FIELD_OLD_TO_EXPECTED" if changed_to_expected else "FIELD_TRANSITION_UNPROVEN"})
        except (OSError, UnicodeError, ValueError, urllib.error.URLError) as exc:
            child = q._control_receipt("READBACK_OBSERVATION", task_id=plan.task_id, execution_id=f"{execution_id}:readback:{index}", head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="BLOCKED", reason_code=f"READBACK_OBSERVATION_BLOCKED:{type(exc).__name__}")
            transitions.append({"index": index, "specific_transition": False, "reason": "OBSERVATION_BLOCKED"})
        children.append(child)
    failed = [item for item in children if item["outcome"] != "PASS"]
    unproven = [item for item in transitions if persistence and not item["specific_transition"]]
    if failed:
        outcome, reason = "FAIL", "READBACK_SOURCE_OF_TRUTH_MISMATCH"
    elif unproven:
        outcome, reason = "FAIL", "READBACK_ASSERTED_FIELD_TRANSITION_UNPROVEN"
    elif persistence and not children:
        outcome, reason = "FAIL", "READBACK_REQUIRED_FOR_PERSISTENCE"
    else:
        outcome, reason = ("PASS", "READBACK_ASSERTED_FIELD_TRANSITION_VERIFIED") if children else ("N/A", "READBACK_NOT_APPLICABLE")
    return q._control_receipt(
        "READBACK_FIELD_TRANSITION_V6", task_id=plan.task_id, execution_id=execution_id,
        head_sha=plan.base_head_sha, input_digest=sha256_json({"manifest": manifest.sha256, "prestate": prestate["output_digest"], "operation": operation_receipt_sha256}),
        outcome=outcome, reason_code=reason, evidence_refs=refs + [f"readback:{item['output_digest']}" for item in children],
        details={"transitions": transitions, "failed_count": len(failed), "persistence_applies": persistence},
    )


def validate_external_hidden_execution_receipt(value: Any, *, expected_head: str) -> list[str]:
    fields = {
        "schema_version", "control_id", "exact_head", "broker", "broker_version", "broker_policy_id",
        "challenge_id", "broker_response_sha256", "families", "outcome", "reason_code", "output_digest",
    }
    if not isinstance(value, dict) or set(value) != fields:
        return ["EXTERNAL_HIDDEN_RECEIPT_FIELDS_INVALID"]
    errors: list[str] = []
    if value.get("schema_version") != HIDDEN_EXECUTION_SCHEMA_VERSION:
        errors.append("EXTERNAL_HIDDEN_SCHEMA_INVALID")
    if value.get("control_id") != "EXTERNAL_HIDDEN_ORACLE_EVIDENCE":
        errors.append("EXTERNAL_HIDDEN_CONTROL_INVALID")
    if value.get("exact_head") != expected_head:
        errors.append("EXTERNAL_HIDDEN_HEAD_MISMATCH")
    if value.get("broker") != "supabase-edge":
        errors.append("EXTERNAL_HIDDEN_BROKER_INVALID")
    for key in ("broker_policy_id", "challenge_id", "broker_response_sha256"):
        item = value.get(key)
        if not isinstance(item, str) or _HEX64.fullmatch(item) is None:
            errors.append(f"EXTERNAL_HIDDEN_DIGEST_INVALID:{key}")
    families = value.get("families")
    if not isinstance(families, dict) or set(families) != set(q.BASELINE_FAMILIES):
        errors.append("EXTERNAL_HIDDEN_FAMILIES_INVALID")
    else:
        for family, item in families.items():
            required = {"status", "command_ids", "command_count", "passed_count", "manifest_sha256", "result_sha256"}
            if not isinstance(item, dict) or set(item) != required:
                errors.append(f"EXTERNAL_HIDDEN_FAMILY_FIELDS_INVALID:{family}")
                continue
            ids = item.get("command_ids")
            if item.get("status") != "PASS":
                errors.append(f"EXTERNAL_HIDDEN_FAMILY_NOT_PASS:{family}")
            if not isinstance(ids, list) or len(ids) != len(set(ids)) or not all(isinstance(name, str) and name for name in ids):
                errors.append(f"EXTERNAL_HIDDEN_IDS_INVALID:{family}")
                ids = []
            if item.get("command_count") != len(ids) or item.get("passed_count") != item.get("command_count"):
                errors.append(f"EXTERNAL_HIDDEN_COUNTS_INVALID:{family}")
            for digest_key in ("manifest_sha256", "result_sha256"):
                digest = item.get(digest_key)
                if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
                    errors.append(f"EXTERNAL_HIDDEN_DIGEST_INVALID:{family}:{digest_key}")
    if value.get("outcome") != "PASS":
        errors.append("EXTERNAL_HIDDEN_OUTCOME_NOT_PASS")
    output = value.get("output_digest")
    if not isinstance(output, str) or _HEX64.fullmatch(output) is None:
        errors.append("EXTERNAL_HIDDEN_OUTPUT_DIGEST_INVALID")
    elif sha256_json({key: value[key] for key in value if key != "output_digest"}) != output:
        errors.append("EXTERNAL_HIDDEN_OUTPUT_DIGEST_MISMATCH")
    return errors


def evaluate_ci_execution_evidence(
    baseline: Mapping[str, Any], config: Mapping[str, Any], successful_test_ids: set[str], hidden_receipt: Mapping[str, Any],
    *, head_sha: str, test_receipt_sha256: str,
) -> dict[str, Any]:
    findings = validate_external_hidden_execution_receipt(hidden_receipt, expected_head=head_sha)
    families: dict[str, Any] = {}
    for family in q.BASELINE_FAMILIES:
        suffixes = config["families"][family]["adversarial_test_suffixes"]
        adversarial = sorted(suffix for suffix in suffixes if any(test_id.endswith(suffix) for test_id in successful_test_ids))
        hidden_family = hidden_receipt.get("families", {}).get(family, {})
        hidden_ids = hidden_family.get("command_ids", []) if isinstance(hidden_family, dict) else []
        required_hidden = baseline["families"][family]["min_hidden_holdouts"]
        required_adversarial = baseline["families"][family]["min_adversarial_tests"]
        if len(hidden_ids) < required_hidden:
            findings.append(f"HIDDEN_EXECUTION_EVIDENCE_BELOW_BASELINE:{family}")
        if len(adversarial) < required_adversarial:
            findings.append(f"ADVERSARIAL_EXECUTION_EVIDENCE_BELOW_BASELINE:{family}")
        families[family] = {"hidden_receipt_ids": list(hidden_ids), "hidden_count": len(hidden_ids), "required_hidden_count": required_hidden, "adversarial_test_ids": adversarial, "adversarial_count": len(adversarial), "required_adversarial_count": required_adversarial}
    value: dict[str, Any] = {
        "schema_version": 4, "control_id": "PROGRAMMING_QUALITY_EXECUTION_EVIDENCE", "exact_head": head_sha,
        "test_receipt_sha256": test_receipt_sha256, "hidden_execution_receipt_sha256": hidden_receipt.get("output_digest"),
        "external_broker_policy_id": hidden_receipt.get("broker_policy_id"), "families": families,
        "findings": sorted(set(findings)), "outcome": "FAIL" if findings else "PASS",
        "reason_code": "EXECUTION_EVIDENCE_INSUFFICIENT" if findings else "EXECUTION_EVIDENCE_BOUND_AND_SUFFICIENT",
    }
    value["output_digest"] = sha256_json(value)
    return value


def run_programming_quality_worker_hardened(
    repo_path: Path, spec: WorkerTaskSpec, client: Any, oracle: HiddenOracle, plan: q.QualityPlan,
    readback_manifest: ReadbackManifest, *, work_parent: Path | None = None,
) -> q.ProgrammingQualityWorkerResult:
    execution = plan.task_id
    if plan.task_id != spec.task_id or plan.base_head_sha != spec.base_head_sha:
        return v5._outer_receipt(plan, spec, [], None, status="BLOCKED", reason="QUALITY_PLAN_TASK_BINDING_MISMATCH", patch="")
    try:
        baseline = q.load_baseline(repo_path / "quality/programming_quality/baseline_v1.json")
    except ValueError as exc:
        return v5._outer_receipt(plan, spec, [], None, status="BLOCKED", reason=f"BASELINE_INVALID:{exc}", patch="")
    controls = [v2.evaluate_bound_risk_profile(plan, spec, oracle, execution_id=execution), hidden_contract_receipt(plan, oracle, baseline, execution_id=execution)]
    failed = next((item for item in controls if item["outcome"] in {"FAIL", "BLOCKED"}), None)
    if failed is not None:
        return v5._outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=failed["reason_code"], patch="")
    prestate = capture_readback_prestate(readback_manifest, plan, execution_id=execution)
    controls.append(prestate)
    if prestate["outcome"] in {"FAIL", "BLOCKED"}:
        return v5._outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=prestate["reason_code"], patch="")
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-aud24-v6-preflight-", dir=parent) as temporary:
            workspace = Path(temporary) / "fixture"
            create_disposable_workspace(repo_path, workspace, identity)
            fixture = run_canonical_fixture_preflight(workspace, plan, execution_id=execution)
    except WorkspaceError as exc:
        fixture = q._control_receipt("FIXTURE_PREFLIGHT_EXACT_MODULE_V6", task_id=plan.task_id, execution_id=execution, head_sha=plan.base_head_sha, input_digest=plan.sha256, outcome="BLOCKED", reason_code=str(exc))
    controls.append(fixture)
    if fixture["outcome"] != "PASS":
        return v5._outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=fixture["reason_code"], patch="")
    legacy = q.run_programming_quality_worker(repo_path, spec, client, oracle, plan, work_parent=work_parent, execution_id=execution)
    if legacy.receipt["status"] != "PASS":
        return v5._outer_receipt(plan, spec, controls, legacy, status=legacy.receipt["status"], reason=legacy.receipt["reason"], patch="")
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-aud24-v6-postgreen-", dir=parent) as temporary:
            candidate = Path(temporary) / "candidate"
            create_disposable_workspace(repo_path, candidate, identity)
            replay_cumulative_patch(candidate, legacy.patch)
            semantic = conservative_semantic_gate(candidate, plan, execution_id=execution)
    except WorkspaceError as exc:
        semantic = q._control_receipt("SEMANTIC_BEHAVIORAL_GUARD", task_id=plan.task_id, execution_id=execution, head_sha=plan.base_head_sha, input_digest=plan.sha256, outcome="BLOCKED", reason_code=str(exc))
    controls.append(semantic)
    if semantic["outcome"] in {"FAIL", "BLOCKED"}:
        return v5._outer_receipt(plan, spec, controls, legacy, status=semantic["outcome"], reason=semantic["reason_code"], patch="")
    readback = run_readback_gate(readback_manifest, plan, prestate, operation_receipt_sha256=legacy.receipt["receipt_sha256"], execution_id=execution)
    controls.append(readback)
    if readback["outcome"] in {"FAIL", "BLOCKED"}:
        return v5._outer_receipt(plan, spec, controls, legacy, status=readback["outcome"], reason=readback["reason_code"], patch="")
    return v5._outer_receipt(plan, spec, controls, legacy, status="PASS", reason="AUD24_V6_SEMANTIC_CAUSAL_GATE_PASSED", patch=legacy.patch)
