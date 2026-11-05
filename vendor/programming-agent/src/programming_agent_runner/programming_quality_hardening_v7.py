from __future__ import annotations

import ast
import re
from typing import Any, Mapping

from . import programming_quality as q
from . import programming_quality_hardening_v2 as v2
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v6 as v6
from .hashutil import sha256_json
from .worker_oracle import HiddenOracle

HIDDEN_EXECUTION_SCHEMA_VERSION = 4
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


_EFFECT_OBSERVER_PREFIX = "effect-observer:"


def _top_level_assignments(tree: ast.AST) -> list[tuple[str, ast.AST, int]]:
    if not isinstance(tree, ast.Module):
        return []
    values: list[tuple[str, ast.AST, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            values.append((node.targets[0].id, node.value, getattr(node, "lineno", 0)))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            values.append((node.target.id, node.value, getattr(node, "lineno", 0)))
    return values


def _declared_effect_observers(plan: q.QualityPlan) -> set[str]:
    observers: set[str] = set()
    for risk in plan.risk_profile:
        for binding in risk.get("coverage", []):
            ref = binding.get("ref") if isinstance(binding, dict) else None
            if not isinstance(ref, str) or not ref.startswith(_EFFECT_OBSERVER_PREFIX):
                continue
            observer = ref[len(_EFFECT_OBSERVER_PREFIX):].strip()
            if observer and all(part.isidentifier() for part in observer.split(".")):
                observers.add(observer)
    return observers


def _semantic_identity_values(positional: list[ast.expr], keywords: list[tuple[str, ast.expr]]) -> str | None:
    values: list[ast.expr] = [
        item for item in positional
        if not (isinstance(item, ast.Constant) and isinstance(item.value, bool))
    ]
    values.extend(
        ast.Tuple(elts=[ast.Constant(name), item], ctx=ast.Load())
        for name, item in keywords
        if not (isinstance(item, ast.Constant) and isinstance(item.value, bool))
    )
    if not values:
        return None
    return ast.dump(ast.Tuple(elts=values, ctx=ast.Load()), include_attributes=False)


def _thread_invocation(
    call: ast.Call,
    tree: ast.AST,
    plan: q.QualityPlan,
) -> tuple[str, str] | None:
    name = v3._call_name(call).lower()
    target_node: ast.AST | None = None
    positional: list[ast.expr] = []
    if name == "thread":
        args_node: ast.AST | None = None
        for keyword in call.keywords:
            if keyword.arg == "target":
                target_node = keyword.value
            elif keyword.arg == "args":
                args_node = keyword.value
        if not isinstance(args_node, (ast.Tuple, ast.List)):
            return None
        positional = list(args_node.elts)
    elif name == "submit" and call.args:
        target_node = call.args[0]
        positional = list(call.args[1:])
    else:
        return None
    reference = v6._canonical_reference(target_node, tree, plan)
    identity = _semantic_identity_values(positional, [])
    if reference is None or identity is None:
        return None
    return ".".join(reference), identity


def _iterable_multiplicity(node: ast.AST) -> int:
    return v6._iterable_multiplicity(node)


def _thread_collection(statement: ast.stmt, tree: ast.AST, plan: q.QualityPlan, entrypoints: set[str]) -> tuple[str, str, str, int] | None:
    if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
        return None
    collection = statement.targets[0].id
    value = statement.value
    if not isinstance(value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) or not isinstance(value.elt, ast.Call):
        return None
    invocation = _thread_invocation(value.elt, tree, plan)
    if invocation is None or invocation[0] not in entrypoints:
        return None
    variables = v6._comprehension_variables(value)
    if variables & v6._name_set(value.elt):
        return None
    multiplicity = 1
    for generator in value.generators:
        multiplicity *= _iterable_multiplicity(generator.iter)
    if multiplicity < 2:
        return None
    return collection, invocation[0], invocation[1], getattr(statement, "lineno", 0)


def _lifecycle_line(statement: ast.stmt, collection: str, method: str) -> int | None:
    def lifecycle_call(call: ast.Call, loop_var: str) -> bool:
        return (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == method
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == loop_var
            and not call.args
            and not call.keywords
        )

    if isinstance(statement, ast.For) and isinstance(statement.target, ast.Name) and isinstance(statement.iter, ast.Name):
        if statement.iter.id != collection or len(statement.body) != 1:
            return None
        body = statement.body[0]
        if isinstance(body, ast.Expr) and isinstance(body.value, ast.Call) and lifecycle_call(body.value, statement.target.id):
            return getattr(statement, "lineno", 0)
        return None
    if isinstance(statement, ast.Expr) and isinstance(statement.value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        comp = statement.value
        if not isinstance(comp.elt, ast.Call) or len(comp.generators) != 1:
            return None
        generator = comp.generators[0]
        if not isinstance(generator.target, ast.Name) or not isinstance(generator.iter, ast.Name) or generator.iter.id != collection:
            return None
        if lifecycle_call(comp.elt, generator.target.id):
            return getattr(statement, "lineno", 0)
    return None


def _concurrency_activity(
    tree: ast.AST, plan: q.QualityPlan, entrypoints: set[str]
) -> tuple[bool, int, int, str]:
    if not isinstance(tree, ast.Module):
        return False, 0, 0, ""
    for index, statement in enumerate(tree.body):
        collection = _thread_collection(statement, tree, plan, entrypoints)
        if collection is None:
            continue
        collection_name, _, identity, construct_line = collection
        start_line = next(
            (
                line
                for item in tree.body[index + 1 :]
                if (line := _lifecycle_line(item, collection_name, "start")) is not None
            ),
            None,
        )
        join_line = next(
            (
                line
                for item in tree.body[index + 1 :]
                if (line := _lifecycle_line(item, collection_name, "join")) is not None
            ),
            None,
        )
        if start_line is None or join_line is None or not (construct_line < start_line < join_line):
            continue
        return True, start_line, join_line, identity
    return False, 0, 0, ""


def _observer_signature(
    call: ast.Call,
    tree: ast.AST,
    plan: q.QualityPlan,
    entrypoints: set[str],
    declared_observers: set[str],
) -> tuple[str, str] | None:
    reference = v6._canonical_reference(call.func, tree, plan)
    if reference is None:
        return None
    name = ".".join(reference)
    if name in entrypoints or name not in declared_observers:
        return None
    args = ast.Tuple(
        elts=[*call.args, *[ast.Tuple(elts=[ast.Constant(item.arg), item.value], ctx=ast.Load()) for item in call.keywords if item.arg]],
        ctx=ast.Load(),
    )
    return name, ast.dump(args, include_attributes=False)


def _equality_assertion(tree: ast.AST, left_name: str, right_name: str) -> bool:
    for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert)):
        test = assertion.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        left, right = test.left, test.comparators[0]
        if isinstance(left, ast.Name) and isinstance(right, ast.Name) and {left.id, right.id} == {left_name, right_name}:
            return True
    return False


def _delta_assertion(tree: ast.AST, before_name: str, after_name: str) -> bool:
    for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert)):
        test = assertion.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        left, right = test.left, test.comparators[0]
        for delta, one in ((left, right), (right, left)):
            if not isinstance(one, ast.Constant) or one.value != 1:
                continue
            if (
                isinstance(delta, ast.BinOp)
                and isinstance(delta.op, ast.Sub)
                and isinstance(delta.left, ast.Name)
                and isinstance(delta.right, ast.Name)
                and delta.left.id == after_name
                and delta.right.id == before_name
            ):
                return True
        if (
            isinstance(left, ast.BinOp)
            and isinstance(left.op, ast.Add)
            and isinstance(left.left, ast.Name)
            and left.left.id == before_name
            and isinstance(left.right, ast.Constant)
            and left.right.value == 1
            and isinstance(right, ast.Name)
            and right.id == after_name
        ):
            return True
        if (
            isinstance(right, ast.BinOp)
            and isinstance(right.op, ast.Add)
            and isinstance(right.left, ast.Name)
            and right.left.id == before_name
            and isinstance(right.right, ast.Constant)
            and right.right.value == 1
            and isinstance(left, ast.Name)
            and left.id == after_name
        ):
            return True
    return False


