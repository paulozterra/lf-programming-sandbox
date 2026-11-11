#!/usr/bin/env python3
"""Independent local-only PG04-PG07 selector bridge tests (PostgreSQL disposable).
Leaves original/ and tests/test_parity.py untouched. The runner uses original SQL.
"""
import copy
import json
import os
import sys
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_experimental import guard, call, run_psql, sql_json, lit, reference
from test_parity import TABLES,FUNCTIONS
STAGES=ROOT.parent
sys.path.insert(0,str(STAGES/"pg05_target_binding_candidate"/"tests"))
from test_pg05_chain_c1_c5_v1 import build_chain
PROFILE_PACKS=STAGES/"programmer_profiles_exp"
sys.path.insert(0,str(PROFILE_PACKS))
from selector_descriptor_from_skill import apply_local_resync, candidates
from stack_skills_exp.project_stack_resolver_exp import (seed_local_binding_table,read_sql_binding,role_material,
    compose_visible_worker_spec,StackBlocked,select_binding)

sys.path.insert(0,str(STAGES/"pg07_worker_candidate"/"tools"))
from pg07_c1_worker_dispatch_plan_v1 import prepare_pg07_c1,PG07WorkerPlanBlocked
from pg07_c2_task_batch_projection_v1 import prepare_pg07_c2,TaskProjectionBlocked

from pg05_profile_assignment_bridge_v1 import (
  BridgeBlocked,digest,declare_pg04_areas,pg04_area_lot,assign_pg05,pg06_currentness,pg07_worker_projection)

def check(x,label):
    if not x:raise AssertionError(label)

def failcode(fn,code):
    try: fn()
    except BridgeBlocked as e:
        check(str(e)==code,f"Expected {code}, got {e}")
        print("PASS blocked",code)
        return
    raise AssertionError("Expected rejection: "+code)

def sql_bridge(dsn):
    def prepare(request,project,area,paths):
        return call(dsn,"public.lf_profile_selector_semantic_prepare_v3_exp("+
                    ",".join([lit(request),lit(project),lit(area),sql_json(paths)])+")")
    def finalize(request,draft):
        return call(dsn,"public.lf_profile_selector_semantic_finalize_v2_exp("+
                    sql_json(request)+","+sql_json(draft)+")")
    return prepare,finalize

def real_producers():
    """Call existing PG04 assembly and the actual PG05 C1/C2 through the repository chain.
    No handcrafted PG04 or C2 digests: the upstream source producers construct them.
    """
    chain=build_chain()
    exit_obj,c2=chain["pg04_exit"],chain["c2"]
    check(exit_obj["schema_version"]=="PG04_TO_PG05_EXIT_CANDIDATE_V1","PG04 producer missing")
    check(c2["schema_version"]=="PG05_C2_WRITE_SCOPE_RESOLUTION_CANDIDATE_V1","C2 producer missing")
    return chain

