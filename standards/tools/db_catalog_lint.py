"""Lint de esquema PostgreSQL 17 del kit. Solo stdlib; psql o docker compose exec."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "standards/catalog.json"
KIT = ROOT / "standards/kit-base"
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
MIGRATION = re.compile(r"^[VU]\d+(?:_\d+)?__[a-z][a-z0-9_]*\.sql$")
TABLES = {"errors","error_occurrences","messages","audit_events","navigation_event_types",
          "navigation_events","legal_documents","consents"}
MUTABLE = {"errors","messages","navigation_event_types"}
APPEND = {"error_occurrences","audit_events","navigation_events","consents"}


def query(sql):
    docker = os.environ.get("KIT_PSQL_MODE") == "docker"
    cmd = (["docker", "compose", "-f", "docker/compose.yaml", "exec", "-T", "postgres",
            "psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", "sandbox", "-d", "sandbox"]
           if docker else ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"])
    return subprocess.run(cmd, input=sql, text=True, capture_output=True, check=True, cwd=ROOT).stdout


def collect(schema):
    if not SNAKE.fullmatch(schema):
        raise ValueError("INVALID_SCHEMA")
    sql = """
SELECT json_build_object(
 'tables', coalesce((SELECT json_agg(json_build_object('name',c.relname,'comment',obj_description(c.oid),'rls',c.relrowsecurity))
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='{schema}' AND c.relkind='r'),'[]'::json),
 'columns', coalesce((SELECT json_agg(json_build_object('table',c.relname,'name',a.attname,
     'type',format_type(a.atttypid,a.atttypmod),'nullable',NOT a.attnotnull,'identity',a.attidentity,
     'default',pg_get_expr(d.adbin,d.adrelid)))
   FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
   JOIN pg_namespace n ON n.oid=c.relnamespace
   LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
   WHERE n.nspname='{schema}' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped),'[]'::json),
 'constraints',coalesce((SELECT json_agg(json_build_object('table',c.relname,'name',k.conname,
    'type',k.contype,'column',array_to_string(ARRAY(SELECT a.attname FROM unnest(k.conkey) z JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=z),',')))
  FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='{schema}'),'[]'::json),
 'indexes',coalesce((SELECT json_agg(json_build_object('table',tablename,'name',indexname))
 FROM pg_indexes WHERE schemaname='{schema}'),'[]'::json),
 'triggers',coalesce((SELECT json_agg(json_build_object('table',c.relname,'name',t.tgname))
 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='{schema}' AND NOT t.tgisinternal),'[]'::json),
 'functions',coalesce((SELECT json_agg(json_build_object('name',p.proname,'definer',p.prosecdef,
   'search_path',p.proconfig,'public_execute',EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) acl WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE')))
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='{schema}'),'[]'::json),
 'public_privileges',coalesce((SELECT json_agg(json_build_object('name',c.relname,'privilege',x.privilege_type))
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 'S' ELSE 'r' END,c.relowner))) x ON true
 WHERE n.nspname='{schema}' AND c.relkind IN ('r','v','S') AND x.grantee=0),'[]'::json)
)::text;
""".replace("{schema}", schema)
    return json.loads(query(sql).strip().splitlines()[-1])


def check_files(path):
    findings = []
    for file in sorted(Path(path).rglob("*.sql")):
        if not MIGRATION.fullmatch(file.name) or not file.name.startswith("V"):
            findings.append({"rule_id":"STD-DB-09","object":file.name,"reason_code":"INVALID_MIGRATION_NAME"})
    return findings


def tokens_from_glossary():
    base=json.loads((ROOT/"standards/glossary/base.json").read_text(encoding="utf-8"))
    technical=set(base["technical_tokens"])
    for term in base["terms"]:
        for value in (term["term_en"],term["plural_en"]):
            technical.update(value.split("_"))
    return technical


def identifier_tokens_valid(identifier):
    known=tokens_from_glossary()
    return all(token in known or (token.endswith("s") and token[:-1] in known)
               or (token.endswith("ies") and token[:-3]+"y" in known)
               for token in identifier.split("_"))


def lint_data(data, schema="kit_test", kit_version="0.1.0", catalog_version="0.4.0"):
    findings = []
    def add(rule, obj, code):
        findings.append({"rule_id":rule,"object":obj,"reason_code":code})
    tables = {t["name"]:t for t in data.get("tables",[])}
    columns = data.get("columns",[])
    by_table = {name:{c["name"]:c for c in columns if c["table"]==name} for name in tables}
    constraints = data.get("constraints",[])
    triggers = {(t["table"],t["name"]) for t in data.get("triggers",[])}
    for table, info in tables.items():
        if not SNAKE.fullmatch(table) or not table.endswith("s") or not identifier_tokens_valid(table):
            add("STD-DB-01",table,"INVALID_TABLE_NAME")
        cols = by_table[table]
        for name,col in cols.items():
            if not SNAKE.fullmatch(name) or not identifier_tokens_valid(name):
                add("STD-DB-01",table+"."+name,"INVALID_COLUMN_NAME")
            if col["type"]=="boolean" and not name.startswith(("is_","has_")):
                add("STD-DB-05",table+"."+name,"INVALID_BOOLEAN_NAME")
            if any(x in name for x in ("amount","balance","price","total")) and col["type"] in ("real","double precision"):
                add("D10",table+"."+name,"FLOAT_MONETARY_COLUMN")
        pk=[c for c in constraints if c["table"]==table and c["type"]=="p"]
        if not pk or not (cols.get("id",{}).get("type")=="bigint" and cols.get("id",{}).get("identity") in ("a","d")):
            add("STD-DB-02",table,"INVALID_PRIMARY_KEY")
        for col in ("created_at","updated_at"):
            c=cols.get(col,{})
            if c.get("type")!="timestamp with time zone" or c.get("nullable") is not False or "now()" not in (c.get("default") or ""):
                add("STD-DB-04",table+"."+col,"INVALID_TIMESTAMP")
        if info.get("comment")=="mutable" and (table,table+"_updated_at") not in triggers:
            add("STD-DB-04",table,"MISSING_UPDATED_AT_TRIGGER")
        for constraint in [c for c in constraints if c["table"]==table]:
            typ=constraint["type"]
            if typ=="f":
                fkcol=constraint.get("column","")
                if not fkcol.endswith("_id"):
                    add("STD-DB-02",table+"."+fkcol,"INVALID_FK_COLUMN")
                if constraint["name"]!=table+"_"+fkcol+"_fkey":
                    add("STD-DB-03",table+"."+constraint["name"],"CUSTOM_FK_NAME")
            if typ=="p" and constraint["name"]!=table+"_pkey":
                add("STD-DB-03",table+"."+constraint["name"],"CUSTOM_PK_NAME")
    for index in data.get("indexes",[]):
        name=index["name"];table=index["table"]
        if name.startswith("idx_") or name.startswith("fk_"):
            add("STD-DB-03",table+"."+name,"CUSTOM_INDEX_NAME")
    for fn in data.get("functions",[]):
        if fn["definer"] and (not fn["search_path"] or fn["public_execute"]):
            add("STD-DB-07",fn["name"],"UNSAFE_SECURITY_DEFINER")
        if fn["public_execute"]:
            add("STD-DB-06",fn["name"],"PUBLIC_PRIVILEGE")
    for obj in data.get("public_privileges",[]):
        add("STD-DB-06",obj["name"],"RLS_REQUIRED")
    return {"schema":schema,"catalog_version":catalog_version,"kit_version":kit_version,
            "findings":findings,"verdict":"FAIL" if findings else "PASS",
            "not_applicable":[{"rule_id":"STD-DB-10","reason":"Solo plataforma LF"}]}


def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    a=sub.add_parser("lint");a.add_argument("--schema",required=True);a.add_argument("--format",choices=["json"],default="json")
    b=sub.add_parser("check-files");b.add_argument("directory")
    sub.add_parser("migrate-test")
    sub.add_parser("test-negative")
    sub.add_parser("test-behavior")
    x=p.parse_args(argv)
    if x.action=="check-files":
        issues=check_files(x.directory)
        print(json.dumps(issues))
        return int(bool(issues))
    if x.action=="test-negative":
        from kit import render
        import tempfile
        expected={
          "01_invalid_table_name.sql":"INVALID_TABLE_NAME",
          "01_singular_table.sql":"INVALID_TABLE_NAME",
          "02_serial_pk.sql":"INVALID_PRIMARY_KEY",
          "03_custom_fk.sql":"CUSTOM_FK_NAME",
          "03_custom_index.sql":"CUSTOM_INDEX_NAME",
          "04_missing_updated_at.sql":"INVALID_TIMESTAMP",
          "05_boolean_without_prefix.sql":"INVALID_BOOLEAN_NAME",
          "06_public_grant.sql":"RLS_REQUIRED",
          "07_unsafe_definer.sql":"UNSAFE_SECURITY_DEFINER",
          "10_float_monetary.sql":"FLOAT_MONETARY_COLUMN"}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for i,(filename,code) in enumerate(expected.items()):
                schema="kit_negative_"+str(i)
                render(schema,"KIT",out)
                try:
                    query(f"DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema};")
                    query((out/"V0_1__common_tables.sql").read_text(encoding="utf-8"))
                    mutation=(KIT/"tests/negative"/filename).read_text(encoding="utf-8").replace("${schema}",schema)
                    query(mutation)
                    found=lint_data(collect(schema),schema)["findings"]
                    if not any(item["reason_code"]==code for item in found):
                        print("NEGATIVE_FAILURE",filename,code,json.dumps(found))
                        return 1
                except (subprocess.CalledProcessError,ValueError) as exc:
                    print("NEGATIVE_SQL_FAILURE",filename,str(exc))
                    return 1
                finally:
                    query(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
        print("OK kit negative checks",len(expected))
        return 0
    if x.action=="test-behavior":
        filename=KIT/"tests/behavior.sql"
        try:
            query(filename.read_text(encoding="utf-8"))
        except subprocess.CalledProcessError as exc:
            print("BEHAVIOR_FAILURE",exc.stderr)
            return 1
        print("OK kit behavior")
        return 0
    if x.action=="migrate-test":
        from kit import render, verify
        import tempfile
        if verify():
            print("DIGEST_MISMATCH")
            return 2
        with tempfile.TemporaryDirectory() as tmp:
            location=Path(tmp)
            schema="kit_test"
            render(schema,"KIT",location)
            def run_file(filename):
                sql=(location/filename).read_text(encoding="utf-8")
                query(sql)
            try:
                query("DROP SCHEMA IF EXISTS kit_test CASCADE; CREATE SCHEMA kit_test;")
                for name in ("V0_1__common_tables.sql","V0_2__common_triggers.sql",
                             "V0_3__support_views.sql","V0_4__technical_errors_seed.sql"):
                    run_file(name)
                # Already-applied detector: the initial migration created all eight tables.
                if not all(table in {t["name"] for t in collect(schema)["tables"]} for table in TABLES):
                    raise ValueError("MIGRATION_NOT_APPLIED")
                run_file("U0_4__technical_errors_seed.sql")
                if query("SELECT count(*) FROM kit_test.errors;").strip()!="0":
                    raise ValueError("SEED_ROLLBACK_FAILED")
                run_file("V0_4__technical_errors_seed.sql")
                if query("SELECT count(*) FROM kit_test.errors;").strip()!="6":
                    raise ValueError("SEED_REAPPLY_FAILED")
                query("INSERT INTO kit_test.errors(error_code,technical_category,http_status) VALUES ('WITNESS','TEST',500);")
                for name in ("U0_3__support_views.sql","U0_2__common_triggers.sql"):
                    run_file(name)
                if query("SELECT count(*) FROM kit_test.errors WHERE error_code='WITNESS';").strip()!="1":
                    raise ValueError("ROLLBACK_LOST_DATA")
                for name in ("V0_2__common_triggers.sql","V0_3__support_views.sql"):
                    run_file(name)
                if query("SELECT count(*) FROM kit_test.errors WHERE error_code='WITNESS';").strip()!="1":
                    raise ValueError("REAPPLY_LOST_DATA")
                findings=lint_data(collect(schema),schema)
                if findings["verdict"]!="PASS":
                    raise ValueError("LINT_FAILURE "+json.dumps(findings["findings"]))
                # Test V0_1 rollback only against an empty schema.
                query("DROP SCHEMA IF EXISTS kit_empty CASCADE; CREATE SCHEMA kit_empty;")
                render("kit_empty","KIT",location)
                run_file("V0_1__common_tables.sql")
                run_file("U0_1__common_tables.sql")
                query("DROP SCHEMA kit_empty;")
                print(json.dumps({"schema":schema,"test":"apply-reapply-detected-rollback-reapply","verdict":"PASS"}))
            except (ValueError,subprocess.CalledProcessError) as exc:
                print("MIGRATE_TEST_FAILED",str(exc))
                return 1
        return 0
    try:
        result=lint_data(collect(x.schema),x.schema,
                         catalog_version=json.loads(CATALOG.read_text(encoding="utf-8"))["catalog_version"])
    except (subprocess.CalledProcessError,ValueError) as e:
        print(f"ERROR: {e}")
        return 2
    print(json.dumps(result))
    return int(result["verdict"]!="PASS")


if __name__=="__main__":
    sys.exit(main())
