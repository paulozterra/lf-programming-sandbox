from __future__ import annotations

import ast
from pathlib import Path

from . import programming_quality as q
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v6 as v6
from . import programming_quality_hardening_v7 as v7
from . import programming_quality_hardening_v8 as v8
from .worker_oracle import HiddenOracle

_ALLOWED_INFRA_MODULES = {"threading", "concurrent.futures"}
_ALLOWED_INFRA_CALL_REFERENCES = {
    ("threading", "Thread"),
    ("concurrent", "futures", "ThreadPoolExecutor"),
    ("concurrent", "futures", "as_completed"),
    ("concurrent", "futures", "wait"),
}
_ALLOWED_LOCAL_ORCHESTRATION_METHODS = {"join", "result", "shutdown", "start", "submit"}


def _semantic_modules(plan: q.QualityPlan) -> set[str]:
    return v6._exact_modules(plan)


def _import_surface_safe(tree: ast.Module, plan: q.QualityPlan) -> bool:
    semantic = _semantic_modules(plan)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in semantic and alias.name not in _ALLOWED_INFRA_MODULES:
                    return False
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _ALLOWED_INFRA_MODULES:
                continue
            if module in semantic:
                continue
            if any(f"{module}.{alias.name}" in semantic for alias in node.names if alias.name != "*"):
                continue
            return False
    return True


def _definition_surface_safe(tree: ast.Module) -> bool:
    return not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda))
        for node in ast.walk(tree)
    )