def _observations(
    tree: ast.AST,
    plan: q.QualityPlan,
    entrypoints: set[str],
    declared_observers: set[str],
    *,
    minimum_line: int | None = None,
    maximum_line: int | None = None,
) -> dict[tuple[str, str], list[tuple[str, int]]]:
    result: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for name, value, line in _top_level_assignments(tree):
        if minimum_line is not None and line <= minimum_line:
            continue
        if maximum_line is not None and line >= maximum_line:
            continue
        if not isinstance(value, ast.Call):
            continue
        signature = _observer_signature(value, tree, plan, entrypoints, declared_observers)
        if signature is not None:
            result.setdefault(signature, []).append((name, line))
    return result


def _stable_names(tree: ast.AST, items: list[tuple[str, int]]) -> set[str]:
    stable: set[str] = set()
    for index, (left, _) in enumerate(items):
        for right, _ in items[index + 1 :]:
            if _equality_assertion(tree, left, right):
                stable.update((left, right))
    return stable


def _module_window_isolated(
    tree: ast.AST,
    plan: q.QualityPlan,
    entrypoints: set[str],
    declared_observers: set[str],
    *,
    start_line: int,
    end_line: int,
) -> bool:
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        line = getattr(call, "lineno", 0)
        if line < start_line or line > end_line:
            continue
        reference = v6._canonical_reference(call.func, tree, plan)
        if reference is None:
            continue
        name = ".".join(reference)
        if name in entrypoints or name in declared_observers:
            continue
        return False
    return True


