"""PG-05_C2 exact write-scope resolution: candidate-only, source-bound, no authorizing writes.

Consumes PG04 exit + PG05_C1. Maps every candidate write-scope token to
explicit, exact repository paths or database objects supplied by a caller.
Does not guess L3 folders, access a repo, allow writes or replace Changeset
Governance's path admission. PG05_C3 owns collision/locks.
"""
import hashlib
import json
import re

class ScopeResolutionBlocked(ValueError):
    pass

_OBJECT=re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")

def _fail(code):
    raise ScopeResolutionBlocked(code)

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _freeze(value, field, code):
    if not isinstance(value,dict):
        _fail(code)
    digest=value.get(field)
    if not isinstance(digest,str) or digest!=_digest({k:v for k,v in value.items() if k!=field}):
        _fail(code)
    return digest

def _strings(value,empty=False):
    return isinstance(value,list) and (empty or bool(value)) and all(isinstance(x,str) and bool(x.strip()) for x in value) and len(set(value))==len(value)

def _path(value):
    if not isinstance(value,str) or not value or len(value)>400 or value.startswith("/") or "\\" in value or ":" in value or any(x in value for x in "*?[]{}\x00") or value.endswith("/"):
        return False
    seg=value.split("/")
    return all(part and part not in (".","..") and not part.isspace() for part in seg)

def _resource(item):
    if not isinstance(item,dict) or set(item)!={"kind","identity","source_ref"}:
        _fail("PG05_SCOPE_RESOURCE_SHAPE_INVALID")
    kind,ident,src=item["kind"],item["identity"],item["source_ref"]
    if not isinstance(src,str) or not src.strip():
        _fail("PG05_SCOPE_RESOURCE_SOURCE_MISSING")
    if kind=="REPO_PATH":
        if not _path(ident):
            _fail("PG05_SCOPE_REPO_PATH_INVALID")
    elif kind=="DB_OBJECT":
        if not isinstance(ident,str) or not _OBJECT.fullmatch(ident):
            _fail("PG05_SCOPE_DB_OBJECT_INVALID")
    else:
        _fail("PG05_SCOPE_RESOURCE_KIND_INVALID")
    return (kind,ident)

