"""PG04->PG05 C2->profile assignment->PG06->PG07 candidate-only integration.
No production dispatch, no model invocation, no Worker receipt authentication.
The PostgreSQL adapter MUST target a local disposable selector_exp_test_* database.
"""
import copy
import hashlib
import json
import re

_SHA=re.compile(r"^[0-9a-f]{64}$")
_PATH=re.compile(r"^[a-zA-Z0-9_./-]+$")
_ALLOWED={"BACKEND","FRONTEND","DATA"}

class BridgeBlocked(ValueError):
    pass

def block(code):
    raise BridgeBlocked(code)

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def frozen(value, field="candidate_sha256"):
    if not isinstance(value,dict) or not isinstance(value.get(field),str) or not _SHA.fullmatch(value[field]):
        block("SOURCE_DIGEST_MISSING")
    if digest({k:v for k,v in value.items() if k!=field})!=value[field]:
        block("SOURCE_DIGEST_INVALID")
    return value[field]

def safe_path(p):
    return (isinstance(p,str) and bool(p) and len(p)<=400 and _PATH.fullmatch(p)
            and not p.startswith("/") and not p.endswith("/")
            and all(part not in ("",".","..") for part in p.split("/")))

def _exact_keys(obj,keys,reason):
    if not isinstance(obj,dict) or set(obj)!=set(keys): block(reason)

def _safe_scope(paths):
    if not isinstance(paths,list) or not paths or len(paths)!=len(set(paths)) or not all(safe_path(p) for p in paths):
        block("WRITE_SCOPE_INVALID")
    return sorted(paths)

def declare_pg04_areas(*,pg04_exit,project_ref,lot_declarations,project_rules):
    """Source-bound PG04 candidate overlay; every solution declares exactly one area."""
    exit_sha=frozen(pg04_exit)
    if (pg04_exit.get("schema_version")!="PG04_TO_PG05_EXIT_CANDIDATE_V1" or
        pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg04_exit.get("production_authority") is not False or
        pg04_exit.get("handoff_allowed") is not False):
        block("PG04_AREA_SOURCE_INVALID")
    if not isinstance(project_ref,str) or not project_ref or not isinstance(project_rules,list):
        block("PG04_PROJECT_RULES_INVALID")
    ids=[x.get("solution_id") for x in pg04_exit.get("solutions",[])]
    if not ids or len(set(ids))!=len(ids) or not isinstance(lot_declarations,list) or len(lot_declarations)!=len(ids):
        block("PG04_AREA_COVERAGE_INVALID")
    seen=set()
    result=[]
    for dec in lot_declarations:
        _exact_keys(dec,{"solution_id","area","paths"},"PG04_AREA_FIELDS_INVALID")
        sid=dec["solution_id"]
        if sid not in ids or sid in seen or dec["area"] not in _ALLOWED:
            block("PG04_AREA_SOLUTION_INVALID")
        seen.add(sid)
        paths=_safe_scope(dec["paths"])
        areas=set()
        for path in paths:
            matched=set()
            for rule in project_rules:
                if (not isinstance(rule,dict) or set(rule)!={"area","path_prefix"} or
                    rule["area"] not in _ALLOWED or not isinstance(rule["path_prefix"],str)):
                    block("PG04_RULE_SHAPE_INVALID")
                if path.startswith(rule["path_prefix"]):
                    matched.add(rule["area"])
            if not matched: block("LOTE_PATH_UNCLASSIFIED")
            if len(matched)>1: block("LOTE_ROUTE_CONFLICT")
            areas|=matched
        if len(areas)>1: block("LOTE_MULTI_AREA")
        if dec["area"]!=next(iter(areas)): block("LOTE_AREA_MISMATCH")
        result.append({"solution_id":sid,"area":dec["area"],"paths":paths})
    out={"schema_version":"PG04_AREA_DECLARATION_OVERLAY_V1",
         "source_pg04_exit_sha256":exit_sha,"project_ref":project_ref,
         "project_rules":copy.deepcopy(sorted(project_rules,key=lambda x:(x["area"],x["path_prefix"]))),
         "lots":sorted(result,key=lambda x:x["solution_id"]),
         "production_authority":False}
    out["area_overlay_sha256"]=digest(out)
    return out

