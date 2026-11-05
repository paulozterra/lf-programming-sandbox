from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import programming_quality as q
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v6 as v6
from . import programming_quality_hardening_v7 as v7
from .worker_oracle import HiddenOracle

_EFFECT_OBSERVER_PREFIX = "effect-observer:"
_MUTATING_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "insert",
    "pop",
    "remove",
    "setdefault",
    "update",
}

AccessPath = tuple[str, ...]


@dataclass(frozen=True)
class _HelperCall:
    name: str
    positional: tuple[ast.expr, ...]
    keywords: tuple[tuple[str, ast.expr], ...]


def _module_name(relative: str) -> str:
    parts = list(Path(relative).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _module_paths(plan: q.QualityPlan, repo_path: Path) -> dict[str, Path]:
    root = repo_path.resolve()
    result: dict[str, Path] = {}
    for relative in plan.semantic_paths:
        candidate = (root / relative).resolve()
        if candidate != root and not candidate.is_relative_to(root):
            continue
        module = _module_name(relative)
        if module:
            result[module] = candidate
    return result


def _top_level_state(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for statement in tree.body:
        targets: Iterable[ast.AST] = ()
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = (statement.target,)
        for target in targets:
            names.update(item.id for item in ast.walk(target) if isinstance(item, ast.Name))
    return names


def _literal_subscript(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)) and not isinstance(node.value, bool):
        return f"[{node.value!r}]"
    if isinstance(node, ast.Constant) and node.value is None:
        return "[None]"
    return None


def _structural_path(node: ast.AST | None) -> AccessPath | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        prefix = _structural_path(node.value)
        return None if prefix is None else (*prefix, f".{node.attr}")
    if isinstance(node, ast.Subscript):
        prefix = _structural_path(node.value)
        item = _literal_subscript(node.slice)
        if prefix is None or item is None:
            return None
        return (*prefix, item)
    return None


def _path_is_extended_by_parent(node: ast.AST, parent: ast.AST | None) -> bool:
    return (
        isinstance(parent, ast.Attribute)
        and parent.value is node
        or isinstance(parent, ast.Subscript)
        and parent.value is node
    )


def _function_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    return tuple(
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
        )
    )


def _simple_aliases(function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, AccessPath]:
    aliases: dict[str, AccessPath] = {}
    for statement in function.body:
        target: ast.Name | None = None
        value: ast.AST | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            target = statement.targets[0]
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            target = statement.target
            value = statement.value
        if target is None or value is None:
            continue
        path = _structural_path(value)
        if path is None:
            continue
        if path[0] in aliases:
            path = (*aliases[path[0]], *path[1:])
        aliases[target.id] = path
    return aliases


def _resolve_alias(path: AccessPath, aliases: dict[str, AccessPath]) -> AccessPath:
    seen: set[str] = set()
    current = path
    while current and current[0] in aliases and current[0] not in seen:
        seen.add(current[0])
        current = (*aliases[current[0]], *current[1:])
    return current


def _direct_accesses(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    local_functions: set[str],
) -> tuple[set[AccessPath], set[AccessPath], tuple[_HelperCall, ...]]:
    aliases = _simple_aliases(function)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(function):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    reads: set[AccessPath] = set()
    writes: set[AccessPath] = set()
    helpers: list[_HelperCall] = []

    for node in ast.walk(function):
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)) and isinstance(getattr(node, "ctx", None), ast.Load):
            path = _structural_path(node)
            if path is not None and not _path_is_extended_by_parent(node, parents.get(node)):
                reads.add(_resolve_alias(path, aliases))

        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        elif isinstance(node, ast.AugAssign):
            targets.append(node.target)
        elif isinstance(node, ast.Delete):
            targets.extend(node.targets)
        for target in targets:
            path = _structural_path(target)
            if path is not None:
                writes.add(path if len(path) == 1 else _resolve_alias(path, aliases))

        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in local_functions:
            helpers.append(
                _HelperCall(
                    node.func.id,
                    tuple(node.args),
                    tuple((item.arg, item.value) for item in node.keywords if item.arg is not None),
                )
            )
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        receiver = _structural_path(node.func.value)
        if receiver is None:
            continue
        receiver = _resolve_alias(receiver, aliases)
        if node.func.attr.lower() in _MUTATING_METHODS:
            writes.add(receiver)
        else:
            reads.add(receiver)

    return reads, writes, tuple(helpers)


