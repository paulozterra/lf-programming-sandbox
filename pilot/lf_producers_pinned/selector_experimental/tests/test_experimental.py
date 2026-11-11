#!/usr/bin/env python3
"""Standalone local-only experimental checks. Does not alter test_parity.py."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_parity import ROOT, TABLES, FUNCTIONS, CASES, run_psql, sql_json, validations

CODES = ("PERFIL-PROG-BACKEND-EXP", "PERFIL-PROG-BACKEND-SPRING-EXP", "PERFIL-PROG-FRONTEND-EXP", "PERFIL-PROG-DATA-EXP", "PERFIL-PROG-BACKEND-NAME-FRONTEND-EXP")

def check(value, message):
    if not value:
        raise AssertionError(message)

def call(dsn, expression):
    return json.loads(run_psql(dsn, sql="SELECT ("+expression+")::text"))

def lit(s):
    return "'" + s.replace("'", "''") + "'"

def prepare(dsn, area, paths, request="Implementar el lote clasificado", project="lf_java"):
    return call(dsn, "public.lf_profile_selector_semantic_prepare_v3_exp("
                +lit(request)+","+lit(project)+","+lit(area)+","+sql_json(paths)+")")

def finalize(dsn, req, draft):
    return call(dsn, "public.lf_profile_selector_semantic_finalize_v2_exp("
                +sql_json(req)+","+sql_json(draft)+")")

def validate(dsn, req, result):
    return call(dsn, "public.lf_profile_selector_semantic_validate_v2_exp("
                +sql_json(req)+","+sql_json(result)+")")

def draft_for(req, selected=None):
    selected = selected or req["candidate_profiles"][0]["profile_code"]
    p = next((x for x in req["candidate_profiles"] if x["profile_code"] == selected), req["candidate_profiles"][0])
    e = p["descriptor"]["selection_evidence"][0]
    return {"decision":"SELECTED","selected_profile_code":selected,"reason":"Coincidencia por lote",
            "ambiguous_profile_codes":[],"material_ambiguities":[],
            "evidence_refs":[{"profile_code":p["profile_code"],"kind":e["kind"],
                              "source_section":e["source_section"]}]}

def reference(dsn):
    for name,expression in CASES.items():
        expected=json.loads((ROOT/"expected"/(name+".json")).read_text(encoding="utf-8"))
        actual=call(dsn, expression)
        check(actual==expected["payload"], "Regression JSON mismatch "+name)
        print("PASS original-regression",name)

def guard(dsn):
    check(os.environ.get("SELECTOR_EXP_DISPOSABLE_DB")=="YES",
          "SELECTOR_EXP_DISPOSABLE_DB=YES required")
    u=urlsplit(dsn)
    check(u.scheme in ("postgres","postgresql") and
          u.hostname in ("127.0.0.1","localhost","::1"),
          "Refusing nonlocal database connection")
    check(unquote(u.path.lstrip("/")).startswith("selector_exp_test_"),
          "Database name must start with selector_exp_test_")
    check(u.query=="" and u.fragment=="", "DSN query parameters forbidden")
    info=run_psql(dsn, sql="SELECT current_database() || '|' || COALESCE(host(inet_server_addr()),'SOCKET') || '|' || (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m'))")
    name,host,relations=info.split("|")
    check(name==unquote(u.path.lstrip("/")) and host in ("127.0.0.1","::1") and relations=="0",
          "Database is not fresh and local: "+info)

def main():
    dsn=os.environ.get("SELECTOR_EXP_TEST_DSN","")
    guard(dsn)
    try:
        run_psql(dsn,file=ROOT/"original/schema/bootstrap.sql")
        run_psql(dsn,file=ROOT/"original/schema/tables.sql")
        run_psql(dsn,file=ROOT/"original/schema/constraints.sql")
        for t in TABLES:
            run_psql(dsn,file=ROOT/"original/data"/(t+".sql"))
        for f in FUNCTIONS:
            run_psql(dsn,file=ROOT/"original/functions"/f)

        reference(dsn)  # original baseline unchanged
        run_psql(dsn,file=ROOT/"experimental/seed_profiles_exp.sql")
        run_psql(dsn,file=ROOT/"experimental/area_policy_exp.sql")
        run_psql(dsn,file=ROOT/"experimental/functions_exp.sql")
        catalog=call(dsn,"public.lf_profile_selector_catalog_v1()")
        enabled={p["profile_code"] for p in catalog["profiles"] if p["selection_eligible"]}
        check(set(CODES)<=enabled,"Original selector did not expose all five fictional profiles")
        ready=call(dsn,"public.lf_profile_selector_semantic_prepare_v2('Modificar código Java','PROGRAMACION',NULL::jsonb)")
        check(set(CODES)<={p["profile_code"] for p in ready["candidate_profiles"]},
              "Original prepare did not offer all five profiles")
        print("PASS unmodified selector discovers 5 new PROGRAMACION profiles")

        # Original validator rerun on PROGRAMACION with >=2 candidates: seven verdict cases.
        validations(dsn,ready)
        print("PASS original-validator 7/7 on PROGRAMACION")

        for area,path in (("BACKEND","src/main/java/com/lf/Loan.java"),
                          ("FRONTEND","web/src/app/loan.component.ts"),
                          ("DATA","db/migration/V001__loan.sql")):
            env=prepare(dsn,area,[path])
            check(env.get("status")=="READY", "Failed route "+area+": "+str(env))
            req=env["request"]
            codes={p["profile_code"] for p in req["candidate_profiles"]}
            if area=="BACKEND":
                check(codes=={"PERFIL-PROG-BACKEND-EXP","PERFIL-PROG-BACKEND-SPRING-EXP"},
                      "BACKEND must offer both declared profiles, not choose by name")
                check("PERFIL-PROG-BACKEND-NAME-FRONTEND-EXP" not in codes,
                      "Misleading BACKEND name admitted to Java routes")
            elif area=="FRONTEND":
                check(codes=={"PERFIL-PROG-FRONTEND-EXP","PERFIL-PROG-BACKEND-NAME-FRONTEND-EXP"},
                      "FRONTEND declared-area candidate set mismatch")
            else:
                check(codes=={"PERFIL-PROG-DATA-EXP"},"DATA candidate set mismatch")
            output=finalize(dsn,req,draft_for(req))
            check(output["status"]=="VALID","Failed selected area "+area+": "+str(output))
            print("PASS positive routing and selected validation",area)

        mixed=prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java","web/src/app/loan.ts"])
        check(mixed.get("blocking_code")=="LOTE_MULTI_AREA_BLOCKED","Mixed routes not blocked")
        print("PASS mixed-area BLOCKED")

        # More than one BACKEND is available: semantic selection remains with the caller.
        req=prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java"])["request"]
        spring=finalize(dsn,req,draft_for(req,selected="PERFIL-PROG-BACKEND-SPRING-EXP"))
        check(spring["status"]=="VALID","Second BACKEND selection rejected")
        original=finalize(dsn,req,draft_for(req,selected="PERFIL-PROG-BACKEND-EXP"))
        check(original["status"]=="VALID","First BACKEND selection rejected")
        first,second=req["candidate_profiles"]
        def evidence(p):
            e=p["descriptor"]["selection_evidence"][0]
            return {"profile_code":p["profile_code"],"kind":e["kind"],"source_section":e["source_section"]}
        ambiguous={"decision":"AMBIGUOUS","selected_profile_code":None,"reason":"Two plausible backend profiles",
                   "ambiguous_profile_codes":[first["profile_code"],second["profile_code"]],
                   "material_ambiguities":[{"reason":"Java general vs Spring"}],
                   "evidence_refs":[evidence(first),evidence(second)]}
        check(finalize(dsn,req,ambiguous)["status"]=="VALID","Two-backend AMBIGUOUS rejected")
        print("PASS two BACKEND candidates: SELECTED each + AMBIGUOUS")
        check("PERFIL-PROG-BACKEND-NAME-FRONTEND-EXP" not in
              {p["profile_code"] for p in req["candidate_profiles"]},
              "Name-driven backend eligibility regression")
        print("PASS misleading BACKEND name declared FRONTEND excluded from Java")

        # Same area with project-specific structures; hardcoded prefixes cannot pass both.
        for project,area,path in (
            ("lf_python","BACKEND","api/app/routes/loan.py"),
            ("lf_python","FRONTEND","ui/src/pages/loan.vue"),
            ("lf_python","DATA","alembic/versions/001_loan.py"),
            ("lf_java","BACKEND","src/main/java/com/lf/Loan.java")):
            e=prepare(dsn,area,[path],project=project)
            check(e["status"]=="READY", "Project path mapping failed "+project+str(e))
            check(e["request"]["project_ref"]==project,"Project binding lost")
            check(finalize(dsn,e["request"],draft_for(e["request"]))["status"]=="VALID",
                  "Project-selected profile failed")
        check(prepare(dsn,"BACKEND",["api/app/routes/loan.py"],project="lf_java")["blocking_code"]=="LOTE_PATH_UNCLASSIFIED",
              "Python project prefix leaked into Java project")
        check(prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java"],project="lf_python")["blocking_code"]=="LOTE_PATH_UNCLASSIFIED",
              "Java project prefix leaked into Python project")
        check(prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java"],project="missing_project")["blocking_code"]=="PROJECT_RULES_NOT_FOUND",
              "Missing project rules accepted")
        print("PASS two project-specific path maps, no cross-project leakage")
        # Mutation of project rules after request issuance invalidates it.
        old=prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java"])["request"]
        run_psql(dsn,sql="INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES ('lf_java','BACKEND','server/src/')")
        check(finalize(dsn,old,draft_for(old))["status"]=="BLOCKED",
              "Project route policy drift did not invalidate request")
        run_psql(dsn,sql="DELETE FROM public.lf_project_area_pattern_exp WHERE project_ref='lf_java' AND path_prefix='server/src/'")
        print("PASS changed project policy invalidates stale request")


        mismatch=prepare(dsn,"FRONTEND",["src/main/java/com/lf/Loan.java"])
        check(mismatch.get("blocking_code")=="LOTE_AREA_ROUTE_MISMATCH","Area/path mismatch not blocked")
        print("PASS area/path mismatch BLOCKED")

        req=prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java"])["request"]
        wrong=finalize(dsn,req,draft_for(req,selected="PERFIL-PROG-FRONTEND-EXP"))
        check(wrong["status"]=="BLOCKED" and
              "EXP_AREA_PROFILE_MISMATCH" in wrong["validation"]["blocking_codes"],
              "Wrong-area AI choice accepted")
        print("PASS AI frontend-for-Java BLOCKED")

        fake=finalize(dsn,req,draft_for(req,selected="OUTSIDE-CATALOG-EXP"))
        check(fake["status"]=="BLOCKED","Out-of-catalog accepted")
        ev=draft_for(req)
        ev["evidence_refs"][0]["source_section"]="FABRICATED_EVIDENCE"
        check(finalize(dsn,req,ev)["status"]=="BLOCKED","Fabricated evidence accepted")
        elevated=draft_for(req)
        elevated["route_authority"]=True
        check(finalize(dsn,req,elevated)["status"]=="BLOCKED","Authority injection accepted")
        good=finalize(dsn,req,draft_for(req))
        altered={**good["result"],"semantic_receipt_sha256":"0"*64}
        verdict=validate(dsn,req,altered)
        check(verdict["status"]=="BLOCKED" and
              "EXP_SEMANTIC_RECEIPT_INVALID" in verdict["blocking_codes"],
              "Altered receipt accepted")
        print("PASS adversarial outside-catalog/evidence/authority/receipt")

        # Stale descriptor in SAME CHANNEL disables only that profile.
        run_psql(dsn,sql="UPDATE public.lf_profile_selection_registry_v1 SET descriptor_status='STALE_SOURCE_CHANGED' WHERE profile_code='PERFIL-PROG-DATA-EXP'")
        stale=call(dsn,"public.lf_profile_selector_catalog_v2_exp('PROGRAMACION')")
        check(any(p["profile_code"]=="PERFIL-PROG-DATA-EXP" for p in stale["blocked_profiles"]),
              "Same-channel stale profile not reported")
        check(prepare(dsn,"DATA",["db/migration/V001__loan.sql"])["blocking_code"]=="NO_PROFILE_FOR_AREA",
              "Stale DATA profile still selected")
        check(prepare(dsn,"BACKEND",["src/main/java/com/lf/Loan.java"])["status"]=="READY",
              "Stale DATA erroneously blocked BACKEND")
        run_psql(dsn,sql="UPDATE public.lf_profile_selection_registry_v1 SET descriptor_status='CURRENT' WHERE profile_code='PERFIL-PROG-DATA-EXP'")
        print("PASS same-channel stale profile only, NO_PROFILE_FOR_AREA")

        # Cross-channel stale descriptor cannot block PROGRAMACION in exp catalog or prepare.
        product=call(dsn,"public.lf_profile_selector_catalog_v2_exp('PRODUCTO')")
        products=[p["profile_code"] for p in product["profiles"]
                  if p.get("selection_eligible") and p.get("descriptor_status")=="CURRENT"]
        check(products,"No PRODUCTO profile to exercise stale isolation")
        victim=products[0]
        run_psql(dsn,sql="UPDATE public.lf_profile_selection_registry_v1 SET descriptor_status='STALE_SOURCE_CHANGED' WHERE profile_code="+lit(victim))
        production=call(dsn,"public.lf_profile_selector_catalog_v2_exp('PROGRAMACION')")
        check(production["selectable_profile_count"]>=3,"Stale PRODUCTO affected PROGRAMACION")
        check(prepare(dsn,"FRONTEND",["web/src/app/loan.ts"])["status"]=="READY",
              "Cross-channel stale PRODUCTO blocked PROGRAMACION")
        run_psql(dsn,sql="UPDATE public.lf_profile_selection_registry_v1 SET descriptor_status='CURRENT' WHERE profile_code="+lit(victim))
        print("PASS cross-channel stale PRODUCTO does not block PROGRAMACION")

        # Roll back fictional records using only the disposable database.
        code_list=",".join(lit(c) for c in CODES)
        for table in ("lf_profile_area_policy_exp","lf_profile_selector_policy_v1","lf_profile_selection_registry_v1"):
            run_psql(dsn,sql="DELETE FROM public."+table+" WHERE profile_code IN ("+code_list+")")
        run_psql(dsn,sql="DELETE FROM public.lf_activos WHERE codigo_activo IN ("+code_list+")")
        reference(dsn)
        print("PASS original expected/ 6/6 after experimental seed removal")
    finally:
        run_psql(dsn,sql="DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS extensions CASCADE")
        leftovers=run_psql(dsn,sql="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','extensions') AND c.relkind IN ('r','p','v','m')")
        check(leftovers=="0","Residual database relations: "+leftovers)
        extensions=run_psql(dsn,sql="SELECT count(*) FROM pg_namespace WHERE nspname='extensions'")
        check(extensions=="0","Residual extension schema")
        print("PASS zero residual relations and extension schemas")
    print("PASS EXPERIMENTAL_SELECTOR_V1")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("FAIL",repr(exc),file=sys.stderr)
        raise SystemExit(1)