def pg04_area_lot(*,pg04_exit,pg05_c2,pg04_areas,solution_id,area,paths):
    """Overlay area on a PG04 solution after C2 exact scope resolution; no alteration to PG04 itself."""
    e=frozen(pg04_exit); c=frozen(pg05_c2)
    if (pg04_exit.get("schema_version")!="PG04_TO_PG05_EXIT_CANDIDATE_V1" or
        pg04_exit.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg04_exit.get("production_authority") is not False or
        pg04_exit.get("handoff_allowed") is not False or
        pg05_c2.get("schema_version")!="PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1" or
        pg05_c2.get("status")!="CANDIDATE_NOT_ADMITTED" or
        pg05_c2.get("source_pg04_exit_sha256")!=e or
        pg05_c2.get("production_authority") is not False or
        pg05_c2.get("write_scope_authorized") is not False):
        block("PG04_PG05_C2_CHAIN_INVALID")
    if area not in _ALLOWED or not isinstance(solution_id,str) or not solution_id: block("LOT_AREA_OR_ID_INVALID")
    _exact_keys(pg04_areas,{"schema_version","source_pg04_exit_sha256","project_ref",
                           "project_rules","lots","production_authority","area_overlay_sha256"},
                "PG04_AREA_OVERLAY_FIELDS_INVALID")
    frozen(pg04_areas,"area_overlay_sha256")
    if (pg04_areas["schema_version"]!="PG04_AREA_DECLARATION_OVERLAY_V1" or
        pg04_areas["production_authority"] is not False or
        pg04_areas["source_pg04_exit_sha256"]!=e):
        block("PG04_AREA_OVERLAY_INVALID")
    declarations=[x for x in pg04_areas["lots"] if x.get("solution_id")==solution_id]
    if len(declarations)!=1 or declarations[0].get("area")!=area or declarations[0].get("paths")!=_safe_scope(paths):
        block("PG04_AREA_LOT_DRIFT")

    es=[s for s in pg04_exit.get("solutions",[]) if s.get("solution_id")==solution_id]
    cs=[s for s in pg05_c2.get("solution_scopes",[]) if s.get("solution_id")==solution_id]
    if len(es)!=1 or len(cs)!=1: block("LOT_SOLUTION_SOURCE_NOT_UNIQUE")
    if cs[0].get("write_authorized") is not False: block("SCOPE_AUTHORITY_FORBIDDEN")
    # C2's exact REPO_PATH resources are the sole admissible write scope here.
    resources=cs[0].get("write_resource_keys")
    if not isinstance(resources,list) or not resources: block("WRITE_SCOPE_RESOURCES_MISSING")
    if any(not isinstance(x,dict) or set(x)!={"kind","identity"} or x["kind"]!="REPO_PATH" for x in resources):
        block("NON_REPO_RESOURCE_UNSUPPORTED")
    resolved=_safe_scope([x["identity"] for x in resources])
    requested=_safe_scope(paths)
    if requested!=resolved: block("LOT_OUTSIDE_PG05_RESOLVED_SCOPE")
    lot={"schema_version":"PG04_AREA_LOT_EXP_V1","solution_id":solution_id,
         "area":area,"paths":requested,
         "pg04_exit_sha256":e,"pg05_c2_sha256":c,
         "pg04_area_overlay_sha256":pg04_areas["area_overlay_sha256"],
         "project_ref":pg04_areas["project_ref"],
         "project_rules":copy.deepcopy(pg04_areas["project_rules"]),
         "production_authority":False}
    lot["lot_sha256"]=digest(lot)
    return lot

def _validate_lot(lot):
    _exact_keys(lot,{"schema_version","solution_id","area","paths","pg04_exit_sha256",
                     "pg05_c2_sha256","pg04_area_overlay_sha256","project_ref","project_rules","production_authority","lot_sha256"},"LOT_FIELDS_INVALID")
    if lot["schema_version"]!="PG04_AREA_LOT_EXP_V1" or lot["production_authority"] is not False or lot["area"] not in _ALLOWED:
        block("LOT_AUTHORITY_OR_AREA_INVALID")
    _safe_scope(lot["paths"])
    frozen(lot,"lot_sha256")