def real_pg07_validation(chain,c2,selected_solution,return_c1=False,spec_transform=None):
    """Exercise actual PG07 C1 and C2 producers on the PG05 chain, not a local reimplementation.
    PG06 C5 receipt and visible Worker specs are explicit synthetic, UNATTESTED input fixtures.
    """
    handoff=chain["handoff"]
    solution_ids=sorted(s["solution_id"] for s in handoff["solutions"])
    subject={"upstream_digests":{"pg05_exit":handoff["candidate_sha256"]},
             "solution_ids":solution_ids}
    pg06={"schema_version":"PG06_C5_INDEPENDENT_REVIEW_REQUEST_CANDIDATE_V1",
          "status":"CANDIDATE_NOT_ADMITTED","subject":subject,"subject_sha256":digest(subject),
          "pg06_admitted":False,"pg07_dispatch_allowed":False,"worker_invoked":False,
          "review_execution_allowed":False,"ledger_subject_receipt_verified":False,
          "subject_receipt_id":None,"production_authority":False,"handoff_allowed":False}
    pg06["request_sha256"]=digest(pg06)
    run={"run_ref":"fixture://pg07-run","provider":"TEST_ONLY","model_id":"fixture-model",
         "model_profile_ref":"fixture://model","pricing_ref":"fixture://no-price",
         "pricing_currency":"USD","input_price_per_million":"0",
         "output_price_per_million":"0","cached_input_price_per_million":"0",
         "lane_executor_ref":"fixture://no-dispatch","worker_contract_ref":"fixture://spec-v2",
         "worker_version":"0.8"}
    base=handoff["target_binding"]["base_head_sha"]
    snapshots={sid:"b"*64 for sid in solution_ids}
    bindings=[{"solution_id":sid,"agent_task_id":i+1,
               "task_binding_ref":"fixture://task/"+sid,"base_head_sha":base,
               "source_snapshot_sha256":snapshots[sid],
               "worker_spec_ref":"fixture://worker-spec/"+sid,
               "task_execution_authority_ref":"fixture://NO_AUTHORITY"}
              for i,sid in enumerate(solution_ids)]
    c1=prepare_pg07_c1(pg05_exit=handoff,pg06_c5=pg06,
                       run_binding=run,worker_task_bindings=bindings)
    projections=[]
    oracles=[]
    chosen=None
    for sid in solution_ids:
        paths=[x["identity"] for x in next(v for v in c2["solution_scopes"]
                                        if v["solution_id"]==sid)["write_resource_keys"]]
        spec={"schema_version":2,"task_id":"fixture-"+sid,
              "objective":"Implement guarded candidate","expected_change":"Scoped change",
              "human_story":"Synthetic PG07 validation","functional_contract":{},
              "scope":{"in_scope":paths,"out_of_scope":[],"must_not_change":[]},
              "cases":[],"dependency_resolution":{},"dependency_task_ids":[],
              "required_tests":[],"required_evidence":[],"blocked_if":[],
              "base_head_sha":base,"source_snapshot_sha256":snapshots[sid],
              "context_path_patterns":paths,"write_path_patterns":paths,
              "protected_path_patterns":[],"files_expected":paths,
              "platform_refs":[],"interface_refs":[],
              "acceptance_commands":["python3 -m compileall ."],
              "max_attempts":2,"max_patch_bytes":10000,"max_changed_files":5,
              "max_context_bytes":20000,"allow_deletions":False}
        if sid==selected_solution and spec_transform is not None:
            spec=spec_transform(spec)
        projections.append({"solution_id":sid,"function_result_ref":"fixture://function/"+sid,
                            "worker_spec":spec,"source_snapshot_sha256":snapshots[sid]})
        oracles.append({"solution_id":sid,"verifier_only_ref":"fixture://oracle/"+sid,
                        "oracle_subject_sha256":"c"*64,"access_policy":"VERIFIER_ONLY"})
        if sid==selected_solution: chosen=spec
    c2_pg07=prepare_pg07_c2(pg07_c1=c1,worker_spec_projections=projections,
                           verifier_oracle_bindings=oracles)
    tampered_projection=copy.deepcopy(projections)
    tampered_projection[0]["worker_spec"]["oracle_envelope"]={"secret":"must_not_reach_worker"}
    try:
        prepare_pg07_c2(pg07_c1=c1,worker_spec_projections=tampered_projection,
                        verifier_oracle_bindings=oracles)
    except TaskProjectionBlocked:
        print("PASS real PG07 C2 rejects hidden-oracle disclosure")
    else:
        raise AssertionError("Real PG07 C2 accepted hidden oracle")
    check(c1["dispatch_allowed"] is False and c2_pg07["dispatch_allowed"] is False,
          "PG07 producer granted dispatch")
    check(any(x["worker_visible_task_spec"]==chosen for x in c2_pg07["worker_payloads"]),
          "Real PG07 C2 did not accept chosen Worker task")
    print("PASS real PG07 C1 and C2 producers accept visible Worker specification")
    return (chosen,c2_pg07,c1) if return_c1 else (chosen,c2_pg07)

