#!/usr/bin/env python3
"""Run pinned producer tests by PG stage, offline and without LF credentials.

A genuinely unavailable external database suite is reported explicitly as
REQUIERE_ENTORNO_LF. Other failures are never silently accepted.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PINNED = ROOT / "pilot/lf_producers_pinned"
STAGES = [
    "pg02", "pg02_qualification", "pg03_stack_source_candidate",
    "pg03_strategy_candidate", "pg04_semantic_partition_candidate",
    "pg05_target_binding_candidate", "pg06_preflight_candidate",
    "pg07_worker_candidate", "pg08_build_candidate", "pg09_iteration_candidate",
    "pg10_conflict_candidate", "pg11_integrity_candidate",
    "pg12_identity_candidate", "pg13_freeze_candidate",
    "pg14_testing_handoff_candidate", "selector_experimental",
    "c6_context_gate", "ex6_real_chain_candidate",
]
# Parity executes psql against an explicitly opted-in disposable Postgres.
ENVIRONMENT_LF = {
    "selector_experimental/tests/test_parity.py":
    "Requires psql and an explicitly opted-in disposable PostgreSQL DSN",
    "selector_experimental/tests/test_experimental.py":
    "Requires psql and an explicitly opted-in disposable PostgreSQL DSN",
    "selector_experimental/integration/test_pg04_pg07_selector_bridge_v1.py":
    "Requires disposable Postgres and LF experimental profile fixtures",
    "pg03_strategy_candidate/test_pg03_semantic_adapter_v1.py":
    "Imports real profiles/systemic_root_cause_repair_lf validator, forbidden to copy",
    "pg04_semantic_partition_candidate/test_analysis_fresh_request_b2b_v1.py":
    "Imports real profiles/programming_analysis_lf validator, forbidden to copy",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    extra_paths = [str(PINNED)] + [str(PINNED / stage) for stage in STAGES]
    extra_paths += [str(PINNED / stage / sub)
                    for stage in STAGES for sub in ("tools", "integration", "tests")]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(extra_paths)
    env.pop("DATABASE_URL", None)
    env.pop("SUPABASE_URL", None)
    env.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    env.pop("PGPASSWORD", None)
    results = []
    failed = False
    for stage in STAGES:
        path = PINNED / stage
        tests = sorted(p for p in path.rglob("test_*.py") if p.is_file())
        if not tests:
            results.append({"suite": stage, "status": "SIN_PRUEBAS", "reason": "No test_*.py files"})
            continue
        if stage == "ex6_real_chain_candidate":
            results.append({"suite": stage, "status": "REQUIERE_ENTORNO_LF",
                            "test_files": len(tests),
                            "reason": "H4 EX6 tests require native-attempt-proof.zip and historical CI evidence; no private artifacts copied"})
            continue
        chosen = [p for p in tests if p.relative_to(PINNED).as_posix() not in ENVIRONMENT_LF]
        excluded = [p for p in tests if p not in chosen]
        if not chosen:
            results.append({"suite": stage, "status": "REQUIERE_ENTORNO_LF",
                            "reason": "; ".join(ENVIRONMENT_LF[p.relative_to(PINNED).as_posix()]
                                               for p in excluded)})
            continue
        call = [sys.executable, "-m", "pytest", "-q", "--tb=short"] + [str(p) for p in chosen]
        try:
            p = subprocess.run(call, cwd=PINNED, env=env, text=True,
                               capture_output=True, timeout=160, check=False)
            output = (p.stdout + "\n" + p.stderr)[-8000:]
            status = "PASS" if p.returncode == 0 else "FAIL"
            if p.returncode == 5 and "no tests ran" in output:
                # These source tests check invariants at module top level.
                scripts = [subprocess.run([sys.executable, "-B", str(test)],
                             cwd=PINNED, env=env, text=True, capture_output=True,
                             timeout=120, check=False) for test in chosen]
                status = "PASS_SCRIPT_ASSERTIONS" if all(x.returncode == 0 for x in scripts) else "FAIL"
                output = ("\n".join(x.stdout + "\n" + x.stderr for x in scripts))[-8000:]
            results.append({"suite": stage, "status": status,
                            "test_files": len(chosen), "output_tail": output})
            failed |= status == "FAIL"
        except subprocess.TimeoutExpired:
            results.append({"suite": stage, "status": "FAIL",
                            "reason": "Offline suite exceeded 160 seconds"})
            failed = True
        for test in excluded:
            results.append({"suite": test.relative_to(PINNED).as_posix(),
                            "status": "REQUIERE_ENTORNO_LF",
                            "reason": ENVIRONMENT_LF[test.relative_to(PINNED).as_posix()]})
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    for item in results:
        print(item["suite"] + ": " + item["status"] +
              (": " + item.get("reason", "") if item.get("reason") else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
