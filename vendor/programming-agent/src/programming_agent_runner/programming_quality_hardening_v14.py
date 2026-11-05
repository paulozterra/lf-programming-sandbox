from __future__ import annotations

import ast
from pathlib import Path

from . import programming_quality as q
from . import programming_quality_hardening_v3 as v3
from . import programming_quality_hardening_v6 as v6
from . import programming_quality_hardening_v9 as v9
from . import programming_quality_hardening_v11 as v11
from . import programming_quality_hardening_v13 as v13
from .worker_oracle import HiddenOracle


def _semantic_result_expression_tainted(
    node: ast.AST,
    *,
    tree: ast.Module,
    plan: q.QualityPlan,
    tainted_names: set[str],
) -> bool:
    return v13._semantic_result_expression_tainted(
        node, tree=tree, plan=plan, tainted_names=tainted_names
    )


def _semantic_result_aliases(tree: ast.Module, plan: q.QualityPlan) -> set[str]:
    aliases = set(v13._semantic_result_aliases(tree, plan))
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.withitem) or node.optional_vars is None:
                continue
            if not _semantic_result_expression_tainted(
                node.context_expr,
                tree=tree,
                plan=plan,
                tainted_names=aliases,
            ):
                continue
            additions = v11._target_names(node.optional_vars) - aliases
            if additions:
                aliases.update(additions)
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
                node.func, tree=tree, plan=plan, tainted_names=aliases
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
            node.value, tree=tree, plan=plan, tainted_names=aliases
        ):
            return True
    return False


def _with_binding_taint_findings(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
) -> list[str]:
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
    """AUD24 V14: preserve semantic-return provenance through with bindings."""
    findings = v13.validate_test007_command_semantics(plan, oracle, repo_path=repo_path)
    findings.extend(_with_binding_taint_findings(plan, oracle))
    return sorted(set(findings))
