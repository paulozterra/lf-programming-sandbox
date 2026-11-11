"""V2 local Testing ACCEPT and BLOCK persisted via two independent psql sessions.

This never sends a Testing request, and never connects to Supabase. Both
responses are local source-only simulations, not production admission.
"""
import json
import os
import uuid

from pg14_disposable_testing_readback_v1 import (
    canonical, digest, psql, fail, database_from_dsn,
)


def persist_readback(accepted, blocked):
    dsn = os.environ.get("PG14_TEST_DSN", "")
    if (os.environ.get("PG14_DISPOSABLE_DB") != "YES" or
            not database_from_dsn(dsn).startswith("pg14_test_")):
        fail("PG14_DISPOSABLE_LOCAL_POSTGRES_REQUIRED")
    for key in ("PGHOST", "PGHOSTADDR"):
        if os.environ.get(key) not in (None, "", "localhost", "127.0.0.1", "::1"):
            fail("PG14_REMOTE_ENV_HOST_FORBIDDEN")
    if os.environ.get("PGSERVICE") or os.environ.get("PGSERVICEFILE"):
        fail("PG14_PG_SERVICE_REDIRECTION_FORBIDDEN")
    connected = psql(dsn, "SELECT current_database() || '|' || coalesce(host(inet_server_addr()),'LOCAL_SOCKET');")
    parts = connected.split("|")
    if len(parts) != 2 or not parts[0].startswith("pg14_test_") or parts[1] not in (
            "LOCAL_SOCKET", "127.0.0.1", "::1"):
        fail("PG14_NOT_LOCAL_DISPOSABLE_POSTGRES")
    responses = {"ACCEPT": accepted, "BLOCK": blocked}
    for label, response in responses.items():
        if (not isinstance(response, dict) or
                response.get("schema_version") != "PG14_LOCAL_TESTING_RECEIVER_RESPONSE_V2" or
                response.get("verdict") != label or
                response.get("production_authority") is not False or
                response.get("testing_real_invoked") is not False or
                response.get("response_sha256") != digest({
                    k: v for k, v in response.items() if k != "response_sha256"})):
            fail("PG14_V2_LOCAL_RESPONSE_NOT_ADMISSIBLE_" + label)
    schema = "pg14_v2_" + uuid.uuid4().hex[:16]
    keys = {}
    try:
        psql(dsn, f'CREATE SCHEMA "{schema}"; CREATE TABLE "{schema}".responses '
                  '(record_key text PRIMARY KEY, verdict text NOT NULL, response jsonb NOT NULL);')
        for label, response in responses.items():
            key = uuid.uuid4().hex
            keys[label] = key
            body = canonical(response).encode("utf-8").hex()
            psql(dsn, f'INSERT INTO "{schema}".responses(record_key,verdict,response) '
                      f"VALUES ('{key}','{label}',convert_from(decode('{body}','hex'),'UTF8')::jsonb);")
        for label, expected in responses.items():
            value = psql(dsn, f'SELECT response::text FROM "{schema}".responses '
                              f"WHERE record_key='{keys[label]}' AND verdict='{label}';")
            if not value:
                fail("PG14_READBACK_MISSING_" + label)
            actual = json.loads(value)
            if actual != expected or digest(actual) != digest(expected):
                fail("PG14_READBACK_NOT_IDENTICAL_" + label)
            print("PG14_C3_LOCAL_" + label + "_PERSISTED_READBACK_PASS")
            print("PG14_C3_V2_" + label + "_READBACK_SHA256=" + digest(actual))
        print("PG14_C3_REAL_TESTING_INVOKED=FALSE")
        print("PG14_C3_PRODUCTION_AUTHORITY=FALSE")
        return {k: digest(v) for k, v in responses.items()}
    finally:
        psql(dsn, f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
