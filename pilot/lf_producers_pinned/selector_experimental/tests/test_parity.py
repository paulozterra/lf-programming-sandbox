#!/usr/bin/env python3
"""Parity harness. Requires psql, a fresh localhost disposable database and explicit opt-in."""
import json, os, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("lf_activos", "lf_profile_selection_registry_v1", "lf_profile_selector_policy_v1",
          "lf_profile_write_authority_v1", "lf_router_action_registry", "lf_operation_execution")
FUNCTIONS = ("lf_profile_execution_source_eligibility_v1.sql", "lf_profile_selector_catalog_v1.sql",
             "lf_profile_selector_descriptor_sync_v1.sql", "lf_profile_selector_semantic_prepare_v2_4args.sql",
             "lf_profile_selector_semantic_prepare_v2_3args.sql", "lf_profile_selector_semantic_validate_v1.sql",
             "lf_profile_selector_semantic_finalize_v1.sql")
CASES = {
    "catalog": "public.lf_profile_selector_catalog_v1()",
    "producto_1": "public.lf_profile_selector_semantic_prepare_v2('Crear un nuevo producto financiero','PRODUCTO',NULL::jsonb)",
    "producto_2": "public.lf_profile_selector_semantic_prepare_v2('Modificar las reglas de un producto','PRODUCTO',NULL::jsonb)",
    "programacion_1": "public.lf_profile_selector_semantic_prepare_v2('Corregir endpoint Java de préstamos','PROGRAMACION',NULL::jsonb)",
    "programacion_2": "public.lf_profile_selector_semantic_prepare_v2('Construir componente de interfaz Angular','PROGRAMACION',NULL::jsonb)",
    "sin_canal": "public.lf_profile_selector_semantic_prepare_v2('Evaluar la solicitud y proponer ruta',NULL::text,NULL::jsonb)"
}
def fail(message):
    raise RuntimeError(message)