def _effect_transition_proven(
    tree: ast.AST,
    plan: q.QualityPlan,
    entrypoints: set[str],
    *,
    first_effect_line: int,
    last_effect_line: int,
) -> bool:
    declared = _declared_effect_observers(plan)
    if not declared:
        return False
    before = _observations(tree, plan, entrypoints, declared, maximum_line=first_effect_line)
    after = _observations(tree, plan, entrypoints, declared, minimum_line=last_effect_line)
    for signature in before.keys() & after.keys():
        stable_before = _stable_names(tree, before[signature])
        stable_after = _stable_names(tree, after[signature])
        if not stable_before or not stable_after:
            continue
        before_lines = dict(before[signature])
        after_lines = dict(after[signature])
        for before_name in stable_before:
            for after_name in stable_after:
                if not _delta_assertion(tree, before_name, after_name):
                    continue
                if _module_window_isolated(
                    tree,
                    plan,
                    entrypoints,
                    declared,
                    start_line=min(before_lines[name] for name in stable_before),
                    end_line=max(after_lines[name] for name in stable_after),
                ):
                    return True
    return False


def _failure_sentinel_proven(attempt: ast.Try, tree: ast.AST) -> bool:
    try_line = getattr(attempt, "lineno", 0)
    end_line = getattr(attempt, "end_lineno", try_line)
    initial_false = {
        name
        for name, value, line in _top_level_assignments(tree)
        if line < try_line and isinstance(value, ast.Constant) and value.value is False
    }
    if not initial_false:
        return False
    set_true: set[str] = set()
    for handler in attempt.handlers:
        for statement in handler.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                if statement.targets[0].id in initial_false and isinstance(statement.value, ast.Constant) and statement.value.value is True:
                    set_true.add(statement.targets[0].id)
            elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.target.id in initial_false:
                if isinstance(statement.value, ast.Constant) and statement.value.value is True:
                    set_true.add(statement.target.id)
    if not set_true:
        return False
    if not isinstance(tree, ast.Module):
        return False
    for assertion in (node for node in tree.body if isinstance(node, ast.Assert)):
        if getattr(assertion, "lineno", 0) <= end_line:
            continue
        test = assertion.test
        if isinstance(test, ast.Name) and test.id in set_true:
            return True
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Is):
            if isinstance(test.left, ast.Name) and test.left.id in set_true:
                rhs = test.comparators[0]
                if isinstance(rhs, ast.Constant) and rhs.value is True:
                    return True
    return False