def assign_pg05(*,lot,project_ref,literal_request,model_draft,prepare,finalize):
    """SQL functions are caller-provided read-only local adapters, NOT a real model dispatcher."""
    _validate_lot(lot)
    if not isinstance(project_ref,str) or not project_ref or not isinstance(literal_request,str) or not literal_request.strip():
        block("ASSIGN_INPUT_INVALID")
    if not isinstance(model_draft,dict): block("MODEL_DRAFT_INVALID")
    allowed_draft={"decision","selected_profile_code","ambiguous_profile_codes",
                   "reason","evidence_refs","material_ambiguities"}
    if set(model_draft) != allowed_draft:
        return {"status":"BLOCKED","blocking_code":"MODEL_DRAFT_FIELD_FORBIDDEN",
                "production_authority":False}
    if lot["project_ref"]!=project_ref: block("LOT_PROJECT_MISMATCH")
    request_wrap=prepare(literal_request,project_ref,lot["area"],lot["paths"])
    if not isinstance(request_wrap,dict) or request_wrap.get("status")!="READY":
        return {"status":"BLOCKED","blocking_code":request_wrap.get("blocking_code","PREPARE_NOT_READY") if isinstance(request_wrap,dict) else "PREPARE_NOT_READY","production_authority":False}
    request=request_wrap["request"]
    if (request.get("project_ref")!=project_ref or request.get("file_paths")!=lot["paths"] or
        request.get("area")!=lot["area"] or request.get("project_rules")!=lot["project_rules"] or
        request.get("downstream_execution_allowed") is not False):
        block("PREPARE_SCOPE_BINDING_INVALID")
    final=finalize(request,model_draft)
    if not isinstance(final,dict) or final.get("status")!="VALID":
        return {"status":"BLOCKED","blocking_code":"SELECTION_NOT_VALID",
                "production_authority":False}
    result=final["result"]
    decision=result.get("decision")
    if decision in ("AMBIGUOUS","NO_MATCH"):
        return {"status":"REQUIRES_HUMAN_DECISION","decision":decision,
                "production_authority":False}
    if decision!="SELECTED": block("SELECTION_DECISION_INVALID")
    selected=result.get("selected_profile_code")
    if not isinstance(selected,str) or selected not in [p.get("profile_code") for p in request.get("candidate_profiles",[])]:
        block("SELECTED_OUTSIDE_CATALOG")
    # An explicit schema prohibits authority insertion even if a forged digest was recomputed.
    assignment={"schema_version":"PG05_PROFILE_ASSIGNMENT_BRIDGE_V1","status":"SELECTED",
      "solution_id":lot["solution_id"],"lot_sha256":lot["lot_sha256"],
      "source_pg05_c2_sha256":lot["pg05_c2_sha256"],
      "project_ref":project_ref,"area":lot["area"],"write_scope":copy.deepcopy(lot["paths"]),
      "source_pg04_area_overlay_sha256":lot["pg04_area_overlay_sha256"],
      "profile_code":selected,"request":copy.deepcopy(request),"result":copy.deepcopy(result),
      "request_sha256":digest(request),"result_sha256":digest(result),
      "catalog_sha256":request["catalog_sha256"],
      "production_authority":False}
    assignment["assignment_sha256"]=digest(assignment)
    return assignment

def pg06_currentness(*,assignment,lot,prepare,finalize):
    _validate_lot(lot)
    keys={"schema_version","status","solution_id","lot_sha256","source_pg05_c2_sha256",
          "project_ref","area","write_scope","profile_code","request","result",
          "source_pg04_area_overlay_sha256",
          "request_sha256","result_sha256","catalog_sha256",
          "production_authority","assignment_sha256"}
    _exact_keys(assignment,keys,"ASSIGNMENT_FIELDS_INVALID")
    frozen(assignment,"assignment_sha256")
    if (assignment["schema_version"]!="PG05_PROFILE_ASSIGNMENT_BRIDGE_V1" or
        assignment["status"]!="SELECTED" or assignment["production_authority"] is not False
        or assignment["lot_sha256"]!=lot["lot_sha256"]
        or assignment["source_pg04_area_overlay_sha256"]!=lot["pg04_area_overlay_sha256"]
        or assignment["source_pg05_c2_sha256"]!=lot["pg05_c2_sha256"]
        or assignment["solution_id"]!=lot["solution_id"]
        or assignment["area"]!=lot["area"]
        or assignment["project_ref"]!=lot["project_ref"]
        or assignment["request"].get("project_rules")!=lot["project_rules"]
        or assignment["write_scope"]!=lot["paths"]
        or assignment["request_sha256"]!=digest(assignment["request"])
        or assignment["result_sha256"]!=digest(assignment["result"])
        or assignment["catalog_sha256"]!=assignment["request"].get("catalog_sha256")):
        block("ASSIGNMENT_SCOPE_OR_AUTHORITY_INVALID")
    current=prepare(assignment["request"]["literal_request"],assignment["project_ref"],
                    assignment["area"],assignment["write_scope"])
    if current.get("status")!="READY" or current.get("request")!=assignment["request"]:
        block("PG06_SELECTOR_POLICY_OR_CATALOG_STALE")
    # Recheck actual sealed result against current descriptor, policy and route rules.
    selected=assignment["profile_code"]
    result=assignment["result"]
    if (result.get("decision")!="SELECTED" or result.get("selected_profile_code")!=selected or
        selected not in [p.get("profile_code") for p in current["request"]["candidate_profiles"]]):
        block("PG06_SELECTED_PROFILE_DRIFT")
    # Revalidate original draft material; do not replay the already-hashed result as a draft.
    draft={k:copy.deepcopy(result.get(k)) for k in
           ("decision","selected_profile_code","ambiguous_profile_codes",
            "reason","evidence_refs","material_ambiguities")}
    renewed=finalize(current["request"],draft)
    if renewed.get("status")!="VALID" or renewed.get("result")!=result:
        block("PG06_RECEIPT_OR_RESULT_STALE")
    out={"schema_version":"PG06_PROFILE_CURRENTNESS_V1","status":"CURRENT",
         "assignment_sha256":assignment["assignment_sha256"],
         "lot_sha256":lot["lot_sha256"],"production_authority":False}
    out["currentness_sha256"]=digest(out)
    return out