def _infra_import_bindings(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    bindings: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in _ALLOWED_INFRA_MODULES:
                    continue
                parts = tuple(alias.name.split("."))
                bindings[alias.asname or parts[0]] = parts if alias.asname else (parts[0],)
        elif isinstance(node, ast.ImportFrom) and node.module in _ALLOWED_INFRA_MODULES:
            module = tuple(node.module.split("."))
            for alias in node.names:
                if alias.name == "*":
                    continue
                bindings[alias.asname or alias.name] = (*module, alias.name)
    return bindings


def _infra_reference(
    node: ast.AST | None,
    bindings: dict[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        prefix = _infra_reference(node.value, bindings)
        return None if prefix is None else (*prefix, node.attr)
    if isinstance(node, ast.Subscript):
        prefix = _infra_reference(node.value, bindings)
        return None if prefix is None else (*prefix, "[*]")
    return None


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _local_value_names(tree: ast.Module) -> set[str]:
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    names.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and isinstance(node.name, str)
    )
    return names


def _root_expression(node: ast.AST) -> ast.AST:
    current = node
    while isinstance(current, (ast.Attribute, ast.Subscript)):
        current = current.value
    return current


def _name_rebound(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == name:
            return True
    return False


def _binding_surface_safe(tree: ast.Module, plan: q.QualityPlan) -> bool:
    semantic_bindings = set(v6._import_bindings(tree, plan)[0])
    infra_bindings = set(_infra_import_bindings(tree))
    protected_bindings = semantic_bindings | infra_bindings | {"range"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in protected_bindings:
            return False
        if isinstance(node, ast.ExceptHandler) and isinstance(node.name, str) and node.name in protected_bindings:
            return False
    return True


def _semantic_reference_sets(plan: q.QualityPlan) -> set[str]:
    return v6._declared_entrypoints(plan) | v7._declared_effect_observers(plan)


def _semantic_result_expression_tainted(
    node: ast.AST,
    *,
    tree: ast.Module,
    plan: q.QualityPlan,
    tainted_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tainted_names
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        return _semantic_result_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            tainted_names=tainted_names,
        )
    if isinstance(node, ast.Call):
        reference = v6._canonical_reference(node.func, tree, plan)
        if reference is not None and ".".join(reference) in _semantic_reference_sets(plan):
            return True
        return _semantic_result_expression_tainted(
            node.func,
            tree=tree,
            plan=plan,
            tainted_names=tainted_names,
        )
    return False


def _semantic_result_aliases(tree: ast.Module, plan: q.QualityPlan) -> set[str]:
    aliases: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            target: ast.Name | None = None
            value: ast.AST | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target, value = node.target, node.value
            if target is None or value is None or target.id in aliases:
                continue
            if _semantic_result_expression_tainted(
                value,
                tree=tree,
                plan=plan,
                tainted_names=aliases,
            ):
                aliases.add(target.id)
                changed = True
    return aliases


def _semantic_result_navigation_unsafe(tree: ast.Module, plan: q.QualityPlan) -> bool:
    aliases = _semantic_result_aliases(tree, plan)
    if not aliases:
        return False
    semantic_references = _semantic_reference_sets(plan)
    parents = _parent_map(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            reference = v6._canonical_reference(node.func, tree, plan)
            if reference is not None and ".".join(reference) in semantic_references:
                continue
            if _semantic_result_expression_tainted(
                node.func,
                tree=tree,
                plan=plan,
                tainted_names=aliases,
            ):
                return True
            continue
        if not isinstance(node, (ast.Attribute, ast.Subscript)):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Call) and parent.func is node:
            reference = v6._canonical_reference(node, tree, plan)
            if reference is not None and ".".join(reference) in semantic_references:
                continue
        if _semantic_result_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            tainted_names=aliases,
        ):
            return True
    return False


def _local_orchestration_method(
    node: ast.AST,
    *,
    local_values: set[str],
    semantic_bindings: set[str],
    infra_bindings: set[str],
) -> bool:
    if not isinstance(node, ast.Attribute) or node.attr.lower() not in _ALLOWED_LOCAL_ORCHESTRATION_METHODS:
        return False
    root = _root_expression(node)
    return (
        isinstance(root, ast.Name)
        and root.id in local_values
        and root.id not in semantic_bindings
        and root.id not in infra_bindings
    )


def _call_surface_safe(tree: ast.Module, plan: q.QualityPlan) -> bool:
    entrypoints = v6._declared_entrypoints(plan)
    observers = v7._declared_effect_observers(plan)
    semantic_bindings = set(v6._import_bindings(tree, plan)[0])
    infra_bindings_map = _infra_import_bindings(tree)
    infra_bindings = set(infra_bindings_map)
    local_values = _local_value_names(tree)

    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        reference = v6._canonical_reference(call.func, tree, plan)
        if reference is not None and ".".join(reference) in entrypoints | observers:
            continue

        infra_reference = _infra_reference(call.func, infra_bindings_map)
        invocation = v6._thread_invocation(call, tree, plan)
        if invocation is not None and invocation[0] in entrypoints:
            name = v3._call_name(call).lower()
            if name == "thread" and infra_reference == ("threading", "Thread"):
                continue
            if name == "submit" and _local_orchestration_method(
                call.func,
                local_values=local_values,
                semantic_bindings=semantic_bindings,
                infra_bindings=infra_bindings,
            ):
                continue

        if infra_reference in _ALLOWED_INFRA_CALL_REFERENCES:
            continue

        if isinstance(call.func, ast.Name) and call.func.id == "range" and not _name_rebound(tree, "range"):
            continue

        if _local_orchestration_method(
            call.func,
            local_values=local_values,
            semantic_bindings=semantic_bindings,
            infra_bindings=infra_bindings,
        ):
            continue
        return False
    return True


def _infrastructure_surface_safe(tree: ast.Module) -> bool:
    bindings = _infra_import_bindings(tree)
    if not bindings:
        return True
    parents = _parent_map(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            continue
        lookup_parent = parents.get(node)
        if isinstance(lookup_parent, (ast.Attribute, ast.Subscript)) and lookup_parent.value is node:
            continue
        reference = _infra_reference(node, bindings)
        if reference is None:
            continue
        if reference in _ALLOWED_INFRA_CALL_REFERENCES:
            continue
        return False
    return True


def _reference_surface_safe(tree: ast.Module, plan: q.QualityPlan) -> bool:
    entrypoints = v6._declared_entrypoints(plan)
    observers = v7._declared_effect_observers(plan)
    semantic_bindings = v6._import_bindings(tree, plan)[0]
    infra_bindings = _infra_import_bindings(tree)
    local_values = _local_value_names(tree)
    parents = _parent_map(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            infra = _infra_reference(node, infra_bindings)
            if infra is not None and infra not in _ALLOWED_INFRA_CALL_REFERENCES:
                return False
            root = _root_expression(node)
            if isinstance(root, ast.Name):
                if root.id in semantic_bindings or root.id in infra_bindings:
                    return False
                if root.id not in local_values:
                    return False
            continue

        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.ctx, ast.Load):
            return False
        lookup_parent = parents.get(node)
        if isinstance(lookup_parent, ast.Attribute) and lookup_parent.value is node:
            continue

        semantic = v6._canonical_reference(node, tree, plan)
        if semantic is not None and ".".join(semantic) in entrypoints | observers:
            continue

        infra = _infra_reference(node, infra_bindings)
        if infra in _ALLOWED_INFRA_CALL_REFERENCES:
            continue

        root = _root_expression(node)
        if isinstance(root, ast.Name) and root.id in local_values:
            if node.attr.startswith("__"):
                return False
            continue
        return False
    return True


def _observer_result_aliases(tree: ast.Module, plan: q.QualityPlan) -> set[str]:
    observers = v7._declared_effect_observers(plan)
    aliases: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            target: ast.Name | None = None
            value: ast.AST | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target, value = node.target, node.value
            if target is None or value is None or target.id in aliases:
                continue
            carries_observer = False
            if isinstance(value, ast.Call):
                reference = v6._canonical_reference(value.func, tree, plan)
                carries_observer = reference is not None and ".".join(reference) in observers
            elif isinstance(value, (ast.Name, ast.Attribute, ast.Subscript)):
                root: ast.AST = value
                while isinstance(root, (ast.Attribute, ast.Subscript)):
                    root = root.value
                carries_observer = isinstance(root, ast.Name) and root.id in aliases
            if carries_observer:
                aliases.add(target.id)
                changed = True
    return aliases


def _observer_result_mutated(tree: ast.Module, plan: q.QualityPlan) -> bool:
    aliases = _observer_result_aliases(tree, plan)
    if not aliases:
        return False
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        elif isinstance(node, ast.AugAssign):
            targets.append(node.target)
        elif isinstance(node, ast.Delete):
            targets.extend(node.targets)
        elif isinstance(node, ast.NamedExpr):
            targets.append(node.target)
        for target in targets:
            root: ast.AST = target
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if not isinstance(root, ast.Name) or root.id not in aliases:
                continue
            if isinstance(node, (ast.AugAssign, ast.Delete, ast.NamedExpr)):
                return True
            if not isinstance(target, ast.Name):
                return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            call_root: ast.AST = node.func.value
            while isinstance(call_root, (ast.Attribute, ast.Subscript)):
                call_root = call_root.value
            if isinstance(call_root, ast.Name) and call_root.id in aliases:
                return True
    return False


def _closed_holdout_surface_findings(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    findings: list[str] = []
    for command in oracle.commands:
        tree = v3._inline_python(command)
        if not isinstance(tree, ast.Module):
            continue
        if not _import_surface_safe(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_IMPORT_SURFACE_UNSAFE:{command.name}")
        if not _definition_surface_safe(tree):
            findings.append(f"HIDDEN_HOLDOUT_DEFINITION_SURFACE_UNSAFE:{command.name}")
        if not _binding_surface_safe(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_BINDING_SURFACE_UNSAFE:{command.name}")
        if not _infrastructure_surface_safe(tree):
            findings.append(f"HIDDEN_HOLDOUT_INFRA_SURFACE_UNSAFE:{command.name}")
        if not _reference_surface_safe(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_REFERENCE_SURFACE_UNSAFE:{command.name}")
        if not _call_surface_safe(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_CALL_SURFACE_UNSAFE:{command.name}")
        if _semantic_result_navigation_unsafe(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_SEMANTIC_RETURN_TAINT:{command.name}")
        if _observer_result_mutated(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_OBSERVER_RESULT_MUTATION:{command.name}")
    return sorted(set(findings))


def validate_test007_command_semantics(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    *,
    repo_path: Path,
) -> list[str]:
    """AUD24 V9: V8 causal proof plus a bounded TEST-007 proof language.

    Hidden code may call only the declared semantic target/observer and provenance-
    bound concurrency primitives. Local test data may use normal indexing and
    non-dunder attribute reads; semantic modules, reflective global roots,
    infrastructure internals, imported-binding rebinding, arbitrary imports,
    executable definitions, semantic-return object-graph navigation, and observer-
    result mutation fail closed.
    """
    findings = v8.validate_test007_command_semantics(plan, oracle, repo_path=repo_path)
    findings.extend(_closed_holdout_surface_findings(plan, oracle))
    return sorted(set(findings))