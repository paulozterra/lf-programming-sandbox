"""PG-05_C4 fail-closed candidate change boundary classifier (non-executable).

Never authorizes writes, grants locks or replaces repository path admission.
Each solution's proposed diff is evaluated independently against the exact
C2 resources and C3 lock plan. Unknown changes and cross-solution changes block
only their submitting solution; other solutions remain NOT_ADMITTED.
"""
import hashlib
import json
import re

class WriteBoundaryBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")
_SHA40=re.compile(r"^[0-9a-f]{40}$")
_PATH=lambda x:isinstance(x,str) and bool(x) and not x.startswith("/") and "\\" not in x and ":" not in x and not any(ch in x for ch in "*?[]{}\x00") and all(p not in ("",".","..") for p in x.split("/"))
_DB=re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")

def _deny(code):raise WriteBoundaryBlocked(code)
def _digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _frozen(value,schema,reason):
    if not isinstance(value,dict) or value.get("schema_version")!=schema:
        _deny(reason)
    sh=value.get("candidate_sha256")
    if not isinstance(sh,str) or not _SHA.fullmatch(sh) or sh!=_digest({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _deny(reason)
    return sh

def _key(value):
    if not isinstance(value,dict) or set(value)!={"kind","identity"}:
        _deny("PG05_C4_RESOURCE_SHAPE_INVALID")
    kind,identity=value["kind"],value["identity"]
    if kind=="REPO_PATH" and _PATH(identity):return (kind,identity)
    if kind=="DB_OBJECT" and isinstance(identity,str) and _DB.fullmatch(identity):return (kind,identity)
    _deny("PG05_C4_RESOURCE_IDENTITY_INVALID")

def _related(a,b):
    if a[0]!=b[0]:return False
    if a[0]=="REPO_PATH":
        return a[1]==b[1] or a[1].startswith(b[1]+"/") or b[1].startswith(a[1]+"/")
    pa,pb=a[1].split("."),b[1].split(".")
    return pa[:len(pb)]==pb or pb[:len(pa)]==pa

def prepare_pg05_c4(*,pg04_exit,pg05_c2,pg05_c3,change_proposals):
    exit_sha=_frozen(pg04_exit,"PG04_TO_PG05_EXIT_CANDIDATE_V1","PG05_C4_EXIT_INVALID")
    c2_sha=_frozen(pg05_c2,"PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1","PG05_C4_SCOPE_INVALID")
    c3_sha=_frozen(pg05_c3,"PG05_C3_CONFLICT_LOCK_PLAN_CANDIDATE_V1","PG05_C4_LOCK_PLAN_INVALID")
    if (pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg04_exit.get("pg05_write_allowed") is not False or pg04_exit.get("pg05_admission_allowed") is not False or
        pg04_exit.get("handoff_allowed") is not False or pg04_exit.get("production_authority") is not False or
        pg05_c2.get("source_pg04_exit_sha256")!=exit_sha or
        pg05_c3.get("source_pg04_exit_sha256")!=exit_sha or pg05_c3.get("source_pg05_c2_sha256")!=c2_sha or
        pg05_c2.get("write_scope_authorized") is not False or
        pg05_c3.get("locks_acquired") is not False or
        pg05_c3.get("writer_dispatch_allowed") is not False or
        pg05_c3.get("production_authority") is not False or
        pg05_c3.get("handoff_allowed") is not False):
        _deny("PG05_C4_SOURCE_AUTHORITY_INVALID")
    solutions=pg04_exit.get("solutions")
    if not isinstance(solutions,list) or not solutions:_deny("PG05_C4_SOLUTIONS_MISSING")
    ids=[s.get("solution_id") if isinstance(s,dict) else None for s in solutions]
    if any(not isinstance(sid,str) or not sid for sid in ids) or len(set(ids))!=len(ids):
        _deny("PG05_C4_SOLUTIONS_INVALID")
    scope_rows=pg05_c2.get("solution_scopes")
    lock_rows=pg05_c3.get("lock_requests")
    if not isinstance(scope_rows,list) or not isinstance(lock_rows,list):_deny("PG05_C4_SCOPE_OR_LOCK_SET_INVALID")
    scope={}
    for item in scope_rows:
        if not isinstance(item,dict) or item.get("solution_id") not in ids or item["solution_id"] in scope or item.get("write_authorized") is not False:
            _deny("PG05_C4_SCOPE_OR_LOCK_SET_INVALID")
        scope[item["solution_id"]]=item
    locks={}
    for item in lock_rows:
        if not isinstance(item,dict) or item.get("solution_id") not in ids or item["solution_id"] in locks or item.get("lock_acquired") is not False or item.get("lock_receipt_id") is not None:
            _deny("PG05_C4_SCOPE_OR_LOCK_SET_INVALID")
        locks[item["solution_id"]]=item
    if set(scope)!=set(ids) or set(locks)!=set(ids):_deny("PG05_C4_SCOPE_OR_LOCK_SET_DRIFT")
    resources={}
    shared={}
    for sid in ids:
        keys=scope[sid].get("write_resource_keys")
        reads=scope[sid].get("shared_read_refs")
        if not isinstance(keys,list) or not keys or not isinstance(reads,list):
            _deny("PG05_C4_RESOURCE_SET_INVALID")
        wk={_key(k) for k in keys}
        lk={_key(k) for k in locks[sid].get("requested_resources",[])}
        if len(wk)!=len(keys) or wk!=lk:_deny("PG05_C4_LOCK_RESOURCE_DRIFT")
        rk=set()
        for ref in reads:
            if not isinstance(ref,dict) or ref.get("access")!="READ_ONLY" or not isinstance(ref.get("resource"),dict):
                _deny("PG05_C4_SHARED_READ_INVALID")
            r=ref["resource"]
            rk.add(_key({"kind":r.get("kind"),"identity":r.get("identity")}))
        resources[sid]=wk
        shared[sid]=rk
    if not isinstance(change_proposals,list) or not change_proposals:
        _deny("PG05_C4_CHANGE_PROPOSALS_REQUIRED")
    if len(change_proposals)!=len(ids):_deny("PG05_C4_PROPOSAL_SET_INCOMPLETE")
    proposals={}
    for entry in change_proposals:
        if not isinstance(entry,dict) or set(entry)!={"solution_id","changes","source_head_sha","proposal_ref"}:
            _deny("PG05_C4_CHANGE_PROPOSAL_INVALID")
        sid=entry["solution_id"]
        if sid not in resources or sid in proposals:_deny("PG05_C4_CHANGE_PROPOSAL_OWNER_INVALID")
        head=entry["source_head_sha"]
        if not isinstance(head,str) or not _SHA40.fullmatch(head) or not isinstance(entry["proposal_ref"],str) or not entry["proposal_ref"].strip():
            _deny("PG05_C4_CHANGE_PROPOSAL_SOURCE_INVALID")
        if not isinstance(entry["changes"],list):_deny("PG05_C4_CHANGE_LIST_INVALID")
        proposals[sid]=entry
    reports=[]
    for sid in sorted(ids):
        proposal=proposals[sid]
        findings=[]
        changes=[]
        seen=set()
        for index,ch in enumerate(proposal["changes"]):
            if not isinstance(ch,dict) or set(ch)!={"operation","resource","change_ref"}:
                _deny("PG05_C4_CHANGE_SHAPE_INVALID")
            operation=ch["operation"]
            if operation not in ("ADD","MODIFY","DELETE","RENAME","MIGRATION","DDL","DML"):
                _deny("PG05_C4_OPERATION_INVALID")
            if not isinstance(ch["change_ref"],str) or not ch["change_ref"].strip():
                _deny("PG05_C4_CHANGE_REF_INVALID")
            key=_key(ch["resource"])
            if key in seen:_deny("PG05_C4_DUPLICATE_CHANGE_RESOURCE")
            seen.add(key)
            reasons=[]
            # Exact-resource only for file paths: directories and globs are not
            # implicitly authorized. DB aliases and object hierarchy need
            # canonical resolution before granting any permission.
            if key not in resources[sid]:
                reasons.append("BLOCK_OUT_OF_WRITE_SCOPE")
            if any(_related(key,r) for r in shared[sid]):
                reasons.append("BLOCK_SHARED_READ_ONLY_RESOURCE")
            for other in sorted(resources):
                if other!=sid and any(_related(key,r) for r in resources[other]):
                    reasons.append("BLOCK_CROSS_SOLUTION_WRITE_COLLISION")
                    break
            for other in sorted(shared):
                if other!=sid and any(_related(key,r) for r in shared[other]):
                    reasons.append("BLOCK_CROSS_SOLUTION_SHARED_READ_CONFLICT")
                    break
            if key[0]=="REPO_PATH" and (key[1].startswith(".github/") or key[1]==".github"):
                reasons.append("REQUIRES_EXISTING_REPOSITORY_PATH_ADMISSION")
            if operation=="RENAME":
                reasons.append("BLOCK_RENAME_REQUIRES_OLD_AND_NEW_PATH_BINDINGS")
            if operation in ("MIGRATION","DDL","DML") and key[0]!="DB_OBJECT":
                reasons.append("BLOCK_DB_OPERATION_WRONG_RESOURCE_KIND")
            if operation in ("ADD","MODIFY","DELETE") and key[0]!="REPO_PATH":
                reasons.append("BLOCK_FILE_OPERATION_WRONG_RESOURCE_KIND")
            reasons=sorted(set(reasons))
            if reasons:
                findings.append({"change_index":index,"resource":ch["resource"],"blocking_codes":reasons})
            changes.append({"change_ref":ch["change_ref"],"operation":operation,"resource":ch["resource"],
                            "diagnostic_verdict":"BLOCK" if reasons else "NO_SCOPE_VIOLATION_VISIBLE_NOT_AUTHORIZED"})
        reports.append({
            "solution_id":sid,
            "proposal_ref":proposal["proposal_ref"],
            "source_head_sha":proposal["source_head_sha"],
            "diagnostic_status":"BLOCKED_SCOPE_VIOLATION" if findings else "NO_SCOPE_VIOLATION_VISIBLE",
            "blocking_findings":findings,
            "changes":changes,
            "write_allowed":False,
            "writer_dispatch_allowed":False,
            "real_scope_admission_verified":False})
    result={
        "schema_version":"PG05_C4_WRITE_BOUNDARY_DIAGNOSTIC_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg04_exit_sha256":exit_sha,
        "source_pg05_c2_sha256":c2_sha,
        "source_pg05_c3_sha256":c3_sha,
        "solution_reports":reports,
        "affected_solutions":[x["solution_id"] for x in reports if x["blocking_findings"]],
        "unaffected_solutions_not_promoted":[x["solution_id"] for x in reports if not x["blocking_findings"]],
        "repository_path_admission_executed":False,
        "real_diff_verified":False,
        "source_head_currentness_verified":False,
        "writer_lock_verified":False,
        "individual_block_isolation":"PER_SOLUTION",
        "pg05_admitted":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"EXISTING_PATH_ADMISSION_LIVE_DIFF_CURRENTNESS_AND_WRITER_AUTHORITY"
    }
    result["candidate_sha256"]=_digest(result)
    return result
