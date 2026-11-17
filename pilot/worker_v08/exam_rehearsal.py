#!/usr/bin/env python3
"""T40 capa 1: rehearse an exam with the real Worker before it can be used.

For every task whose registration, exam or reference changes in a pull request
(or the task named by hand), the examiner's reference must pass visible and
hidden acceptance through the original run_verified_worker, on the registered
base, in the CI Worker environment. No attempt, proposal or issue is touched.

Data (registration, ciphertexts) is read from the --data checkout; code always
comes from trusted main (--control). Output is a verdict per task, never exam
content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
WATCHED = re.compile(
    r"pilot/(?:worker_v08/native_tasks/([a-z][a-z0-9_-]{0,31})\.json"
    r"|holdouts/([a-z][a-z0-9_-]{0,31})\.(?:oracle|reference)\.json\.age)\Z")


def changed_tasks(data: Path, base_ref: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(data), "diff", "--name-only", base_ref, "HEAD"],
                         check=True, capture_output=True, text=True).stdout.split()
    tasks = set()
    for path in out:
        m = WATCHED.fullmatch(path)
        if m:
            tasks.add(m.group(1) or m.group(2))
    # only tasks that still exist as exam-backed registrations at HEAD
    return sorted(t for t in tasks
                  if (data / "pilot/worker_v08/native_tasks" / (t + ".json")).is_file())


def rehearse(control: Path, data: Path, task: str, private: Path, age_bin: str,
             key: str) -> str:
    sys.path.insert(0, str(control / "pilot/worker_v08"))
    sys.path.insert(0, str(control / "vendor/programming-agent/src"))
    from dataclasses import replace
    from native_run import load_registration
    from holdout_age import decrypt_private, decrypt_reference, AgeBlocked
    from native_exam_control import load_reference, run_reference
    from programming_agent_runner.worker_spec import parse_worker_task
    from programming_agent_runner.worker_oracle import load_hidden_oracle

    raw_task, holdout_sha = load_registration(data, task)
    reg = json.loads((data / "pilot/worker_v08/native_tasks" / (task + ".json")).read_text("utf-8"))
    if "holdout_ref" not in reg:
        return "REHEARSAL_SKIPPED_LEGACY"
    spec = replace(parse_worker_task(raw_task), max_attempts=1)
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        decrypt_private(data, task, reg["holdout_ref"], holdout_sha, key, private, age_bin)
        if decrypt_reference(data, task, key, private, age_bin) is None:
            return "REHEARSAL_FAIL:EXAM_REFERENCE_MISSING"
    except AgeBlocked as exc:
        return "REHEARSAL_FAIL:" + str(exc)
    try:
        patch = load_reference(private, task, holdout_sha)
    except (ValueError, UnicodeError) as exc:
        return "REHEARSAL_FAIL:" + str(exc).split(":", 1)[0]
    source = private / "source"
    subprocess.run(["git", "-C", str(data), "worktree", "add", "-q", "--detach",
                    str(source), spec.base_head_sha], check=True, capture_output=True)
    try:
        oracle = load_hidden_oracle(private / "holdout.oracle.json", holdout_sha)
        result = run_reference(source, spec, oracle, patch, private / "work")
    finally:
        subprocess.run(["git", "-C", str(data), "worktree", "remove", "--force", str(source)],
                       capture_output=True)
    if result["status"] == "PASS":
        return "REHEARSAL_PASS"
    return "REHEARSAL_FAIL:" + result["reason"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--age-bin", default="age")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--task")
    g.add_argument("--changed-since")
    a = p.parse_args()
    import os
    key = os.environ.get("PILOT_HOLDOUT_AGE_KEY", "")
    tasks = [a.task] if a.task else changed_tasks(a.data, a.changed_since)
    if a.task and not TASK.fullmatch(a.task):
        print("REHEARSAL_FAIL:TASK_INVALID")
        return 1
    if not tasks:
        print("REHEARSAL_NOTHING_TO_DO")
        return 0
    failed = False
    for task in tasks:
        try:
            verdict = rehearse(a.control, a.data, task, a.private / task, a.age_bin, key)
        except Exception as exc:  # never print exam content
            verdict = "REHEARSAL_FAIL:ERROR_" + type(exc).__name__
        print(f"{task}: {verdict}")
        failed |= verdict.startswith("REHEARSAL_FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
