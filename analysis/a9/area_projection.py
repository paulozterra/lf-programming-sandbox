"""A9 area-level obligation ownership. Source-agnostic PG04-compatible projection."""
from __future__ import annotations

from copy import deepcopy


class AreaOwnershipGap(ValueError):
    pass


def project(scope_id, requirements, fronts, *, readiness):
    if not isinstance(scope_id, str) or not scope_id:
        raise AreaOwnershipGap("A9_AREA_SCOPE_INVALID")
    if not isinstance(fronts, list) or not fronts:
        raise AreaOwnershipGap("A9_AREA_FRONTS_EMPTY")
    reqs = deepcopy(requirements)
    projected = deepcopy(fronts)
    origins = {r["requirement_id"]: deepcopy(r) for r in reqs}
    if len(origins) != len(reqs):
        raise AreaOwnershipGap("A9_AREA_REQUIREMENT_DUPLICATED")
    area_order = [f["execution_area"] for f in projected]
    if len(area_order) != len(set(area_order)):
        raise AreaOwnershipGap("A9_AREA_DUPLICATE_FRONT")
    source_areas = {
        rid: [f["execution_area"] for f in projected
              if rid in f["requirement_ids"]]
        for rid in origins
    }
    if any(not areas for areas in source_areas.values()):
        raise AreaOwnershipGap("A9_REQUIRED_OBLIGATION_WITHOUT_AREA")
    scopes_by_area = {area: scope_id + "-" + area for area in area_order}
    preferred = {
        rid: f["execution_area"]
        for f in projected for rid in f.get("preferred_owner_ids", [])
    }
    if any(preferred.get(rid, areas[0]) not in areas
           for rid, areas in source_areas.items()):
        raise AreaOwnershipGap("A9_PRIMARY_OWNER_NOT_IN_FRONT")
    owner_area = {rid: preferred.get(rid, areas[0])
                  for rid, areas in source_areas.items()}
    primary_front_by_code = {
        req["source_requirement_id"]:
            next(f["front_id"] for f in projected
                 if f["execution_area"] == owner_area[req["requirement_id"]])
        for req in reqs
    }
    for row in reqs:
        row["scope_id"] = scopes_by_area[owner_area[row["requirement_id"]]]
    derived = []
    for front in projected:
        area = front["execution_area"]
        sid = scopes_by_area[area]
        front["scope_ids"] = [sid]
        ids = []
        refs = {}
        for rid in front["requirement_ids"]:
            if rid not in origins:
                raise AreaOwnershipGap("A9_AREA_FRONT_REQUIREMENT_UNKNOWN")
            source = origins[rid]
            if owner_area[rid] == area:
                new_id = rid
            else:
                new_id = rid + "-" + area
                clone = deepcopy(source)
                clone["requirement_id"] = new_id
                clone["scope_id"] = sid
                clone["derived_from_requirement_id"] = rid
                clone["execution_area"] = area
                clone["area_binding_evidence_refs"] = deepcopy(front["evidence_refs"])
                derived.append(clone)
            ids.append(new_id)
            refs[new_id] = deepcopy(source["evidence_refs"])
        front["requirement_ids"] = sorted(ids)
        front["obligation_refs"] = sorted(ids)
        front["requirement_source_refs"] = refs
    reqs.extend(derived)
    if len({r["requirement_id"] for r in reqs}) != len(reqs):
        raise AreaOwnershipGap("A9_AREA_DERIVED_ID_COLLISION")
    scopes = [{
        "scope_id": scopes_by_area[area], "scope_kind": "SCREEN",
        "material_front_refs": [next(f["front_id"] for f in projected
                                     if f["execution_area"] == area)],
        "readiness_candidate": readiness,
        "simulation_mode": projected[0]["simulation_mode"],
    } for area in area_order]
    return reqs, projected, scopes, primary_front_by_code
