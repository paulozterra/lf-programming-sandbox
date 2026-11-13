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
    if (status.get("stage") not in ("INTAKE_ACCEPTED", "LOTS_PLANNED")
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



# Owner decision is a bounded sandbox routing authorization, not LF authority.
# Paths are proposed future write boundaries: no Java files are created here.
AUTH_PATHS = [
    "apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java",
    "apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java",
    "apps/time-service/src/main/java/lf/sandbox/time/auth/AuthUser.java",
    "apps/time-service/src/main/java/lf/sandbox/time/auth/AuthConfiguration.java",
]
OWNER_FILE = "owner_area_decision.json"
OWNER_SCHEMA = "F51_OWNER_AREA_DECISION_SANDBOX_V1"


def _decision(package, folder, slug):
    decision_path = folder / OWNER_FILE
    if not decision_path.exists():
        return None
    if decision_path.is_symlink() or not decision_path.is_file():
        blocked("F51_OWNER_DECISION_INVALID")
    try:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError):
        blocked("F51_OWNER_DECISION_INVALID")
    expected_requirements = sorted(x["requirement_id"] for x in package["requirements"])
    expected_fronts = sorted(x["front_id"] for x in package["material_fronts"])
    if (not isinstance(decision, dict)
            or decision.get("schema_version") != OWNER_SCHEMA
            or decision.get("decision_type") != "OWNER_DECISION_SANDBOX"
            or decision.get("decided_by") != "Paulo"
            or decision.get("role") != "owner"
            or decision.get("date") != "2026-11-12"
            or decision.get("request_id") != slug
            or decision.get("scope_id") != "SBX-AUTH-LOGIN"
            or decision.get("area") != "BACKEND"
            or decision.get("lot_count") != 1
            or decision.get("requirement_ids") != expected_requirements
            or decision.get("front_ids") != expected_fronts
            or decision.get("analysis_sha256") !=
               hashlib.sha256(intake.canonical(package)).hexdigest()
            or decision.get("analysis_gap_pending_before_lf") is not True
            or decision.get("sandbox_only") is not True
            or decision.get("production_authority") is not False
            or decision.get("handoff_allowed") is not False
            or decision.get("pg01_consumer_verified") is not False
            or decision.get("default_users_source") != "apps/time-service/.env.example"
            or decision.get("password_hash_algorithm") != "BCrypt"
            or decision.get("data_migration_required") is not False):
        blocked("F51_OWNER_DECISION_INVALID")
    return decision


def _planning_fixture(package, decision, base_head_sha):
    if (not isinstance(base_head_sha, str) or len(base_head_sha) != 40
            or any(ch not in "0123456789abcdef" for ch in base_head_sha)):
        blocked("F51_BASE_SHA_INVALID")
    # PG-04 receives the original source requirements through plan_lots:
    # one real A9 scope/atom, all six unmodified outcomes and acceptance
    # signals. The atom's business outcome is an exact concatenation only.
    return {
        "schema_version": "CP33_SIMULATED_INPUTS_V1",
        "simulation_only": True,
        "project_ref": "lf_java",
        "target_binding": {
            "repo_full_name": "paulozterra/lf-programming-sandbox",
            "base_head_sha": base_head_sha,
            "target_binding_ref": "fixture://f5-login/owner-decision",
        },
        "profile_choices": {"BACKEND": "PERFIL-PROG-BACKEND-SPRING-EXP"},
        "owner_area_decision": {
            "schema_version": OWNER_SCHEMA,
            "decision_type": "OWNER_DECISION_SANDBOX",
            "simulation_only": True,
            "production_authority": False,
            "area": "BACKEND",
            "scope_id": decision["scope_id"],
            "front_ids": list(decision["front_ids"]),
        },
        "atoms": [{
            "atom_id": "ATOM-F5-LOGIN-BACKEND",
            "scope_id": decision["scope_id"],
            "front_id": decision["front_ids"][0],
            "area": "BACKEND",
            "paths": list(AUTH_PATHS),
            "depends_on": [],
            "outcome_id": "OUTCOME-F5-LOGIN-BACKEND",
            "business_outcome": "\\n".join(
                r["outcome"] for r in package["requirements"]),
        }],
    }


def _business_context(package, decision):
    rules = package["applicable_rules"]
    ids = {r["requirement_id"] for r in rules}
    if (len(rules) != 6 or ids != set(decision["requirement_ids"])
            or len({r["rule_code"] for r in rules}) != len(rules)
            or package["programming_context_snapshot"]["applicable_rules"] != rules):
        blocked("F51_BUSINESS_RULE_COVERAGE_INVALID")
    return {
        "schema_version": "F51_CANDIDATE_BUSINESS_RULES_V1",
        "area": "BACKEND",
        "registration_status": "NOT_REGISTERED",
        "status": "CANDIDATE_ONLY",
        "source_analysis_sha256": decision["analysis_sha256"],
        "owner_decision_ref": "pilot/runs/f5-login/" + OWNER_FILE,
        "rules": deepcopy(rules),
        "requirements": deepcopy(package["requirements"]),
        "production_authority": False,
    }


def _write_once(path, value):
    content = intake.canonical(value)
    if path.is_symlink():
        blocked("F51_OUTPUT_PATH_INVALID")
    if path.exists():
        if path.read_bytes() != content:
            blocked("F51_OUTPUT_DRIFT:" + path.name)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out:
            out.write(content)


