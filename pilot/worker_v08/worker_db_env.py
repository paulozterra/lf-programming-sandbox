"""Trusted LF bridge for disposable PostgreSQL in the pinned Worker.

Vendor source and its immutable provenance stay untouched. Only the exact
DB_* variables supplied by the trusted job and their derived libpq PG_* values
reach command subprocesses; ambient GitHub tokens, HOME and PG* stay out.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import re
import subprocess
from unittest.mock import patch

DB_KEYS = ("DB_URL", "DB_USERNAME", "DB_PASSWORD")


def _approved_environment():
    values = {key: os.environ.get(key) for key in DB_KEYS}
    if not any(value is not None for value in values.values()):
        # Historical offline tasks without a DB have the original isolation.
        return None
    if not all(values.values()):
        raise ValueError("WORKER_DB_ENV_INCOMPLETE")
    url = values["DB_URL"]
    match = re.fullmatch(r"jdbc:postgresql://127[.]0[.]0[.]1:5432/([A-Za-z0-9_][A-Za-z0-9_-]*)", url)
    if match is None:
        raise ValueError("WORKER_DB_URL_UNTRUSTED")

    # libpq/psql does not consume JDBC or Spring's DB_* names. Derive only
    # from the validated job values; never read ambient PG* variables.
    pg = {"PGHOST": "127.0.0.1", "PGPORT": "5432",
          "PGDATABASE": match.group(1), "PGUSER": values["DB_USERNAME"],
          "PGPASSWORD": values["DB_PASSWORD"]}
    return values, pg


def reset_disposable_database():
    """Reset only the job-owned database, never a remote or system database.

    The maintenance connection is fixed to postgres and used only to execute
    DROP/CREATE against the explicitly allowlisted job database. No ambient
    PG variables or credentials in argv, output or errors.
    """
    approved = _approved_environment()
    if approved is None:
        return
    _, pg = approved
    target = pg["PGDATABASE"]
    if target not in ("pilot", "lf_ci") or pg["PGUSER"] != "pilot":
        raise ValueError("WORKER_DB_RESET_TARGET_UNTRUSTED")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", **pg,
           "PGDATABASE": "postgres", "PGCONNECT_TIMEOUT": "10"}
    for sql in (f'DROP DATABASE "{target}" WITH (FORCE)',
                f'CREATE DATABASE "{target}" TEMPLATE template0'):
        try:
            subprocess.run(["psql", "-X", "-w", "-v", "ON_ERROR_STOP=1",
                            "-c", sql], env=env, check=True, timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            raise ValueError("WORKER_DB_RESET_FAILED") from None


@contextmanager
def worker_database_environment():
    from programming_agent_runner import worker_commands

    from pilot.worker_v08.fixture_credentials import fixture_environment

    approved = _approved_environment()
    fixtures = fixture_environment()
    if approved is None and not fixtures:
        yield
        return
    values, pg = approved if approved is not None else ({}, {})
    original = worker_commands._command_environment

    def isolated_with_db(runtime_root):
        env = original(runtime_root)
        # Fictitious SBX_FIXTURE_* credentials (published in their spec) let
        # hidden oracles sign in without a literal secret in their argv.
        return {**env, **fixtures, **values, **pg}

    with patch.object(worker_commands, "_command_environment",
                      side_effect=isolated_with_db):
        yield
