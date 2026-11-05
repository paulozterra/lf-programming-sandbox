from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hashutil import sha256_json

_SECRET_PATTERNS = (
    ("AWS_ACCESS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("OPENAI_STYLE_SECRET", re.compile(r"sk-[A-Za-z0-9_-]{32,}")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN " + r"PRIVATE KEY-----")),
)
_SCAN_SUFFIXES = {".py", ".yml", ".yaml", ".json", ".toml", ".md", ".txt"}


@dataclass(frozen=True)
class SecurityFinding:
    path: str
    line: int
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _python_findings(path: Path, text: str, display: str) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    try:
        tree = ast.parse(text, filename=display)
    except SyntaxError:
        return findings
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            findings.append(SecurityFinding(display, node.lineno, "DYNAMIC_EXECUTION", node.func.id))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        findings.append(SecurityFinding(display, node.lineno, "SUBPROCESS_SHELL_TRUE", node.func.attr))
    return findings


def scan_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    findings: list[SecurityFinding] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith((".git/", "build/", ".venv/", "venv/")):
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            for code, pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(SecurityFinding(relative, lineno, code, "probable embedded secret"))
        if path.suffix.lower() == ".py":
            findings.extend(_python_findings(path, text, relative))
    ordered = sorted(findings, key=lambda item: (item.path, item.line, item.code))
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "status": "PASS" if not ordered else "FAIL",
        "files_scanned": scanned,
        "findings": [item.to_dict() for item in ordered],
        "scanner": "programming_agent_runner.security_gate",
    }
    evidence["evidence_sha256"] = sha256_json(evidence)
    return evidence
