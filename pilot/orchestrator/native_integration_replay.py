"""T24: one trusted CP3.5 recovery per immutable native PASS run.

The failed integration must be proven to have reached the exact route-owned
TASK_SCOPE_UNSAFE guard; never replay genuine worker failures or user patches
without the original native PASS artifacts. The CP3.5 workflow reattests the
source run, proof, patch and exact attempt on every replay.
"""
from __future__ import annotations
# Resolve the trusted repository package when executed as a script.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import json
from pathlib import Path
import re

from pilot.orchestrator.native_write_scope import WriteScopeError, validate_write_paths

WORKER = "worker-native.yml"
INTEGRATION = "native-verified-integration.yml"
WORKER_PATH = ".github/workflows/" + WORKER
INTEGRATION_PATH = ".github/workflows/" + INTEGRATION
FAIL_CODE = "CP35_TASK_SCOPE_UNSAFE"
REPLAY_TITLE = re.compile(r"CP3[.]5 recovery native-run-([1-9][0-9]*)\Z")
WORKER_TITLE = re.compile(
    r"(?:lf-native-auto-lf/native-proposal/|lf-native-route-retry-|"
    r"lf-native-infra-retry-)([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
MANUAL_WORKER_TITLE = re.compile(
    r"lf-native-([a-z][a-z0-9_-]{0,31})-a[123]-([0-9a-f]{40})\Z")


def _listed(api, workflow: str) -> list[dict]:
    """Complete bounded run history; a truncated first page cannot prove absence."""
    response = api(f"actions/workflows/{workflow}/runs?per_page=100")
    rows = response.get("workflow_runs")
    total = response.get("total_count")
    if (not isinstance(rows, list) or type(total) is not int or
            total < 0 or total > 1000 or len(rows) > 100 or
            len(rows) != min(total, 100) or
            any(not isinstance(row, dict) for row in rows)):
        raise ValueError("R1_CP35_HISTORY_INCOMPLETE")
    found = list(rows)
    for page in range(2, (total + 99) // 100 + 1):
        response = api(f"actions/workflows/{workflow}/runs?per_page=100&page={page}")
        chunk = response.get("workflow_runs")
        if (not isinstance(chunk, list) or response.get("total_count") != total
                or len(chunk) != min(100, total - len(found))
                or any(not isinstance(row, dict) for row in chunk)):
            raise ValueError("R1_CP35_HISTORY_INCOMPLETE")
        found.extend(chunk)
    if len(found) != total or len({row.get("id") for row in found}) != len(found):
        raise ValueError("R1_CP35_HISTORY_INCOMPLETE")
    return found


def _trusted_worker(run: dict, repo: str) -> bool:
    return (
        type(run.get("id")) is int and run["id"] > 0
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("head_branch") == "main"
        and run.get("event") in ("workflow_run", "workflow_dispatch")
        and run.get("run_attempt") == 1
        and (run.get("path") or "").split("@")[0] == WORKER_PATH
        and (run.get("repository") or {}).get("full_name") == repo
        and (WORKER_TITLE.fullmatch(str(run.get("display_title") or "")) is not None
             or MANUAL_WORKER_TITLE.fullmatch(str(run.get("display_title") or "")) is not None)
    )


def _trusted_failed_integration(run: dict, repo: str) -> bool:
    return (
        type(run.get("id")) is int and run["id"] > 0
        and run.get("status") == "completed" and run.get("conclusion") == "failure"
        and run.get("head_branch") == "main"
        and run.get("event") == "workflow_run"
        and run.get("run_attempt") == 1
        and (run.get("path") or "").split("@")[0] == INTEGRATION_PATH
        and (run.get("repository") or {}).get("full_name") == repo
        and str(run.get("display_title") or "").startswith("CP3.5 ")
    )


def _failed_for_scope(api, run, repo: str, integration: dict) -> bool:
    identity = integration["id"]
    response = api(f"actions/runs/{identity}/jobs?per_page=100")
    jobs = response.get("jobs")
    if (not isinstance(jobs, list) or response.get("total_count") != 1
            or len(jobs) != 1 or jobs[0].get("name") != "integrate"
            or jobs[0].get("conclusion") != "failure"):
        return False
    steps = jobs[0].get("steps")
    if not isinstance(steps, list) or not any(
            isinstance(step, dict)
            and step.get("name") == "Integrate PASS artifact into a draft PR with C9 and head-specific CI"
            and step.get("conclusion") == "failure"
            for step in steps):
        return False
    # A known fail-closed machine code emitted by the trusted integration
    # script; do not accept arbitrary untrusted logs/tracebacks as evidence.
    logs = run("gh", "run", "view", str(identity), "--repo", repo, "--log")
    if not isinstance(logs, str) or len(logs) > 2_000_000:
        return False
    return any(re.fullmatch(
        r"[^\n]{0,600}\bCP35_TASK_SCOPE_UNSAFE\s*", line)
        is not None for line in logs.splitlines())


def recover(head: str, run, api, repo: str, root: Path,
            *, allowed_tasks: set[str] | None = None, allowed_task=None) -> list[dict]:
    """Idempotent CP3.6 dispatch; all GitHub effects through injected run/API."""
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("INTEGRATION_REPLAY_HEAD_INVALID")
    integration_runs = _listed(api, INTEGRATION)
    worker_runs = _listed(api, WORKER)
    dispatched = set()
    for item in integration_runs:
        match = REPLAY_TITLE.fullmatch(str(item.get("display_title") or ""))
        if match and item.get("event") == "workflow_dispatch":
            dispatched.add(int(match.group(1)))
    results = []
    scheduled = set()
    # Newest first; never replay a successful/failed prior retry for this
    # immutable source run, including a queued workflow_dispatch.
    for failure in sorted(integration_runs, key=lambda x: x.get("id", 0),
                          reverse=True):
        if not _trusted_failed_integration(failure, repo):
            continue
        candidates = [source for source in worker_runs
                      if _trusted_worker(source, repo)
                      and "CP3.5 " + str(source.get("display_title")) ==
                      failure.get("display_title")
                      and source.get("head_sha") == failure.get("head_sha")
                      and source["id"] < failure["id"]]
        if len(candidates) != 1:
            continue
        source = candidates[0]
        source_id = source["id"]
        if source_id in dispatched or source_id in scheduled:
            continue
        identity = (WORKER_TITLE.fullmatch(source["display_title"]) or
                    MANUAL_WORKER_TITLE.fullmatch(source["display_title"]))
        task = identity.group(1)
        # A sweep invokes this once per request. Never dispatch a PASS
        # belonging to another request, nor replay it twice in one sweep.
        if allowed_tasks is not None and task not in allowed_tasks:
            continue
        registration = storage_path("registrations_root", root=root) / (task + ".json")
        if not registration.is_file() or registration.is_symlink():
            continue
        try:
            record = json.loads(registration.read_text("utf-8"))
            validate_write_paths(record["task_spec"]["write_path_patterns"])
        except (ValueError, KeyError, TypeError, OSError, WriteScopeError):
            continue
        branch = "lf/native-integration/" + task + "-run-" + str(source_id)
        remote = run("git", "ls-remote", "origin", "refs/heads/" + branch)
        if remote.strip():
            results.append({"status": "INTEGRATION_ALREADY_PUBLISHED",
                            "source_run_id": source_id, "task": task})
            continue
        if not _failed_for_scope(api, run, repo, failure):
            continue
        if allowed_task is not None and not allowed_task(task):
            continue
        run("gh", "workflow", "run", INTEGRATION, "--repo", repo, "--ref",
            "main", "-f", "source_run_id=" + str(source_id))
        scheduled.add(source_id)
        results.append({"status": "NATIVE_INTEGRATION_REPLAY_DISPATCHED",
                        "source_run_id": source_id, "failed_integration_run_id": failure["id"],
                        "task": task})
    return results


def recover_unstarted(head: str, run, api, repo: str, root: Path,
                      *, allowed_tasks: set[str], allowed_task=None) -> list[dict]:
    """R1: reconcile immutable PASS Worker runs missing a CP3.5 execution.

    Cancelled/skipped CP3.5 runs are not delivery receipts. This reads only
    trusted run history and registered tasks; never re-runs the Worker.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("R1_CP35_BASE_INVALID")
    workers = _listed(api, WORKER)
    integrations = _listed(api, INTEGRATION)
    outcomes = []
    for source in sorted(workers, key=lambda row: row.get("id", 0)):
        if not _trusted_worker(source, repo):
            continue
        match = (WORKER_TITLE.fullmatch(source["display_title"]) or
                 MANUAL_WORKER_TITLE.fullmatch(source["display_title"]))
        task = match.group(1)
        if task not in allowed_tasks:
            continue
        registration = storage_path("registrations_root", root=root) / (task + ".json")
        if registration.is_symlink() or not registration.is_file():
            raise ValueError("R1_CP35_REGISTRATION_MISSING")
        source_id = source["id"]
        branch = "lf/native-integration/" + task + "-run-" + str(source_id)
        remote = run("git", "ls-remote", "origin", "refs/heads/" + branch)
        if remote.strip():
            continue
        title = "CP3.5 " + source["display_title"]
        retry_title = "CP3.5 recovery native-run-" + str(source_id)
        matching = [row for row in integrations
                    if row.get("display_title") in (title, retry_title)
                    and (row.get("path") or "").split("@")[0] == INTEGRATION_PATH
                    and (row.get("repository") or {}).get("full_name") == repo]
        delivered = [row for row in matching
                     if row.get("status") in ("queued", "in_progress")
                     or (row.get("status") == "completed"
                         and row.get("conclusion") in ("success", "failure"))]
        if delivered:
            # A completed failure needs the existing typed T24 recovery, not
            # an unbounded generic retry. A concurrent in-flight run is left alone.
            if all(row.get("status") == "completed" for row in delivered) and any(
                    row.get("conclusion") == "failure" for row in delivered):
                outcomes.append({"status": "BLOCKED", "task": task,
                                 "reason": "R1_CP35_COMPLETED_FAILURE",
                                 "source_run_id": source_id})
            continue
        if allowed_task is not None and not allowed_task(task):
            continue
        run("gh", "workflow", "run", INTEGRATION, "--repo", repo,
            "--ref", "main", "-f", "source_run_id=" + str(source_id))
        outcomes.append({"status": "R1_CP35_REDISPATCHED",
                         "task": task, "source_run_id": source_id})
    return outcomes
