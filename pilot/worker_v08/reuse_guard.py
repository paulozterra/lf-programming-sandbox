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


def _public_signature(method: tuple[str, str, str]) -> tuple[str, str]:
    ret, _, args = method
    # Name-independent public method fingerprint detects copied services.
    signature = re.sub(r"\s+", " ", ret.strip())
    parts = []
    for arg in args.split(","):
        tokens = arg.strip().split()
        if len(tokens) >= 2:
            parts.append(" ".join(tokens[:-1]))
    return signature, ",".join(parts)


def check(root: Path, patch: str, reuse_context: list[dict]) -> None:
    if not isinstance(patch, str) or not isinstance(reuse_context, list):
        raise DuplicateComponent("REUTILIZACION_INDETERMINADA")
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
    touched = set()
    for line in patch.splitlines():
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
    for path in sorted(touched & context.keys()):
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
            if key in existing_endpoints:
                raise DuplicateComponent("DUPLICA_COMPONENTE_EXISTENTE:endpoint:" + key +
                                         ":" + existing_endpoints[key])
        for typ in JAVA_TYPE.findall(snippet):
            key = "type:" + typ
            if key in existing_types and existing_types[key] != path:
                raise DuplicateComponent("DUPLICA_COMPONENTE_EXISTENTE:type:" + key +
                                         ":" + existing_types[key])
        # An existing public method name is only protected if it is explicitly
        # present in reuse_context; otherwise common method names are ambiguous.
        public = JAVA_METHOD.findall(snippet)
        for existing_path in context:
            source = (root / existing_path).read_text("utf-8")
            known = {_public_signature(v) for v in JAVA_METHOD.findall(source)}
            for method in public:
                if _public_signature(method) in known and existing_path != path:
                    raise DuplicateComponent(
                        "DUPLICA_COMPONENTE_EXISTENTE:signature:" + existing_path)
