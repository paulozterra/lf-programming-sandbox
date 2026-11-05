from __future__ import annotations

import ast
from pathlib import Path

from . import programming_quality as q
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v6 as v6
from . import programming_quality_hardening_v9 as v9
from . import programming_quality_hardening_v11 as v11
from . import programming_quality_hardening_v14 as v14
from .worker_oracle import HiddenOracle


def _semantic_submit_call(node: ast.AST, tree: ast.Module, plan: q.QualityPlan) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "submit" or not node.args:
        return False
    target = v6._canonical_reference(node.args[0], tree, plan)
    return target is not None and ".".join(target) in v9._semantic_reference_sets(plan)


def _transport_expression_tainted(
    node: ast.AST,
    *,
    tree: ast.Module,
    plan: q.QualityPlan,
    transport_names: set[str],
) -> bool:
    if _semantic_submit_call(node, tree, plan):
        return True
    if isinstance(node, ast.Call):
        reference = v9._infra_reference(node.func, v9._infra_import_bindings(tree))
        if reference == ("concurrent", "futures", "as_completed"):
            return any(
                _transport_expression_tainted(
                    item,
                    tree=tree,
                    plan=plan,
                    transport_names=transport_names,
                )
                for item in (
                    *node.args,
                    *(kw.value for kw in node.keywords),
                )
            )
    if isinstance(node, ast.Name):
        return node.id in transport_names
    if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        return _transport_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            transport_names=transport_names,
        )
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(
            _transport_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                transport_names=transport_names,
            )
            for item in node.elts
        )
    if isinstance(node, ast.Dict):
        return any(
            item is not None
            and _transport_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                transport_names=transport_names,
            )
            for item in (*node.keys, *node.values)
        )
    if isinstance(node, ast.IfExp):
        return any(
            _transport_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                transport_names=transport_names,
            )
            for item in (node.body, node.orelse)
        )
    if isinstance(node, ast.BoolOp):
        return any(
            _transport_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                transport_names=transport_names,
            )
            for item in node.values
        )
    if isinstance(node, ast.NamedExpr):
        return _transport_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            transport_names=transport_names,
        )
    return False


def _transport_aliases(tree: ast.Module, plan: q.QualityPlan) -> set[str]:
    aliases: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            targets: set[str] = set()
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                value = node.value
                for target in node.targets:
                    targets.update(v11._target_names(target))
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value = node.value
                targets.update(v11._target_names(node.target))
            elif isinstance(node, ast.NamedExpr):
                value = node.value
                targets.update(v11._target_names(node.target))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                value = node.iter
                targets.update(v11._target_names(node.target))
            elif isinstance(node, ast.comprehension):
                value = node.iter
                targets.update(v11._target_names(node.target))
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                value = node.context_expr
                targets.update(v11._target_names(node.optional_vars))
            if value is None or not targets:
                continue
            if _transport_expression_tainted(
                value,
                tree=tree,
                plan=plan,
                transport_names=aliases,
            ):
                additions = targets - aliases
                if additions:
                    aliases.update(additions)
                    changed = True
    return aliases


def _transport_result_call(
    node: ast.AST,
    *,
    tree: ast.Module,
    plan: q.QualityPlan,
    transport_names: set[str],
) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "result"
        and _transport_expression_tainted(
            node.func.value,
            tree=tree,
            plan=plan,
            transport_names=transport_names,
        )
    )


def _semantic_result_expression_tainted(
    node: ast.AST,
    *,
    tree: ast.Module,
    plan: q.QualityPlan,
    tainted_names: set[str],
    transport_names: set[str],
) -> bool:
    if _transport_result_call(
        node,
        tree=tree,
        plan=plan,
        transport_names=transport_names,
    ):
        return True
    return v14._semantic_result_expression_tainted(
        node,
        tree=tree,
        plan=plan,
        tainted_names=tainted_names,
    )


def _semantic_result_aliases(tree: ast.Module, plan: q.QualityPlan) -> tuple[set[str], set[str]]:
    transport_names = _transport_aliases(tree, plan)
    aliases = set(v14._semantic_result_aliases(tree, plan))
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            targets: set[str] = set()
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                value = node.value
                for target in node.targets:
                    targets.update(v11._target_names(target))
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value = node.value
                targets.update(v11._target_names(node.target))
            elif isinstance(node, ast.NamedExpr):
                value = node.value
                targets.update(v11._target_names(node.target))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                value = node.iter
                targets.update(v11._target_names(node.target))
            elif isinstance(node, ast.comprehension):
                value = node.iter
                targets.update(v11._target_names(node.target))
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                value = node.context_expr
                targets.update(v11._target_names(node.optional_vars))
            if value is None or not targets:
                continue
            if _semantic_result_expression_tainted(
                value,
                tree=tree,
                plan=plan,
                tainted_names=aliases,
                transport_names=transport_names,
            ):
                additions = targets - aliases
                if additions:
                    aliases.update(additions)
                    changed = True
    return aliases, transport_names


def _semantic_result_navigation_unsafe(tree: ast.Module, plan: q.QualityPlan) -> bool:
    aliases, transport_names = _semantic_result_aliases(tree, plan)
    if not aliases:
        return False
    semantic_references = v9._semantic_reference_sets(plan)
    parents = v9._parent_map(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            reference = v6._canonical_reference(node.func, tree, plan)
            if reference is not None and ".".join(reference) in semantic_references:
                continue
            if _transport_result_call(
                node,
                tree=tree,
                plan=plan,
                transport_names=transport_names,
            ):
                continue
            if _semantic_result_expression_tainted(
                node.func,
                tree=tree,
                plan=plan,
                tainted_names=aliases,
                transport_names=transport_names,
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
            if _transport_result_call(
                parent,
                tree=tree,
                plan=plan,
                transport_names=transport_names,
            ):
                continue
        if _semantic_result_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            tainted_names=aliases,
            transport_names=transport_names,
        ):
            return True
    return False


def _future_transport_taint_findings(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    findings: list[str] = []
    for command in oracle.commands:
        tree = v3._inline_python(command)
        if isinstance(tree, ast.Module) and _semantic_result_navigation_unsafe(tree, plan):
            findings.append(f"HIDDEN_HOLDOUT_SEMANTIC_RETURN_TAINT:{command.name}")
    return sorted(set(findings))


def validate_test007_command_semantics(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    *,
    repo_path: Path,
) -> list[str]:
    """AUD24 V15: preserve semantic-return provenance through submitted Futures."""
    findings = v14.validate_test007_command_semantics(plan, oracle, repo_path=repo_path)
    findings.extend(_future_transport_taint_findings(plan, oracle))
    return sorted(set(findings))
