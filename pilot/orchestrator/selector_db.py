#!/usr/bin/env python3
"""CP3.3: bootstrap only the pinned SQL selector on a *fresh local disposable* PG17.

Never connects to Supabase; rejects nonlocal/nonempty/non-opted-in databases.
The SQL is the byte-pinned LF source, not a rewritten selector.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

PINNED = Path(__file__).resolve().parents[1] / "lf_producers_pinned"
SELECTOR = PINNED / "selector_experimental"
sys.path.insert(0, str(SELECTOR / "tests"))
from test_parity import TABLES, FUNCTIONS, run_psql
from test_experimental import guard, reference


def dsn_checked() -> str:
    dsn = os.environ.get("SELECTOR_EXP_TEST_DSN", "")
    if os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES" or not dsn:
        raise ValueError("SELECTOR_REQUIERE_ENTORNO")
    # The pinned guard checks localhost, the disposable selector_exp_test_ name,
    # real host and zero user relations, BEFORE any SQL is installed.
    return dsn


def bootstrap() -> None:
    dsn = dsn_checked()
    guard(dsn)
    for path in ("original/schema/bootstrap.sql", "original/schema/tables.sql",
                 "original/schema/constraints.sql"):
        run_psql(dsn, file=SELECTOR / path)
    for name in TABLES:
        run_psql(dsn, file=SELECTOR / "original/data" / (name + ".sql"))
    for name in FUNCTIONS:
        run_psql(dsn, file=SELECTOR / "original/functions" / name)
    # Verify the untouched original fixture BEFORE extending it.
    reference(dsn)
    for path in ("experimental/seed_profiles_exp.sql",
                 "experimental/area_policy_exp.sql",
                 "experimental/functions_exp.sql"):
        run_psql(dsn, file=SELECTOR / path)
    print("CP33_PINNED_LOCAL_SELECTOR_BOOTSTRAP_PASS")


if __name__ == "__main__":
    try:
        bootstrap()
    except (ValueError, RuntimeError, OSError) as exc:
        print("SELECTOR_REQUIERE_ENTORNO", file=sys.stderr)
        sys.exit(1)
