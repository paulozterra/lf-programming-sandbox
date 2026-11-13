"""A9 source-bound partition: no identities, prefixes or code-name inferences.

The verified screen contract explicitly links each field/error/visual variant
to rule source refs. A versioned table describes section-to-area semantics.
Unknown links, missing obligations and unresolved dependencies fail closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

POLICY = Path(__file__).with_name("area_rules_v1.json")


class FrontBindingGap(ValueError):
    pass


def _policy():
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    if (data.get("schema_version") != "A9_AREA_SOURCE_RULES_V1"
            or data.get("source_policy") != "EXPLICIT_RULE_REFS_ONLY"
            or data.get("section_areas") != {
                "fields": ["BACKEND"],
                "errors": ["BACKEND"],
                "visual.variants": ["FRONTEND"],
            }
            or not isinstance(data.get("rule_categories"), dict)):
        raise FrontBindingGap("A9_AREA_POLICY_INVALID")
    return data


def _new_id(scope, area):
    return "F3-" + hashlib.sha256((scope + "|T1-A|" + area).encode()).hexdigest()[:16]


def partition(fronts, requirements, sections, effective_rules, *, scope, create_empty_inventory):
    policy = _policy()
    if not isinstance(scope, str) or not scope:
        raise FrontBindingGap("A9_SCOPE_INVALID")
    if not isinstance(sections, dict) or not isinstance(effective_rules, dict):
        raise FrontBindingGap("A9_SCREEN_SECTIONS_INVALID")
    by_code = {r["source_requirement_id"]: r for r in requirements}
    by_ref = {ref: r for r in requirements for ref in r["evidence_refs"]}
    if len(by_code) != len(requirements) or len(by_ref) != len(requirements):
        raise FrontBindingGap("A9_REQUIREMENT_ID_OR_SOURCE_DUPLICATE")
    approved = {row["source_ref"]: row for row in sections.get("rules", [])
                if isinstance(row, dict) and row.get("source_ref")}
    if not approved or any(not row.get("association_ref") for row in approved.values()):
        raise FrontBindingGap("A9_SCREEN_RULE_ASSOCIATION_MISSING")
    by_front = {row["candidate_ref"]: row for row in fronts}
    ids = {}
    evidence = {}
    linked_sections = set()
    gaps = []
    excluded = []

    def add(area, source_ref, section_ref):
        if source_ref not in by_ref:
            gaps.append("A9_SECTION_RULE_WITHOUT_APPROVED_REQUIREMENT:" + source_ref)
            return
        req = by_ref[source_ref]
        rule = effective_rules.get(req["source_requirement_id"], {})
        if rule.get("source_ref") != source_ref:
            gaps.append("A9_RULE_SOURCE_MISMATCH:" + source_ref)
            return
        # Global effective rules are separately governed; screen-specific
        # obligations must have an actual rule↔screen association.
        if source_ref not in approved and rule.get("binding_source") != "DERIVED_GLOBAL":
            gaps.append("A9_SCREEN_RULE_ASSOCIATION_MISSING:" + source_ref)
            return
        ids.setdefault(area, set()).add(req["requirement_id"])
        evidence.setdefault(area, set()).add(section_ref)
        evidence[area].add(source_ref)
        linked_sections.add(section_ref)

    def consume(section, section_key, predicate):
        items = sections.get(section, [])
        if section == "visual":
            items = items.get("variants", []) if isinstance(items, dict) else None
        if not isinstance(items, list):
            raise FrontBindingGap("A9_SCREEN_SECTION_INVALID:" + section)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise FrontBindingGap("A9_SCREEN_SECTION_INVALID:" + section)
            suffix = ("visual/variants/" if section == "visual" else section + "/") + str(index)
            matches = [ref for ref in by_front if ref.endswith("#contract/" + suffix)]
            if len(matches) != 1:
                gaps.append("A9_SECTION_EVIDENCE_MISSING:" + suffix)
                continue
            ref = matches[0]
            refs = item.get("rule_refs")
            if predicate(item):
                if (not isinstance(refs, list) or not refs
                        or len(refs) != len(set(refs))):
                    gaps.append("A9_SECTION_RULE_REFS_MISSING:" + suffix)
                    continue
                for rule_ref in sorted(refs):
                    if not isinstance(rule_ref, str) or not rule_ref:
                        gaps.append("A9_SECTION_RULE_REF_INVALID:" + suffix)
                        continue
                    for area in policy["section_areas"][section_key]:
                        add(area, rule_ref, ref)

    consume("fields", "fields",
            lambda row: row.get("required") is True and row.get("status") == "VIGENTE")
    consume("errors", "errors",
            lambda row: row.get("status") == "VIGENTE" and row.get("generic") is True)
    consume("visual", "visual.variants",
            lambda row: row.get("status") == "VIGENTE")

    # Each governed requirement either has an explicit screen-section
    # relation, or a typed category whose versioned rule identifies its area.
    for req in requirements:
        code = req["source_requirement_id"]
        rule_ref = req["evidence_refs"][0]
        if any(req["requirement_id"] in owned for owned in ids.values()):
            continue
        rule = effective_rules.get(code)
        if not isinstance(rule, dict) or rule.get("source_ref") != rule_ref:
            gaps.append("A9_REQUIREMENT_EFFECTIVE_RULE_MISSING:" + code)
            continue
        category = rule.get("categoria")
        if not isinstance(category, str):
            gaps.append("A9_RULE_CATEGORY_MISSING:" + code)
            continue
        areas = policy["rule_categories"].get(category.casefold(), [])
        if len(areas) != 1:
            gaps.append("A9_RULE_AREA_UNRESOLVED:" + code)
            continue
        add(areas[0], rule_ref, rule_ref)

    for front in fronts:
        source = front["candidate_ref"]
        if source.startswith("A4:unresolved:"):
            if not create_empty_inventory:
                gaps.append("A9_A4_DEPENDENCY_UNRESOLVED:" + source)
                continue
            excluded.append({**front, "obligation_mode": "NOT_APPLICABLE",
                "reason": "NON_BLOCKING_GAP_EMPTY_INVENTORY_CREATE",
                "non_blocking_gap": True,
                "evidence_refs": sorted(set(front["evidence_refs"] + [source])),
                "execution_area": None, "execution_area_source_ref": None})
        elif front.get("status") == "NOT_APPLICABLE":
            excluded.append({**front, "obligation_mode": "NOT_APPLICABLE"})
        elif ("#contract/" in source and source not in linked_sections):
            if source.endswith("#contract/context") or source.endswith("#contract/metadata"):
                excluded.append({**front, "obligation_mode": "NOT_APPLICABLE",
                    "reason": "SOURCE_SECTION_HAS_NO_OBLIGATION",
                    "execution_area": None, "execution_area_source_ref": None,
                    "evidence_refs": sorted(set(front["evidence_refs"] + [source]))})
            elif any(x in source for x in ("#contract/fields/", "#contract/errors/",
                                            "#contract/visual/variants/")):
                gaps.append("A9_REQUIRED_SECTION_UNBOUND:" + source)
            else:
                excluded.append({**front, "obligation_mode": "NOT_APPLICABLE",
                    "reason": "SOURCE_SECTION_HAS_NO_OBLIGATION",
                    "execution_area": None, "execution_area_source_ref": None,
                    "evidence_refs": sorted(set(front["evidence_refs"] + [source]))})
        elif (source not in linked_sections
              and source not in by_ref
              and not source.startswith("A6:requirement:")):
            gaps.append("A9_UNSOURCED_REQUIRED_FRONT:" + source)
    if gaps:
        raise FrontBindingGap("A9_FRONT_BINDING_GAP:" + "|".join(sorted(set(gaps))))
    if not ids or any(not value for value in ids.values()):
        raise FrontBindingGap("A9_MISSING_IMPLEMENTATION_AREA")
    rows = []
    ordered_areas = [area for area in ("DATA", "BACKEND", "FRONTEND") if area in ids]
    for area in ordered_areas:
        refs = sorted(evidence[area])
        if area == "FRONTEND":
            area_source = next((ref for ref in refs
                                if "#contract/visual/variants/" in ref), refs[0])
        elif area == "BACKEND":
            area_source = next((ref for ref in refs
                                if "#contract/fields/" in ref or "#contract/errors/" in ref), refs[0])
        else:
            area_source = refs[0]
        kind = {"DATA": "DATA_CONTRACT", "BACKEND": "API_CONTRACT",
                "FRONTEND": "UI_VISUAL"}[area]
        rows.append({
            "front_id": _new_id(scope, area), "scope_ids": [scope],
            "front_kind": kind, "obligation_mode": "REQUIRED",
            "closure": "CLOSED", "blockers": [],
            "reason": "A9 section-to-area and explicit source rule relations",
            "evidence_refs": refs, "source_signal_refs": refs,
            "obligation_refs": sorted(ids[area]), "requirement_ids": sorted(ids[area]),
            "requirement_source_refs": {
                req["requirement_id"]: req["evidence_refs"]
                for req in requirements if req["requirement_id"] in ids[area]
            },
            "execution_area": area, "execution_area_source_ref": area_source,
            "source_ref": area_source, "execution_area_policy": "SOURCE_DERIVED",
            "area_rule_version": policy["schema_version"],
            "materiality_level": "HIGH", "requires_independent_exam": True,
            "simulation_mode": fronts[0]["simulation_mode"],
        })
    return rows, excluded
