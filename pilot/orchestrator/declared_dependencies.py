"""T7.2: interpret only explicitly pinned screen dependencies, fail closed.

A dependency binds an A9 obligation by requirement_id or rule_code and names
an exact endpoint (method + route), page or exported public signature.
adds_rule is explicit source metadata: never infer novelty from prose.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ENDPOINT = re.compile(r"(?:GET|POST|PUT|PATCH|DELETE|PAGE) /[A-Za-z0-9_/{}/.-]*\Z")
SIGNATURE = re.compile(r"(?:export|type|method):[A-Za-z0-9_(),.<> ?\[\]:-]+\Z")
TOKEN = re.compile(r"[A-Za-z0-9_-]+\Z")


class DependencyBlocked(ValueError):
    pass


def _fail():
    raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")


def _context(root, path, sha):
    if (not isinstance(path, str) or not path or Path(path).is_absolute()
            or ".." in Path(path).parts or not isinstance(sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha)):
        _fail()
    file = root / path
    if (file.is_symlink() or not file.is_file()
            or hashlib.sha256(file.read_bytes()).hexdigest() != sha):
        _fail()
    return {"path": path, "sha256": sha}


def _area(dep):
    """Typed dependency location, never guessed from rule prose."""
    kind = dep.get("kind")
    if kind == "endpoint":
        return "BACKEND"
    if kind in ("component", "page"):
        return "FRONTEND"
    if kind in ("table", "migration"):
        return "DATA"
    _fail()


def _req_area(row):
    """Only accept A9's projected scope or explicit typed area."""
    area = row.get("execution_area")
    if area in ("BACKEND", "FRONTEND", "DATA"):
        return area
    scope = row.get("scope_id")
    if isinstance(scope, str):
        for candidate in ("BACKEND", "FRONTEND", "DATA"):
            if scope.endswith("-" + candidate):
                return candidate
    return None


def select(dependencies, requirements):
    """One typed dependency resolves to exactly one A9 area-bound requirement.

    Both simulated Git attestation and implementation reuse call this function.
    A rule_code may have a primary and derived obligations: never default to
    the primary if its area differs from the declared component's area.
    """
    if not isinstance(dependencies, list) or not isinstance(requirements, list):
        _fail()
    result = {}
    known = {}
    for req in requirements:
        if not isinstance(req, dict):
            _fail()
        rid, rule = req.get("requirement_id"), req.get("source_requirement_id")
        if not isinstance(rid, str) or not isinstance(rule, str) or rid in known:
            _fail()
        known[rid] = req
    for dep in dependencies:
        if not isinstance(dep, dict):
            _fail()
        area = _area(dep)
        rid, code = dep.get("requirement_id"), dep.get("rule_code")
        if bool(rid) == bool(code):
            raise DependencyBlocked("DEPENDENCIA_SIN_REQUISITO")
        if rid:
            row = known.get(rid)
            if row is None:
                raise DependencyBlocked("DEPENDENCIA_SIN_REQUISITO")
            if _req_area(row) != area:
                raise DependencyBlocked("DEPENDENCIA_AREA_INCOMPATIBLE")
        else:
            if not isinstance(code, str):
                raise DependencyBlocked("DEPENDENCIA_SIN_REQUISITO")
            linked = [r for r in requirements
                      if r["source_requirement_id"] == code]
            if not linked:
                raise DependencyBlocked("DEPENDENCIA_SIN_REQUISITO")
            match = [r for r in linked if _req_area(r) == area]
            if len(match) != 1:
                raise DependencyBlocked("DEPENDENCIA_AREA_INCOMPATIBLE")
            rid = match[0]["requirement_id"]
        kind = dep["kind"]
        if kind in ("endpoint", "page"):
            method = dep.get("method", "PAGE" if kind == "page" else None)
            route = dep.get("route")
            key = str(method) + " " + str(route)
            if not ENDPOINT.fullmatch(key) or (kind == "page") != (method == "PAGE"):
                _fail()
            index_kind = "endpoint"
        elif kind == "component":
            key = dep.get("signature")
            if not isinstance(key, str) or not SIGNATURE.fullmatch(key):
                _fail()
            index_kind = "public_signature"
        else:
            # Future SQL index contracts must provide an exact table/migration
            # identity; never claim availability by mention in the fiche.
            key = dep.get("signature")
            if not isinstance(key, str) or not key:
                _fail()
            index_kind = "sql_" + kind
        if not isinstance(dep.get("adds_rule"), bool):
            _fail()
        witness = dep.get("reuse_rule_code")
        signature = dep.get("reuse_component_signature")
        if witness is not None and (not isinstance(witness, str)
                                    or not TOKEN.fullmatch(witness)):
            _fail()
        if signature is not None and (not isinstance(signature, str)
                                      or not SIGNATURE.fullmatch(signature)):
            _fail()
        if dep["adds_rule"] != bool(witness or signature) or (witness and signature):
            _fail()
        if rid in result:
            _fail()
        result[rid] = {"kind": index_kind, "key": key,
                       "adds_rule": dep["adds_rule"],
                       "reuse_rule_code": witness,
                       "reuse_component_signature": signature,
                       "area": area}
    return result

def resolve(index_obj, registry, root, dep):
    """Exact indexed component plus SHA-verified registry evidence where present."""
    if root is None:
        _fail()
    entries = [entry for entry in index_obj.get("entries", [])
               if entry.get("kind") == dep["kind"] and entry.get("key") == dep["key"]]
    if len({item.get("path") for item in entries}) != 1 or not entries:
        _fail()
    primary = _context(root, entries[0].get("path"), entries[0].get("sha256"))
    registry_matches = []
    for row in registry.get("entries", []):
        if not isinstance(row, dict):
            _fail()
        if dep["kind"] == "endpoint" and dep["key"] in row.get("endpoints", []):
            registry_matches.append(row)
    if len(registry_matches) > 1:
        _fail()
    if registry_matches:
        from pilot.orchestrator.reuse_assessment import _verified_context
        context = _verified_context(root, registry_matches[0])
        if primary["path"] not in {x["path"] for x in context}:
            _fail()
    extra = []
    if dep["adds_rule"]:
        rule = dep["reuse_rule_code"]
        signature = dep["reuse_component_signature"]
        rule_entries = [x for x in index_obj.get("entries", [])
                        if x.get("kind") == ("public_signature" if signature else "implemented_rule")
                        and x.get("key") == (signature or rule)]
        if len({x.get("path") for x in rule_entries}) > 1:
            _fail()
        if rule_entries:
            extra.append(_context(root, rule_entries[0]["path"], rule_entries[0]["sha256"]))
        else:
            from pilot.orchestrator.reuse_assessment import _verified_context
            matched = [x for x in registry.get("entries", [])
                       if isinstance(x, dict) and x.get("status") == "ATTESTED"
                       and rule is not None and rule in x.get("rule_codes", [])]
            if len(matched) != 1:
                _fail()
            extra = _verified_context(root, matched[0])
        if primary["path"] in {x["path"] for x in extra}:
            # A file cannot be both a protected reuse source and writable.
            _fail()
    return primary, sorted({x["path"]: x for x in extra}.values(),
                           key=lambda x: x["path"])
