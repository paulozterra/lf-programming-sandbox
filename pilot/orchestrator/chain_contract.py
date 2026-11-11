#!/usr/bin/env python3
"""CP3.6: fail-closed DAG/merge/failure reducer. No hidden oracle or model.

Inputs are trusted main lot files and independently verified GitHub metadata;
in particular a user-supplied completed lot ID is never a handoff proof.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from native_lot_binding import next_ready, NativeLotBlocked
from native_lot_registration import canonical

ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
PR_HEAD = re.compile(r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-([1-9][0-9]*)\Z")
TRIES = 3
BLOCK_CODE = "CP36_MAX_VERIFIED_ATTEMPTS_EXCEEDED"


class ChainBlocked(ValueError):
    pass


def deny(code: str):
    raise ChainBlocked("CP36_" + code)


def validate_plan(plan: dict, lots: dict, request: str) -> dict[str, dict]:
    if (not isinstance(plan, dict) or plan.get("schema_version") != "CP36_CHAIN_PLAN_V1"
            or plan.get("request_id") != request or plan.get("production_authority") is not False
            or plan.get("lots_sha256") != hashlib.sha256(canonical(lots)).hexdigest()):
        deny("CHAIN_PLAN_DRIFT")
    rows = plan.get("bindings")
    if not isinstance(rows, list) or len(rows) != len(lots.get("lots", [])):
        deny("BINDING_COUNT_MISMATCH")
    by_lot = {lot["id"]: lot for lot in lots["lots"]}
    if len(by_lot) != len(lots["lots"]):
        deny("DUPLICATE_LOTS")
    found, tasks = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
                "lot_id", "task_name", "template_path", "holdout_metadata_path"}:
            deny("BINDING_SHAPE_INVALID")
        lot, task = row["lot_id"], row["task_name"]
        if (lot not in by_lot or lot in found or not isinstance(task, str)
                or not ID.fullmatch(task) or task in tasks):
            deny("BINDING_ID_INVALID")
        for key in ("template_path", "holdout_metadata_path"):
            name = row[key]
            expected = f"pilot/orchestrator/native_inputs/{task}."
            suffix = "task.json" if key == "template_path" else "holdout.json"
            if name != expected + suffix:
                deny("BINDING_PATH_INVALID")
        tasks.add(task)
        found[lot] = row
    if set(found) != set(by_lot):
        deny("BINDING_INCOMPLETE")
    next_ready(lots, set())  # validate dependency references and flags
    return found


def attest_merge(merge_sha: str, pr: dict, lots: dict,
                 bindings: dict[str, dict], changes: set[str]) -> tuple[str, dict]:
    """The caller separately verifies the merge's two parents on main."""
    if not isinstance(merge_sha, str) or not SHA40.fullmatch(merge_sha):
        deny("MERGE_SHA_INVALID")
    if (pr.get("merged") is not True or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") !=
            "paulozterra/lf-programming-sandbox"
            or pr.get("merge_commit_sha") != merge_sha
            or pr.get("head", {}).get("repo", {}).get("full_name") !=
            "paulozterra/lf-programming-sandbox"):
        deny("PR_NOT_MERGED_ON_MAIN")
    branch = pr.get("head", {}).get("ref", "")
    match = PR_HEAD.fullmatch(branch)
    if not match:
        deny("NOT_NATIVE_INTEGRATION")
    task = match.group(1)
    matching = [lot for lot, value in bindings.items() if value["task_name"] == task]
    if len(matching) != 1:
        deny("INTEGRATION_TASK_UNBOUND")
    lot_id = matching[0]
    lot = next(x for x in lots["lots"] if x["id"] == lot_id)
    allowed = set(lot["write_paths"])
    actual = changes - {p for p in changes if p.startswith("standards/changes/")} - {"standards/CAMBIOS.md"}
    if not actual or not actual.issubset(allowed):
        deny("INTEGRATION_SCOPE_MISMATCH")
    return lot_id, {"lot_id": lot_id, "merge_sha": merge_sha,
                    "expected_files": sorted(lot["write_paths"]),
                    "integration_pr": pr["number"], "task_name": task}