def draft_for_code(request,code):
    p=next(p for p in request["candidate_profiles"] if p["profile_code"]==code)
    evidence=p["descriptor"]["selection_evidence"][0]
    return {"decision":"SELECTED","selected_profile_code":code,
            "ambiguous_profile_codes":[],"material_ambiguities":[],
            "reason":"Elección semántica de ensayo",
            "evidence_refs":[{"profile_code":code,"kind":evidence["kind"],
                              "source_section":evidence["source_section"]}]}

def test_chain(dsn):
    prepare,finalize=sql_bridge(dsn)
    chain=real_producers()
    exit,c2=chain["pg04_exit"],chain["c2"]
    sid="SOL-002"
    scopes={row["solution_id"]:row for row in c2["solution_scopes"]}
    path=scopes[sid]["write_resource_keys"][0]["identity"]
    project="bridge_fixture"
    print("PASS actual PG04 and PG05 C2 producers, source digests")
    # The real C2 fixture uses src/SOL-*/... paths; these rules are isolated to this disposable project.
    for solution in c2["solution_scopes"]:
        run_psql(dsn,sql="INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES ("+
                 lit(project)+",'BACKEND',"+lit("src/"+solution["solution_id"]+"/")+")")
    run_psql(dsn,sql="INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES ("+
             lit(project)+",'FRONTEND','web/src/')")
    project_rules=call(dsn,"coalesce((SELECT jsonb_agg(jsonb_build_object('area',area,'path_prefix',path_prefix) ORDER BY area,path_prefix) FROM public.lf_project_area_pattern_exp WHERE project_ref="+lit(project)+"),'[]'::jsonb)")
    declarations=[]
    for sol in c2["solution_scopes"]:
        declarations.append({"solution_id":sol["solution_id"],"area":"BACKEND",
            "paths":[x["identity"] for x in sol["write_resource_keys"]]})
    pg04_areas=declare_pg04_areas(pg04_exit=exit,project_ref=project,project_rules=project_rules,lot_declarations=declarations)
    mixed=copy.deepcopy(declarations)
    mixed[-1]["paths"].append("web/src/app/x.ts")
    failcode(lambda:declare_pg04_areas(pg04_exit=exit,project_ref=project,project_rules=project_rules,
                                       lot_declarations=mixed),"LOTE_MULTI_AREA")
    conflict=project_rules+[{"area":"FRONTEND","path_prefix":"src/"+sid+"/"}]
    failcode(lambda:declare_pg04_areas(pg04_exit=exit,project_ref=project,project_rules=conflict,
                                       lot_declarations=declarations),"LOTE_ROUTE_CONFLICT")
    wrong=copy.deepcopy(declarations);wrong[-1]["area"]="FRONTEND"
    failcode(lambda:declare_pg04_areas(pg04_exit=exit,project_ref=project,project_rules=project_rules,
                                       lot_declarations=wrong),"LOTE_AREA_MISMATCH")
    print("PASS PG04 real solutions with explicit project areas and route conflict blocks")
    lot=pg04_area_lot(pg04_exit=exit,pg05_c2=c2,pg04_areas=pg04_areas,solution_id=sid,area="BACKEND",paths=[path])
    print("PASS PG04 real exit + PG05 real C2 exact write scope")
    forged=copy.deepcopy(c2);forged["solution_scopes"][0]["write_resource_keys"][0]["identity"]="forged/other.py"
    failcode(lambda:pg04_area_lot(pg04_exit=exit,pg05_c2=forged,pg04_areas=pg04_areas,
                                  solution_id=sid,area="BACKEND",paths=[path]),"SOURCE_DIGEST_INVALID")
    out_scope="src/"+sid+"/not-resolved.py"
    amended=copy.deepcopy(declarations)
    amended[-1]["paths"]=[out_scope]
    alt=declare_pg04_areas(pg04_exit=exit,project_ref=project,project_rules=project_rules,lot_declarations=amended)
    failcode(lambda:pg04_area_lot(pg04_exit=exit,pg05_c2=c2,pg04_areas=alt,
                                 solution_id=sid,area="BACKEND",paths=[out_scope]),"LOT_OUTSIDE_PG05_RESOLVED_SCOPE")
    req=prepare("Corregir servicio Spring",project,"BACKEND",[path])["request"]
    general="PERFIL-PROG-BACKEND-EXP"
    spring="PERFIL-PROG-BACKEND-SPRING-EXP"
    args={"lot":lot,"project_ref":project,"literal_request":"Corregir servicio Spring",
          "prepare":prepare,"finalize":finalize}
    assignment=assign_pg05(**args,model_draft=draft_for_code(req,general))
    check(assignment["status"]=="SELECTED" and assignment["profile_code"]==general
          and assignment["production_authority"] is False,"Assignment not selected")
    check(assignment["catalog_sha256"]==req["catalog_sha256"],"Catalog digest drift")
    check(assignment["request_sha256"]==digest(req) and
          assignment["result_sha256"]==digest(assignment["result"]),"Unbound hashes")
    print("PASS PG05 SELECTED, three bound digests, no production authority")
    alternative=assign_pg05(**args,model_draft=draft_for_code(req,spring))
    check(alternative["status"]=="SELECTED" and alternative["profile_code"]==spring,
          "Alternative valid BACKEND must remain selectable")
    print("PASS PG05 second valid backend selected by fixed AI draft")
    amb={"decision":"AMBIGUOUS","selected_profile_code":None,
         "ambiguous_profile_codes":[general,spring],"reason":"Two candidates",
         "material_ambiguities":[{"reason":"Both backend"}],
         "evidence_refs":[v for c in (general,spring)
                          for v in draft_for_code(req,c)["evidence_refs"]]}
    check(assign_pg05(**args,model_draft=amb)["status"]=="REQUIRES_HUMAN_DECISION",
          "Ambiguous must stop")
    no={"decision":"NO_MATCH","selected_profile_code":None,"ambiguous_profile_codes":[],
        "reason":"No suitable profile","material_ambiguities":[],"evidence_refs":[]}
    check(assign_pg05(**args,model_draft=no)["status"]=="REQUIRES_HUMAN_DECISION",
          "No match must stop")
    print("PASS PG05 AMBIGUOUS and NO_MATCH human stop")
    wrong=assign_pg05(**args,model_draft=draft_for_code(
       prepare("Frontend","lf_java","FRONTEND",["web/src/app/x.ts"])["request"],
       "PERFIL-PROG-FRONTEND-EXP"))
    check(wrong["status"]=="BLOCKED","Wrong area selected")
    print("PASS wrong-area selected BLOCKED")
    for field,value in (("production_authority",True),("route_authority",True),
                        ("write_scope",[path]),("completely_unknown",{"x":42})):
        elevated=draft_for_code(req,spring)
        elevated[field]=value
        def should_never_finalize(_request,_draft):
            raise AssertionError("Forbidden model draft reached finalize")
        blocked=assign_pg05(**{**args,"finalize":should_never_finalize},model_draft=elevated)
        check(blocked=={"status":"BLOCKED","blocking_code":"MODEL_DRAFT_FIELD_FORBIDDEN",
                        "production_authority":False},"Forbidden draft field not blocked: "+field)
        print("PASS model draft whitelist rejected",field)
    current=pg06_currentness(assignment=assignment,lot=lot,prepare=prepare,finalize=finalize)
    check(current["status"]=="CURRENT","PG06 currentness failed")
    print("PASS PG06 reprepare and sealed result revalidation")
    tampered=copy.deepcopy(assignment);tampered["profile_code"]=spring
    failcode(lambda:pg06_currentness(assignment=tampered,lot=lot,prepare=prepare,finalize=finalize),
             "SOURCE_DIGEST_INVALID")
    tampered=copy.deepcopy(assignment);tampered["production_authority"]=True
    tampered["assignment_sha256"]=digest({k:v for k,v in tampered.items() if k!="assignment_sha256"})
    failcode(lambda:pg06_currentness(assignment=tampered,lot=lot,prepare=prepare,finalize=finalize),
             "ASSIGNMENT_SCOPE_OR_AUTHORITY_INVALID")
    # Simulate stale areas/route/descriptor, restore in the disposable DB.
    for sql,undo,reason in [
       ("UPDATE public.lf_profile_area_policy_exp SET areas='[\"FRONTEND\"]'::jsonb WHERE profile_code="+lit(spring),
        "UPDATE public.lf_profile_area_policy_exp SET areas='[\"BACKEND\"]'::jsonb WHERE profile_code="+lit(spring),"area"),
       ("INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES ("+lit(project)+",'BACKEND','server/src/')",
        "DELETE FROM public.lf_project_area_pattern_exp WHERE project_ref="+lit(project)+" AND path_prefix='server/src/'","routes"),
       ("UPDATE public.lf_profile_selection_registry_v1 SET descriptor_status='STALE_SOURCE_CHANGED' WHERE profile_code="+lit(spring),
        "UPDATE public.lf_profile_selection_registry_v1 SET descriptor_status='CURRENT' WHERE profile_code="+lit(spring),"descriptor")]:
        run_psql(dsn,sql=sql)
        try:
            failcode(lambda:pg06_currentness(assignment=assignment,lot=lot,prepare=prepare,finalize=finalize),
                     "PG06_SELECTOR_POLICY_OR_CATALOG_STALE")
        finally:run_psql(dsn,sql=undo)
        print("PASS PG06 changed",reason,"blocked")
    # Project/area are SQL data, not profile keywords or AI-generated skill selections.
    java_skill=read_sql_binding(dsn,run_psql,"lf_java","BACKEND")
    python_skill=read_sql_binding(dsn,run_psql,"lf_python","BACKEND")
    check(java_skill["skill_code"]=="SPRINGBOOT_EXP" and python_skill["skill_code"]=="FASTAPI_EXP",
          "Same BACKEND role must resolve different project skill")
    check(role_material(general)["profile_code"]==general,
          "Shared role changed between projects")
    print("PASS same generic BACKEND role uses Spring / FastAPI from project bindings")
    try:
        read_sql_binding(dsn,run_psql,"lf_python","FRONTEND")
    except StackBlocked as ex:
        check(str(ex)=="SKILL_NOT_BOUND",str(ex))
        print("PASS SKILL_NOT_BOUND for unbound project area")
    else: raise AssertionError("Unbound skill accepted")
    check([x["skill_code"]+"@"+x["skill_version"] for x in java_skill["skills"]]==
          ["SPRINGBOOT_EXP@3","KAFKA_EXP@3"],"SQL priority failed to order multi-skill BACKEND")
    print("PASS SQL multi-skill priority Spring Boot@3 then Kafka@3")
    original_java_sha=java_skill["skill_sha256"]
    # Mutate only primary row: multi-area now contains two skills.
    primary_filter=" WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='SPRINGBOOT_EXP' AND skill_version='3'"
    run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET skill_sha256="+lit("0"*64)+primary_filter)
    try:
        try:read_sql_binding(dsn,run_psql,"lf_java","BACKEND")
        except StackBlocked as ex:
            check(str(ex)=="SKILL_SHA256_MISMATCH",str(ex))
            print("PASS tampered stack skill SHA blocked")
        else:raise AssertionError("Tampered skill accepted")
    finally:
        run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET skill_sha256="+lit(original_java_sha)+primary_filter)
    run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET skill_version='2'"+primary_filter)
    try:
        try:read_sql_binding(dsn,run_psql,"lf_java","BACKEND")
        except StackBlocked as ex:
            check(str(ex)=="SKILL_VERSION_MISMATCH",str(ex))
            print("PASS linked skill version changed BLOCK")
        else:raise AssertionError("Wrong version accepted")
    finally:
        run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET skill_version='3' WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='SPRINGBOOT_EXP' AND skill_version='2'")
    run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET priority=NULL WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='KAFKA_EXP'")
    try:
        try:read_sql_binding(dsn,run_psql,"lf_java","BACKEND")
        except StackBlocked as ex:
            check(str(ex)=="SKILL_PRIORITY_REQUIRED",str(ex))
            print("PASS missing SQL priority BLOCK")
        else:raise AssertionError("Missing priority accepted")
    finally:
        run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET priority=2 WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='KAFKA_EXP'")
    run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET priority=1 WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='KAFKA_EXP'")
    try:
        try:read_sql_binding(dsn,run_psql,"lf_java","BACKEND")
        except StackBlocked as ex:
            check(str(ex)=="SKILL_PRIORITY_CONFLICT",str(ex))
            print("PASS conflicting SQL priorities BLOCK")
        else:raise AssertionError("Duplicate priorities accepted")
    finally:
        run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET priority=2 WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='KAFKA_EXP'")
    front=read_sql_binding(dsn,run_psql,"lf_java","FRONTEND")
    run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET skill_code="+lit(front["skill_code"])+
                     ",skill_version="+lit(front["skill_version"])+
                     ",skill_sha256="+lit(front["skill_sha256"])+primary_filter)
    try:
        try:read_sql_binding(dsn,run_psql,"lf_java","BACKEND")
        except StackBlocked as ex:
            check(str(ex)=="SKILL_AREA_MISMATCH",str(ex))
            print("PASS cross-area skill blocked")
        else:raise AssertionError("Wrong-area skill accepted")
    finally:
        run_psql(dsn,sql="UPDATE public.project_stack_binding_exp SET skill_code='SPRINGBOOT_EXP',skill_version='3',skill_sha256="+
                         lit(original_java_sha)+" WHERE project_ref='lf_java' AND area='BACKEND' AND skill_code='ANGULAR_EXP'")
    role=role_material(assignment["profile_code"])
    skill=read_sql_binding(dsn,run_psql,assignment["project_ref"],assignment["area"])
    spec,pg07_c2=real_pg07_validation(chain,c2,sid,
        spec_transform=lambda raw:compose_visible_worker_spec(raw,assignment,role,skill))
    check(spec["functional_contract"]["role_and_stack"]["skill_code"]==skill["skill_code"],
          "Bound stack not inserted in Worker visible task")

    out=pg07_worker_projection(assignment=assignment,lot=lot,
                               currentness=current,worker_spec=spec,pg07_c2=pg07_c2,
                               role=role,skill=skill,project_binding_row=skill["binding_row"])
    task=out["worker_task_overlay"];receipt=out["receipt_link_candidate"]
    check(task["profile_code"]==general and task["write_scope"]==[path] and
          task["profile_assignment_sha256"]==assignment["assignment_sha256"] and
          receipt["profile_assignment_sha256"]==assignment["assignment_sha256"] and
          task["profile_sha256"]==role["profile_sha256"] and
          task["skill_sha256"]==skill["skill_sha256"] and
          task["skill_set_sha256"]==skill["skill_set_sha256"] and
          len(task["skill_versions"])==len(skill["skills"]) and
          receipt["profile_sha256"]==role["profile_sha256"] and
          receipt["skill_sha256"]==skill["skill_sha256"] and
          receipt["worker_receipt_verified"] is False and
          out["worker_invoked"] is False and out["production_authority"] is False,
          "PG07 chain not intact")
    print("PASS PG07 scoped worker task and candidate receipt digest chain")
    modified_role=copy.deepcopy(role)
    modified_role["role_text"]+="\\nUNAUTHORIZED CHANGE"
    failcode(lambda:pg07_worker_projection(assignment=assignment,lot=lot,
               currentness=current,worker_spec=spec,pg07_c2=pg07_c2,
               role=modified_role,skill=skill,project_binding_row=skill["binding_row"]),
             "PG07_ROLE_OR_SKILL_SHA256_MISMATCH")
    modified_skill=copy.deepcopy(skill)
    modified_skill["skill_text"]+="\\nINJECTED STACK RULE"
    failcode(lambda:pg07_worker_projection(assignment=assignment,lot=lot,
               currentness=current,worker_spec=spec,pg07_c2=pg07_c2,
               role=role,skill=modified_skill,project_binding_row=skill["binding_row"]),
             "PG07_ROLE_OR_SKILL_SHA256_MISMATCH")
    print("PASS PG07 unmodified role and skill SHA invariants")
    failcode(lambda:pg07_worker_projection(assignment=assignment,lot=lot,
               currentness=current,worker_spec={"schema_version":2,"oracle_envelope":{}},pg07_c2=pg07_c2,
               role=role,skill=skill,project_binding_row=skill["binding_row"]),
             "PG07_ORACLE_EXPOSURE")
    failcode(lambda:pg07_worker_projection(assignment=assignment,lot=lot,
               currentness=current,worker_spec={**spec,
               "write_path_patterns":[path,"src/"+sid+"/Unexpected.java"]},pg07_c2=pg07_c2,
               role=role,skill=skill,project_binding_row=skill["binding_row"]),
             "PG07_WORKER_SPEC_SCOPE_EXCEEDS_ASSIGNMENT")
    print("PASS PG07 Worker-visible write scope cannot expand outside PG05 C2")

    # PG04-mixed projects are also blocked by the actual SQL classifier.
    mixed=prepare("Split or block",project,"BACKEND",
                  [path,"web/src/app/loan.ts"])
    check(mixed.get("blocking_code")=="LOTE_MULTI_AREA_BLOCKED","Mixed-area PG04 lot accepted")
    print("PASS PG04 mixed area LOTE_MULTI_AREA_BLOCKED")

