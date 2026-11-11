"""Opt-in PG12 C4 PostgreSQL disposable DB exercise (not production).

Require PG12_TEST_DSN with database name pg12_test_* and
PG12_DISPOSABLE_DB=YES. Uses psql sessions, creates a unique schema,
writes a real C4 producer payload, commits, reads it in a DIFFERENT
session, compares exact JSON data and digest, then removes the schema.
Does not change C4's governed-authority fields or Supabase.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse, unquote

def fail(code):raise RuntimeError(code)
def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True)
def digest(v):return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()

def database_from_dsn(dsn):
    if dsn.startswith(("postgresql://","postgres://")):
        parsed=urlparse(dsn)
        return unquote(parsed.path.lstrip("/"))
    m=re.search(r"(?:^|\\s)dbname=([^\\s]+)",dsn)
    if m:return m.group(1).strip("'\\\"")
    return dsn if re.fullmatch(r"[A-Za-z0-9_]+",dsn) else ""

def psql(dsn,sql):
    proc=subprocess.run(["psql","-X","-A","-t","-v","ON_ERROR_STOP=1",
        "--dbname",dsn,"--command",sql],capture_output=True,text=True,timeout=20)
    if proc.returncode:fail("PG12_PGSQL_COMMAND_FAILED: "+proc.stderr.strip())
    return proc.stdout.strip()

def run():
    dsn=os.environ.get("PG12_TEST_DSN","")
    if (os.environ.get("PG12_DISPOSABLE_DB")!="YES" or
        not database_from_dsn(dsn).startswith("pg12_test_")):
        fail("PG12_POSTGRES_DISPOSABLE_DATABASE_AND_EXPLICIT_OPT_IN_REQUIRED")
    # Import the actual source C1-C4 test fixture only after safeguard.
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"tests"))
    from test_pg12_identity_chain_v1 import inputs
    request=inputs()["c4"]
    assert request["persisted"] is False
    payload=request["payload_candidate"]
    expected=request["payload_candidate_sha256"]
    if digest(payload)!=expected:fail("PG12_C4_PREWRITE_PAYLOAD_DIGEST_MISMATCH")
    schema="pg12_sandbox_"+uuid.uuid4().hex[:16]
    record=uuid.uuid4().hex
    jsonhex=canonical(payload).encode("utf-8").hex()
    try:
        # Session 1: create and commit actual JSONB write.
        psql(dsn,f'CREATE SCHEMA "{schema}"; CREATE TABLE "{schema}".receipts '
             '(record_key text PRIMARY KEY, payload jsonb NOT NULL); '
             f'INSERT INTO "{schema}".receipts(record_key,payload) '
             f"VALUES ('{record}',convert_from(decode('{jsonhex}','hex'),'UTF8')::jsonb);")
        # Session 2: independent connection and actual persisted readback.
        data=psql(dsn,f'SELECT payload::text FROM "{schema}".receipts '
             f"WHERE record_key='{record}';")
        if not data:fail("PG12_C4_READBACK_MISSING")
        actual=json.loads(data)
        if actual!=payload:fail("PG12_C4_READBACK_NOT_IDENTICAL")
        if digest(actual)!=expected:fail("PG12_C4_READBACK_DIGEST_MISMATCH")
        print("PG12_C4_POSTGRES_DISPOSABLE_READBACK_PASS")
        print("PG12_C4_RECORD_KEY="+record)
        print("PG12_C4_EXPECTED_SHA256="+expected)
        print("PG12_C4_READBACK_SHA256="+digest(actual))
        print("PG12_C4_DIFFERENT_PSQL_SESSIONS=TRUE")
        print("PG12_C4_PRODUCTION_AUTHORITY=FALSE")
    finally:
        try:
            psql(dsn,f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
        except Exception as err:
            print("PG12_C4_CLEANUP_FAILED="+str(err),file=sys.stderr)
            raise

if __name__=="__main__":
    run()