def verified_failures(task: str, runs: list[dict], proofs: dict[int, dict | None]) -> list[int]:
    """Count only three authenticated, spent native attempts; not queued or preflight.

    The proof is the trusted Actions 'native-attempt-proof' artifact, never
    a proposal-branch file or a model response.
    """
    if not ID.fullmatch(task):
        deny("TASK_INVALID")
    matched = {}
    for run in runs:
        if run.get("status") != "completed" or run.get("conclusion") != "failure":
            continue
        if (run.get("head_branch") != "main" or run.get("run_attempt") != 1
                or run.get("event") not in ("workflow_dispatch", "workflow_run")):
            continue
        run_id = run.get("id")
        if type(run_id) is not int or run_id <= 0:
            continue
        proof = proofs.get(run_id)
        if proof is None:
            continue
        if (not isinstance(proof, dict) or set(proof) !=
                {"task_id", "attempt", "task_pack_sha256", "run_id"}
                or proof.get("task_id") != task or proof.get("run_id") != run_id
                or type(proof.get("attempt")) is not int
                or not 1 <= proof["attempt"] <= TRIES
                or not isinstance(proof.get("task_pack_sha256"), str)
                or not SHA64.fullmatch(proof["task_pack_sha256"])):
            deny("ATTEMPT_PROOF_INVALID")
        n = proof["attempt"]
        if n in matched or (matched and any(existing == run_id for existing in matched.values())):
            deny("ATTEMPT_DUPLICATE")
        matched[n] = run_id
    if matched and set(matched) != set(range(1, max(matched) + 1)):
        deny("ATTEMPT_GAP")
    return [matched[k] for k in sorted(matched)]


def progress(lots: dict, completed: dict[str, dict], failures: dict[str, list[int]],
             bindings: dict[str, dict]) -> dict:
    if not isinstance(completed, dict) or not set(completed).issubset(bindings):
        deny("COMPLETION_UNTRUSTED")
    for lot_id, proof in completed.items():
        if not isinstance(proof, dict) or proof.get("lot_id") != lot_id:
            deny("COMPLETION_UNTRUSTED")
    for lot_id, attempts in failures.items():
        if lot_id not in bindings or not isinstance(attempts, list):
            deny("FAILURE_LEDGER_INVALID")
        if len(attempts) > TRIES or len(set(attempts)) != len(attempts):
            deny("FAILURE_LEDGER_INVALID")
    bad = sorted(lot for lot, attempts in failures.items()
                 if len(attempts) >= TRIES and lot not in completed)
    if bad:
        return {"stage": "BLOCKED", "reason_code": BLOCK_CODE,
                "blocked_lot_ids": bad, "ready_lot_ids": [],
                "production_authority": False, "handoff_allowed": False}
    eligible = next_ready(lots, set(completed))
    already = set(completed)
    return {"stage": "CHAIN_READY" if eligible else "CHAIN_COMPLETE_CANDIDATE",
            "reason_code": None,
            "blocked_lot_ids": [],
            "ready_lot_ids": [lot["id"] for lot in eligible if lot["id"] not in already],
            "production_authority": False, "handoff_allowed": False}


def blocked_state(original: dict, result: dict) -> dict:
    if result.get("stage") != "BLOCKED" or result.get("reason_code") != BLOCK_CODE:
        deny("BLOCK_STATE_NOT_REQUIRED")
    if original.get("stage") not in ("LOTS_PLANNED", "BLOCKED"):
        deny("STATE_NOT_PLANNED")
    state = dict(original, stage="BLOCKED",
                 reason_code=BLOCK_CODE,
                 blocked_lot_ids=result["blocked_lot_ids"],
                 production_authority=False, handoff_allowed=False,
                 downstream_authorized=False)
    return state
