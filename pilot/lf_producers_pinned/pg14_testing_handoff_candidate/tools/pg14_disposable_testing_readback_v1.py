"""PG14 local fixture Testing ACCEPT/BLOCK, REAL isolated PostgreSQL readback.

Runs only with PG14_TEST_DSN naming database pg14_test_* and
PG14_DISPOSABLE_DB=YES. Never accesses Testing service or Supabase.
Compares full locally simulated receiver responses after commit and independent
psql readback. Both records are fixtures and do not grant Testing authority.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote,urlparse

def fail(code):raise RuntimeError(code)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True)
def digest(v):return hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()
def database_from_dsn(dsn):
    if not isinstance(dsn,str):return ""
    if dsn.startswith(("postgresql://","postgres://")):
        p=urlparse(dsn)
        # No remote hosts for local disposable integration tests.
        if p.hostname not in ("localhost","127.0.0.1",None):
            fail("PG14_REMOTE_DATABASE_FORBIDDEN")
        return unquote(p.path.lstrip("/"))
    if "host=" in dsn and not re.search(r"(?:^|\s)host=(localhost|127\.0\.0\.1)(?:\s|$)",dsn):
        fail("PG14_REMOTE_DATABASE_FORBIDDEN")
    m=re.search(r"(?:^|\s)dbname=([A-Za-z0-9_]+)(?:\s|$)",dsn)
    if m:return m.group(1)
    return dsn if re.fullmatch(r"[A-Za-z0-9_]+",dsn) else ""
def psql(dsn,sql):
    proc=subprocess.run(["psql","-X","-A","-t","-v","ON_ERROR_STOP=1",
        "--dbname",dsn,"--command",sql],capture_output=True,text=True,timeout=20)
    if proc.returncode:
        fail("PG14_PSQL_FAILED: "+proc.stderr.strip())
    return proc.stdout.strip()
def build_fixture_verdicts():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"tests"))
    from test_pg14_final_chain_v1 import make_chain
    from pg14_local_testing_receiver_v1 import simulate_testing_receiver
    x=make_chain()
    expected=x["verdict"]
    tampered=dict(x["c3"]["admission_request"])
    tampered["frozen_candidate_sha256_reported"]="f"*64
    blocked=simulate_testing_receiver(
        pg14_bridge=x["bridge"],pg14_c1=x["c1"],pg14_c2=x["c2"],
        pg14_c3=x["c3"],request_payload=tampered)
    if expected.get("verdict")!="ACCEPT" or blocked.get("verdict")!="BLOCK":
        fail("PG14_LOCAL_RECEIVER_EXPECTED_ACCEPT_BLOCK_NOT_OBSERVED")
    if any(v.get("testing_real_invoked") is not False or
           v.get("production_authority") is not False for v in (expected,blocked)):
        fail("PG14_TESTING_AUTHORITY_ESCALATION")
    return {"ACCEPT":expected,"BLOCK":blocked}

def main():
    dsn=os.environ.get("PG14_TEST_DSN","")
    if (os.environ.get("PG14_DISPOSABLE_DB")!="YES"
        or not database_from_dsn(dsn).startswith("pg14_test_")):
        fail("PG14_DISPOSABLE_LOCAL_POSTGRES_REQUIRED")
    for key in ("PGHOST","PGHOSTADDR"):
        if os.environ.get(key) not in (None,"","localhost","127.0.0.1","::1"):
            fail("PG14_REMOTE_ENV_HOST_FORBIDDEN")
    if os.environ.get("PGSERVICE") or os.environ.get("PGSERVICEFILE"):
        fail("PG14_PG_SERVICE_REDIRECTION_FORBIDDEN")
    # Verify the connected database itself rather than relying on DSN naming alone.
    connected=psql(dsn,"SELECT current_database() || '|' || coalesce(inet_server_addr()::text,'LOCAL_SOCKET');")
    parts=connected.split("|")
    if len(parts)!=2 or not parts[0].startswith("pg14_test_") or parts[1] not in (
            "LOCAL_SOCKET","127.0.0.1","::1"):
        fail("PG14_NOT_LOCAL_DISPOSABLE_POSTGRES")
    responses=build_fixture_verdicts()
    schema="pg14_local_"+uuid.uuid4().hex[:16]
    stored_keys={}
    try:
        psql(dsn,f'CREATE SCHEMA "{schema}"; CREATE TABLE "{schema}".responses '
            '(record_key text PRIMARY KEY, verdict text NOT NULL, response jsonb NOT NULL);')
        # Session A: perform real INSERT + COMMIT of both responses.
        for label,value in responses.items():
            key=uuid.uuid4().hex
            stored_keys[label]=key
            bodyhex=canonical(value).encode("utf-8").hex()
            psql(dsn,f'INSERT INTO "{schema}".responses(record_key,verdict,response) '
                f"VALUES ('{key}','{label}',convert_from(decode('{bodyhex}','hex'),'UTF8')::jsonb);")
        # Session B, separately invoked: actual persisted SELECT.
        for label,expected in responses.items():
            key=stored_keys[label]
            observed_text=psql(dsn,f'SELECT response::text FROM "{schema}".responses '
                               f"WHERE record_key='{key}' AND verdict='{label}';")
            if not observed_text:fail("PG14_READBACK_MISSING_"+label)
            observed=json.loads(observed_text)
            if observed!=expected or digest(observed)!=digest(expected):
                fail("PG14_READBACK_NOT_IDENTICAL_"+label)
            print("PG14_C3_LOCAL_"+label+"_PERSISTED_READBACK_PASS")
            print("PG14_C3_LOCAL_"+label+"_EXPECTED_SHA256="+digest(expected))
            print("PG14_C3_LOCAL_"+label+"_READBACK_SHA256="+digest(observed))
        print("PG14_C3_DIFFERENT_PSQL_SESSIONS=TRUE")
        print("PG14_C3_REAL_TESTING_INVOKED=FALSE")
        print("PG14_C3_PRODUCTION_AUTHORITY=FALSE")
    finally:
        try:
            psql(dsn,f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
        except Exception as exc:
            print("PG14_C3_CLEANUP_FAILED="+str(exc),file=sys.stderr)
            raise

if __name__=="__main__":main()
