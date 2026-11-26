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


_HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)")


def _postimage(root: Path, path: str, diff: list[str]) -> tuple[str, str]:
    """Reconstruct a Java postimage from checked unified-diff hunks, in memory."""
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts or not (root / rel).resolve().is_relative_to(root.resolve()):
        raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
    candidate = root / rel
    if candidate.is_symlink():
        raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
    before = candidate.read_text("utf-8") if candidate.is_file() else ""
    old = before.splitlines()
    result = []
    cursor = 0
    starts = [i for i, line in enumerate(diff) if line.startswith("@@ ")]
    for start, end in zip(starts, starts[1:] + [len(diff)]):
        hunk = _HUNK.fullmatch(diff[start])
        if hunk is None:
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
        old_start, old_count, new_start, new_count = hunk.groups()
        old_count, new_count = int(old_count or "1"), int(new_count or "1")
        offset = int(old_start) - (1 if old_count else 0)
        new_offset = int(new_start) - (1 if new_count else 0)
        if not cursor <= offset <= len(old):
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
        result.extend(old[cursor:offset])
        cursor = offset
        if len(result) != new_offset:
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
        consumed = produced = 0
        for line in diff[start + 1:end]:
            if line == r"\ No newline at end of file":
                continue
            if not line or line[0] not in " +-":
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            if line[0] in " -":
                if cursor >= len(old) or old[cursor] != line[1:]:
                    raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
                cursor += 1
                consumed += 1
            if line[0] in " +":
                result.append(line[1:])
                produced += 1
        if (consumed, produced) != (old_count, new_count):
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
    result.extend(old[cursor:])
    return before, "\n".join(result)


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
    diffs = {}
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
            diffs[current] = []
        elif line.startswith("+") and not line.startswith("+++"):
            if current is None:
                raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
            added.append((current, line[1:]))
            block.append(line[1:])
        if current is not None and not line.startswith("diff --git a/"):
            diffs[current].append(line)
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
    # Real submissions have hunks (validated by worker_patch.inspect_patch).
    # Compare changed/new methods against pinned context, not unchanged legacy
    # methods. Fragment-only inputs are retained for the offline guard fixtures.
    from collections import Counter

    candidates = []
    for path, diff in diffs.items():
        if not path.endswith(".java"):
            continue
        if any(line.startswith("@@ ") for line in diff):
            before, after = _postimage(root, path, diff)
            previous = Counter((method, body) for method, body in _methods_with_body(before))
            for method, body in _methods_with_body(after):
                if previous[(method, body)]:
                    previous[(method, body)] -= 1
                else:
                    candidates.append((path, method, body))
        else:
            for added_path, snippet in added_blocks:
                if added_path == path:
                    candidates.extend((path, method, body) for method, body in _methods_with_body(snippet))
    known_methods = {
        path: list(_methods_with_body((root / path).read_text("utf-8")))
        for path in sorted(context) if path.endswith(".java")
    }
    for path, method, body in candidates:
        for existing_path, methods in known_methods.items():
            if existing_path == path:
                continue
            for known, known_body in methods:
                if _public_signature(method) == _public_signature(known) and body == known_body:
                    raise DuplicateComponent(
                        "DUPLICA_COMPONENTE_EXISTENTE:signature:"
                        + existing_path + "#" + known[1] + ":" + path + "#" + method[1])
