"""Trusted LF bridge for disposable PostgreSQL in the pinned Worker.

Vendor source and its immutable provenance stay untouched. Only the exact
DB_* variables supplied by the trusted job reach visible and hidden command
subprocesses; GitHub tokens, HOME, PGPASSWORD and other process env stay out.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
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
    if (not url.startswith("jdbc:postgresql://127.0.0.1:5432/")
            or "@" in url or "?" in url or "#" in url):
        raise ValueError("WORKER_DB_URL_UNTRUSTED")

    original = worker_commands._command_environment

    def isolated_with_db(runtime_root):
        env = original(runtime_root)
        return {**env, **values}

    with patch.object(worker_commands, "_command_environment",
                      side_effect=isolated_with_db):
        yield
