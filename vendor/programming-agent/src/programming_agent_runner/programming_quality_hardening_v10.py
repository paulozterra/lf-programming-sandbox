from __future__ import annotations

import ast
from pathlib import Path

from . import programming_quality as q
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v6 as v6
from . import programming_quality_hardening_v9 as v9
from .worker_oracle import HiddenOracle


def _semantic_result_expression_tainted(
    node: ast.AST,
    *,
    tree: ast.Module,
    plan: q.QualityPlan,
    tainted_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tainted_names
    if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        return _semantic_result_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            tainted_names=tainted_names,
        )
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(
            _semantic_result_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                tainted_names=tainted_names,
            )
            for item in node.elts
        )
    if isinstance(node, ast.Dict):
        return any(
            item is not None
            and _semantic_result_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                tainted_names=tainted_names,
            )
            for item in (*node.keys, *node.values)
        )
    if isinstance(node, ast.IfExp):
        return any(
            _semantic_result_expression_tainted(
                item,
                tree=tree,
                plan=plan,
                tainted_names=tainted_names,
            )
            for item in (node.body, node.orelse)
        )
    if isinstance(node, ast.NamedExpr):
        return _semantic_result_expression_tainted(
            node.value,
            tree=tree,
            plan=plan,
            tainted_names=tainted_names,
        )
    if isinstance(node, ast.Call):
        reference = v6._canonical_reference(node.func, tree, plan)
        if reference is not None and ".".join(reference) in v9._semantic_reference_sets(plan):
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
            elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
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
    semantic_references = v9._semantic_reference_sets(plan)
    parents = v9._parent_map(tree)
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


def _container_taint_findings(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
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
    """AUD24 V10: preserve semantic-return provenance through local containers."""
    findings = v9.validate_test007_command_semantics(plan, oracle, repo_path=repo_path)
    findings.extend(_container_taint_findings(plan, oracle))
    return sorted(set(findings))
