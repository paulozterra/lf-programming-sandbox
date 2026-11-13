"""T1-A: source-only A9 front/requirement binding. No guessed area or obligation.

A source identifies an obligation only if it is an A6 rule ref or a
typed screen-field/error code that matches an independently sourced rule.
Unresolved front coverage is an explicit material gap, never READY.
"""
from __future__ import annotations

AREAS = {
    "DATA_CONTRACT": "DATA",
    "DATABASE_SCHEMA": "DATA",
    "API_CONTRACT": "BACKEND",
    "PERMISSION": "BACKEND",
    "SECURITY_PRIVACY": "BACKEND",
    "OBSERVABILITY": "BACKEND",
    "UI_VISUAL": "FRONTEND",
    "UI_INTERACTION": "FRONTEND",
    "RESPONSIVE": "FRONTEND",
    "ACCESSIBILITY": "FRONTEND",
}


def bind(front, requirements, screen_sections, effective_rules):
    """Returns a new front, preserving original A7 evidence and identity."""
    row = dict(front)
    refs = set(row.get("evidence_refs", []))
    by_code = {r["source_requirement_id"]: r for r in requirements}
    ids = {r["requirement_id"] for r in requirements if refs.intersection(r["evidence_refs"])}
    candidate = row.get("candidate_ref", "")
    source = None

    # The typed screen field code carries the exact rule suffix; require
    # matching source status and a real A6 obligation, not a prose guess.
    if "#contract/fields/" in candidate:
        try:
            ix = int(candidate.rsplit("/", 1)[1])
            field = screen_sections["fields"][ix]
            code = "SBX-R-" + field["field_code"].removeprefix("SBX-F-")
            if field.get("status") == "VIGENTE" and field.get("required") is True and code in by_code:
                ids.add(by_code[code]["requirement_id"])
                source = candidate
        except (KeyError, ValueError, IndexError, TypeError):
            pass
    elif "#contract/errors/" in candidate:
        try:
            ix = int(candidate.rsplit("/", 1)[1])
            error = screen_sections["errors"][ix]
            matches = [code for code, item in effective_rules.items()
                       if item.get("config", {}).get("generic_error") is True
                       and code in by_code]
            if error.get("status") == "VIGENTE" and error.get("generic") is True and len(matches) == 1:
                ids.add(by_code[matches[0]]["requirement_id"])
                source = candidate
        except (KeyError, ValueError, IndexError, TypeError):
            pass

    # An A6 requirement front inherits its exact pinned rule source. Other
    # screen-level context/metadata/visual evidence cannot manufacture a
    # relationship to any one requirement.
    obligation_refs = sorted(ids)
    row["obligation_refs"] = obligation_refs
    row["requirement_ids"] = obligation_refs
    row["requirement_source_refs"] = {rid: sorted(by_code[r["source_requirement_id"]]["evidence_refs"])
                                     for rid in obligation_refs for r in requirements
                                     if r["requirement_id"] == rid}
    kind = row["front_kind"]
    area = AREAS.get(kind)
    if kind == "STATE_ERROR":
        # API behavior and visible error message are distinct potential areas.
        # A7's UNKNOWN hint is not evidence of either side.
        area = None
    if kind == "OTHER":
        area = None
    row["execution_area"] = area
    row["execution_area_source_ref"] = (source or (sorted(refs)[0] if refs else None)) if area else None
    # Compatibility with T1 atomize._area (requires the name source_ref).
    row["source_ref"] = row["execution_area_source_ref"]
    gaps = []
    if row["obligation_mode"] == "REQUIRED" and not obligation_refs:
        gaps.append("A9_REQUIRED_FRONT_WITHOUT_REQUIREMENT")
    if row["obligation_mode"] == "REQUIRED" and not area:
        gaps.append("A9_FRONT_AREA_NOT_SOURCE_RESOLVED")
    row["front_gaps"] = gaps
    if gaps:
        row["closure"] = "BLOCKED"
        row["blockers"] = sorted(set(row["blockers"] + gaps))
        row["reason"] += "; A9 source-only binding gap"
    return row
