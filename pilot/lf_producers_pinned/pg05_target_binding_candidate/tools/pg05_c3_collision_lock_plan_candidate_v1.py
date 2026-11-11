"""PG-05_C3: conflict graph and lock request preparation, never lock acquisition.

Conservative conflicts include equal/nested paths, hierarchical database
identifiers, write-vs-shared-read and solution dependency ordering. Existence,
alias and dynamic resource conflict checks require the governed resolver.
"""
import hashlib
import json

class CollisionPlanBlocked(ValueError):
    pass

def _block(reason):
    raise CollisionPlanBlocked(reason)

def _sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _frozen(value,schema,code):
    if not isinstance(value,dict) or value.get("schema_version")!=schema:
        _block(code)
    checksum=value.get("candidate_sha256")
    if not isinstance(checksum,str) or checksum!=_sha({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _block(code)
    return checksum

def _ids(values,allow_empty=False):
    return (isinstance(values,list) and (allow_empty or bool(values))
        and all(isinstance(x,str) and bool(x.strip()) for x in values)
        and len(values)==len(set(values)))

def _related(a,b):
    if a[0]!=b[0]:
        return False
    if a[0]=="REPO_PATH":
        return a[1]==b[1] or a[1].startswith(b[1]+"/") or b[1].startswith(a[1]+"/")
    if a[0]=="DB_OBJECT":
        pa=a[1].split(".")
        pb=b[1].split(".")
        return pa==pb or pa[:len(pb)]==pb or pb[:len(pa)]==pa
    _block("PG05_C3_RESOURCE_KIND_UNKNOWN")

def prepare_pg05_c3(*,pg04_exit,pg05_c2):
    exit_sha=_frozen(pg04_exit,"PG04_TO_PG05_EXIT_CANDIDATE_V1","PG05_C3_PG04_EXIT_INVALID")
    c2_sha=_frozen(pg05_c2,"PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1","PG05_C3_C2_DIGEST_INVALID")
    if (pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg04_exit.get("pg05_admission_allowed") is not False
        or pg04_exit.get("pg05_write_allowed") is not False
        or pg04_exit.get("handoff_allowed") is not False
        or pg05_c2.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_c2.get("source_pg04_exit_sha256")!=exit_sha
        or pg05_c2.get("write_scope_authorized") is not False
        or pg05_c2.get("writer_lock_acquired") is not False
        or pg05_c2.get("branch_created") is not False
        or pg05_c2.get("repository_path_admission_executed") is not False
        or pg05_c2.get("production_authority") is not False
        or pg05_c2.get("handoff_allowed") is not False):
        _block("PG05_C3_AUTHORITY_BOUNDARY_INVALID")
    original=pg04_exit.get("solutions")
    resolved=pg05_c2.get("solution_scopes")
    if not isinstance(original,list) or not original or not isinstance(resolved,list) or len(resolved)!=len(original):
        _block("PG05_C3_SOLUTION_SET_INVALID")
    sol={}
    for entry in original:
        if not isinstance(entry,dict) or not isinstance(entry.get("solution_id"),str) or entry["solution_id"] in sol:
            _block("PG05_C3_SOLUTION_SET_INVALID")
        if (not _ids(entry.get("depends_on"),True)
            or entry.get("pg05_write_scope_authorized") is not False
            or entry.get("pg05_parallel_writer_lock_acquired") is not False
            or entry.get("execution_allowed") is not False):
            _block("PG05_C3_SOLUTION_AUTHORITY_INVALID")
        sol[entry["solution_id"]]=entry
    scopes={}
    writes={}
    reads={}
    for row in resolved:
        if not isinstance(row,dict) or row.get("solution_id") not in sol or row["solution_id"] in scopes or row.get("write_authorized") is not False:
            _block("PG05_C3_SCOPE_RESOLUTION_INVALID")
        sid=row["solution_id"]
        scopes[sid]=row
        w=row.get("write_resource_keys")
        r=row.get("shared_read_refs")
        if not isinstance(w,list) or not w or not isinstance(r,list):
            _block("PG05_C3_RESOURCE_SET_INVALID")
        def parse_key(key):
            if not isinstance(key,dict) or set(key)!={"kind","identity"} or key["kind"] not in ("REPO_PATH","DB_OBJECT") or not isinstance(key["identity"],str) or not key["identity"]:
                _block("PG05_C3_RESOURCE_KEY_INVALID")
            return (key["kind"],key["identity"])
        wk=[parse_key(key) for key in w]
        if len(set(wk))!=len(wk):
            _block("PG05_C3_DUPLICATE_WRITE_RESOURCE")
        rk=[]
        for ref in r:
            if not isinstance(ref,dict) or ref.get("access")!="READ_ONLY" or not isinstance(ref.get("resource"),dict):
                _block("PG05_C3_SHARED_READ_INVALID")
            res=ref["resource"]
            rk.append(parse_key({"kind":res.get("kind"),"identity":res.get("identity")}))
        if any(_related(a,b) for a in wk for b in rk):
            _block("PG05_C3_LOCAL_SHARED_READ_WRITE_CONFLICT")
        writes[sid]=sorted(wk)
        reads[sid]=sorted(rk)
    if set(scopes)!=set(sol):
        _block("PG05_C3_SOLUTION_SET_DRIFT")
    graph={sid:entry["depends_on"] for sid,entry in sol.items()}
    visiting=set()
    visited=set()
    def visit(sid):
        if sid in visiting:_block("PG05_C3_DEPENDENCY_CYCLE")
        if sid in visited:return
        visiting.add(sid)
        for dep in graph[sid]:
            if dep not in graph or dep==sid:_block("PG05_C3_DEPENDENCY_INVALID")
            visit(dep)
        visiting.remove(sid)
        visited.add(sid)
    for sid in graph:visit(sid)
    def precedes(a,b):
        if a==b:return False
        todo=list(graph[a])
        found=set()
        while todo:
            dep=todo.pop()
            if dep==b:return True
            if dep not in found:
                found.add(dep)
                todo.extend(graph[dep])
        return False
    pairs=[]
    ids=sorted(sol)
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            causes=[]
            if precedes(a,b) or precedes(b,a):
                causes.append({"kind":"DEPENDENCY_ORDER","resource":None})
            for aw in writes[a]:
                for bw in writes[b]:
                    if _related(aw,bw):
                        causes.append({"kind":"WRITE_WRITE_MATERIAL_OVERLAP",
                                       "resource":[{"kind":aw[0],"identity":aw[1]},{"kind":bw[0],"identity":bw[1]}]})
                for br in reads[b]:
                    if _related(aw,br):
                        causes.append({"kind":"WRITE_SHARED_READ_ONLY_CONFLICT",
                                       "resource":[{"kind":aw[0],"identity":aw[1]},{"kind":br[0],"identity":br[1]}]})
            for bw in writes[b]:
                for ar in reads[a]:
                    if _related(bw,ar):
                        causes.append({"kind":"WRITE_SHARED_READ_ONLY_CONFLICT",
                                       "resource":[{"kind":bw[0],"identity":bw[1]},{"kind":ar[0],"identity":ar[1]}]})
            pairs.append({"solution_ids":[a,b],
                          "material_conflicts":causes,
                          "classification":("BLOCK_CONCURRENT_WRITERS" if causes
                                            else "NOT_PROVEN_SAFE_FOR_PARALLELISM"),
                          "parallel_execution_allowed":False})
    locks=[]
    for sid in ids:
        locks.append({"solution_id":sid,
                      "requested_resources":[{"kind":kind,"identity":identity} for kind,identity in writes[sid]],
                      "lock_scope":"EXACT_SOURCE_BOUND_RESOURCES",
                      "lock_owner_execution_id":None,
                      "lock_receipt_id":None,
                      "lock_acquired":False})
    result={
        "schema_version":"PG05_C3_CONFLICT_LOCK_PLAN_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg04_exit_sha256":exit_sha,
        "source_pg05_c2_sha256":c2_sha,
        "solution_pairs":pairs,
        "lock_requests":locks,
        "material_conflict_pair_count":sum(bool(p["material_conflicts"]) for p in pairs),
        "safe_parallelism_attested":False,
        "unknown_aliases_or_dynamic_resources_resolved":False,
        "resource_currentness_verified":False,
        "repo_path_admission_verified":False,
        "actual_lock_mechanism_resolved":False,
        "locks_acquired":False,
        "writer_dispatch_allowed":False,
        "branch_created":False,
        "pg05_admitted":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"GOVERNED_CURRENT_RESOURCE_RESOLUTION_PATH_ADMISSION_AND_REAL_LOCK_ACQUISITION",
    }
    result["candidate_sha256"]=_sha(result)
    return result