def pg07_worker_projection(*,assignment,lot,currentness,worker_spec,pg07_c2,role,skill,project_binding_row):
    """Output is a CANDIDATE overlay, NOT fn_agent_task_worker_spec or an authenticated Worker receipt."""
    _validate_lot(lot)
    frozen(assignment,"assignment_sha256")
    frozen(currentness,"currentness_sha256")
    if (currentness.get("schema_version")!="PG06_PROFILE_CURRENTNESS_V1" or
        currentness.get("status")!="CURRENT" or currentness.get("production_authority") is not False
        or currentness.get("assignment_sha256")!=assignment["assignment_sha256"]
        or currentness.get("lot_sha256")!=lot["lot_sha256"]):
        block("PG07_CURRENTNESS_MISSING")
    if assignment["write_scope"]!=lot["paths"] or assignment["production_authority"] is not False:
        block("PG07_SCOPE_OR_AUTHORITY_INVALID")
    if not isinstance(role,dict) or not isinstance(skill,dict) or not isinstance(project_binding_row,dict):
        block("PG07_ROLE_STACK_BINDING_REQUIRED")
    if (role.get("profile_code")!=assignment["profile_code"] or
        role.get("area")!=assignment["area"] or
        skill.get("area")!=assignment["area"] or
        skill.get("project_ref")!=assignment["project_ref"]):
        block("PG07_ROLE_OR_SKILL_AREA_MISMATCH")
    required_binding={"project_ref","area","skill_code","skill_version","skill_sha256","priority"}
    if set(project_binding_row)!=required_binding or (
        project_binding_row["project_ref"]!=assignment["project_ref"] or
        project_binding_row["area"]!=assignment["area"] or
        project_binding_row["skill_code"]!=skill.get("skill_code") or
        project_binding_row["skill_version"]!=skill.get("skill_version") or
        project_binding_row["skill_sha256"]!=skill.get("skill_sha256") or
        project_binding_row["priority"]!=skill.get("priority")):
        block("PG07_STACK_BINDING_DRIFT")
    items=skill.get("skills",[])
    if not isinstance(items,list) or not items:block("PG07_STACK_SKILL_SET_MISSING")
    identities=[{"skill_code":x["skill_code"],"skill_version":x["skill_version"],
                 "skill_sha256":x["skill_sha256"],"priority":x["priority"]} for x in items]
    if (digest(identities)!=skill.get("skill_set_sha256") or
        sorted(x["priority"] for x in items)!=[x["priority"] for x in items] or
        len(set(x["priority"] for x in items))!=len(items)):
        block("PG07_SKILL_SET_PRIORITY_OR_HASH_INVALID")
    for item in items:
        if item.get("area")!=assignment["area"] or hashlib.sha256(
            item.get("skill_text","").encode("utf-8")).hexdigest()!=item.get("skill_sha256"):
            block("PG07_ROLE_OR_SKILL_SHA256_MISMATCH")
    if (hashlib.sha256(role.get("role_text","").encode("utf-8")).hexdigest()!=role.get("profile_sha256") or
        hashlib.sha256(skill.get("skill_text","").encode("utf-8")).hexdigest()!=skill.get("skill_sha256")):
        block("PG07_ROLE_OR_SKILL_SHA256_MISMATCH")
    if not isinstance(worker_spec,dict) or worker_spec.get("schema_version")!=2:
        block("PG07_WORKER_SPEC_INVALID")
    if any(x in worker_spec for x in ("oracle_envelope","hidden_oracle_ref","hidden_oracle_sha256")):
        block("PG07_ORACLE_EXPOSURE")
    if not isinstance(worker_spec.get("write_path_patterns"),list) or (
        _safe_scope(worker_spec["write_path_patterns"])!=lot["paths"]):
        block("PG07_WORKER_SPEC_SCOPE_EXCEEDS_ASSIGNMENT")
    visible=worker_spec.get("functional_contract",{}).get("role_and_stack") if isinstance(worker_spec,dict) else None
    if (not isinstance(visible,dict) or
        visible.get("profile_code")!=role["profile_code"] or
        visible.get("profile_sha256")!=role["profile_sha256"] or
        visible.get("profile_rules")!=role["role_text"] or
        visible.get("skill_code")!=skill["skill_code"] or
        visible.get("skill_sha256")!=skill["skill_sha256"] or
        visible.get("skill_rules")!=skill["skill_text"] or
        visible.get("project_ref")!=assignment["project_ref"] or
        visible.get("area")!=assignment["area"] or
        visible.get("skill_version")!=skill["skill_version"] or
        visible.get("skill_set_sha256")!=skill["skill_set_sha256"]):
        block("PG07_ROLE_STACK_NOT_IN_VISIBLE_TASK")
    listed=visible.get("skills",[])
    if not isinstance(listed,list) or len(listed)!=len(items):
        block("PG07_WORKER_SKILLS_INCOMPLETE")
    for source,shown in zip(items,listed):
        if (shown.get("skill_code")!=source["skill_code"] or
            shown.get("skill_version")!=source["skill_version"] or
            shown.get("skill_sha256")!=source["skill_sha256"] or
            shown.get("priority")!=source["priority"] or
            shown.get("skill_rules")!=source["skill_text"]):
            block("PG07_WORKER_SKILL_BINDING_DRIFT")
        declared=source.get("expert_rules",[])
        actual=shown.get("expert_rules",[])
        if not isinstance(actual,list) or len(actual)<3 or len({r.get("rule_id") for r in actual})<3:
            block("PG07_WORKER_SKILL_RULES_TOO_FEW")
        for r in actual:
            if not any(r==x for x in declared) or not r.get("source_url","").startswith("https://"):
                block("PG07_WORKER_SKILL_RULES_UNVERIFIED")
    if not isinstance(pg07_c2,dict) or pg07_c2.get("schema_version")!="PG07_C2_WORKER_TASK_BATCH_CANDIDATE_V1":
        block("PG07_REAL_C2_VALIDATION_REQUIRED")
    frozen(pg07_c2)
    if (pg07_c2.get("production_authority") is not False or
        pg07_c2.get("dispatch_allowed") is not False or
        pg07_c2.get("worker_invoked") is not False):
        block("PG07_REAL_C2_AUTHORITY_INVALID")
    rows=[x for x in pg07_c2.get("worker_payloads",[]) if x.get("solution_id")==lot["solution_id"]]
    if len(rows)!=1 or rows[0].get("worker_visible_task_spec")!=worker_spec or rows[0].get("worker_task_spec_sha256")!=digest(worker_spec):
        block("PG07_REAL_C2_TASK_DRIFT")
    task={"schema_version":"PG07_PROFILE_TASK_OVERLAY_V1","status":"CANDIDATE_NOT_ADMITTED",
        "profile_code":assignment["profile_code"],
        "profile_assignment_sha256":assignment["assignment_sha256"],
        "write_scope":copy.deepcopy(lot["paths"]),
        "worker_spec_sha256":digest(worker_spec),
        "profile_sha256":role["profile_sha256"],"skill_code":skill["skill_code"],
        "skill_sha256":skill["skill_sha256"],
        "skill_set_sha256":skill["skill_set_sha256"],
        "skill_versions":[{"skill_code":i["skill_code"],"skill_version":i["skill_version"],"priority":i["priority"],"skill_sha256":i["skill_sha256"]} for i in items],
        "pg07_c2_candidate_sha256":pg07_c2["candidate_sha256"],"production_authority":False,
        "dispatch_allowed":False}
    task["task_sha256"]=digest(task)
    receipt={"schema_version":"PG07_PROFILE_RECEIPT_LINK_CANDIDATE_V1",
        "task_sha256":task["task_sha256"],"profile_assignment_sha256":assignment["assignment_sha256"],
        "worker_receipt_verified":False,
        "profile_sha256":role["profile_sha256"],"skill_sha256":skill["skill_sha256"],
        "skill_set_sha256":skill["skill_set_sha256"],
        "production_authority":False}
    receipt["receipt_chain_sha256"]=digest(receipt)
    return {"worker_task_overlay":task,"receipt_link_candidate":receipt,
            "worker_invoked":False,"production_authority":False}
