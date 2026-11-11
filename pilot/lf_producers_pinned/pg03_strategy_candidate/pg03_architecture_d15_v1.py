"""PG-03_C10 architecture D15 source-only conformance assessment.

Validates a caller-supplied exact-revision D15 profile and D14 resource declarations.
Never authenticates repository provenance, approves ADRs, or grants deployment authority.
"""
from collections.abc import Mapping
import re

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")

class ArchitectureBlocked(ValueError):
    pass

def _id(value, code):
    if not isinstance(value, str) or not value.strip():
        raise ArchitectureBlocked(code)
    return value

def assess_architecture(*, strategy, profile, pieces):
    if not isinstance(strategy, Mapping) or strategy.get("status") != "CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False or strategy.get("handoff_allowed") is not False:
        raise ArchitectureBlocked("STRATEGY_UNTRUSTED")
    if not isinstance(profile, Mapping):
        raise ArchitectureBlocked("D15_PROFILE_MISSING")
    for name in ("repository", "source_ref"):
        _id(profile.get(name), "D15_PROVENANCE_MISSING")
    if not isinstance(profile.get("commit_sha"),str) or not SHA40.fullmatch(profile["commit_sha"]) or not isinstance(profile.get("sha256"),str) or not SHA64.fullmatch(profile["sha256"]):
        raise ArchitectureBlocked("D15_EXACT_GIT_BINDING_INVALID")
    units = profile.get("deployment_units")
    if not isinstance(units,list) or not units:
        raise ArchitectureBlocked("D15_UNITS_MISSING")
    available={}
    for unit in units:
        if not isinstance(unit,Mapping):
            raise ArchitectureBlocked("D15_UNIT_INVALID")
        uid=_id(unit.get("id"),"D15_UNIT_ID_INVALID")
        if uid in available:
            raise ArchitectureBlocked("D15_UNIT_DUPLICATE")
        modules=unit.get("modules")
        if not isinstance(modules,list) or not modules or any(not isinstance(m,str) or not m.strip() for m in modules) or len(set(modules))!=len(modules):
            raise ArchitectureBlocked("D15_MODULES_INVALID")
        resources=unit.get("allowed_resources")
        if not isinstance(resources,list) or any(not isinstance(x,str) or not x.strip() for x in resources) or len(set(resources))!=len(resources):
            raise ArchitectureBlocked("D15_RESOURCES_INVALID")
        available[uid]={"modules":set(modules),"resources":set(resources)}
    if not isinstance(pieces,list) or not pieces:
        raise ArchitectureBlocked("ARCHITECTURE_PIECES_MISSING")
    seen=set()
    deviations=[]
    locations=[]
    scopes=strategy.get("scope_ids")
    if not isinstance(scopes,list) or not scopes:
        raise ArchitectureBlocked("STRATEGY_SCOPES_MISSING")
    for piece in pieces:
        if not isinstance(piece,Mapping):
            raise ArchitectureBlocked("ARCHITECTURE_PIECE_INVALID")
        pid=_id(piece.get("piece_id"),"PIECE_ID_INVALID")
        if pid in seen:
            raise ArchitectureBlocked("PIECE_DUPLICATE")
        seen.add(pid)
        scope=_id(piece.get("scope_id"),"PIECE_SCOPE_MISSING")
        if scope not in scopes:
            raise ArchitectureBlocked("PIECE_SCOPE_UNCLASSIFIED")
        uid=_id(piece.get("deployment_unit"),"PIECE_UNIT_MISSING")
        module=_id(piece.get("module"),"PIECE_MODULE_MISSING")
        declared=piece.get("resources")
        if not isinstance(declared,list) or any(not isinstance(x,str) or not x.strip() for x in declared) or len(set(declared))!=len(declared):
            raise ArchitectureBlocked("D14_RESOURCE_DECLARATION_REQUIRED")
        if uid not in available or module not in available[uid]["modules"] or not set(declared).issubset(available[uid]["resources"]):
            deviations.append({"piece_id":pid,"code":"D15_PROFILE_DEVIATION","route":"REQUIRES_DECISION_ADR_PROPOSAL"})
        locations.append({"piece_id":pid,"scope_id":scope,"deployment_unit":uid,"module":module,"resources":sorted(declared)})
    return {
        "schema_version":"PG03_C10_D15_ARCHITECTURE_CANDIDATE_V1",
        "status":"REQUIRES_DECISION" if deviations else "CANDIDATE_CONFORMANT_NOT_ADMITTED",
        "production_authority":False,"deployment_allowed":False,"handoff_allowed":False,
        "d15_source_ref":profile["source_ref"],"d15_commit_sha":profile["commit_sha"],"d15_sha256":profile["sha256"],
        "locations":sorted(locations,key=lambda x:x["piece_id"]),
        "deviations":sorted(deviations,key=lambda x:x["piece_id"]),
        "source_authenticity":"UNVERIFIED",
        "reason":"ADR_DECISION_REQUIRED" if deviations else "D15_SOURCE_AND_D14_DECLARATIONS_NOT_AUTHENTICATED"
    }
