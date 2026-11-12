#!/usr/bin/env python3
"""CP3.3 — candidate-only PG-02→PG-05 orchestration with pinned LF producers.

Only adapters/project-specific *synthetic* inputs live here. Semantics of
classification, strategy, partition, DoD, review, binding, area overlay,
selector and currentness are always executed in their pinned producers.
No authority/Worker invocation, fake model reply, Supabase or private exams.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from intake import IntakeBlocked, canonical, validate, ROOT

PINNED = ROOT / "pilot/lf_producers_pinned"
# The real pinned modules are not Python packages. Keep their original import
# signatures; do not edit their source, use test fixtures as producer outputs,
# or substitute an equivalent local implementation.
PATHS = [
    "pg02", "pg03_strategy_candidate",
    "pg04_semantic_partition_candidate/tools",
    "pg05_target_binding_candidate/tools",
    "selector_experimental/integration",
    "selector_experimental/tests",
]
for folder in PATHS:
    absolute = str(PINNED / folder)
    if absolute not in sys.path:
        sys.path.insert(0, absolute)

from pg02_classification_outcome_v1 import classify_with_outcome
from pg03_strategy_v1 import prepare_strategy
from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome
from pg04_c7_coverage_dossier_v1 import build_coverage_dossier
from pg04_definition_of_done_candidate_v1 import prepare_dod
from pg04_independent_review_request_v1 import prepare_partition_review_request
from pg04_pg05_exit_candidate_v1 import assemble_pg04_exit_candidate
from pg05_c1_target_binding_preflight_v1 import prepare_pg05_c1
from pg05_c2_write_scope_candidate_v1 import prepare_pg05_c2
from pg05_c3_collision_lock_plan_candidate_v1 import prepare_pg05_c3
from pg05_c4_write_boundary_preflight_v1 import prepare_pg05_c4
from pg05_c5_independent_assurance_request_v1 import prepare_pg05_assurance_request
from pg05_pg06_exit_candidate_v1 import assemble_pg05_pg06_candidate
from pg05_profile_assignment_bridge_v1 import (
    declare_pg04_areas, pg04_area_lot, assign_pg05, pg06_currentness)
from test_experimental import call, lit
from test_parity import sql_json

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
AREAS = {"DATA", "BACKEND", "FRONTEND"}
KIND = {"DATA":"CP33_DATA", "BACKEND":"CP33_BACKEND", "FRONTEND":"CP33_FRONTEND"}
DOMAIN = {"DATA":"STD-DATA", "BACKEND":"STD-BE", "FRONTEND":"STD-FE"}
WORK = "CP33"
POLICY_PATH = PINNED / "wave1_boundary_contracts/programming_solution_partition_contract_v1.json"


class PlanningBlocked(ValueError):
    pass


def blocked(reason):
    raise PlanningBlocked(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def topo(lots):
    """Only DAG ordering and safety belong to the orchestrator, not partitioning."""
    ids = [lot["id"] for lot in lots]
    if len(set(ids)) != len(ids):
        blocked("LOTES_DUPLICADOS")
    by_id = {lot["id"]: lot for lot in lots}
    result, active, done = [], set(), set()
    def visit(sid):
        if sid in active:
            blocked("LOTES_CICLO")
        if sid in done:
            return
        if sid not in by_id:
            blocked("LOTES_DEPENDENCIA_DESCONOCIDA")
        active.add(sid)
        for dep in sorted(by_id[sid]["depends_on"]):
            visit(dep)
        active.remove(sid)
        done.add(sid)
        result.append(by_id[sid])
    for sid in sorted(ids):
        visit(sid)
    return result


def _inputs(package, fixture):
    if (not isinstance(fixture, dict) or
            fixture.get("schema_version") != "CP33_SIMULATED_INPUTS_V1" or
            fixture.get("simulation_only") is not True):
        blocked("LOTES_FIXTURE_INVALIDA")
    if package.get("analysis_mode") != "SIMULATED_ANALYSIS":
        blocked("LOTES_ANALYSIS_NOT_SIMULATED")
    rows = fixture.get("atoms")
    binding = fixture.get("target_binding")
    prefs = fixture.get("profile_choices")
    if (not isinstance(rows, list) or not rows or not isinstance(binding, dict)
            or not isinstance(prefs, dict) or not isinstance(fixture.get("project_ref"), str)):
        blocked("LOTES_FIXTURE_INVALIDA")
    if (not SHA40.fullmatch(binding.get("base_head_sha","")) or
            not isinstance(binding.get("repo_full_name"),str) or "/" not in binding["repo_full_name"] or
            not isinstance(binding.get("target_binding_ref"),str)):
        blocked("LOTES_TARGET_INVALIDO")
    scopes = {s["scope_id"]:s for s in package["scope_proposals"]}
    front_by_id = {f["front_id"]:f for f in package["material_fronts"]}
    requirements = package["requirements"]
    req_by_scope = {}
    for r in requirements:
        req_by_scope.setdefault(r["scope_id"], []).append(r)
    if len({x.get("atom_id") for x in rows}) != len(rows):
        blocked("LOTES_ATOMO_DUPLICADO")
    referenced = set()
    for a in rows:
        if (not isinstance(a,dict) or
            not {"atom_id","scope_id","front_id","area","paths","depends_on",
                 "outcome_id","business_outcome"}.issubset(a)):
            blocked("LOTES_FIXTURE_INVALIDA")
        sid=a["scope_id"]
        if sid not in scopes or a["front_id"] not in front_by_id:
            blocked("LOTES_SCOPE_SIN_ANALISIS")
        if a["front_id"] not in scopes[sid].get("material_front_refs",[]) or (
                sid not in front_by_id[a["front_id"]].get("scope_ids",[])):
            blocked("LOTES_FRENTE_SIN_TRAZABILIDAD")
        if not req_by_scope.get(sid):
            blocked("LOTES_FRENTE_SIN_REQUISITOS")
        if scopes[sid].get("readiness_candidate") != "READY_CANDIDATE":
            blocked("LOTES_ANALISIS_NO_LISTO")
        if a["area"] not in AREAS or not isinstance(a["paths"],list) or not a["paths"]:
            blocked("LOTE_MULTIAREA")
        if not isinstance(a["depends_on"],list):
            blocked("LOTES_FIXTURE_INVALIDA")
        if sid in referenced:
            blocked("LOTES_SCOPE_DUPLICADO")
        referenced.add(sid)
    if set(scopes)!=referenced:
        blocked("LOTES_COBERTURA_INCOMPLETA")
    if not set(prefs).issuperset({a["area"] for a in rows}):
        blocked("SELECTOR_REQUIERE_DECISION")
    return sorted(rows,key=lambda x:x["atom_id"])


def _source_inputs(package, rows, fixture, request_sha, state):
    # Exact A9→PG02 candidate snapshot projection; never PG-01 attestation.
    scopes = {s["scope_id"]:s for s in package["scope_proposals"]}
    by_front = {f["front_id"]:f for f in package["material_fronts"]}
    matrix,fronts = [],[]
    for a in rows:
        f = by_front[a["front_id"]]
        fronts.append({"front_id":a["front_id"],"front_kind":KIND[a["area"]],
                       "status":f["obligation_mode"],"closure":f["closure"],
                       "scope_refs":[a["scope_id"]]})
        matrix.append({"scope_id":a["scope_id"],"front_id":a["front_id"],
                       "front_status":f["obligation_mode"],"front_closure":f["closure"],
                       "effect_on_scope":"PRESERVE" if f["closure"]=="CLOSED" else "BLOCKS"})
    snapshot = {"schema_version":"PROGRAMMING_CONTEXT_SNAPSHOT_V1",
        "target_granularity":{"level":package["classification"]["target_granularity"],
                              "target_ref":package["request_context"]["target_ref"]},
        "scope_readiness":[{"scope_id":sid,
                            "status":"READY" if s["readiness_candidate"]=="READY_CANDIDATE" else "BLOCKED",
                            "material_front_refs":s["material_front_refs"]}
                           for sid,s in sorted(scopes.items())],
        "material_front_coverage":{"all_material_fronts_accounted":True,
              "unmapped_material_signals":[],"material_fronts":fronts},
        "scope_front_matrix":matrix}
    mapping = {"state":"SOURCE_ONLY_CANDIDATE","source_ref":"fixture://cp33/domain-mapping",
       "version":"CP33_LOCAL_V1",
       "front_kind_domains":{KIND[a]:[DOMAIN[a]] for a in sorted(AREAS)},
       "domain_stack_layers":{DOMAIN[a]:[a] for a in sorted(AREAS)}}
    pg01 = {"source":"PG01_C4","architecture_repo":"fixture://sandbox",
         "architecture_commit":fixture["target_binding"]["base_head_sha"],
         "manifest_digest_sha256":digest(fixture),
         "architecture_profile":{"active_layers":sorted({r["area"] for r in rows})},
         "context_binding":{"context_id":"fixture://"+request_sha[:16],
                            "context_sha256":request_sha,
                            "receipt_ref":"fixture://pg01/unattested"}}
    return snapshot,mapping,pg01


def _policy():
    contract = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if contract.get("schema_version")!="PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1":
        blocked("PG04_CONTRACT_INVALIDO")
    return contract


def _source_chain(package, fixture, rows, sha, state):
    snapshot,mapping,pg01 = _source_inputs(package, rows, fixture, sha, state)
    pg02 = classify_with_outcome(snapshot,mapping,pg01_binding=pg01)
    if pg02.get("status")!="CANDIDATE_NOT_ADMITTED" or any(
            s["state"]!="READY_FOR_CLASSIFICATION" for s in pg02["candidate"]["scopes"]):
        blocked("PG02_NO_CLASIFICA:"+str(pg02.get("reason_code","NON_READY_SCOPE")))
    contract = _policy()
    requirements = package["requirements"]
    req_ids = sorted(x["requirement_id"] for x in requirements)
    acceptances = sorted("ACC-"+x for x in req_ids)
    stack = {"status":"CANDIDATE_NOT_ADMITTED","authority":False,
             "commit_sha":fixture["target_binding"]["base_head_sha"],
             "sources":[{"sha256":digest({"request_sha256":sha,"fixture":fixture})}]}
    strategy = prepare_strategy(
        classification=pg02,stack_evidence=stack,partition_contract=contract,
        requirement_ids=req_ids,acceptance_ids=acceptances,
        reuse_refs=["fixture://reuse-assessment"],capability_selector="FIXTURE_CANDIDATE_ONLY",
        alternatives=["REUSE_EXISTING","BUILD_NEW"],fallback="REQUIRES_DECISION")
    req_by_scope={}
    for r in requirements:
        req_by_scope.setdefault(r["scope_id"],[]).append(r)
    obligations=[]
    outcomes=[]
    for row in rows:
        rids=sorted(r["requirement_id"] for r in req_by_scope[row["scope_id"]])
        outcomes.append({"outcome_id":row["outcome_id"],
                         "business_outcome":row["business_outcome"],
                         "evidence_ref":"fixture://a7/"+row["front_id"]})
        obligations.append({
            "atom_id":row["atom_id"],"outcome_id":row["outcome_id"],
            "source_ref":"fixture://a7/"+row["front_id"],
            "scope_id":row["scope_id"],"risk_level":"MEDIUM",
            "semantic_rationale":"Explicit synthetic A7 material front, not an inferred code split",
            "write_scope_reason":"Paths declared in synthetic A9 planning evidence",
            "write_scope":sorted(row["paths"]),"shared_contract_refs":[],
            "implementation_state":package["classification"]["implementation_state"],
            "bounded_reuse_assessment_ref":"fixture://a3/reuse/"+row["atom_id"],
            "requirement_ids":rids,"acceptance_ids":["ACC-"+r for r in rids],
            "depends_on":sorted(row["depends_on"]),"coimplement_with":[]})
    from pg04_semantic_partition_candidate_v1 import PartitionBlocked
    try:
        partition=partition_by_semantic_outcome(strategy=strategy,partition_contract=contract,
                    obligations=obligations,outcome_registry=outcomes)
    except PartitionBlocked as exc:
        if str(exc)=="SOLUTION_DEPENDENCY_CYCLE":
            blocked("LOTES_CICLO")
        raise
    dossier=build_coverage_dossier(partition=partition,strategy=strategy,original_obligations=obligations)
    # DoD checks are unexecuted synthetic candidate obligations, never PASS.
    standard="STD-CP33-FIXTURE"
    standards=[{"standard_code":standard,"source_ref":"fixture://cp33/standards",
                "source_sha256":digest(contract),
                "applies_to_write_scopes":sorted({p for o in obligations for p in o["write_scope"]})}]
    registry=[{"validation_code":"CP33_VISIBLE_FIXTURE_CHECK","status":"ACTIVE",
               "source_ref":"fixture://cp33/offline-gate"}]
    plans=[]
    for sol in partition["solutions"]:
        checks=[{"check_id":"STD-"+sol["id"],"kind":"STANDARD",
                 "validation_code":"CP33_VISIBLE_FIXTURE_CHECK",
                 "input_ref":"fixture://standard/"+standard,
                 "requirement_ids":[],"acceptance_ids":[],"standard_code":standard}]
        checks += [{"check_id":"REQ-"+r,"kind":"REQUIREMENT",
                    "validation_code":"CP33_VISIBLE_FIXTURE_CHECK",
                    "input_ref":"fixture://requirement/"+r,"requirement_ids":[r],
                    "acceptance_ids":[]}
                   for r in sol["requirement_ids"]]
        checks += [{"check_id":"CHECK-"+a,"kind":"ACCEPTANCE",
                    "validation_code":"CP33_VISIBLE_FIXTURE_CHECK",
                    "input_ref":"fixture://acceptance/"+a,"requirement_ids":[],
                    "acceptance_ids":[a]}
                   for a in sol["acceptance_ids"]]
        checks += [{"check_id":"DEP-"+d,"kind":"DEPENDENCY",
                    "validation_code":"CP33_VISIBLE_FIXTURE_CHECK",
                    "input_ref":"fixture://dependency/"+d,
                    "requirement_ids":[],"acceptance_ids":[],"dependency_ids":[d]}
                   for d in sol["depends_on"]]
        plans.append({"solution_id":sol["id"],"standard_codes":[standard],"checks":checks})
    dod=prepare_dod(partition=partition,standards_catalog_version="CP33-FIXTURE-NOT-VERIFIED",
                    standards=standards,validation_registry=registry,solution_plans=plans)
    manifest={key:{"ref":"fixture://cp33/"+key,"sha256":value} for key,value in {
        "a9_package":digest(package),"pg03_strategy":strategy["candidate_sha256"],
        "pg04_partition_contract":digest(contract),
        "outcome_registry":digest(outcomes),"typed_obligations":digest(obligations)}.items()}
    manifest["source_head_sha"]=fixture["target_binding"]["base_head_sha"]
    review=prepare_partition_review_request(partition=partition,sources=manifest,
          producer_execution_id="fixture://cp33/pg04",coverage_dossier=dossier)
    pg04=assemble_pg04_exit_candidate(partition=partition,dod=dod,
          coverage_dossier=dossier,review_request=review,
          target_binding=fixture["target_binding"])
    c1=prepare_pg05_c1(pg04_exit=pg04,work_code=WORK,slug="synthetic-lots")
    resolutions=[]
    for sol in pg04["solutions"]:
        resolutions.append({
          "solution_id":sol["solution_id"],
          "resolved_scopes":[{"scope_token":p,
            "derivation_ref":"fixture://cp33/l3/"+sol["solution_id"],
            "resources":[{"kind":"REPO_PATH","identity":p,
                          "source_ref":"fixture://cp33/path/"+sol["solution_id"]}]}
              for p in sol["write_scope_candidates"]],
          "shared_read_refs":[],"l3_structure_ref":"fixture://cp33/l3"})
    c2=prepare_pg05_c2(pg04_exit=pg04,pg05_c1=c1,scope_resolutions=resolutions)
    if c2["collisions_for_pg05_c3"]:
        blocked("LOTE_COLISION_ESCRITURA")
    c3=prepare_pg05_c3(pg04_exit=pg04,pg05_c2=c2)
    proposals=[]
    for sol in c2["solution_scopes"]:
        proposals.append({"solution_id":sol["solution_id"],
             "source_head_sha":fixture["target_binding"]["base_head_sha"],
             "proposal_ref":"fixture://cp33/no-actual-code",
             "changes":[{"operation":"MODIFY","resource":copy.deepcopy(r),
                         "change_ref":"fixture://cp33/proposed-change/"+sol["solution_id"]}
                        for r in sol["write_resource_keys"]]})
    c4=prepare_pg05_c4(pg04_exit=pg04,pg05_c2=c2,pg05_c3=c3,change_proposals=proposals)
    parts={"pg04_exit":pg04,"pg05_c1":c1,"pg05_c2":c2,"pg05_c3":c3,"pg05_c4":c4}
    source_manifest={"source_head_sha":fixture["target_binding"]["base_head_sha"],
        **{name:{"ref":"fixture://cp33/"+name,"sha256":output["candidate_sha256"]}
           for name,output in parts.items()}}
    c5=prepare_pg05_assurance_request(pg04_exit=pg04,pg05_c1=c1,pg05_c2=c2,
        pg05_c3=c3,pg05_c4=c4,source_manifest=source_manifest,
        producer_execution_id="fixture://cp33/pg05")
    handoff=assemble_pg05_pg06_candidate(pg04_exit=pg04,pg05_c1=c1,
        pg05_c2=c2,pg05_c3=c3,pg05_c4=c4,pg05_c5=c5)
    outputs={"PG02":pg02["candidate"],"PG03":strategy,"PG04":partition,
        "PG04_C7":dossier,"PG04_DOD":dod,"PG04_REVIEW":review,"PG04_EXIT":pg04,
        "PG05_C1":c1,"PG05_C2":c2,"PG05_C3":c3,"PG05_C4":c4,
        "PG05_C5":c5,"PG05_EXIT":handoff}
    return outputs


def _selector(dsn, project, area, paths):
    def prepare(request, project_ref, selected_area, files):
        return call(dsn,"public.lf_profile_selector_semantic_prepare_v3_exp("+
                    ",".join((lit(request),lit(project_ref),lit(selected_area),sql_json(files)))+")")
    def finalize(request, draft):
        return call(dsn,"public.lf_profile_selector_semantic_finalize_v2_exp("+
                    sql_json(request)+","+sql_json(draft)+")")
    return prepare,finalize


def _rules(dsn, project):
    q="COALESCE((SELECT jsonb_agg(jsonb_build_object('area',area,'path_prefix',path_prefix) ORDER BY area,path_prefix) FROM public.lf_project_area_pattern_exp WHERE project_ref="+lit(project)+"),'[]'::jsonb)"
    rules=call(dsn,q)
    if not isinstance(rules,list) or not rules:
        blocked("SELECTOR_REQUIERE_ENTORNO")
    return rules


def _produce_lots(package, fixture, rows, outputs, dsn):
    pg04=outputs["PG04_EXIT"]
    c2=outputs["PG05_C2"]
    rules=_rules(dsn,fixture["project_ref"])
    sols=pg04["solutions"]
    by_atom={r["atom_id"]:r for r in rows}
    declarations=[]
    for sol in sols:
        areas={by_atom[a]["area"] for a in sol["atom_ids"]}
        if len(areas)!=1:
            blocked("LOTE_MULTIAREA")
        declarations.append({"solution_id":sol["solution_id"],
            "area":next(iter(areas)),
            "paths":[r["identity"] for r in next(x for x in c2["solution_scopes"]
                if x["solution_id"]==sol["solution_id"])["write_resource_keys"]]})
    try:
        area_overlay=declare_pg04_areas(pg04_exit=pg04,project_ref=fixture["project_ref"],
                                        lot_declarations=declarations,project_rules=rules)
    except ValueError as exc:
        if str(exc) in ("LOTE_MULTI_AREA","LOTE_ROUTE_CONFLICT","LOTE_AREA_MISMATCH"):
            blocked("LOTE_MULTIAREA")
        raise
    lots=[]
    assignment_hashes={}
    currentness_hashes={}
    for dec in declarations:
        sid,area,paths=dec["solution_id"],dec["area"],dec["paths"]
        lot=pg04_area_lot(pg04_exit=pg04,pg05_c2=c2,pg04_areas=area_overlay,
                          solution_id=sid,area=area,paths=paths)
        prepare,finalize=_selector(dsn,fixture["project_ref"],area,paths)
        preference=fixture["profile_choices"].get(area)
        if not preference:
            blocked("SELECTOR_REQUIERE_DECISION")
        request_wrap=prepare(package["request_context"]["intent"],fixture["project_ref"],area,paths)
        if request_wrap.get("status")!="READY":
            blocked("SELECTOR_REQUIERE_ENTORNO")
        request=request_wrap["request"]
        matches=[p for p in request["candidate_profiles"] if p["profile_code"]==preference]
        if len(matches)!=1:
            blocked("SELECTOR_PERFIL_NO_CANDIDATO")
        evidence=matches[0]["descriptor"]["selection_evidence"][0]
        draft={"decision":"SELECTED","selected_profile_code":preference,
             "ambiguous_profile_codes":[],"reason":"Preferencia explícita de fixture sintético; validada por SQL",
             "evidence_refs":[{"profile_code":preference,"kind":evidence["kind"],
                               "source_section":evidence["source_section"]}],
             "material_ambiguities":[]}
        assignment=assign_pg05(lot=lot,project_ref=fixture["project_ref"],
            literal_request=package["request_context"]["intent"],
            model_draft=draft,prepare=prepare,finalize=finalize)
        if assignment.get("status")!="SELECTED":
            blocked("SELECTOR_REQUIERE_DECISION")
        current=pg06_currentness(assignment=assignment,lot=lot,
             prepare=prepare,finalize=finalize)
        original=next(s for s in sols if s["solution_id"]==sid)
        lots.append({"id":sid,"area":area,"profile_code":assignment["profile_code"],
            "write_paths":paths,"depends_on":original["depends_on"],
            "requirement_ids":original["requirement_ids"],
            "production_authority":False,"handoff_allowed":False,
            "pg04_exit_sha256":pg04["candidate_sha256"],
            "pg05_c2_sha256":c2["candidate_sha256"],
            "bridge_lot_sha256":lot["lot_sha256"],
            "profile_assignment_sha256":assignment["assignment_sha256"],
            "profile_currentness_sha256":current["currentness_sha256"]})
        assignment_hashes[sid]=assignment["assignment_sha256"]
        currentness_hashes[sid]=current["currentness_sha256"]
    # Pin the complete bytes of every actual producer output; a few producers
    # intentionally have no candidate_sha256 property (do not add one to LF).
    hashes={key:digest(value) for key,value in outputs.items()}
    hashes["PG04_AREA_OVERLAY"]=area_overlay["area_overlay_sha256"]
    return topo(lots),hashes,assignment_hashes,currentness_hashes


def plan(root: Path, run: str) -> dict:
    from intake import SLUG, normalized_request_bytes
    if not isinstance(run,str) or not SLUG.fullmatch(run):
        blocked("LOTES_RUN_INVALIDO")
    folder=root/"pilot/runs"/run
    if folder.is_symlink():
        blocked("LOTES_RUTA_INVALIDA")
    inputs=[folder/name for name in ("request.md","analysis.json","state.json","planning_fixture.json")]
    if any(not p.is_file() or p.is_symlink() for p in inputs):
        blocked("LOTES_ENTRADA_FALTANTE")
    request,analysis_raw,state_raw,fixture_raw=[p.read_bytes() for p in inputs]
    try:
        package=json.loads(analysis_raw)
        state=json.loads(state_raw)
        fixture=json.loads(fixture_raw)
    except (UnicodeError,ValueError):
        blocked("LOTES_JSON_INVALIDO")
    try:
        _, sha=validate(package,request)
    except IntakeBlocked as exc:
        blocked(str(exc))
    if (state.get("stage") not in ("INTAKE_ACCEPTED","LOTS_PLANNED") or
         state.get("request_sha256")!=sha or
         state.get("analysis_sha256")!=hashlib.sha256(canonical(package)).hexdigest()
         or state.get("pg01",{}).get("status")!="FIXTURE_UNATTESTED" or
         state.get("production_authority") is not False):
        blocked("LOTES_INTAKE_NO_ACEPTADO")
    rows=_inputs(package,fixture)
    outputs=_source_chain(package,fixture,rows,sha,state)
    dsn=os.environ.get("SELECTOR_EXP_TEST_DSN","")
    if os.environ.get("SELECTOR_EXP_DISPOSABLE_DB")!="YES" or not dsn:
        blocked("SELECTOR_REQUIERE_ENTORNO")
    from urllib.parse import urlsplit,unquote
    parsed=urlsplit(dsn)
    if (parsed.scheme not in ("postgres","postgresql") or
        parsed.hostname not in ("localhost","127.0.0.1","::1") or
        not unquote(parsed.path.lstrip("/")).startswith("selector_exp_test_") or
        parsed.query or parsed.fragment):
        blocked("SELECTOR_REQUIERE_ENTORNO")
    try:
        lots,producer_hashes,assignments,currentness=_produce_lots(package,fixture,rows,outputs,dsn)
    except (OSError,RuntimeError):
        blocked("SELECTOR_REQUIERE_ENTORNO")
    document={"schema_version":"CP33_LOTS_CANDIDATE_V1","request_id":run,
        "request_sha256":sha,"analysis_sha256":state["analysis_sha256"],
        "planning_fixture_sha256":digest(fixture),
        "pg01_status":"FIXTURE_UNATTESTED",
        "producer_outputs_sha256":producer_hashes,
        "profile_assignments_sha256":assignments,
        "profile_currentness_sha256":currentness,
        "lots":lots,"topological_order":[lot["id"] for lot in lots],
        "production_authority":False,"handoff_allowed":False,
        "worker_invoked":False,"pg07_projection_status":"PENDING_ROLE_AND_SKILL_BINDING_CP3_4"}
    state_next=dict(state,stage="LOTS_PLANNED",lots_sha256=hashlib.sha256(canonical(document)).hexdigest(),
                    lot_count=len(lots),production_authority=False,
                    handoff_allowed=False,downstream_authorized=False,
                    pg01_consumer_verified=False)
    output=folder/"lots.json"
    future=canonical(document)
    if output.exists():
        if output.is_symlink() or output.read_bytes()!=future:
            blocked("LOTES_OUTPUT_DRIFT")
    if state["stage"]=="LOTS_PLANNED" and state_raw!=canonical(state_next):
        blocked("LOTES_STATE_DRIFT")
    if not output.exists():
        with output.open("xb") as f:
            f.write(future)
    next_bytes=canonical(state_next)
    if next_bytes!=state_raw:
        temp=folder/".state.cp33.tmp"
        if temp.exists() or temp.is_symlink():
            blocked("LOTES_STATE_TEMP_EXISTS")
        with temp.open("xb") as f:
            f.write(next_bytes)
        temp.replace(folder/"state.json")
    return document


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--request-id",required=True)
    args=p.parse_args()
    try:
        output=plan(args.root,args.request_id)
    except (PlanningBlocked,IntakeBlocked,ValueError,KeyError,TypeError,IndexError) as exc:
        reason=str(exc) if isinstance(exc,(PlanningBlocked,IntakeBlocked)) else "SOURCE_CONTRACT_BLOCKED"
        print("LOTS_BLOCKED:"+reason,file=sys.stderr)
        return 1
    print("LOTS_PLANNED "+args.request_id+" "+str(len(output["lots"])))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
