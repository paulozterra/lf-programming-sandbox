"""PG-06_C3: A7 material-front-bound rollback plan, source-only candidate.

Does not modify Analysis, invent A7 fronts, apply SQL, or certify rollback.
Absent material front is unresolved, not NOT_APPLICABLE.
"""
import hashlib
import json
import re

class ReversibilityBlocked(ValueError):
    pass

SHA=re.compile(r"^[0-9a-f]{64}$")
KINDS=("MIGRATION_CUTOVER","ROLLBACK_RECOVERY")

def _fail(code):raise ReversibilityBlocked(code)
def _hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _text(v):return isinstance(v,str) and bool(v.strip())
def _ids(v,empty=False):return isinstance(v,list) and (empty or bool(v)) and all(_text(x) for x in v) and len(v)==len(set(v))
def _freeze(v,schema,code):
    if not isinstance(v,dict) or v.get("schema_version")!=schema:_fail(code)
    sha=v.get("candidate_sha256")
    if not isinstance(sha,str) or not SHA.fullmatch(sha) or sha!=_hash({k:x for k,x in v.items() if k!="candidate_sha256"}):_fail(code)
    return sha

def prepare_pg06_c3(*,pg05_exit,pg06_c1,pg06_c2,a7_material_front_coverage,solution_reversibility_plans):
    exit_sha=_freeze(pg05_exit,"PG05_TO_PG06_EXIT_CANDIDATE_V1","PG06_C3_EXIT_INVALID")
    c1_sha=_freeze(pg06_c1,"PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1","PG06_C3_C1_INVALID")
    c2_sha=_freeze(pg06_c2,"PG06_C2_TOOLCHAIN_PREFLIGHT_CANDIDATE_V1","PG06_C3_C2_INVALID")
    if (pg05_exit.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg05_exit.get("production_authority") is not False or pg05_exit.get("handoff_allowed") is not False
        or pg06_c1.get("source_pg05_exit_sha256")!=exit_sha or pg06_c2.get("source_pg05_exit_sha256")!=exit_sha
        or pg06_c2.get("source_pg06_c1_sha256")!=c1_sha
        or pg06_c1.get("execution_allowed") is not False or pg06_c2.get("pg06_ready") is not False
        or pg06_c1.get("production_authority") is not False or pg06_c2.get("production_authority") is not False):
        _fail("PG06_C3_SOURCE_CHAIN_INVALID")
    sols=pg05_exit.get("solutions")
    if not isinstance(sols,list) or not sols:_fail("PG06_C3_SOLUTIONS_MISSING")
    sids=[r.get("solution_id") if isinstance(r,dict) else None for r in sols]
    if not _ids(sids):_fail("PG06_C3_SOLUTIONS_INVALID")
    if not isinstance(a7_material_front_coverage,dict) or set(a7_material_front_coverage)!={
        "schema_version","artifact_ref","artifact_sha256","all_material_fronts_accounted",
        "material_fronts","source_refs","currentness_refs"}:
        _fail("PG06_C3_A7_COVERAGE_SHAPE_INVALID")
    a7=a7_material_front_coverage
    if (a7["schema_version"]!="MATERIAL_FRONT_COVERAGE_V1" or not _text(a7["artifact_ref"])
        or not isinstance(a7["artifact_sha256"],str) or not SHA.fullmatch(a7["artifact_sha256"])
        or a7["all_material_fronts_accounted"] is not True
        or not _ids(a7["source_refs"]) or not _ids(a7["currentness_refs"])):
        _fail("PG06_C3_A7_COVERAGE_UNRESOLVED")
    fronts=a7["material_fronts"]
    if not isinstance(fronts,list):_fail("PG06_C3_A7_FRONTS_INVALID")
    relevant={}
    for front in fronts:
        if not isinstance(front,dict) or set(front)!={
            "front_id","front_kind","status","closure","scope_refs",
            "source_signal_refs","authority_refs","evidence_refs","currentness_refs",
            "blockers","reason"}:
            _fail("PG06_C3_FRONT_SHAPE_INVALID")
        if (not _text(front["front_id"]) or not _text(front["front_kind"])
            or front["status"] not in ("REQUIRED","REUSE_AS_IS","NOT_APPLICABLE")
            or front["closure"] not in ("CLOSED","BLOCKED")
            or not _ids(front["scope_refs"])
            or any(not _ids(front[k],True) for k in ("source_signal_refs","authority_refs","evidence_refs","currentness_refs","blockers"))
            or not _text(front["reason"])):
            _fail("PG06_C3_FRONT_INVALID")
        if front["front_kind"] in KINDS:
            if front["front_id"] in relevant:_fail("PG06_C3_FRONT_DUPLICATE")
            relevant[front["front_id"]]=front
    if not relevant:_fail("PG06_C3_REVERSIBILITY_FRONT_NOT_ACCOUNTED")
    if not isinstance(solution_reversibility_plans,list) or len(solution_reversibility_plans)!=len(sids):
        _fail("PG06_C3_PLANS_INCOMPLETE")
    by_solution={}
    all_front_ids=set()
    rows=[]
    for plan in solution_reversibility_plans:
        if not isinstance(plan,dict) or set(plan)!={"solution_id","scope_refs","front_plans"}:
            _fail("PG06_C3_PLAN_SHAPE_INVALID")
        sid=plan["solution_id"]
        if sid not in sids or sid in by_solution or not _ids(plan["scope_refs"]):
            _fail("PG06_C3_PLAN_BINDING_INVALID")
        by_solution[sid]=plan
        parts=plan["front_plans"]
        if not isinstance(parts,list):_fail("PG06_C3_FRONT_PLANS_INVALID")
        seen=set()
        issues=[]
        output=[]
        for part in parts:
            if not isinstance(part,dict) or set(part)!={
                "front_id","disposition","technical_steps_ref","rollback_steps_ref",
                "verification_ref","cutover_or_recovery_strategy_ref"}:
                _fail("PG06_C3_TECHNICAL_PLAN_SHAPE_INVALID")
            fid=part["front_id"]
            if fid not in relevant or fid in seen:_fail("PG06_C3_FRONT_PLAN_ID_INVALID")
            front=relevant[fid]
            if not set(front["scope_refs"]).intersection(plan["scope_refs"]):
                _fail("PG06_C3_FRONT_SCOPE_DRIFT")
            seen.add(fid)
            all_front_ids.add(fid)
            disp=part["disposition"]
            expected={"REQUIRED":"PLAN_REQUIRED","REUSE_AS_IS":"REUSE_EXISTING","NOT_APPLICABLE":"JUSTIFIED_NOT_APPLICABLE"}[front["status"]]
            if disp!=expected:_fail("PG06_C3_DISPOSITION_DRIFT")
            refs=("technical_steps_ref","rollback_steps_ref","verification_ref","cutover_or_recovery_strategy_ref")
            if disp=="PLAN_REQUIRED" and any(not _text(part[x]) for x in refs):
                _fail("PG06_C3_REQUIRED_PLAN_EVIDENCE_MISSING")
            if disp!="PLAN_REQUIRED" and any(part[x] is not None for x in refs):
                _fail("PG06_C3_NONREQUIRED_FRONT_PLAN_FORBIDDEN")
            if front["closure"]!="CLOSED" or front["blockers"]:
                issues.append(fid)
            output.append({"front_id":fid,"front_kind":front["front_kind"],
                           "a7_status":front["status"],"a7_closure":front["closure"],
                           "disposition":disp,"source_a7_front_sha256":_hash(front),
                           "technical_steps_ref":part["technical_steps_ref"],
                           "rollback_steps_ref":part["rollback_steps_ref"],
                           "verification_ref":part["verification_ref"],
                           "strategy_ref":part["cutover_or_recovery_strategy_ref"],
                           "reversibility_executed":False})
        expected_ids={fid for fid,f in relevant.items() if set(f["scope_refs"]).intersection(plan["scope_refs"])}
        if seen!=expected_ids:_fail("PG06_C3_FRONT_SCOPE_COVERAGE_INCOMPLETE")
        rows.append({"solution_id":sid,"front_plans":sorted(output,key=lambda x:x["front_id"]),
                     "blocked_front_ids":sorted(issues),
                     "diagnostic_status":"BLOCKED_A7_FRONT" if issues else "PLAN_DECLARED_UNVERIFIED",
                     "rollback_executed":False,"execution_allowed":False})
    if set(by_solution)!=set(sids):_fail("PG06_C3_SOLUTION_PLAN_SET_DRIFT")
    relevant_scopes={s for front in relevant.values() for s in front["scope_refs"]}
    supplied_scopes={s for plan in by_solution.values() for s in plan["scope_refs"]}
    if not relevant_scopes.issubset(supplied_scopes) or all_front_ids!=set(relevant):
        _fail("PG06_C3_REVERSIBILITY_FRONT_COVERAGE_INCOMPLETE")
    blocked=sorted({fid for row in rows for fid in row["blocked_front_ids"]})
    output={
        "schema_version":"PG06_C3_REVERSIBILITY_PLAN_CANDIDATE_V1",
        "status":"BLOCKED_A7_FRONT" if blocked else "CANDIDATE_NOT_ADMITTED",
        "source_pg05_exit_sha256":exit_sha,"source_pg06_c1_sha256":c1_sha,
        "source_pg06_c2_sha256":c2_sha,
        "a7_material_front_coverage_sha256":a7["artifact_sha256"],
        "a7_manifest_input_sha256":_hash(a7),
        "solutions":sorted(rows,key=lambda x:x["solution_id"]),
        "blocked_front_ids":blocked,
        "a7_artifact_currentness_verified":False,
        "a7_fronts_semantically_verified":False,
        "rollback_plan_verified":False,
        "migration_or_rollback_executed":False,
        "write_allowed":False,
        "pg06_admitted":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"A7_CURRENT_MATERIAL_FRONT_READBACK_AND_GOVERNED_REVERSIBILITY_REVIEW"
    }
    output["candidate_sha256"]=_hash(output)
    return output
