"""T46: recover a retired integration using the exact trusted CP3.5 dispatch.

No local second implementation of CP3.5 and no execution of bot branch code.
All GitHub interfaces are injected by CP3.6 for offline verification.
"""
from __future__ import annotations

import json
import re

BRANCH = re.compile(r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-([1-9][0-9]*)\\Z")
SHA = re.compile(r"[0-9a-f]{40}\\Z")
WORKER = ".github/workflows/worker-native.yml"
INTEGRATION = "native-verified-integration.yml"
INTEGRATION_PATH = ".github/workflows/" + INTEGRATION
BOT = {"github-actions[bot]", "app/github-actions", "github-actions"}


class ReplayBlocked(ValueError):
    """Only stable, public machine codes are accepted at the CP3.6 boundary."""


def block(code: str):
    raise ReplayBlocked(code)


def _native_pass(api, repo: str, run_id: int, task: str) -> None:
    try:
        item = api("actions/runs/" + str(run_id))
        jobs = api("actions/runs/" + str(run_id) + "/jobs?per_page=100")
    except (OSError, ValueError, KeyError, TypeError):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    if not isinstance(item, dict) or not isinstance(jobs, dict):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    title = str(item.get("display_title") or "")
    prefix = "lf-native-auto-lf/native-proposal/"
    alternatives = ("lf-native-route-retry-", "lf-native-infra-retry-")
    match = None
    for value in (prefix,) + alternatives:
        if title.startswith(value):
            match = re.fullmatch(re.escape(value) + r"([a-z][a-z0-9_-]{0,31})-[0-9a-f]{40}", title)
            break
    valid = (item.get("id") == run_id
             and item.get("status") == "completed"
             and item.get("conclusion") == "success"
             and item.get("run_attempt") == 1
             and item.get("event") in ("workflow_run", "workflow_dispatch")
             and item.get("head_branch") == "main"
             and (item.get("path") or "").split("@")[0] == WORKER
             and (item.get("repository") or {}).get("full_name") == repo
             and match is not None and match.group(1) == task)
    entries = jobs.get("jobs")
    valid = valid and isinstance(entries, list) and sum(
        1 for j in entries if isinstance(j, dict)
        and j.get("name") == "native"
        and j.get("conclusion") == "success") == 1
    if not valid:
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")


def recover(row: dict, run, api, repo: str) -> dict:
    branch = row.get("branch")
    match = BRANCH.fullmatch(branch) if isinstance(branch, str) else None
    if not match:
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    task, digits = match.groups()
    run_id = int(digits)
    _native_pass(api, repo, run_id, task)

    # A still-open integration for the same immutable PASS is already the
    # intended regeneration: do not create a second branch/PR.
    try:
        raw = run("gh", "pr", "list", "--repo", repo, "--state", "open",
                  "--limit", "100", "--json",
                  "number,headRefName,author")
        candidates = json.loads(raw)
    except (OSError, ValueError, TypeError):
        block("CONFLICT_RECOVERY_OPEN_PRS_UNRESOLVED")
    if not isinstance(candidates, list) or len(candidates) >= 100:
        block("CONFLICT_RECOVERY_OPEN_PRS_UNRESOLVED")
    if any(isinstance(p, dict) and p.get("headRefName") == branch
           and (p.get("author") or {}).get("login") in BOT
           for p in candidates):
        return {"status": "CONFLICT_INTEGRATION_ALREADY_PUBLISHED",
                "source_run_id": run_id, "task": task}

    # A dispatch still running must not be triggered twice across sweeps.
    try:
        history = api("actions/workflows/" + INTEGRATION + "/runs?per_page=100")
    except (OSError, ValueError, TypeError):
        block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
    records = history.get("workflow_runs") if isinstance(history, dict) else None
    if not isinstance(records, list) or len(records) > 100:
        block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
    if any(isinstance(item, dict)
           and item.get("event") == "workflow_dispatch"
           and item.get("display_title") == "CP3.5 recovery native-run-" + str(run_id)
           and item.get("status") in ("queued", "in_progress", "requested", "waiting", "pending")
           and item.get("head_branch") == "main"
           and (item.get("path") or "").split("@")[0] == INTEGRATION_PATH
           and (item.get("repository") or {}).get("full_name") == repo
           for item in records):
        return {"status": "CONFLICT_INTEGRATION_DISPATCH_PENDING",
                "source_run_id": run_id, "task": task}

    run("gh", "workflow", "run", INTEGRATION, "--repo", repo,
        "--ref", "main", "-f", "source_run_id=" + str(run_id))
    return {"status": "CONFLICT_INTEGRATION_REDISPATCHED",
            "source_run_id": run_id, "task": task}
