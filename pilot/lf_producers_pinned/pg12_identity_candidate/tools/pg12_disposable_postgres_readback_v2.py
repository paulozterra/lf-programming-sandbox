"""Exact V2 PG12 C4 JSONB readback, separate local PostgreSQL sessions.

No Supabase and no production writes. Requires PG12_TEST_DSN=pg12_test_* and
PG12_DISPOSABLE_DB=YES, with a loopback/local socket host.
"""
import json
import os
import uuid
from urllib.parse import urlparse

from pg12_disposable_postgres_readback_v1 import canonical, digest, psql, fail, database_from_dsn


def persist_readback(c4):
    dsn = os.environ.get("PG12_TEST_DSN", "")
    if (os.environ.get("PG12_DISPOSABLE_DB") != "YES" or
            not database_from_dsn(dsn).startswith("pg12_test_")):
        fail("PG12_POSTGRES_DISPOSABLE_DATABASE_AND_EXPLICIT_OPT_IN_REQUIRED")
    if os.environ.get("PGSERVICE") or os.environ.get("PGSERVICEFILE"):
        fail("PG12_V2_PG_SERVICE_REDIRECTION_FORBIDDEN")
    if any(os.environ.get(key) not in (None, "", "localhost", "127.0.0.1", "::1")
           for key in ("PGHOST", "PGHOSTADDR")):
        fail("PG12_V2_REMOTE_ENV_HOST_FORBIDDEN")
    if dsn.startswith(("postgresql://", "postgres://")):
        if urlparse(dsn).hostname not in ("localhost", "127.0.0.1", None):
            fail("PG12_V2_REMOTE_DATABASE_FORBIDDEN")
    identity = psql(dsn, "SELECT current_database() || '|' || coalesce(host(inet_server_addr()),'LOCAL_SOCKET');")
    parts = identity.split("|")
    if len(parts) != 2 or not parts[0].startswith("pg12_test_") or parts[1] not in (
            "LOCAL_SOCKET", "127.0.0.1", "::1"):
        fail("PG12_V2_NOT_LOCAL_DISPOSABLE_DATABASE")
    if (not isinstance(c4, dict) or
            c4.get("schema_version") != "PG12_C4_PERSISTENCE_READBACK_REQUEST_CANDIDATE_V2" or
            c4.get("production_authority") is not False or
            c4.get("handoff_allowed") is not False or
            c4.get("persisted") is not False or
            c4.get("readback_matched") is not False):
        fail("PG12_V2_SOURCE_SCHEMA_OR_AUTHORITY_INVALID")
    payload = c4["payload_candidate"]
    expected = c4["payload_candidate_sha256"]
    if digest(payload) != expected:
        fail("PG12_C4_PREWRITE_PAYLOAD_DIGEST_MISMATCH")
    schema = "pg12_v2_" + uuid.uuid4().hex[:16]
    key = uuid.uuid4().hex
    try:
        body = canonical(payload).encode("utf-8").hex()
        psql(dsn, f'CREATE SCHEMA "{schema}"; CREATE TABLE "{schema}".receipts '
                  '(record_key text PRIMARY KEY, payload jsonb NOT NULL); '
                  f'INSERT INTO "{schema}".receipts(record_key,payload) '
                  f"VALUES ('{key}',convert_from(decode('{body}','hex'),'UTF8')::jsonb);")
        observed_text = psql(dsn, f'SELECT payload::text FROM "{schema}".receipts '
                                  f"WHERE record_key='{key}';")
        if not observed_text:
            fail("PG12_C4_READBACK_MISSING")
        observed = json.loads(observed_text)
        if observed != payload or digest(observed) != expected:
            fail("PG12_C4_READBACK_NOT_IDENTICAL")
        print("PG12_C4_POSTGRES_DISPOSABLE_READBACK_PASS")
        print("PG12_C4_V2_READBACK_PASS")
        print("PG12_C4_V2_EXPECTED_SHA256=" + expected)
        print("PG12_C4_V2_READBACK_SHA256=" + digest(observed))
        print("PG12_C4_PRODUCTION_AUTHORITY=FALSE")
        return expected
    finally:
        psql(dsn, f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
