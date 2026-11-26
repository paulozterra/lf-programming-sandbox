"""T7 patch anti-duplication gate; deterministic and visible-safe.

Operate on the proposal's unified diff and a pinned source-code index.
No oracle content or secrets. Never approve on an unparseable reuse context.
"""
from __future__ import annotations

import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pilot.orchestrator.reuse_assessment import index, JAVA_TYPE, JAVA_METHOD, JAVA_MAPPING, METHODS


class DuplicateComponent(ValueError):
    pass


# Lexical tokens preserve string literals and ignore comments/whitespace. A
# matching signature is only a candidate; require a complete matching body.
_JAVA_TOKEN = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'|[A-Za-z_$][\w$]*|\d+|\S"
)
_NON_METHOD = {"record", "class", "interface", "enum"}


def _public_signature(method: tuple[str, str, str]) -> tuple[str, str]:
    ret, _, args = method
    signature = re.sub(r"\s+", " ", ret.strip())
    parts = []
    for arg in args.split(","):
        tokens = arg.strip().split()
        if len(tokens) >= 2:
            parts.append(" ".join(tokens[:-1]))
    return signature, ",".join(parts)


def _methods_with_body(source: str):
    for match in JAVA_METHOD.finditer(source):
        method = match.groups()
        if method[0].strip() in _NON_METHOD:
            continue
        tail = source[match.end():]
        opening = re.match(r"\s*\{", tail)
        if opening is None:
            continue
        depth = 0
        body = []
        for token in _JAVA_TOKEN.findall(tail[opening.end() - 1:]):
            if token.startswith(("//", "/*")):
                continue
            body.append(token)
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth == 0:
                    if len(body) > 2:
                        yield method, tuple(body)
                    break


def check(root: Path, patch: str, reuse_context: list[dict],
          writable: tuple[str, ...] | list[str] = ()) -> None:
    """``writable``: files the registered task is authorized to change (an
    EXTEND lot). Editing them in place is the task itself, never a duplicate;
    duplicating them elsewhere is still rejected."""
    if not isinstance(patch, str) or not isinstance(reuse_context, list):
        raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
    writable = frozenset(p for p in writable if isinstance(p, str))
    baseline = index(root)["entries"]
    existing_endpoints = {r["key"]: r["path"] for r in baseline if r["kind"] == "endpoint"}
    existing_types = {r["key"]: r["path"] for r in baseline if r["kind"] == "public_signature"}
    context = {}
    for entry in reuse_context:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
        context[entry["path"]] = entry.get("sha256")
    current = None
    added = []
    added_blocks = []
    block = []
    touched = set()
    for line in patch.splitlines():
        if not (line.startswith("+") and not line.startswith("+++")):
            if block:
                added_blocks.append((current, "\n".join(block)))
                block = []
        if line.startswith("diff --git a/"):
            match = re.fullmatch(r"diff --git a/([^\s]+) b/\1", line)
            if not match:
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            current = match.group(1)
            touched.add(current)
        elif line.startswith("+") and not line.startswith("+++"):
            if current is None:
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            added.append((current, line[1:]))
            block.append(line[1:])
    if block:
        added_blocks.append((current, "\n".join(block)))
    for path in sorted((touched & context.keys()) - writable):
        raise DuplicateComponent("DUPLICA_COMPONENTE_EXISTENTE:reuse_context:" + path)
    for path, sha in sorted(context.items()):
        candidate = root / path
        if (candidate.is_symlink() or not candidate.is_file()
                or not isinstance(sha, str)):
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
        import hashlib
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != sha:
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
    grouped = {}
    for path, line in added:
        grouped.setdefault(path, []).append(line)
    for path, lines in grouped.items():
        snippet = "\n".join(lines)
        for kind, left, right in JAVA_MAPPING.findall(snippet):
            key = METHODS.get(kind, "ANY") + " " + (left or right)
            if key in existing_endpoints and not (
                    existing_endpoints[key] == path and path in writable):
                raise DuplicateComponent("DUPLICA_COMPONENTE_EXISTENTE:endpoint:" + key +
                                         ":" + existing_endpoints[key])
        for typ in JAVA_TYPE.findall(snippet):
            key = "type:" + typ
            if key in existing_types and existing_types[key] != path:
                raise DuplicateComponent("DUPLICA_COMPONENTE_EXISTENTE:type:" + key +
                                         ":" + existing_types[key])
    # Never join unrelated diff hunks to fabricate a method body. A signature
    # alone (even the same method name) is not evidence of copied behavior.
    for path, snippet in added_blocks:
        if not path.endswith(".java"):
            continue
        for method, body in _methods_with_body(snippet):
            for existing_path in sorted(context):
                if existing_path == path or not existing_path.endswith(".java"):
                    continue
                source = (root / existing_path).read_text("utf-8")
                for known, known_body in _methods_with_body(source):
                    if _public_signature(method) == _public_signature(known) and body == known_body:
                        raise DuplicateComponent(
                            "DUPLICA_COMPONENTE_EXISTENTE:signature:"
                            + existing_path + "#" + known[1] + ":" + path + "#" + method[1])