def _safe_argument(node: ast.AST) -> bool:
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_safe_argument(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all((key is None or _safe_argument(key)) and _safe_argument(value) for key, value in zip(node.keys, node.values))
    return False


def _direct_target_call(
    statement: ast.stmt,
    tree: ast.AST,
    plan: q.QualityPlan,
    entrypoints: set[str],
) -> tuple[ast.Call, str, str] | None:
    value: ast.AST | None = None
    if isinstance(statement, ast.Expr):
        value = statement.value
    elif isinstance(statement, ast.Assign):
        value = statement.value
    elif isinstance(statement, ast.AnnAssign):
        value = statement.value
    if not isinstance(value, ast.Call):
        return None
    reference = v6._canonical_reference(value.func, tree, plan)
    if reference is None or ".".join(reference) not in entrypoints:
        return None
    if not all(_safe_argument(item) for item in value.args):
        return None
    if not all(item.arg is not None and _safe_argument(item.value) for item in value.keywords):
        return None
    identity = _semantic_identity_values(
        list(value.args),
        [(item.arg, item.value) for item in value.keywords if item.arg is not None],
    )
    if identity is None:
        return None
    return value, ".".join(reference), identity


def _partial_failure_activity(
    tree: ast.AST, plan: q.QualityPlan, entrypoints: set[str]
) -> tuple[bool, int, int, int]:
    if not isinstance(tree, ast.Module):
        return False, 0, 0, 0
    for index, statement in enumerate(tree.body):
        if not isinstance(statement, ast.Try) or not statement.handlers or len(statement.body) != 1:
            continue
        if not _failure_sentinel_proven(statement, tree):
            continue
        inside = _direct_target_call(statement.body[0], tree, plan, entrypoints)
        if inside is None:
            continue
        end_line = getattr(statement, "end_lineno", getattr(statement, "lineno", 0))
        for retry_statement in tree.body[index + 1 :]:
            retry = _direct_target_call(retry_statement, tree, plan, entrypoints)
            if retry is None or retry[1] != inside[1] or retry[2] != inside[2]:
                continue
            return True, getattr(inside[0], "lineno", 0), end_line, getattr(retry[0], "lineno", 0)
    return False, 0, 0, 0


def _partial_failure_effect_proven(
    tree: ast.AST,
    plan: q.QualityPlan,
    entrypoints: set[str],
    *,
    target_line: int,
    try_end_line: int,
    retry_line: int,
) -> bool:
    declared = _declared_effect_observers(plan)
    if not declared:
        return False
    before = _observations(tree, plan, entrypoints, declared, maximum_line=target_line)
    failed = _observations(tree, plan, entrypoints, declared, minimum_line=try_end_line, maximum_line=retry_line)
    retried = _observations(tree, plan, entrypoints, declared, minimum_line=retry_line)
    for signature in before.keys() & failed.keys() & retried.keys():
        stable_before = _stable_names(tree, before[signature])
        stable_failed = _stable_names(tree, failed[signature])
        stable_retried = _stable_names(tree, retried[signature])
        if not stable_before or not stable_failed or not stable_retried:
            continue
        before_lines = dict(before[signature])
        retried_lines = dict(retried[signature])
        for before_name in stable_before:
            for failed_name in stable_failed:
                if not _delta_assertion(tree, before_name, failed_name):
                    continue
                for retry_name in stable_retried:
                    if not _equality_assertion(tree, failed_name, retry_name):
                        continue
                    if _module_window_isolated(
                        tree,
                        plan,
                        entrypoints,
                        declared,
                        start_line=min(before_lines[name] for name in stable_before),
                        end_line=max(retried_lines[name] for name in stable_retried),
                    ):
                        return True
    return False


def validate_test007_command_semantics(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    if oracle.family != v2.SEMANTIC_HIDDEN_FAMILY:
        return []
    entrypoints = v6._declared_entrypoints(plan)
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
            causal, first_line, last_line, _ = _concurrency_activity(tree, plan, entrypoints)
            if not causal:
                findings.append("HIDDEN_HOLDOUT_SAME_IDENTITY_CONCURRENCY_UNPROVEN")
            elif not _effect_transition_proven(
                tree,
                plan,
                entrypoints,
                first_effect_line=first_line,
                last_effect_line=last_line,
            ):
                findings.append("HIDDEN_HOLDOUT_CAUSAL_EFFECT_TRANSITION_UNPROVEN")
        else:
            causal, target_line, try_end_line, retry_line = _partial_failure_activity(tree, plan, entrypoints)
            if not causal:
                findings.append("HIDDEN_HOLDOUT_PARTIAL_FAILURE_OBSERVATION_UNPROVEN")
            elif not _partial_failure_effect_proven(
                tree,
                plan,
                entrypoints,
                target_line=target_line,
                try_end_line=try_end_line,
                retry_line=retry_line,
            ):
                findings.append("HIDDEN_HOLDOUT_CAUSAL_EFFECT_TRANSITION_UNPROVEN")
    return sorted(set(findings))


def validate_external_hidden_execution_receipt(value: Any, *, expected_head: str) -> list[str]:
    fields = {
        "schema_version",
        "control_id",
        "exact_head",
        "broker",
        "broker_version",
        "broker_policy_id",
        "challenge_id",
        "broker_response_sha256",
        "generator_mode",
        "generation_commitment",
        "provenance_guard_sha256",
        "families",
        "outcome",
        "reason_code",
        "output_digest",
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
    if value.get("broker") != "supabase-edge" or value.get("broker_version") != "2":
        errors.append("EXTERNAL_HIDDEN_BROKER_INVALID")
    if value.get("generator_mode") != "runtime-randomized-grammar-v2":
        errors.append("EXTERNAL_HIDDEN_GENERATOR_MODE_INVALID")
    for key in (
        "broker_policy_id",
        "challenge_id",
        "broker_response_sha256",
        "generation_commitment",
        "provenance_guard_sha256",
    ):
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
    return sorted(set(errors))


def evaluate_ci_execution_evidence(
    baseline: Mapping[str, Any],
    config: Mapping[str, Any],
    successful_test_ids: set[str],
    hidden_receipt: Mapping[str, Any],
    *,
    head_sha: str,
    test_receipt_sha256: str,
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
        families[family] = {
            "hidden_receipt_ids": list(hidden_ids),
            "hidden_count": len(hidden_ids),
            "required_hidden_count": required_hidden,
            "adversarial_test_ids": adversarial,
            "adversarial_count": len(adversarial),
            "required_adversarial_count": required_adversarial,
        }
    value: dict[str, Any] = {
        "schema_version": 5,
        "control_id": "PROGRAMMING_QUALITY_EXECUTION_EVIDENCE",
        "exact_head": head_sha,
        "test_receipt_sha256": test_receipt_sha256,
        "hidden_execution_receipt_sha256": hidden_receipt.get("output_digest"),
        "external_broker_policy_id": hidden_receipt.get("broker_policy_id"),
        "external_generation_commitment": hidden_receipt.get("generation_commitment"),
        "families": families,
        "findings": sorted(set(findings)),
        "outcome": "FAIL" if findings else "PASS",
        "reason_code": "EXECUTION_EVIDENCE_INSUFFICIENT" if findings else "EXECUTION_EVIDENCE_BOUND_AND_SUFFICIENT",
    }
    value["output_digest"] = sha256_json(value)
    return value
