#!/usr/bin/env python3
"""CHG-0248 live GitHub Actions history dry-run (read-only, NO Worker/model).

This inspects all currently existing lf/native-proposal/* branch tasks and the
six req-186/req-286 lot tasks. The synthetic current run is MEMORY ONLY;
no GitHub Actions workflow is dispatched and no repository/file is written.

Before PR #370 merges, the simulated policy cutover is the future merge SHA:
all *real* earlier runs are historical. The actual production admission resolves
the trusted merged_at/merge_commit_sha from GET /pulls/370 after integration.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
import native_run_history as history

REPO = "paulozterra/lf-programming-sandbox"
EXPLICIT = (
    "req186contrato1", "req186backend2", "req186frontend3",
    "req286contrato1", "req286backend2", "req286frontend3",
)
BRANCH_PREFIX = "refs/heads/lf/native-proposal/"
REF_ROUTE = "git/matching-refs/heads/lf/native-proposal/"
WORKER_RUNS = "actions/workflows/worker-native.yml/runs?"
WORKER_PATH = ".github/workflows/worker-native.yml"


class MemoryOutput:
    """The real admit_attempt writes to this memory sink, never a filesystem."""
    def __init__(self):
        self.value = None

    def write_text(self, value, encoding="utf-8"):
        self.value = value


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token or os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise SystemExit("R3_DRY_RUN_TOKEN_OR_REPO_MISSING")
    real_api = history._api

    def api(route):
        return real_api(REPO, token, route)

    refs = api(REF_ROUTE)
    if not isinstance(refs, list):
        raise SystemExit("R3_DRY_RUN_REFS_INCOMPLETE")
    branches = {}
    for row in refs:
        name = row.get("ref") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name.startswith(BRANCH_PREFIX):
            raise SystemExit("R3_DRY_RUN_REF_INVALID")
        task = name[len(BRANCH_PREFIX):]
        if not history._TASK.fullmatch(task):
            raise SystemExit("R3_DRY_RUN_TASK_INVALID")
        sha = row.get("object", {}).get("sha")
        if not isinstance(sha, str) or not history._SHA40.fullmatch(sha):
            raise SystemExit("R3_DRY_RUN_SHA_INVALID")
        if task in branches:
            raise SystemExit("R3_DRY_RUN_DUPLICATE_REF")
        branches[task] = sha
    if not branches or not set(EXPLICIT).issubset(set(branches) | set(EXPLICIT)):
        raise SystemExit("R3_DRY_RUN_REFS_EMPTY")
    tasks = sorted(set(branches) | set(EXPLICIT))
    if not set(EXPLICIT).issubset(tasks):
        raise SystemExit("R3_DRY_RUN_MISSING_SCOPE")

    runs = []
    total = None
    for page in range(1, 11):
        obj = api(WORKER_RUNS + f"per_page=100&page={page}")
        rows = obj.get("workflow_runs")
        if (not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows)
                or type(obj.get("total_count")) is not int
                or obj["total_count"] > 999):
            raise SystemExit("R3_DRY_RUN_WORKER_HISTORY_INCOMPLETE")
        if total is None:
            total = obj["total_count"]
        if obj["total_count"] != total:
            raise SystemExit("R3_DRY_RUN_WORKER_HISTORY_DRIFT")
        runs.extend(rows)
        if len(runs) == total:
            break
    if total is None or len(runs) != total or len({r.get("id") for r in runs}) != len(runs):
        raise SystemExit("R3_DRY_RUN_WORKER_HISTORY_INCOMPLETE")
    if any(r.get("path", "").split("@")[0] != WORKER_PATH for r in runs):
        raise SystemExit("R3_DRY_RUN_FOREIGN_WORKFLOW")

    # The synthetic run is admitted by the same production function, but is
    # injected into an in-memory copy of GET /actions/workflows/worker-native.yml/runs.
    # No dispatch is possible: this script has no POST operation.
    fake_id = max([r.get("id", 0) for r in runs] + [1]) + 1000
    fake_sha = "0" * 40
    cut = ("f" * 40, datetime.now(timezone.utc) + timedelta(days=1))
    original_artifact = history._artifact_json

    @lru_cache(maxsize=4096)
    def cached_artifact(run_id, artifact_name):
        return original_artifact(REPO, token, run_id, artifact_name=artifact_name)

    def artifact(base, t, run_id, *, artifact_name=history._ARTIFACT):
        if base != REPO or t != token:
            raise ValueError("R3_DRY_RUN_REPO_SCOPE_INVALID")
        return cached_artifact(run_id, artifact_name)

    def artifact_class(run):
        rid = run["id"]
        if run.get("status") != "completed":
            return "UNFINISHED"
        obj = api(f"actions/runs/{rid}/artifacts?per_page=100")
        artifacts = obj.get("artifacts")
        if (not isinstance(artifacts, list) or
                type(obj.get("total_count")) is not int or
                obj["total_count"] > 100):
            return "ARTIFACT_LIST_INVALID"
        proofs = [a for a in artifacts if a.get("name") == history._ARTIFACT]
        if len(proofs) > 1:
            return "PROOF_DUPLICATE"
        if proofs:
            return "EXPIRED_LEGACY" if proofs[0].get("expired") else "PROOF"
        markers = [a for a in artifacts if a.get("name") == history._NO_ATTEMPT_ARTIFACT]
        if markers:
            return "NO_ATTEMPT_MARKER"
        jobs = api(f"actions/runs/{rid}/jobs?per_page=100")
        rows = jobs.get("jobs")
        if rows == [] and jobs.get("total_count") == 0 and run.get("conclusion") == "cancelled":
            return "CANCELLED_NO_JOB"
        if isinstance(rows, list) and len(rows) == 1 and rows[0].get("name") == "native":
            if rows[0].get("conclusion") == "skipped":
                return "SKIPPED_NATIVE_JOB"
            steps = rows[0].get("steps")
            if isinstance(steps, list):
                worker = [x for x in steps if x.get("name") == history._WORKER_STEP]
                if len(worker) == 1 and worker[0].get("conclusion") == "skipped":
                    return "SKIPPED_WORKER_STEP"
                if len(worker) == 1 and worker[0].get("conclusion") in ("success", "failure"):
                    return "LEGACY_WORKER_EXECUTED_NO_PROOF"
        return "LEGACY_NO_PROOF_UNKNOWN_STAGE"

    print("R3_LIVE_DRY_RUN: READ_ONLY; synthetic current run in memory; no dispatch/model/files")
    print("R3_CUTOVER: merge SHA of PR #370 (NOT MERGED); simulated cutoff is future")
    print(f"R3_HISTORY: tasks={len(tasks)} branches={len(branches)} real_worker_runs={len(runs)}")
    print("| Tarea | Intentos contados | Runs sin prueba (id:clase) | Admitir siguiente |")
    print("|---|---:|---|---|")
    report = []
    for task in tasks:
        matching = [r for r in runs if history._recognized_run(r, task)]
        missing = []
        proofs = []
        for row in matching:
            classification = artifact_class(row)
            if classification == "PROOF":
                proofs.append(row["id"])
            elif classification not in ("UNFINISHED",):
                missing.append(f'{row["id"]}:{classification}')
        synthetic = {
            "id": fake_id, "event": "workflow_run", "head_branch": "main",
            "display_title": f"lf-native-auto-lf/native-proposal/{task}-{fake_sha}",
            "status": "in_progress", "run_attempt": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "path": WORKER_PATH,
        }
        allrows = [synthetic] + runs

        def patched_api(base, t, route):
            if route.startswith(WORKER_RUNS):
                params = parse_qs(route.partition("?")[2])
                page = int(params["page"][0])
                start = (page - 1) * 100
                return {"total_count": len(allrows),
                        "workflow_runs": allrows[start:start + 100]}
            return real_api(base, t, route)

        sink = MemoryOutput()
        error = None
        admitted = None
        counted = len(proofs)
        with patch.object(history, "_api", side_effect=patched_api), patch.object(
                history, "_artifact_json", side_effect=artifact), patch.object(
                history, "_r3_merge_cutover", return_value=cut):
            try:
                admitted = history.admit_attempt(
                    repository=REPO, token=token, task=task, attempt=None,
                    run_id=fake_id, run_attempt=1, sha=fake_sha, output=sink,
                    event="workflow_run", proposal_branch="lf/native-proposal/" + task)
                counted = len(json.loads(sink.value)["prior_run_ids"])
            except (ValueError, OSError) as exc:
                error = str(exc).split(":", 1)[0]
        detail = ", ".join(missing) if missing else "—"
        status = f"OK (intento {admitted})" if error is None else f"ERROR {error}"
        print(f"| `{task}` | {counted} | {detail} | {status} |")
        report.append((task, counted, missing, status, error))
    # A result can be legitimately blocked by max attempts, a duplicate SHA,
    # registration/exam context or other existing governance. Report exactly.
    # The script never calls GitHub write APIs and never invokes the Worker.
    unexpected = [(t, e) for t, _, _, _, e in report
                  if e in ("NATIVE_PRIOR_PROOF_MISSING",
                           "NATIVE_PROOF_CUTOFF_UNRESOLVED",
                           "NATIVE_PRIOR_RUN_DATE_INVALID")]
    print(f"R3_DRY_RUN_RESULT: total={len(report)} unexplained_history_blocks={len(unexpected)}")
    if unexpected:
        raise SystemExit("R3_DRY_RUN_HISTORY_REGRESSION")


if __name__ == "__main__":
    main()
