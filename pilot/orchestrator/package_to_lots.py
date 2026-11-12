#!/usr/bin/env python3
"""F5.1 candidate package-to-PG04 bridge. No model, no owner decision inference.

The stock plan_lots._inputs contract permits exactly one atom per scope, each
with a sourced requirement. The A9 Login package has ONE scope and no A6
obligation explicitly bound to its DATA_CONTRACT fronts. This adapter blocks
instead of inventing a DATA requirement or silently assigning UNKNOWN fronts.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import intake
import plan_lots

CANDIDATES = {
    "DATA_CONTRACT": "DATA",
    "API_CONTRACT": "BACKEND",
    "PERMISSION": "BACKEND",
    "SECURITY_PRIVACY": "BACKEND",
    "OBSERVABILITY": "BACKEND",
}
BUSINESS_KEYS = ("rule_code", "source_ref", "source_status", "source_attested",
                 "titulo", "categoria", "valor_config", "es_transversal",
                 "origen", "front_id", "requirement_id")
PG00 = ROOT / "pilot/lf_profiles_pinned/stack_skills_exp/pg00_normative_catalog_snapshot.json"
PG00_SOURCES = ROOT / "pilot/lf_profiles_pinned/stack_skills_exp/pg00_catalog_sources_exp.json"


class PackageLotsBlocked(ValueError):
    pass


def blocked(code):
    raise PackageLotsBlocked(code)


def read_package(root, slug):
    folder = root / "pilot/runs" / slug
    if folder.is_symlink():
        blocked("F51_RUN_PATH_INVALID")
    paths = [folder / name for name in ("request.md", "analysis.json", "state.json")]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        blocked("F51_INTAKE_INPUT_MISSING")
    raw, analysis, state = [p.read_bytes() for p in paths]
    package = json.loads(analysis)
    _, request_sha = intake.validate(package, raw)
    status = json.loads(state)
    if (status.get("stage") != "INTAKE_ACCEPTED"
            or status.get("request_sha256") != request_sha
            or status.get("analysis_sha256") != hashlib.sha256(intake.canonical(package)).hexdigest()
            or status.get("pg01", {}).get("status") != "FIXTURE_UNATTESTED"):
        blocked("F51_INTAKE_NOT_ACCEPTED")
    if (package.get("simulation_mode") != "SIMULATED_SANDBOX_ONLY"
            or package.get("package_readiness_candidate") != "READY_CANDIDATE"
            or package.get("research_stop", {}).get("decision") != "STOP"):
        blocked("F51_ANALYSIS_NOT_READY")
    return package, status


def technical_rules(area):
    """Source rule text *only* from PG00 pinned snapshot, never business A9."""
    if area not in ("DATA", "BACKEND"):
        blocked("F51_AREA_UNKNOWN")
    catalogue = json.loads(PG00.read_text(encoding="utf-8"))
    source = json.loads(PG00_SOURCES.read_text(encoding="utf-8"))
    if (catalogue.get("schema_version") != "LF_STANDARDS_CATALOG_V1"
            or source.get("schema_version") != "LF_PG00_STANDARD_SOURCE_POINTERS_EXP_V2"
            or source.get("catalog_version") != catalogue.get("catalog_version")
            or source.get("source_git_blob_sha1") is None):
        blocked("F51_PG00_SOURCE_INVALID")
    families = {"STD-DB", "STD-SEC"} if area == "DATA" else {"STD-BE", "STD-SEC"}
    rows = [{k: deepcopy(rule[k]) for k in ("id", "domain", "rule", "severity", "status")}
            for rule in catalogue["rules"]
            if rule.get("domain") in families]
    if not rows or {r["domain"] for r in rows} != families:
        blocked("F51_PG00_FAMILY_MISSING")
    return {
        "schema_version": "F51_PG00_TECHNICAL_RULES_V1",
        "area": area, "source_ref": source["source_ref"],
        "source_blob_sha1": source["source_git_blob_sha1"],
        "catalog_version": catalogue["catalog_version"],
        "families": sorted(families), "rules": rows,
        "production_authority": False,
    }


def derive(package):
    """Assess the exact A9 business-to-front binding without guessing areas."""
    scopes = package["scope_proposals"]
    if len(scopes) != 1:
        blocked("F51_SCOPE_COUNT_UNSUPPORTED")
    scope = scopes[0]
    if not scope["material_front_refs"]:
        blocked("F51_EMPTY_MATERIAL_FRONT_COVERAGE")
    fronts = {f["front_id"]: f for f in package["material_fronts"]}
    rules = package.get("applicable_rules")
    if not isinstance(rules, list):
        blocked("F51_TYPED_BUSINESS_RULES_MISSING")
    requirements = {r["requirement_id"]: r for r in package["requirements"]}
    if len(requirements) != len(package["requirements"]):
        blocked("F51_REQUIREMENTS_DUPLICATED")
    attributed = {"DATA": [], "BACKEND": []}
    unknown, unassigned = [], []
    for rule in rules:
        if not isinstance(rule, dict) or any(key not in rule for key in BUSINESS_KEYS):
            blocked("F51_BUSINESS_RULE_FIELDS_MISSING")
        rid, fid = rule["requirement_id"], rule["front_id"]
        if rid not in requirements or fid not in fronts:
            blocked("F51_BUSINESS_RULE_UNBOUND")
        f = fronts[fid]
        if rule["source_ref"] not in requirements[rid]["evidence_refs"]:
            blocked("F51_BUSINESS_RULE_SOURCE_MISMATCH")
        if f["closure"] != "CLOSED":
            blocked("F51_MATERIAL_FRONT_NOT_CLOSED")
        area = CANDIDATES.get(f.get("front_kind"), "UNKNOWN")
        # A7's execution_area_hint is a SANDBOX_HINT, not owner authority.
        if area == "UNKNOWN":
            unassigned.append({"requirement_id": rid, "front_id": fid,
                               "front_kind": f["front_kind"], "reason": "PG04_AREA_UNDETERMINED"})
        else:
            attributed[area].append(deepcopy(rule))
    for f in package["material_fronts"]:
        if f["front_id"] not in {r["front_id"] for r in rules} and f.get("front_kind") not in CANDIDATES:
            unknown.append({"front_id": f["front_id"], "front_kind": f["front_kind"],
                            "reason": "UNBOUND_UNKNOWN_FRONT_REQUIRES_PG04"})
    return {
        "schema_version": "F51_PACKAGE_TO_LOTS_ASSESSMENT_V1",
        "request_scope_id": scope["scope_id"],
        "business_rules_by_area": attributed,
        "unassigned_business_rules": unassigned,
        "unassigned_material_fronts": unknown,
        "pg04_area_resolution_pending": bool(unknown or unassigned),
        "production_authority": False, "worker_invoked": False,
    }


def prepare(root, slug):
    package, state = read_package(root, slug)
    assessment = derive(package)
    # plan_lots requires one atom per scope, each with >=1 requirement.
    # No A6 requirement currently belongs to a DATA_CONTRACT front, even
    # though A7 reports two DATA_CONTRACT screen-field candidates.
    if not assessment["business_rules_by_area"]["DATA"]:
        blocked("F51_DATA_REQUIREMENT_NOT_SOURCE_BOUND")
    if assessment["pg04_area_resolution_pending"]:
        blocked("F51_PG04_UNKNOWN_FRONT_NEEDS_DECISION")
    # Implementation of PG04 planning is deliberately fail-closed until
    # source-bound per-area scopes exist; never forge scope IDs or DoD.
    blocked("F51_PG04_SCOPE_PARTITION_NOT_SOURCE_BOUND")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--request-id", default="f5-login")
    args = p.parse_args()
    try:
        prepare(args.root, args.request_id)
    except PackageLotsBlocked as exc:
        print("F51_BLOCKED:" + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
