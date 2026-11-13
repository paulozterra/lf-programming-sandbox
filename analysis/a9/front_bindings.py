"""T1-A source-derived work fronts for the A9→T1 atomizer boundary.

Original A7 front discovery is retained in the source snapshot. A9 exports
one bounded, non-overlapping write scope per implementation area; each area
front carries the exact source requirement IDs and evidence used to derive it.
The source-only accounting ledger keeps excluded/non-atomized fronts visible.
"""
from __future__ import annotations

import hashlib


class FrontBindingGap(ValueError):
    pass


def _new_id(scope, area):
    return "F3-" + hashlib.sha256((scope + "|T1-A|" + area).encode()).hexdigest()[:16]


def partition(fronts, requirements, sections, effective_rules, *, scope, create_empty_inventory):
    by_code = {r["source_requirement_id"]: r for r in requirements}
    by_ref = {ref: r for r in requirements for ref in r["evidence_refs"]}
    if len(by_code) != len(requirements):
        raise FrontBindingGap("A9_REQUIREMENT_ID_DUPLICATE")
    evidence = {"BACKEND": set(), "FRONTEND": set()}
    ids = {"BACKEND": set(), "FRONTEND": set()}
    non_atomized = []
    gaps = []

    def add(area, req, ref):
        if req not in by_code or not ref:
            raise FrontBindingGap("A9_UNSOURCED_AREA_OR_REQUIREMENT")
        ids[area].add(by_code[req]["requirement_id"])
        evidence[area].add(ref)

    fields = sections.get("fields", [])
    errors = sections.get("errors", [])
    visuals = sections.get("visual", {})
    variants = visuals.get("variants", []) if isinstance(visuals, dict) else []
    if not isinstance(fields, list) or not isinstance(errors, list) or not isinstance(variants, list):
        raise FrontBindingGap("A9_SCREEN_SECTIONS_INVALID")

    # The immutable screen-contract field is a form field, not a database table.
    # REQUIRED fields have sourced server and form-validation obligations.
    for index, field in enumerate(fields):
        code = field.get("field_code")
        rule = "SBX-R-" + code.removeprefix("SBX-F-") if isinstance(code, str) else None
        ref = next((f["candidate_ref"] for f in fronts
                    if f["candidate_ref"].endswith("#contract/fields/" + str(index))), None)
        if field.get("required") is True and field.get("status") == "VIGENTE":
            if rule not in by_code or not ref:
                gaps.append("A9_FIELD_REQUIREMENT_NOT_SOURCED:" + str(code))
            else:
                add("BACKEND", rule, ref)
                add("FRONTEND", rule, ref)
    # A generic API error has two obligations: HTTP response and visible text.
    for index, error in enumerate(errors):
        ref = next((f["candidate_ref"] for f in fronts
                    if f["candidate_ref"].endswith("#contract/errors/" + str(index))), None)
        matches = [code for code, row in effective_rules.items()
                   if row.get("config", {}).get("generic_error") is True and code in by_code]
        if error.get("status") == "VIGENTE" and error.get("generic") is True:
            if len(matches) != 1 or not ref:
                gaps.append("A9_ERROR_REQUIREMENT_NOT_SOURCED:" + str(error.get("error_code")))
            else:
                add("BACKEND", matches[0], ref)
                add("FRONTEND", matches[0], ref)
    visual_refs = [f["candidate_ref"] for f in fronts
                   if "#contract/visual/variants/" in f["candidate_ref"]]
    if variants:
        if len(visual_refs) != len(variants):
            gaps.append("A9_VISUAL_VARIANT_SOURCE_MISSING")
        elif ids["FRONTEND"]:
            evidence["FRONTEND"].update(visual_refs)
        else:
            gaps.append("A9_VISUAL_WITHOUT_REQUIREMENT")

    for front in fronts:
        source = front["candidate_ref"]
        required_codes = set(front.get("obligation_refs", []))
        if source.startswith("A4:unresolved:"):
            if not create_empty_inventory:
                gaps.append("A9_A4_DEPENDENCY_UNRESOLVED:" + source)
                continue
            non_atomized.append({**front, "obligation_mode": "NOT_APPLICABLE",
                "reason": "NON_BLOCKING_GAP_EMPTY_INVENTORY_CREATE",
                "non_blocking_gap": True, "evidence_refs": sorted(set(front["evidence_refs"] + [source])),
                "execution_area": None, "execution_area_source_ref": None})
            continue
        req = by_ref.get(source)
        if req is not None:
            code = req["source_requirement_id"]
            kind = front["front_kind"]
            if kind in ("SECURITY_PRIVACY", "PERMISSION", "API_CONTRACT", "OBSERVABILITY"):
                add("BACKEND", code, source)
            elif kind == "STATE_ERROR":
                # Typed error-state rule + generic_error flag authorizes BE.
                # FE presentation is sourced from errors[] + visual variants.
                if effective_rules.get(code, {}).get("config", {}).get("generic_error") is True:
                    add("BACKEND", code, source)
                else:
                    gaps.append("A9_STATE_ERROR_UNCLASSIFIED:" + source)
            elif kind == "OTHER" and code in ("SBX-R-USER", "SBX-R-PASS"):
                # Source category "flujo" alone is not a technical area.
                # The typed form fields above are the only authority for both.
                if by_code[code]["requirement_id"] not in ids["BACKEND"]:
                    gaps.append("A9_FLOW_FIELD_BINDING_MISSING:" + source)
            elif kind == "OTHER":
                gaps.append("A9_RULE_AREA_UNRESOLVED:" + source)
        if front.get("status") == "NOT_APPLICABLE":
            non_atomized.append({**front, "obligation_mode": "NOT_APPLICABLE"})
        elif (req is None and not source.startswith("A4:unresolved:")
              and source not in evidence["BACKEND"] and source not in evidence["FRONTEND"]):
            # A screen section with no independent obligation is accounted
            # as non-executable evidence, never turned into a fake task.
            has_section = "#contract/" in source
            if not has_section:
                gaps.append("A9_UNSOURCED_REQUIRED_FRONT:" + source)
                continue
            non_atomized.append({**front, "obligation_mode": "NOT_APPLICABLE",
                "reason": "SOURCE_SECTION_HAS_NO_OBLIGATION",
                "execution_area": None, "execution_area_source_ref": None,
                "evidence_refs": sorted(set(front["evidence_refs"] + [source]))})
    if gaps:
        raise FrontBindingGap("A9_FRONT_BINDING_GAP:" + "|".join(sorted(set(gaps))))
    if not ids["BACKEND"] or not ids["FRONTEND"]:
        raise FrontBindingGap("A9_MISSING_IMPLEMENTATION_AREA")
    rows = []
    for area, kind in (("BACKEND", "API_CONTRACT"), ("FRONTEND", "UI_VISUAL")):
        refs = sorted(evidence[area])
        row = {
            "front_id": _new_id(scope, area), "scope_ids": [scope],
            "front_kind": kind, "obligation_mode": "REQUIRED",
            "closure": "CLOSED", "blockers": [],
            "reason": "T1-A split by typed screen fields/errors and approved rule sources",
            "evidence_refs": refs, "source_signal_refs": refs,
            "obligation_refs": sorted(ids[area]), "requirement_ids": sorted(ids[area]),
            "requirement_source_refs": {
                req["requirement_id"]: req["evidence_refs"]
                for req in requirements if req["requirement_id"] in ids[area]
            },
            "execution_area": area, "execution_area_source_ref": refs[0],
            "source_ref": refs[0], "execution_area_policy": "SOURCE_DERIVED",
            "materiality_level": "HIGH", "requires_independent_exam": True,
            "simulation_mode": fronts[0]["simulation_mode"],
        }
        rows.append(row)
    return rows, non_atomized