def prepare_legacy(root, slug, *, base_head_sha=None):
    package, state = read_package(root, slug)
    assessment = derive(package)
    folder = Path(root) / "pilot/runs" / slug
    owner = _decision(package, folder, slug)
    if owner is None:
        # Preserve the original exact fail-closed code and behavior.
        if not assessment["business_rules_by_area"]["DATA"]:
            blocked("F51_DATA_REQUIREMENT_NOT_SOURCE_BOUND")
        blocked("F51_PG04_SCOPE_PARTITION_NOT_SOURCE_BOUND")
    if slug != "f5-login":
        blocked("F51_OWNER_DECISION_SCOPE_INVALID")
    context = _business_context(package, owner)
    _write_once(Path(root) / ".lf/worker-context/f5backend/reglas_tecnicas.json",
                technical_rules("BACKEND"))
    _write_once(Path(root) / ".lf/worker-context/f5backend/reglas_negocio.json",
                context)
    # For already planned runs, the fixture is immutable and the original
    # planner provides the canonical drift + state checks.
    fixture_path = folder / "planning_fixture.json"
    if fixture_path.exists():
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if (fixture.get("schema_version") != "CP33_SIMULATED_INPUTS_V1"
                or fixture.get("target_binding", {}).get("target_binding_ref") !=
                "fixture://f5-login/owner-decision"):
            blocked("F51_PLANNING_FIXTURE_INVALID")
    else:
        if not base_head_sha:
            blocked("F51_BASE_SHA_REQUIRED")
        fixture = _planning_fixture(package, owner, base_head_sha)
        _write_once(fixture_path, fixture)
    planned = plan_lots.plan(Path(root), slug)
    if len(planned["lots"]) != 1:
        blocked("F51_LOT_COUNT_INVALID")
    lot = planned["lots"][0]
    if (lot["area"] != "BACKEND"
            or len(lot["write_paths"]) > 6
            or sorted(lot["write_paths"]) != sorted(AUTH_PATHS)
            or lot["depends_on"] != []
            or sorted(lot["requirement_ids"]) != owner["requirement_ids"]
            or lot["production_authority"] is not False
            or planned.get("worker_invoked") is not False):
        blocked("F51_LOT_OWNER_SCOPE_INVALID")
    return planned


def read_accepted_package(root, slug):
    """T1 accepts the shared intake contract, not F5-specific screen fields."""
    folder = Path(root) / "pilot/runs" / slug
    paths = [folder / name for name in ("request.md", "analysis.json", "state.json")]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        blocked("ATOM_INTAKE_INPUT_MISSING")
    request, raw, raw_state = [p.read_bytes() for p in paths]
    try:
        package, state = json.loads(raw), json.loads(raw_state)
        _, digest = intake.validate(package, request)
    except (ValueError, UnicodeError, intake.IntakeBlocked):
        blocked("ATOM_INTAKE_INVALID")
    if (state.get("stage") not in ("INTAKE_ACCEPTED", "LOTS_PLANNED")
            or state.get("request_sha256") != digest
            or state.get("analysis_sha256") != hashlib.sha256(intake.canonical(package)).hexdigest()
            or state.get("pg01", {}).get("status") != "FIXTURE_UNATTESTED"
            or state.get("production_authority") is not False):
        blocked("ATOM_INTAKE_NOT_ACCEPTED")
    return package, state


def prepare(root, slug, *, base_head_sha=None, legacy=False, contract_mode=False):
    """Default T1 path; old F5.1 owner fixture only via explicit regression flag."""
    if legacy:
        return prepare_legacy(root, slug, base_head_sha=base_head_sha)
    if not base_head_sha:
        blocked("ATOM_BASE_SHA_REQUIRED")
    import atomize
    import generate_chain
    root = Path(root)
    package, state = read_accepted_package(root, slug)
    folder = root / "pilot/runs" / slug
    # Detect pre-T1 owner intervention, but never read or grant authority to it.
    report = {"schema_version": "T1_INTERVENTION_REPORT_V1", "request_id": slug,
              "INTERVENCION_MANUAL": "SI" if (folder/"owner_area_decision.json").exists() else "NO",
              "interventions": (["owner_area_decision.json"] if
                                (folder/"owner_area_decision.json").exists() else []),
              "production_authority": False}
    _write_once(folder/"t1_interventions.json", report)
    try:
        generated = atomize.atomize(package, root, base_head_sha, run=slug)
    except atomize.AtomBlocked as exc:
        blocked(str(exc))
    _write_once(folder/"atomized_inputs.json", generated)
    planned = plan_lots.plan(root, slug, contract_mode=contract_mode)
    generate_chain.generate(root, slug, planned)
    return planned


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--request-id", default="f5-login")
    p.add_argument("--base-head-sha", default=None)
    p.add_argument("--legacy", action="store_true")
    p.add_argument("--with-contract", action="store_true", help="CP1.5 T2 contract mode")
    args = p.parse_args()
    try:
        result = prepare(args.root, args.request_id, base_head_sha=args.base_head_sha,
                         legacy=args.legacy, contract_mode=args.with_contract)
        print("F51_LOTS_PLANNED:" + args.request_id + ":" + str(len(result["lots"])))
    except PackageLotsBlocked as exc:
        print("F51_BLOCKED:" + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
