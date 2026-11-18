#!/usr/bin/env python3
"""T46: read the project's EKB live, read-only, returning ONLY error codes.

Content (root cause, prevention, evidence...) never leaves the database through
the route: this repository and its logs are public. The connection string is a
CI secret named in the project config; it is never printed. Any failure is
reported as a code class, never with the server message (it may echo the URL).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_config import AuditConfigError, load  # noqa: E402


class EkbError(ValueError):
    pass


def read_codes(config: dict, env: dict | None = None, psql: str = "psql") -> list[str]:
    ekb = config["audit"]["ekb"]
    if ekb["source"] == "NONE":
        return []
    env = dict(os.environ if env is None else env)
    url = env.get(ekb["secret"], "").strip().strip("'\"").strip()
    if not url:
        raise EkbError("AUDIT_EKB_UNAVAILABLE:SECRET_MISSING")
    if not url.startswith(("postgresql://", "postgres://")):
        # Never echo the value: it may be a credential pasted in another form.
        raise EkbError("AUDIT_EKB_UNAVAILABLE:SECRET_MALFORMED")
    # ORM-only query parameters (Prisma) that libpq rejects as invalid.
    base, _, query = url.partition("?")
    kept = [kv for kv in query.split("&") if kv and kv.split("=")[0] not in ("pgbouncer", "connection_limit", "pool_timeout", "schema")]
    url = base + ("?" + "&".join(kept) if kept else "")
    # Identifiers are validated by audit_config (IDENT); no user input reaches SQL.
    sql = (f"begin transaction read only; select {ekb['code_column']} from {ekb['table']} "
           f"where {ekb['code_column']} is not null order by 1; rollback;")
    child_env = {k: v for k, v in env.items() if k in ("PATH", "HOME", "LANG", "LC_ALL")}
    child_env["PGCONNECT_TIMEOUT"] = "15"
    try:
        out = subprocess.run([psql, url, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
                              "-c", sql], capture_output=True, text=True, timeout=60,
                             env=child_env)
    except (OSError, subprocess.TimeoutExpired):
        raise EkbError("AUDIT_EKB_UNAVAILABLE:CLIENT") from None
    if out.returncode != 0:
        err = out.stderr.lower()
        # Only a 5-char SQLSTATE ever leaves this function, never server text.
        state = re.search(r"error:\s+([0-9a-z]{5}):", err)
        kind = ("SECRET_MALFORMED" if "invalid" in err and ("uri" in err or "connection option" in err
                                                              or "port" in err or "integer" in err) else
                "AUTH" if "password" in err or "authentication" in err
                or "tenant or user not found" in err else
                "PERMISSION" if "permission denied" in err else
                "SCHEMA" if "does not exist" in err else
                "NETWORK_IPV6_UNREACHABLE" if "unreachable" in err or "cannot assign requested address" in err else
                "NETWORK_SSL" if "ssl" in err else
                "NETWORK" if "could not" in err or "timeout" in err or "connection to server" in err
                or "refused" in err or "server closed" in err else "QUERY")
        role = ""
        if kind == "PERMISSION":
            try:
                who = subprocess.run([psql, url, "-X", "-q", "-A", "-t", "-c", "select current_user"],
                                     capture_output=True, text=True, timeout=30, env=child_env)
                name = who.stdout.strip()
                role = ":ROLE=" + name if who.returncode == 0 and re.fullmatch(r"[A-Za-z0-9_]{1,63}", name) else ""
            except (OSError, subprocess.TimeoutExpired):
                pass
        raise EkbError("AUDIT_EKB_UNAVAILABLE:" + kind
                       + (":" + state.group(1).upper() if state else "")
                       + (":" + obj.group(1).upper() if kind == "PERMISSION" and (obj := re.search(
                           r"permission denied (?:for|to) (table|schema|sequence|function|database|relation|view|column)", err)) else "")
                       + role)
    codes = [line.strip() for line in out.stdout.splitlines() if line.strip()
             and line.strip() not in ("BEGIN", "ROLLBACK")]
    return sorted(set(codes))


def summary(codes: list[str]) -> dict:
    return {"rows": len(codes),
            "codes_sha256": hashlib.sha256("\n".join(codes).encode()).hexdigest()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    try:
        codes = read_codes(load(a.project))
    except (AuditConfigError, EkbError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    print(json.dumps({"status": "EKB_READ", **summary(codes)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