def _substitute_path(path: AccessPath, parameter_map: dict[str, AccessPath]) -> AccessPath:
    replacement = parameter_map.get(path[0])
    if replacement is None:
        return path
    return (*replacement, *path[1:])


def _helper_parameter_map(
    helper: ast.FunctionDef | ast.AsyncFunctionDef,
    call: _HelperCall,
) -> dict[str, AccessPath]:
    parameters = _function_parameters(helper)
    mapping: dict[str, AccessPath] = {}
    for name, value in zip(parameters, call.positional):
        path = _structural_path(value)
        if path is not None:
            mapping[name] = path
    for name, value in call.keywords:
        if name not in parameters:
            continue
        path = _structural_path(value)
        if path is not None:
            mapping[name] = path
    return mapping


def _function_accesses(
    name: str,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    *,
    seen: set[str] | None = None,
) -> tuple[set[AccessPath], set[AccessPath]]:
    if seen is None:
        seen = set()
    if name in seen or name not in functions:
        return set(), set()
    seen = {*seen, name}
    reads, writes, helpers = _direct_accesses(functions[name], local_functions=set(functions))
    for call in helpers:
        helper = functions.get(call.name)
        if helper is None:
            continue
        child_reads, child_writes = _function_accesses(call.name, functions, seen=seen)
        parameter_map = _helper_parameter_map(helper, call)
        reads.update(_substitute_path(path, parameter_map) for path in child_reads)
        writes.update(_substitute_path(path, parameter_map) for path in child_writes)
    return reads, writes


def _module_state_paths(paths: set[AccessPath], module_state: set[str]) -> set[AccessPath]:
    return {path for path in paths if path and path[0] in module_state}


