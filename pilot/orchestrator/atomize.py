#!/usr/bin/env python3
"""T1 A9→area-sourced, deterministically bounded atoms. Offline; no model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RULES = HERE / "atomize_rules_v1.json"
REPO = "paulozterra/lf-programming-sandbox"
SAFE = re.compile(r"[a-z][a-z0-9-]{0,45}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class AtomBlocked(ValueError):
    pass


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def _slug(source):
    if not isinstance(source, str):
        raise AtomBlocked("ATOM_IDENTITY_INVALID")
    result = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    for prefix in ("sbx-auth-", "scope-"):
        if result.startswith(prefix):
            result = result[len(prefix):]
    if not SAFE.fullmatch(result):
        raise AtomBlocked("ATOM_IDENTITY_INVALID")
    return result


def _rules():
    data = json.loads(RULES.read_text(encoding="utf-8"))
    if data.get("schema_version") != "T1_ATOMIZE_RULES_V1":
        raise AtomBlocked("ATOM_RULES_INVALID")
    return data


def _next_version(root):
    # The staging root often contains only request artifacts. Include the
    # checked-out repository migrations so the next version is not reset to V1.
    numbers = []
    for base in (HERE.parents[1], Path(root)):
        for file in (base / "db/migration").glob("V*__*.sql"):
            match = re.fullmatch(r"V([0-9]+)__[a-z0-9_]+\.sql", file.name)
            if match:
                numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _class(module, suffix):
    return "".join(part.capitalize() for part in module.split("-")) + suffix


def _route(area, module, rules, root):
    service = rules["service"]
    if area == "DATA":
        return [rules["routes"]["DATA"].format(
            next=_next_version(root), module=module.replace("-", "_"))]
    if area == "BACKEND":
        return [rules["routes"]["BACKEND"].format(
            service=service, service_java=service.split("-")[0],
            module=module, **{"class": _class(module, suffix)})
            for suffix in rules["backend_classes"]]
    if area == "FRONTEND":
        return [p.format(module=module) for p in rules["routes"]["FRONTEND"]]
    raise AtomBlocked("ATOM_AREA_UNRESOLVED")


def _area(front, requirements, business_rules, rules):
    direct = front.get("execution_area")
    source = front.get("source_ref")
    if direct is not None or source is not None:
        if direct in rules["order"] and isinstance(source, str) and source:
            return direct, {"method": "A7_EXPLICIT", "source_ref": source}
        raise AtomBlocked("ATOM_AREA_UNRESOLVED:" + str(front.get("front_id")))
    front_kind = front.get("front_kind")
    categories = {r.get("categoria") for r in business_rules
                  if r.get("front_id") == front.get("front_id")}
    signals = " ".join(str(v) for r in requirements for v in
                       r.get("acceptance_checks", [r.get("acceptance_signal", "")]))
    # When a front has no typed category/kind, only a uniquely scoped
    # requirement (one front, one requirement) may supply its acceptance text.
    candidates = []
    for area in rules["order"]:
        policy = rules["patterns"][area]
        if front_kind in policy["front_kinds"]:
            candidates.append((area, "front_kind:" + front_kind))
        if categories.intersection(policy["categories"]):
            candidates.append((area, "categoria:" + sorted(categories.intersection(policy["categories"]))[0]))
        if signals and re.search(policy["acceptance_regex"], signals):
            candidates.append((area, "acceptance_checks"))
    areas = {x[0] for x in candidates}
    if len(areas) != 1:
        return None, {"method": "UNRESOLVED", "front_id": front.get("front_id"),
                      "candidate_areas": sorted(areas)}
    return next(iter(areas)), {"method": "T1_RULES_V1", "rule": sorted(
        reason for area, reason in candidates if area in areas)[0],
        "rules_ref": "pilot/orchestrator/atomize_rules_v1.json"}


def atomize(package, root, base_head_sha, *, run):
    rules = _rules()
    if (not isinstance(package, dict) or package.get("schema_version") !=
            "ANALYSIS_IMPLEMENTATION_PACKAGE_V1" or
            not isinstance(run, str) or not SAFE.fullmatch(run) or
            not isinstance(base_head_sha, str) or not SHA40.fullmatch(base_head_sha)):
        raise AtomBlocked("ATOM_INPUT_INVALID")
    scopes = {s["scope_id"]: s for s in package["scope_proposals"]}
    req_by_scope = {}
    for item in package["requirements"]:
        req_by_scope.setdefault(item["scope_id"], []).append(item)
    fronts = package["material_fronts"]
    business_rules = package.get("applicable_rules", [])
    rows, provenance, unresolved = [], {}, []
    # One front per semantic atom. A9 fronts are individually accounted for.
    for scope_id in sorted(scopes):
        scope = scopes[scope_id]
        refs = sorted(scope.get("material_front_refs", []))
        selected = [f for f in fronts if f["front_id"] in refs and scope_id in f["scope_ids"]]
        if len(selected) != len(refs):
            raise AtomBlocked("ATOM_FRONT_COVERAGE_INVALID:" + scope_id)
        reqs = req_by_scope.get(scope_id, [])
        if not reqs:
            raise AtomBlocked("ATOM_REQUIREMENT_MISSING:" + scope_id)
        for front in sorted(selected, key=lambda f: f["front_id"]):
            related = [r for r in reqs if any(rule.get("requirement_id") == r["requirement_id"]
                       and rule.get("front_id") == front["front_id"] for rule in business_rules)]
            # Old synthetic A9 samples have one front/requirement in each scope.
            if not related and len(refs) == 1 and len(reqs) == 1:
                related = reqs
            if not related and not (front.get("execution_area") in rules["order"]
                                    and isinstance(front.get("source_ref"), str)
                                    and front["source_ref"]):
                unresolved.append({"scope_id": scope_id, "front_id": front["front_id"],
                                   "why": {"method": "NO_RULE_OR_REQUIREMENT"}})
                continue
            area, area_source = _area(front, related, business_rules, rules)
            if area is None:
                unresolved.append({"scope_id": scope_id, "front_id": front["front_id"],
                                   "why": area_source})
                continue
            module = _slug(scope_id)
            atom_id = "ATOM-" + hashlib.sha256((scope_id + "|" + front["front_id"]).encode()).hexdigest()[:12]
            paths = _route(area, module, rules, root)
            groups = [paths[i:i + rules["max_paths"]] for i in range(0, len(paths), rules["max_paths"])]
            for i, group in enumerate(groups):
                suffix = ("-" + str(i + 1)) if len(groups) > 1 else ""
                identifier = atom_id + suffix
                row = {"atom_id": identifier, "scope_id": scope_id,
                       "front_id": front["front_id"], "area": area,
                       "paths": group, "depends_on": [],
                       "outcome_id": "OUTCOME-" + identifier,
                       "business_outcome": " | ".join(r["outcome"] for r in sorted(
                           related, key=lambda x: x["requirement_id"]))}
                rows.append(row)
                provenance[identifier] = {
                    "scope_id": {"source": "A9.scope_proposals", "value": scope_id},
                    "front_id": {"source": "A9.material_fronts", "value": front["front_id"]},
                    "area": area_source,
                    "paths": {"source": "pilot/orchestrator/atomize_rules_v1.json",
                              "route": area},
                    "business_outcome": {"source": "A9.requirements",
                                         "requirement_ids": [r["requirement_id"] for r in related]},
                    "atom_id": {"source": "SHA256(scope_id|front_id)"},
                    "outcome_id": {"source": "atom_id"},
                }
    if unresolved:
        raise AtomBlocked("ATOM_AREA_UNRESOLVED:" + json.dumps(
            unresolved, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    order = {a: i for i, a in enumerate(rules["order"])}
    # Across scopes chain all areas in stable order; no imaginary dependencies.
    rows.sort(key=lambda r: (order[r["area"]], r["scope_id"], r["atom_id"]))
    last = None
    for row in rows:
        if last is not None and order[last["area"]] < order[row["area"]]:
            row["depends_on"] = [last["atom_id"]]
        last = row
        provenance[row["atom_id"]]["depends_on"] = {
            "source": "T1_AREA_ORDER", "order": rules["order"]}
    return {
        "schema_version": "T1_ATOMIZED_INPUTS_V1",
        "simulation_only": True,
        "project_ref": "lf_java",
        "target_binding": {
            "repo_full_name": REPO,
            "base_head_sha": base_head_sha,
            "target_binding_ref": "atomize://t1/" + run,
        },
        "atoms": rows,
        "provenance": provenance,
        "rules_sha256": hashlib.sha256(RULES.read_bytes()).hexdigest(),
    }
