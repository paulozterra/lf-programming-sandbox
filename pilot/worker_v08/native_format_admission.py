#!/usr/bin/env python3
"""Token-free format admission before examiner loading."""
import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

from programming_agent_runner.hashutil import canonical_json_bytes, strict_json_loads
from programming_agent_runner.model_client import ModelError
from programming_agent_runner.worker_patch import PatchValidationError, inspect_patch, parse_patch_proposal
from programming_agent_runner.worker_spec import parse_worker_task
from pilot.config.project_config import active_project, load, storage_path
from export_task_pack import export
from native_format_preflight import FormatResult, prevalidate
from native_proposal_client import read_proposal_envelope
from native_run import load_registration, proposal_path

CONTINUE = {"PASS", "SKIPPED"}
BLOCK = {"FORMAT_FAIL", "BASELINE_FAIL", "INVALID_PROPOSAL", "INFRA_ERROR"}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9_./-]{1,1024}\Z")
SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
LOCATION = re.compile(r"([A-Za-z0-9_./-]{1,1024}): original line [0-9]{1,8}, [0-9]{1,8} lines; formatted line [0-9]{1,8}, [0-9]{1,8} lines\Z")


def _write(path, data):
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(data) + b"\n")


def _check_pack(control, source, task, raw, submitted, *, route_retry, sha, attempt):
    # Capture-only Worker verifies source identity and terminates at model input.
    # No acceptance command or examiner is executed.
    with tempfile.TemporaryDirectory(prefix="lf-format-pack-") as temp:
        folder = Path(temp)
        spec = folder / "spec.json"
        spec.write_bytes(canonical_json_bytes(raw))
        actual = export(source, spec, folder / "pack.json")
    if route_retry:
        from native_route_defect import verified_migration
        record = strict_json_loads(storage_path("registrations_root", task + ".json", root=control).read_text("utf-8"))
        migration = verified_migration(control, task, record, proposal_sha=sha)
        return (migration is not None and attempt == 1
                and actual == migration["corrected_task_pack_sha256"]
                and submitted["task_pack_sha256"] == migration["legacy_task_pack_sha256"])
    return actual == submitted["task_pack_sha256"]


def _evaluate(control, source, checkout, task, sha, attempt, route_retry):
    try:
        raw, _ = load_registration(control, task)
        spec = parse_worker_task(raw)
    except Exception:
        return FormatResult("INFRA_ERROR", "FORMAT_REGISTRATION_INVALID")
    try:
        submitted = read_proposal_envelope(checkout / proposal_path(task))
        candidate = parse_patch_proposal(submitted["proposal"], spec)
        inspect_patch(candidate, spec)
    except (ModelError, PatchValidationError, ValueError, OSError):
        return FormatResult("INVALID_PROPOSAL", "FORMAT_ENVELOPE_OR_SCOPE_INVALID")
    try:
        if not _check_pack(control, source, task, raw, submitted, route_retry=route_retry, sha=sha, attempt=attempt):
            return FormatResult("INVALID_PROPOSAL", "FORMAT_TASK_PACK_MISMATCH")
        return prevalidate(source, spec, submitted["proposal"], load(active_project(root=control), root=control))
    except Exception:
        return FormatResult("INFRA_ERROR", "FORMAT_ADMISSION_EXECUTION_FAILED")


def _public(result):
    paths, diagnostics = result.paths, result.diagnostics
    if (result.status not in CONTINUE | BLOCK or not SAFE_CODE.fullmatch(result.reason)
            or len(paths) > 100 or len(diagnostics) > 32
            or any(not SAFE_PATH.fullmatch(p) for p in paths)
            or any(not (match := LOCATION.fullmatch(row)) or match.group(1) not in paths for row in diagnostics)
            or (result.status == "FORMAT_FAIL" and
                (not paths or not diagnostics or any(not any(row.startswith(p + ":") for row in diagnostics) for p in paths)))):
        result = FormatResult("INFRA_ERROR", "FORMAT_PUBLIC_EVIDENCE_INVALID")
        paths = diagnostics = ()
    return {"status": result.status, "reason": result.reason,
            "paths": list(paths), "diagnostics": list(diagnostics)}


def admit(control, source, checkout, task, sha, attempt, run_id, output, *, route_retry=False):
    proposal_path(task)
    if not SHA40.fullmatch(sha) or type(attempt) is not int or not 1 <= attempt <= 3 or run_id <= 0:
        raise ValueError("FORMAT_ADMISSION_IDENTITY_INVALID")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = _public(_evaluate(control, source, checkout, task, sha, attempt, route_retry))
    proceed = result["status"] in CONTINUE
    _write(output / "format-result.json", {
        "schema_version": "LF_NATIVE_FORMAT_RESULT_V1", "task_id": task,
        "proposal_commit_sha": sha, "run_id": run_id, "next_functional_attempt": attempt,
        "functional_attempt_consumed": False, **result,
    })
    if not proceed:
        _write(output / "no-attempt.json", {
            "schema_version": "LF_NATIVE_NO_ATTEMPT_V1", "task_id": task,
            "run_id": run_id, "attempt": attempt, "reason": "PRE_ATTEMPT",
        })
    print("LF_NATIVE_FORMAT_" + result["status"])
    return proceed


def main():
    parser = argparse.ArgumentParser()
    for arg in ("control", "source", "proposal", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--route-retry", action="store_true")
    a = parser.parse_args()
    try:
        ok = admit(a.control, a.source, a.proposal, a.task, a.sha, a.attempt, a.run_id,
                   a.output, route_retry=a.route_retry)
    except Exception:
        print("LF_NATIVE_FORMAT_ADMISSION_FAILED", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