def _source_causality_proven(
    plan: q.QualityPlan,
    repo_path: Path,
    *,
    observer: str,
    entrypoints: set[str],
) -> bool:
    observer_parts = observer.rsplit(".", 1)
    if len(observer_parts) != 2:
        return False
    module, observer_name = observer_parts
    module_path = _module_paths(plan, repo_path).get(module)
    if module_path is None or not module_path.is_file():
        return False
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return False
    functions = {
        item.name: item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if observer_name not in functions:
        return False
    module_state = _top_level_state(tree)
    observer_reads, observer_writes = _function_accesses(observer_name, functions)
    observer_reads = _module_state_paths(observer_reads, module_state)
    observer_writes = _module_state_paths(observer_writes, module_state)
    if not observer_reads or observer_writes:
        return False

    for entrypoint in entrypoints:
        parts = entrypoint.rsplit(".", 1)
        if len(parts) != 2 or parts[0] != module or parts[1] not in functions:
            continue
        _, target_writes = _function_accesses(parts[1], functions)
        target_writes = _module_state_paths(target_writes, module_state)
        if target_writes & observer_reads:
            return True
    return False


def _semantic_modules(plan: q.QualityPlan) -> set[tuple[str, ...]]:
    return {tuple(module.split(".")) for module in v6._exact_modules(plan)}


def _bound_reference(node: ast.AST | None, tree: ast.Module, plan: q.QualityPlan) -> tuple[str, ...] | None:
    """Resolve an imported semantic reference, preserving unknown subscripts as a marker."""
    if isinstance(node, ast.Name):
        parts: tuple[str, ...] = (node.id,)
    elif isinstance(node, ast.Attribute):
        prefix = _bound_reference(node.value, tree, plan)
        if prefix is None:
            raw = v6._dotted(node)
            if raw is None:
                return None
            parts = raw
        else:
            return (*prefix, node.attr)
    elif isinstance(node, ast.Subscript):
        prefix = _bound_reference(node.value, tree, plan)
        return None if prefix is None else (*prefix, "[*]")
    else:
        return None

    bindings, _ = v6._import_bindings(tree, plan)
    replacement = bindings.get(parts[0])
    return (*replacement, *parts[1:]) if replacement is not None else parts


def _semantic_reference(node: ast.AST | None, tree: ast.Module, plan: q.QualityPlan) -> tuple[str, ...] | None:
    reference = _bound_reference(node, tree, plan)
    if reference is None:
        return None
    for module in _semantic_modules(plan):
        if len(reference) >= len(module) and reference[: len(module)] == module:
            return reference
    return None


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    result: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            result[child] = parent
    return result


def _allowed_semantic_use(
    node: ast.AST,
    reference: tuple[str, ...],
    parents: dict[ast.AST, ast.AST],
    *,
    entrypoints: set[str],
    observers: set[str],
) -> bool:
    dotted = ".".join(reference)
    parent = parents.get(node)
    if dotted in observers:
        return isinstance(parent, ast.Call) and parent.func is node
    if dotted not in entrypoints:
        return False
    if isinstance(parent, ast.Call) and parent.func is node:
        return True
    if isinstance(parent, ast.keyword) and parent.arg == "target" and parent.value is node:
        call = parents.get(parent)
        return isinstance(call, ast.Call) and v3._call_name(call).lower() == "thread"
    if isinstance(parent, ast.Call) and parent.args and parent.args[0] is node:
        return v3._call_name(parent).lower() == "submit"
    return False


def _holdout_unsafe_semantic_access(tree: ast.Module, plan: q.QualityPlan) -> bool:
    """Fail closed on semantic-module access outside exact target/observer use.

    This intentionally reasons from the semantic module boundary rather than from a
    growing deny-list of reflection primitives. Therefore getattr/vars/__dict__,
    setattr/delattr, dynamic subscripts, aliases and future reflection helpers are
    rejected as soon as they receive or expose the semantic module/state object.
    """
    entrypoints = v6._declared_entrypoints(plan)
    observers = v7._declared_effect_observers(plan)
    parents = _parent_map(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            continue
        if _path_is_extended_by_parent(node, parents.get(node)):
            continue
        reference = _semantic_reference(node, tree, plan)
        if reference is None:
            continue
        if _allowed_semantic_use(node, reference, parents, entrypoints=entrypoints, observers=observers):
            continue
        return True
    return False


def _holdout_direct_state_mutation(tree: ast.Module, plan: q.QualityPlan) -> bool:
    # Structural fail-closed boundary: any semantic access other than exact target /
    # read-only observer exercise is forbidden, so reflective aliases cannot escape.
    return _holdout_unsafe_semantic_access(tree, plan)


def _holdout_mutation_findings(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    findings: list[str] = []
    for command in oracle.commands:
        tree = v3._inline_python(command)
        if not isinstance(tree, ast.Module):
            continue
        if _holdout_direct_state_mutation(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_DIRECT_SEMANTIC_STATE_MUTATION:{command.name}")
    return sorted(set(findings))


def _source_bound_plan(plan: q.QualityPlan, repo_path: Path) -> q.QualityPlan:
    entrypoints = v6._declared_entrypoints(plan)
    allowed = {
        observer
        for observer in v7._declared_effect_observers(plan)
        if _source_causality_proven(plan, repo_path, observer=observer, entrypoints=entrypoints)
    }
    filtered_risks: list[dict[str, object]] = []
    for risk in plan.risk_profile:
        item = dict(risk)
        coverage: list[dict[str, str]] = []
        for binding in risk.get("coverage", []):
            if not isinstance(binding, dict):
                continue
            ref = binding.get("ref")
            if isinstance(ref, str) and ref.startswith(_EFFECT_OBSERVER_PREFIX):
                observer = ref[len(_EFFECT_OBSERVER_PREFIX):].strip()
                if observer not in allowed:
                    continue
            coverage.append(dict(binding))
        item["coverage"] = coverage
        filtered_risks.append(item)
    return q.QualityPlan(
        plan.task_id,
        plan.base_head_sha,
        tuple(filtered_risks),
        plan.fixture_preflight_commands,
        plan.semantic_paths,
        plan.sha256,
    )


def validate_test007_command_semantics(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    *,
    repo_path: Path,
) -> list[str]:
    """AUD24 V8: exact causal binding plus fail-closed semantic holdout isolation."""
    source_bound = _source_bound_plan(plan, repo_path)
    findings = v7.validate_test007_command_semantics(source_bound, oracle)
    findings.extend(_holdout_mutation_findings(source_bound, oracle))
    if v7._declared_effect_observers(plan) and not v7._declared_effect_observers(source_bound):
        findings.append("HIDDEN_HOLDOUT_EFFECT_OBSERVER_SOURCE_CAUSALITY_UNPROVEN")
    return sorted(set(findings))
