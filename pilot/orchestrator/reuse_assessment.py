"""T7: bounded repository implementation index and evidence-only reuse decision.

No models, filename guessing, substring matching, or implicit BUILD_NEW.
A requirement without an exact typed implementation marker stays unresolved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
RULE_REF = re.compile(r"(?<![A-Za-z0-9_])(?:REQ|RULE)-[A-Za-z0-9_-]+")
JAVA_TYPE = re.compile(r"(?m)^\s*public\s+(?:abstract\s+|final\s+)?(?:class|interface|record|enum)\s+([A-Za-z_]\w*)")
JAVA_METHOD = re.compile(r"(?m)^\s*public\s+(?:static\s+|final\s+|synchronized\s+)*([\w<>, ?\[\].]+)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)")
JAVA_MAPPING = re.compile(r'@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:"([^"]+)"|value\s*=\s*"([^"]+)")')
JAVA_ERRORS = re.compile(r'\b[A-Z][A-Z0-9]*-[A-Z0-9-]{2,}\b')
TS_EXPORT = re.compile(r"(?m)^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|type|interface)\s+([A-Za-z_]\w*)")
METHODS = {"Get": "GET", "Post": "POST", "Put": "PUT", "Patch": "PATCH", "Delete": "DELETE"}


class ReuseBlocked(ValueError):
    pass


def _code_files(root: Path):
    folders = (root / "apps/time-service/src/main/java", root / "frontend/src")
    for folder in folders:
        if not folder.is_dir() or folder.is_symlink():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
            if path.is_file() and path.suffix in (".java", ".ts", ".tsx") \
                    and not any(part in ("node_modules", "__tests__", "test") for part in path.parts):
                yield path


def index(root: Path) -> dict:
    entries = []
    for file in _code_files(root):
        raw = file.read_bytes()
        try:
            src = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA") from exc
        rel = file.relative_to(root).as_posix()
        sha = hashlib.sha256(raw).hexdigest()
        markers = sorted(set(RULE_REF.findall(src)))
        signatures = []
        endpoints = []
        if file.suffix == ".java":
            signatures = ["type:" + name for name in JAVA_TYPE.findall(src)]
            signatures += ["method:" + name + "(" + re.sub(r"\s+", " ", params.strip()) + "):" +
                           re.sub(r"\s+", " ", result.strip())
                           for result, name, params in JAVA_METHOD.findall(src)]
            endpoints = [{"method": METHODS.get(kind, "ANY"),
                          "route": a or b} for kind, a, b in JAVA_MAPPING.findall(src)]
        else:
            signatures = ["export:" + name for name in TS_EXPORT.findall(src)]
            if "/app/" in rel and file.name == "page.tsx":
                route = "/" + rel.split("/app/", 1)[1].rsplit("/page.tsx", 1)[0]
                endpoints = [{"method": "PAGE", "route": route.rstrip("/") or "/"}]
        for sig in signatures:
            entries.append({"kind": "public_signature", "key": sig, "path": rel,
                            "sha256": sha, "rule_refs": markers})
        for row in endpoints:
            entries.append({"kind": "endpoint", "key": row["method"] + " " + row["route"],
                            "path": rel, "sha256": sha, "rule_refs": markers})
        for code in sorted(set(JAVA_ERRORS.findall(src))):
            entries.append({"kind": "error_code", "key": code, "path": rel,
                            "sha256": sha, "rule_refs": markers})
        for marker in markers:
            entries.append({"kind": "implemented_rule", "key": marker, "path": rel,
                            "sha256": sha, "rule_refs": markers})
    return {"schema_version": "T7_CODE_INDEX_V1",
            "entries": sorted(entries, key=lambda e:(e["kind"],e["key"],e["path"]))}


def _unique(entries, kind, key):
    matches = [e for e in entries if e["kind"] == kind and e["key"] == key]
    paths = {e["path"] for e in matches}
    if len(paths) > 1:
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    return matches[0] if matches else None


def assess(index_obj: dict, obligations: list[dict], *, current_paths: list[str] | None = None) -> dict:
    if index_obj.get("schema_version") != "T7_CODE_INDEX_V1":
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    rows = []
    for obligation in obligations:
        rid = obligation.get("requirement_id")
        source = obligation.get("source_requirement_id")
        if not isinstance(rid, str) or not isinstance(source, str):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        # Only exact existing rule markers can attest the obligation.
        matches = [_unique(index_obj["entries"], "implemented_rule", code)
                   for code in sorted({rid, source})]
        matches = [row for row in matches if row is not None]
        if len({m["path"] for m in matches}) > 1:
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        if not matches:
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA:" + rid)
        matched = matches[0]
        if not SHA.fullmatch(matched["sha256"]):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        rows.append({"requirement_id": rid, "decision": "REUSE_AS_IS",
                     "path": matched["path"], "sha256": matched["sha256"],
                     "evidence": {"kind": "exact_rule_reference",
                                  "key": matched["key"]}, "reuse_context": [{
                                      "path": matched["path"], "sha256": matched["sha256"]}]})
    return {"schema_version": "T7_REUSE_ASSESSMENT_V1", "obligations": rows}


def write_assessment(root: Path, slug: str, package: dict) -> dict:
    folder = root / "pilot/runs" / slug
    if folder.is_symlink() or not folder.is_dir():
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    report = assess(index(root), package.get("requirements", []))
    output = folder / "reuse_assessment.json"
    raw = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    if output.is_symlink() or (output.exists() and output.read_bytes() != raw):
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    if not output.exists():
        output.write_bytes(raw)
    return report
