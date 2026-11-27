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
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

# A delayed/replayed step cannot reuse an old local admission.
GATE_MAX_AGE_NS = 60 * 1_000_000_000

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
                  if (storage_path("registrations_root", root=data) / (t + ".json")).is_file())


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
    reg = json.loads((storage_path("registrations_root", root=data) / (task + ".json")).read_text("utf-8"))
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
    failed = [n for n in result.get("visible_failed", []) if re.fullmatch(r"[a-z0-9_-]{1,64}", n)]
    patch = result.get("patch_reason")
    return ("REHEARSAL_FAIL:" + result["reason"]
            + (" visible_failed=" + ",".join(failed) if failed else "")
            + (" patch=" + patch if isinstance(patch, str) and patch else ""))


def checkout_sha(root: Path) -> str:
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("REHEARSAL_CHECKOUT_UNVERIFIED")
    return sha


def gate_binding(control: Path, data: Path, task: str) -> dict:
    if not TASK.fullmatch(task):
        raise ValueError("REHEARSAL_TASK_INVALID")
    return {"task": task, "control_sha": checkout_sha(control),
            "data_sha": checkout_sha(data)}


def authorize_task(control: Path, data: Path, task: str, receipt: Path, *, api=None):
    """Trusted step with read-only GitHub token; never decrypt or run tests."""
    from pilot.orchestrator.request_lifecycle import (
        require_open, request_for_task, github_issue_api)
    binding = gate_binding(control, data, task)
    request = request_for_task(task, root=control, registered=False)
    require_open(request, api or github_issue_api, root=control)
    binding["authorized_at_ns"] = time.monotonic_ns()
    # An exclusive, runner-local, one-use handoff. No token or exam data.
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(binding, handle)


def consume_authorization(control: Path, data: Path, task: str, receipt: Path):
    """Adjacent secret-free handoff, bound to this task and both checkouts."""
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("REHEARSAL_AUTHORIZATION_MISSING")
    try:
        binding = json.loads(receipt.read_text("utf-8"))
    finally:
        receipt.unlink()
    if not isinstance(binding, dict):
        raise ValueError("REHEARSAL_AUTHORIZATION_MISMATCH")
    stamp = binding.pop("authorized_at_ns", None)
    if binding != gate_binding(control, data, task):
        raise ValueError("REHEARSAL_AUTHORIZATION_MISMATCH")
    if type(stamp) is not int or not 0 <= time.monotonic_ns() - stamp <= GATE_MAX_AGE_NS:
        raise ValueError("REHEARSAL_AUTHORIZATION_EXPIRED")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--age-bin", default="age")
    p.add_argument("--gate-receipt", type=Path)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--lifecycle-only", action="store_true")
    mode.add_argument("--select-only", action="store_true")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--task")
    g.add_argument("--changed-since")
    a = p.parse_args()
    import os
    from pilot.orchestrator.request_lifecycle import RequestStateError
    if a.task and not TASK.fullmatch(a.task):
        print("REHEARSAL_FAIL:TASK_INVALID")
        return 1
    if a.select_only:
        tasks = [a.task] if a.task else changed_tasks(a.data, a.changed_since)
        print(json.dumps(tasks, separators=(",", ":")))
        return 0
    # The workflow selects first, then each task has its own adjacent gate
    # and rehearsal. No grouped execution or transferable authorization.
    if not a.task or a.gate_receipt is None:
        print("REHEARSAL_FAIL:INDIVIDUAL_AUTHORIZATION_REQUIRED")
        return 1
    if a.lifecycle_only:
        try:
            authorize_task(a.control, a.data, a.task, a.gate_receipt)
        except RequestStateError as exc:
            code = str(exc)
            if code not in ("REQUEST_SUSPENDED", "REQUEST_CLOSED", "REQUEST_STATE_UNRESOLVED"):
                code = "REQUEST_STATE_UNRESOLVED"
            print(f"{a.task}: REHEARSAL_SKIPPED_LIFECYCLE:{code}")
            return 1
        except Exception:
            print(f"{a.task}: REHEARSAL_SKIPPED_LIFECYCLE:REQUEST_STATE_UNRESOLVED")
            return 1
        print(f"{a.task}: REHEARSAL_LIFECYCLE_OPEN")
        return 0

    # The execution step never receives a GitHub token. The AGE key is used
    # only by trusted decryption, removed from inherited command environment.
    # The pinned Worker still builds its own isolated acceptance environment.
    if any(os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN")):
        print(f"{a.task}: REHEARSAL_FAIL:UNEXPECTED_GITHUB_CREDENTIAL")
        return 1
    key = os.environ.pop("PILOT_HOLDOUT_AGE_KEY", "")
    try:
        consume_authorization(a.control, a.data, a.task, a.gate_receipt)
        verdict = rehearse(a.control, a.data, a.task, a.private / a.task, a.age_bin, key)
    except Exception as exc:  # never print exam content
        verdict = "REHEARSAL_FAIL:ERROR_" + type(exc).__name__
    print(f"{a.task}: {verdict}")
    return 1 if verdict.startswith("REHEARSAL_FAIL") else 0


if __name__ == "__main__":
    raise SystemExit(main())
