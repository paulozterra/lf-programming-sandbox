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


def _registry_matches(ledger: dict, key: str, endpoint: str | None) -> tuple[list[dict], list[dict]]:
    exact, related = [], []
    for row in ledger.get("entries", []):
        if not isinstance(row, dict):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        rules = row.get("rule_codes", [])
        endpoints = row.get("endpoints", [])
        if not isinstance(rules, list) or not isinstance(endpoints, list):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        if key in rules:
            exact.append(row)
        elif endpoint and endpoint in endpoints:
            related.append(row)
    return exact, related


def _verified_context(root: Path, row: dict) -> list[dict]:
    refs = row.get("files")
    if not isinstance(refs, list) or not refs:
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    result = []
    for item in refs:
        if not isinstance(item, dict):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        rel, expected = item.get("path"), item.get("sha256")
        if (not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts
                or not isinstance(expected, str) or not SHA.fullmatch(expected)):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        file = root / rel
        # A stale registry is not evidence of a new component or permission
        # to overwrite previously integrated source.
        if (file.is_symlink() or not file.is_file()
                or hashlib.sha256(file.read_bytes()).hexdigest() != expected):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA:REGISTRY_SHA_DRIFT:" + rel)
        result.append({"path": rel, "sha256": expected})
    return result


def _requested_endpoint(item: dict) -> str | None:
    value = item.get("endpoint")
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
            r"(?:GET|POST|PUT|PATCH|DELETE|PAGE) /[A-Za-z0-9_/{}/.-]*", value):
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    return value


def assess(index_obj: dict, obligations: list[dict], *,
           current_paths: list[str] | None = None,
           registry: dict | None = None, root: Path | None = None,
           declared_dependencies: list[dict] | None = None) -> dict:
    if (index_obj.get("schema_version") != "T7_CODE_INDEX_V1"
            or not isinstance(obligations, list)):
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    if registry is not None and (registry.get("schema_version") !=
                                 "T7_IMPLEMENTED_REGISTRY_V1" or root is None):
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    from pilot.orchestrator.declared_dependencies import select, resolve
    declared = select(declared_dependencies, obligations) if declared_dependencies is not None else {}
    rows = []
    for obligation in obligations:
        rid, rule = obligation.get("requirement_id"), obligation.get("source_requirement_id")
        if not isinstance(rid, str) or not isinstance(rule, str):
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        endpoint = _requested_endpoint(obligation)
        if rid in declared:
            if registry is None or root is None:
                raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
            from pilot.orchestrator.declared_dependencies import DependencyBlocked
            try:
                dep = declared[rid]
                current, protected = resolve(index_obj, registry, root, dep)
            except DependencyBlocked as exc:
                raise ReuseBlocked(str(exc)) from exc
            decision = "EXTEND" if dep["adds_rule"] else "REUSE_AS_IS"
            rows.append({"requirement_id": rid, "decision": decision,
                         "path": current["path"], "sha256": current["sha256"],
                         "write_paths": [current["path"]] if dep["adds_rule"] else [],
                         "evidence": {"kind": "declared_screen_dependency",
                                      "key": dep["key"],
                                      "source": "inventory.json#dependencies"},
                         "reuse_context": protected if dep["adds_rule"] else [current],
                         "reused_endpoints": [dep["key"]] if dep["kind"] == "endpoint" else []})
            continue
        if registry is not None:
            exact, related = _registry_matches(registry, rule, endpoint)
            if len(exact) > 1 or len(related) > 1 or exact and related:
                raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
            if exact or related:
                source = (exact or related)[0]
                context = _verified_context(root, source)
                if source.get("status") not in ("ATTESTED", "NO_DERIVABLE"):
                    raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
                # Partial historical metadata can prove an *exact rule* only;
                # absent contract endpoints never attest an endpoint match.
                if source.get("status") == "NO_DERIVABLE" and not exact:
                    raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
                decision = "REUSE_AS_IS" if exact else "EXTEND"
                rows.append({"requirement_id": rid, "decision": decision,
                             "path": context[0]["path"], "sha256": context[0]["sha256"],
                             "write_paths": ([x["path"] for x in context]
                                             if decision == "EXTEND" else []),
                             "evidence": {"kind": "registered_rule" if exact
                                          else "registered_endpoint_new_rule",
                                          "key": rule if exact else endpoint,
                                          "merge_sha": source["merge_sha"]},
                             "reuse_context": ([] if decision == "EXTEND" else context),
                             "reused_endpoints": sorted(source.get("endpoints", []))})
                continue
        # The code index is a second independently checked source. Exact rule
        # markers are enough to reuse, but common names alone never are.
        matches = [_unique(index_obj["entries"], "implemented_rule", code)
                   for code in sorted({rid, rule})]
        matches = [x for x in matches if x is not None]
        if len({x["path"] for x in matches}) > 1:
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        if matches:
            matched = matches[0]
            if root is not None:
                _verified_context(root, {"files": [{"path": matched["path"],
                                                    "sha256": matched["sha256"]}]})
            rows.append({"requirement_id": rid, "decision": "REUSE_AS_IS",
                         "path": matched["path"], "sha256": matched["sha256"],
                         "write_paths": [],
                         "evidence": {"kind": "exact_rule_reference",
                                      "key": matched["key"]},
                         "reuse_context": [{"path": matched["path"],
                                            "sha256": matched["sha256"]}]})
            continue
        if endpoint:
            candidates = [x for x in index_obj["entries"]
                          if x["kind"] == "endpoint" and x["key"] == endpoint]
            if candidates:
                # Without a rule-to-endpoint contract, this is a partial
                # match, not proof of an existing compatible implementation.
                raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
        if registry is None:
            # Legacy direct callers must not silently fabricate BUILD_NEW.
            raise ReuseBlocked("REUTILIZACION_INDETERMINADA:" + rid)
        rows.append({"requirement_id": rid, "decision": "BUILD_NEW",
                     "path": None, "sha256": None, "write_paths": [],
                     "evidence": {"kind": "sin coincidencias",
                                  "index_entries_checked": len(index_obj["entries"]),
                                  "registry_entries_checked": len(registry["entries"])},
                     "reuse_context": []})
    return {"schema_version": "T7_REUSE_ASSESSMENT_V1", "obligations": rows}



def write_assessment(root: Path, slug: str, package: dict, *,
                     declared_dependencies: list[dict] | None = None) -> dict:
    folder = root / "pilot/runs" / slug
    if folder.is_symlink() or not folder.is_dir():
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    registry_path = root / "pilot/registry/implemented.json"
    if registry_path.is_symlink() or not registry_path.is_file():
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA:REGISTRY_NOT_PUBLISHED")
    try:
        registry = json.loads(registry_path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA") from exc
    report = assess(index(root), package.get("requirements", []),
                    registry=registry, root=root,
                    declared_dependencies=declared_dependencies)
    output = folder / "reuse_assessment.json"
    raw = (json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    if output.is_symlink() or (output.exists() and output.read_bytes() != raw):
        raise ReuseBlocked("REUTILIZACION_INDETERMINADA")
    if not output.exists():
        output.write_bytes(raw)
    return report