def run_psql(dsn, *, sql=None, file=None):
    args = ["psql", "-X", "--no-psqlrc", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", dsn]
    if file is not None: args += ["-f", str(file)]
    else: args += ["-c", sql]
    p = subprocess.run(args, capture_output=True, text=True, timeout=45, check=False)
    if p.returncode: fail("psql failed on " + (str(file) if file else "SQL") + ": " + p.stderr[-1500:])
    return p.stdout.strip()
def sql_json(value):
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"
def sqlstr(value):
    return "'" + str(value).replace("'", "''") + "'"
def assert_status(dsn, request, draft, expected):
    result = json.loads(run_psql(dsn, sql="SELECT public.lf_profile_selector_semantic_finalize_v1(" + sql_json(request) + "," + sql_json(draft) + ")::text"))
    actual = result["status"]
    assert actual == expected, (draft, expected, actual, result.get("validation"))
    return result

def validations(dsn, request):
    profiles = request["candidate_profiles"]
    assert profiles, "No candidates to exercise validation"
    first = profiles[0]
    code = first["profile_code"]
    evidence = first["descriptor"]["selection_evidence"][0]
    ev = {"profile_code":code, "kind":evidence["kind"], "source_section":evidence["source_section"]}
    base = {"decision":"SELECTED", "selected_profile_code":code, "reason":"Paridad determinista",
            "evidence_refs":[ev], "ambiguous_profile_codes":[], "material_ambiguities":[]}
    good = assert_status(dsn, request, base, "VALID")
    assert_status(dsn, request, {**base,"selected_profile_code":"OUTSIDE_CATALOG_FAKE"}, "BLOCKED")
    assert_status(dsn, request, {**base,"evidence_refs":[{**ev,"source_section":"FABRICATED_SOURCE"}]}, "BLOCKED")
    assert_status(dsn, request, {**base,"route_authority":True}, "BLOCKED")
    no_match = {"decision":"NO_MATCH","selected_profile_code":None,"reason":"Sin coincidencia",
                "evidence_refs":[],"ambiguous_profile_codes":[],"material_ambiguities":[]}
    assert_status(dsn, request, no_match, "VALID")
    if len(profiles)>1:
        p2 = profiles[1]; ev2 = p2["descriptor"]["selection_evidence"][0]
        amb = {"decision":"AMBIGUOUS", "selected_profile_code":None, "reason":"Ambigüedad material",
               "ambiguous_profile_codes":[code,p2["profile_code"]], "material_ambiguities":[{"reason":"Solapamiento"}],
               "evidence_refs":[ev,{"profile_code":p2["profile_code"],"kind":ev2["kind"],"source_section":ev2["source_section"]}]}
        assert_status(dsn, request, amb, "VALID")
    altered = {**good["result"],"semantic_receipt_sha256":"0"*64}
    validation = json.loads(run_psql(dsn, sql="SELECT public.lf_profile_selector_semantic_validate_v1("+sql_json(request)+","+sql_json(altered)+")::text"))
    assert validation["status"]=="BLOCKED" and "PROFILE_SELECTOR_SEMANTIC_RECEIPT_INVALID" in validation["blocking_codes"], validation
    print("PASS validation SELECTED, NO_MATCH, out-of-catalog, fabricated evidence, authority injection, altered receipt" + (", AMBIGUOUS" if len(profiles)>1 else ""))

def main():
    if os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES":
        fail("Explicit SELECTOR_EXP_DISPOSABLE_DB=YES required")
    dsn = os.environ.get("SELECTOR_EXP_TEST_DSN", "")
    u = urlsplit(dsn)
    if u.scheme not in ("postgres", "postgresql") or u.hostname not in ("localhost","127.0.0.1","::1"):
        fail("Only an explicit local postgresql:// URI is allowed")
    if not unquote(u.path.lstrip("/")).startswith("selector_exp_test_"):
        fail("Disposable database name must start selector_exp_test_")
    db_name = unquote(u.path.lstrip("/"))
    preflight = run_psql(dsn, sql="SELECT current_database() || '|' || COALESCE(host(inet_server_addr()),'SOCKET') || '|' || (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m'))")
    name,host,count=preflight.split("|")
    if name != db_name or host not in ("127.0.0.1","::1") or count!="0":
        fail("Refusing nonempty or nonlocal database: "+preflight)
    success=False
    try:
        run_psql(dsn,file=ROOT/"original/schema/bootstrap.sql")
        run_psql(dsn,file=ROOT/"original/schema/tables.sql")
        run_psql(dsn,file=ROOT/"original/schema/constraints.sql")
        for table in TABLES: run_psql(dsn,file=ROOT/"original/data"/(table+".sql"))
        for fn in FUNCTIONS: run_psql(dsn,file=ROOT/"original/functions"/fn)
        outputs={}
        for name,expression in CASES.items():
            expected=json.loads((ROOT/"expected"/(name+".json")).read_text(encoding="utf-8"))
            row=json.loads(run_psql(dsn,sql="SELECT jsonb_build_object('payload',"+expression+",'sha256_pg_jsonb_text',encode(extensions.digest(convert_to(("+expression+")::text,'UTF8'),'sha256'),'hex'))::text"))
            assert row["payload"]==expected["payload"], "JSON parity mismatch: "+name
            assert row["sha256_pg_jsonb_text"]==expected["sha256_pg_jsonb_text"], "SHA-256 parity mismatch: "+name
            outputs[name]=row["payload"]
            print("PASS expected/",name,"sha256",row["sha256_pg_jsonb_text"])
        validations(dsn, outputs["producto_1"])
        success=True
    finally:
        # Only reached after opt-in, URI check, DB-name check, local server check and empty DB check.
        run_psql(dsn,sql="DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; DROP SCHEMA IF EXISTS extensions CASCADE")
        left=run_psql(dsn,sql="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','extensions') AND c.relkind IN ('r','p','v','m')")
        assert left=="0","Residual relations: "+left
        left_schema=run_psql(dsn,sql="SELECT count(*) FROM pg_namespace WHERE nspname='extensions'")
        assert left_schema=="0","Residual extensions schema"
        print("PASS cleanup: 0 residual tables/views, 0 extensions schemas")
    if not success: fail("Parity test did not complete")
    print("PASS selector original parity against six live reference outputs")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("FAIL:",str(exc),file=sys.stderr)
        raise SystemExit(1)
