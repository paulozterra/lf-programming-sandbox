"""Trusted LF bridge for disposable PostgreSQL in the pinned Worker.

Vendor source and its immutable provenance stay untouched. Only the exact
DB_* variables supplied by the trusted job and their derived libpq PG_* values
reach command subprocesses; ambient GitHub tokens, HOME and PG* stay out.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import re
from unittest.mock import patch

DB_KEYS = ("DB_URL", "DB_USERNAME", "DB_PASSWORD")


@contextmanager
def worker_database_environment():
    from programming_agent_runner import worker_commands

    values = {key: os.environ.get(key) for key in DB_KEYS}
    if not any(value is not None for value in values.values()):
        # Historical offline tasks without a DB have the original isolation.
        yield
        return
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
    original = worker_commands._command_environment

    def isolated_with_db(runtime_root):
        env = original(runtime_root)
        return {**env, **values, **pg}

    with patch.object(worker_commands, "_command_environment",
                      side_effect=isolated_with_db):
        yield
