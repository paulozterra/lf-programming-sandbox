from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)


@dataclass(frozen=True)
class FunctionMetric:
    file: str
    qualified_name: str
    line: int
    end_line: int
    lines: int
    branch_nodes: int
    max_nesting: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    next_depth = depth + 1 if isinstance(node, BRANCH_NODES) else depth
    values = [next_depth]
    for child in ast.iter_child_nodes(node):
        values.append(_max_nesting(child, next_depth))
    return max(values)


def analyze_python(root: Path) -> dict[str, Any]:
    metrics: list[FunctionMetric] = []
    parse_errors: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {".git", ".venv", "venv", "__pycache__", "build", "dist"} for part in path.parts):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            parse_errors.append({"file": rel, "error": str(exc)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                branch_nodes = sum(1 for child in ast.walk(node) if isinstance(child, BRANCH_NODES))
                metrics.append(FunctionMetric(rel, node.name, node.lineno, end, end - node.lineno + 1, branch_nodes, _max_nesting(node)))
    return {
        "functions": [m.to_dict() for m in sorted(metrics, key=lambda m: (m.file, m.line, m.qualified_name))],
        "parse_errors": parse_errors,
        "thresholds_applied": None,
        "threshold_policy": "NO_CANONICAL_THRESHOLD_JUDGE_REQUIRED",
    }