def prepare_pg05_c2(*,pg04_exit,pg05_c1,scope_resolutions):
    exit_sha=_freeze(pg04_exit,"candidate_sha256","PG05_SCOPE_EXIT_DIGEST_INVALID")
    c1_sha=_freeze(pg05_c1,"candidate_sha256","PG05_SCOPE_C1_DIGEST_INVALID")
    if (pg04_exit.get("schema_version")!="PG04_TO_PG05_EXIT_CANDIDATE_V1"
        or pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg04_exit.get("pg05_write_allowed") is not False
        or pg04_exit.get("handoff_allowed") is not False
        or pg04_exit.get("production_authority") is not False
        or pg05_c1.get("schema_version")!="PG05_C1_TARGET_BINDING_PREFLIGHT_CANDIDATE_V1"
        or pg05_c1.get("source_pg04_exit_sha256")!=exit_sha
        or pg05_c1.get("write_allowed") is not False
        or pg05_c1.get("branch_created") is not False
        or pg05_c1.get("pg05_admitted") is not False
        or pg05_c1.get("production_authority") is not False):
        _fail("PG05_SCOPE_SOURCE_NOT_CANDIDATE")
    sols=pg04_exit.get("solutions")
    if not isinstance(sols,list) or not sols:
        _fail("PG05_SCOPE_SOLUTIONS_MISSING")
    sol_map={}
    for sol in sols:
        if not isinstance(sol,dict) or not isinstance(sol.get("solution_id"),str) or not sol["solution_id"].strip() or sol["solution_id"] in sol_map:
            _fail("PG05_SCOPE_SOLUTION_ID_INVALID")
        if (not _strings(sol.get("write_scope_candidates")) or not _strings(sol.get("shared_contract_refs"),True)
            or sol.get("shared_contract_access_default")!="READ_ONLY"
            or sol.get("pg05_write_scope_authorized") is not False
            or sol.get("execution_allowed") is not False):
            _fail("PG05_SCOPE_SOLUTION_NOT_UNTRUSTED")
        sol_map[sol["solution_id"]]=sol
    if set(sol_map)!=set(pg05_c1.get("solution_ids",[])):
        _fail("PG05_SCOPE_C1_SOLUTIONS_DRIFT")
    if not isinstance(scope_resolutions,list) or len(scope_resolutions)!=len(sol_map):
        _fail("PG05_SCOPE_RESOLUTION_INCOMPLETE")
    resolutions={}
    for row in scope_resolutions:
        if not isinstance(row,dict) or set(row)!={"solution_id","resolved_scopes","shared_read_refs","l3_structure_ref"}:
            _fail("PG05_SCOPE_RESOLUTION_FIELDS_INVALID")
        sid=row["solution_id"]
        if sid not in sol_map or sid in resolutions:
            _fail("PG05_SCOPE_RESOLUTION_SOLUTION_INVALID")
        if not isinstance(row["l3_structure_ref"],str) or not row["l3_structure_ref"].strip():
            _fail("PG05_SCOPE_L3_STRUCTURE_REF_REQUIRED")
        assigned=row["resolved_scopes"]
        sol=sol_map[sid]
        if not isinstance(assigned,list) or len(assigned)!=len(sol["write_scope_candidates"]):
            _fail("PG05_SCOPE_TOKEN_RESOLUTION_INCOMPLETE")
        by_token={}
        resource_owners={}
        for group in assigned:
            if not isinstance(group,dict) or set(group)!={"scope_token","resources","derivation_ref"}:
                _fail("PG05_SCOPE_GROUP_INVALID")
            token=group["scope_token"]
            if token not in sol["write_scope_candidates"] or token in by_token:
                _fail("PG05_SCOPE_TOKEN_INVALID")
            if not isinstance(group["derivation_ref"],str) or not group["derivation_ref"].strip():
                _fail("PG05_SCOPE_DERIVATION_REF_MISSING")
            resources=group["resources"]
            if not isinstance(resources,list) or not resources:
                _fail("PG05_SCOPE_RESOURCES_MISSING")
            resolved=[]
            for resource in resources:
                key=_resource(resource)
                if key in resource_owners:
                    _fail("PG05_SCOPE_RESOURCE_DUPLICATED_IN_SOLUTION")
                resource_owners[key]=token
                resolved.append({"kind":key[0],"identity":key[1],
                                 "source_ref":resource["source_ref"]})
            by_token[token]={"scope_token":token,"resources":sorted(resolved,key=lambda x:(x["kind"],x["identity"])),
                              "derivation_ref":group["derivation_ref"]}
        if set(by_token)!=set(sol["write_scope_candidates"]):
            _fail("PG05_SCOPE_TOKEN_COVERAGE_DRIFT")
        shared=row["shared_read_refs"]
        if not isinstance(shared,list) or len(shared)!=len(sol["shared_contract_refs"]):
            _fail("PG05_SCOPE_SHARED_READ_INCOMPLETE")
        shared_by_ref={}
        for entry in shared:
            if not isinstance(entry,dict) or set(entry)!={"contract_ref","resource","derivation_ref"}:
                _fail("PG05_SCOPE_SHARED_READ_INVALID")
            ref=entry["contract_ref"]
            if ref not in sol["shared_contract_refs"] or ref in shared_by_ref or not isinstance(entry["derivation_ref"],str) or not entry["derivation_ref"].strip():
                _fail("PG05_SCOPE_SHARED_READ_DRIFT")
            key=_resource(entry["resource"])
            if key in resource_owners:
                _fail("PG05_SCOPE_SHARED_RESOURCE_WRITE_CONFLICT")
            shared_by_ref[ref]={"contract_ref":ref,
                                "resource":{"kind":key[0],"identity":key[1],
                                            "source_ref":entry["resource"]["source_ref"]},
                                "access":"READ_ONLY","derivation_ref":entry["derivation_ref"]}
        if set(shared_by_ref)!=set(sol["shared_contract_refs"]):
            _fail("PG05_SCOPE_SHARED_READ_INCOMPLETE")
        resolutions[sid]={"solution_id":sid,"l3_structure_ref":row["l3_structure_ref"],
                          "resolved_scopes":[by_token[k] for k in sorted(by_token)],
                          "shared_read_refs":[shared_by_ref[k] for k in sorted(shared_by_ref)],
                          "write_resource_keys":sorted([{"kind":k[0],"identity":k[1]} for k in resource_owners],
                                                       key=lambda x:(x["kind"],x["identity"])),
                          "write_authorized":False}
    owner={}
    collisions=[]
    shared_owner={}
    for sid,row in sorted(resolutions.items()):
        for entry in row["write_resource_keys"]:
            key=(entry["kind"],entry["identity"])
            owner.setdefault(key,[]).append(sid)
        for entry in row["shared_read_refs"]:
            resource=entry["resource"]
            shared_owner.setdefault((resource["kind"],resource["identity"]),[]).append(sid)
    for key,sids in sorted(owner.items()):
        if len(sids)>1:
            collisions.append({"kind":key[0],"identity":key[1],
                               "solution_ids":sorted(sids),
                               "classification":"PG05_C3_WRITE_COLLISION_UNRESOLVED"})
    for key,readers in sorted(shared_owner.items()):
        if key in owner:
            collisions.append({"kind":key[0],"identity":key[1],
                               "solution_ids":sorted(set(owner[key]+readers)),
                               "classification":"SHARED_READ_ONLY_WRITE_CONFLICT"})
    out={
        "schema_version":"PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg04_exit_sha256":exit_sha,
        "source_pg05_c1_sha256":c1_sha,
        "target_binding":pg05_c1.get("target_binding"),
        "solution_scopes":[resolutions[sid] for sid in sorted(resolutions)],
        "collisions_for_pg05_c3":collisions,
        "l3_structure_currentness_verified":False,
        "resource_existence_verified":False,
        "repository_path_admission_executed":False,
        "shared_resources_read_only_default":True,
        "write_scope_derived_from_explicit_bindings":True,
        "write_scope_authorized":False,
        "writer_lock_acquired":False,
        "branch_created":False,
        "pg05_admitted":False,
        "production_authority":False,
        "handoff_allowed":False,
        "first_blocker":("PG05_C3_RESOURCE_COLLISION_REVIEW_REQUIRED" if collisions
                         else "PG05_SCOPE_SOURCE_ATTESTATION_AND_PG04_ADMISSION_REQUIRED"),
        "next_gate":"EXISTING_CHANGESET_GOVERNANCE_PATH_ADMISSION_AND_PG05_C3_LOCK_REVIEW"
    }
    out["candidate_sha256"]=_digest(out)
    return out