def main():
    dsn=os.environ.get("SELECTOR_EXP_TEST_DSN","")
    guard(dsn)
    try:
        run_psql(dsn,file=ROOT/"original/schema/bootstrap.sql")
        run_psql(dsn,file=ROOT/"original/schema/tables.sql")
        run_psql(dsn,file=ROOT/"original/schema/constraints.sql")
        for t in TABLES:run_psql(dsn,file=ROOT/"original/data"/(t+".sql"))
        for f in FUNCTIONS:run_psql(dsn,file=ROOT/"original/functions"/f)
        reference(dsn)
        for f in ("seed_profiles_exp.sql","area_policy_exp.sql","functions_exp.sql"):
            run_psql(dsn,file=ROOT/"experimental"/f)
        checkout=subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
        head=os.environ.get("PROFILE_CANDIDATE_HEAD_SHA",checkout)
        check(head==checkout,"Exact candidate HEAD differs from checkout")
        bound=apply_local_resync(dsn,head,run_psql,sql_json)
        check(len(bound)==3,"Three SKILL-backed descriptors required")
        print("PASS original descriptor_sync_v1 generated 3 candidate descriptors from SKILL.md")
        run_psql(dsn,file=STAGES/"programmer_profiles_exp/stack_skills_exp/project_stack_binding_exp.sql")
        seed_local_binding_table(dsn,run_psql)
        test_chain(dsn)
    finally:
        run_psql(dsn,sql="DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS extensions CASCADE")
        left=run_psql(dsn,sql="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','extensions') AND c.relkind IN ('r','p','v','m')")
        check(left=="0","Residual tables/views: "+left)
        check(run_psql(dsn,sql="SELECT count(*) FROM pg_namespace WHERE nspname='extensions'")=="0",
              "Residual extensions schema")
        print("PASS cleanup 0 residual schemas/objects")
    print("PASS PG04_TO_PG07_BRIDGE_CANDIDATE_V1")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("FAIL",repr(exc),file=sys.stderr)
        raise SystemExit(1)
