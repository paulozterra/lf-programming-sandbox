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
from pilot.orchestrator.reuse_assessment import index, JAVA_TYPE, JAVA_MAPPING, METHODS


class DuplicateComponent(ValueError):
    pass


# Lexical tokens preserve string literals and ignore comments/whitespace. A
# matching signature is only a candidate; require a complete matching body.
_JAVA_TOKEN = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'|[A-Za-z_$][\w$]*|\d+|\S"
)
_NON_METHOD = {"record", "class", "interface", "enum"}


_IDENT = re.compile(r"[A-Za-z_$][\w$]*\Z")
_MODIFIERS = {"static", "final", "synchronized", "abstract", "native", "strictfp", "default"}
_RESERVED = {"return", "throw", "new", "case", "yield", "break", "continue",
             "else", "assert", "instanceof", "this", "super", "null", "true", "false"}


def _tokens(source: str) -> list[str]:
    return [t for t in _JAVA_TOKEN.findall(source) if not t.startswith(("//", "/*"))]


def _closing(tokens: list[str], start: int, left: str, right: str) -> int | None:
    depth = 0
    for i in range(start, len(tokens)):
        if tokens[i] == left:
            depth += 1
        elif tokens[i] == right:
            depth -= 1
            if depth == 0:
                return i
    return None


def _annotation_end(tokens: list[str], start: int) -> int:
    i = start + 1
    if i >= len(tokens) or not _IDENT.fullmatch(tokens[i]):
        return start
    i += 1
    while i + 1 < len(tokens) and tokens[i] == "." and _IDENT.fullmatch(tokens[i + 1]):
        i += 2
    if i < len(tokens) and tokens[i] == "(":
        end = _closing(tokens, i, "(", ")")
        return end + 1 if end is not None else start
    return i


def _parameters(tokens: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    clean = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "@":
            end = _annotation_end(tokens, i)
            if end == i:
                return None
            i = end
        elif tokens[i] == "final":
            i += 1
        else:
            clean.append(tokens[i])
            i += 1
    groups = [[]]
    depth = 0
    for token in clean:
        if token == "<":
            depth += 1
        elif token == ">":
            depth -= 1
        if token == "," and depth == 0:
            groups.append([])
        else:
            groups[-1].append(token)
    if depth != 0:
        return None
    if groups == [[]]:
        return (), ()
    names, types = [], []
    for group in groups:
        suffix = []
        while group[-2:] == ["[", "]"]:
            suffix.extend(group[-2:])
            group = group[:-2]
        if len(group) < 2 or not _IDENT.fullmatch(group[-1]):
            return None
        names.append(group[-1])
        types.append(" ".join(group[:-1] + suffix))
    return tuple(types), tuple(names)


def _methods_with_body(source: str):
    """Bounded lexical method extraction, not a Java compiler or AST."""
    tokens = _tokens(source)
    for start, token in enumerate(tokens):
        if token != "public":
            continue
        i = start + 1
        while i < len(tokens):
            if tokens[i] in _MODIFIERS:
                i += 1
            elif tokens[i] == "@":
                end = _annotation_end(tokens, i)
                if end == i:
                    break
                i = end
            else:
                break
        if i >= len(tokens) or tokens[i] in _NON_METHOD:
            continue
        head = i
        while i < len(tokens) and tokens[i] not in {"(", "{", "}", ";", "="}:
            i += 1
        if i >= len(tokens) or tokens[i] != "(" or i - head < 2:
            continue
        name = tokens[i - 1]
        if not _IDENT.fullmatch(name):
            continue
        end = _closing(tokens, i, "(", ")")
        if end is None:
            continue
        params = _parameters(tokens[i + 1:end])
        if params is None:
            continue
        j = end + 1
        if j < len(tokens) and tokens[j] == "throws":
            j += 1
            while j < len(tokens) and tokens[j] not in {"{", "}", ";", "(", "="}:
                j += 1
        if j >= len(tokens) or tokens[j] != "{":
            continue
        close = _closing(tokens, j, "{", "}")
        if close is None:
            continue
        body = tuple(tokens[j:close + 1])
        if len(body) > 2:
            yield (" ".join(tokens[head:i - 1]), name, params[0], params[1]), body


def _public_signature(method):
    return method[0], method[2]


def _local_declaration(tokens: tuple[str, ...], i: int) -> int | None:
    """Recognize common local declarations at statement/for/catch boundaries."""
    if i and tokens[i - 1] not in {"{", "}", ";", "("}:
        return None
    if i and tokens[i - 1] == "(" and (i < 2 or tokens[i - 2] not in {"for", "catch", "try"}):
        return None
    j = i + (tokens[i] == "final")
    if j >= len(tokens) or not _IDENT.fullmatch(tokens[j]) or tokens[j] in _RESERVED:
        return None
    j += 1
    while j < len(tokens):
        if tokens[j] == "." and j + 1 < len(tokens) and _IDENT.fullmatch(tokens[j + 1]):
            j += 2
        elif tokens[j] == "<":
            end = _closing(list(tokens), j, "<", ">")
            if end is None:
                return None
            j = end + 1
        elif tokens[j:j + 2] == ("[", "]"):
            j += 2
        else:
            break
    if (j + 1 < len(tokens) and _IDENT.fullmatch(tokens[j])
            and tokens[j] not in _RESERVED and tokens[j + 1] in {"=", ";", ",", ":", ")"}):
        return j
    return None


def _normalized_body(method, body: tuple[str, ...]) -> tuple[str, ...]:
    # Only declared parameters/locals are renamed. Preserve member accesses,
    # calls, type names, operators and literal contents. This is intentionally
    # lexical: helper extraction or reordered statements are not equivalence.
    names = {name: f"$param:{i}" for i, name in enumerate(method[3])}
    declarations = {}
    for i in range(len(body)):
        end = _local_declaration(body, i)
        if end is not None:
            name = body[end]
            if name not in names:
                names[name] = f"$local:{len(declarations)}"
            declarations[end] = names[name]
    out = []
    parens = 0
    for i, token in enumerate(body):
        prev = body[i - 1] if i else ""
        nxt = body[i + 1] if i + 1 < len(body) else ""
        if token == "final" and _local_declaration(body, i) is not None:
            continue
        if token == ";" and parens == 0 and prev in {";", "{"}:
            continue
        if token == "(":
            parens += 1
        elif token == ")":
            parens -= 1
        if i in declarations:
            token = declarations[i]
        elif token in names and prev != "." and nxt != "(":
            token = names[token]
        out.append(token)
    return tuple(out)


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
    touched = set()
    for line in patch.splitlines():
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
        if current is not None and not line.startswith("diff --git a/"):
            diffs[current].append(line)
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
    # methods. Reject fragment-only Java inputs, including offline dry runs.
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
            raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
    known_methods = {
        path: list(_methods_with_body((root / path).read_text("utf-8")))
        for path in sorted(context) if path.endswith(".java")
    }
    for path, method, body in candidates:
        for existing_path, methods in known_methods.items():
            if existing_path == path:
                continue
            for known, known_body in methods:
                if _public_signature(method) == _public_signature(known) and _normalized_body(method, body) == _normalized_body(known, known_body):
                    raise DuplicateComponent(
                        "DUPLICA_COMPONENTE_EXISTENTE:signature:"
                        + existing_path + "#" + known[1] + ":" + path + "#" + method[1])
