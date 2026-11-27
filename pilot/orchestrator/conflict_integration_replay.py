"""T46.1: bounded, fail-closed replay of one authenticated native PASS via CP3.5."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from pilot.orchestrator.native_integration_replay import (
    _trusted_worker, WORKER_TITLE, REPLAY_TITLE, INTEGRATION_PATH,
)

BRANCH = re.compile(r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-([1-9][0-9]*)\Z")
INTEGRATION = "native-verified-integration.yml"
BOT = {"github-actions[bot]", "app/github-actions", "github-actions"}
HISTORY_LIMIT = 100
PAGE_LIMIT_ENV = "CP36_CP35_REPLAY_HISTORY_PAGE_LIMIT"
FAIL_LIMIT_ENV = "CP36_CP35_REPLAY_FAILURE_LIMIT"
PENDING = {"queued", "in_progress", "requested", "waiting", "pending"}


class ReplayBlocked(ValueError):
    """Bounded, public machine code only."""


def block(code: str):
    raise ReplayBlocked(code)


def _failure_limit() -> int:
    """Owner-configurable bound, deliberately small and fail-closed."""
    raw = os.environ.get(FAIL_LIMIT_ENV, "1")
    if not re.fullmatch(r"[1-9][0-9]{0,1}", raw):
        block("CONFLICT_RECOVERY_FAILURE_LIMIT_INVALID")
    value = int(raw)
    if value > 10:
        block("CONFLICT_RECOVERY_FAILURE_LIMIT_INVALID")
    return value


def _native_pass(api, repo: str, run_id: int, task: str) -> str:
    """Use precisely T24's native-run predicate and title regex, not a copy."""
    try:
        item = api("actions/runs/" + str(run_id))
        jobs = api("actions/runs/" + str(run_id) + "/jobs?per_page=100")
    except (OSError, ValueError, KeyError, TypeError):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    if not isinstance(item, dict) or not isinstance(jobs, dict):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    title = WORKER_TITLE.fullmatch(str(item.get("display_title") or ""))
    entries = jobs.get("jobs")
    if (item.get("id") != run_id or not _trusted_worker(item, repo)
            or title is None or title.group(1) != task
            or not isinstance(entries, list) or sum(
                1 for entry in entries if isinstance(entry, dict)
                and entry.get("name") == "native"
                and entry.get("conclusion") == "success") != 1):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    # GitHub's created>= filter excludes all workflow runs older than the
    # immutable original PASS. An unknown/invalid timestamp cannot be guessed.
    created = item.get("created_at")
    if not isinstance(created, str):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    try:
        parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _trusted_dispatch(item: object, repo: str, run_id: int) -> bool:
    """Canonical run-name and immutable origin for a CP3.5 replay."""
    if not isinstance(item, dict):
        return False
    title = REPLAY_TITLE.fullmatch(str(item.get("display_title") or ""))
    return (title is not None and int(title.group(1)) == run_id
            and item.get("event") == "workflow_dispatch"
            and item.get("head_branch") == "main"
            and (item.get("path") or "").split("@")[0] == INTEGRATION_PATH
            and (item.get("repository") or {}).get("full_name") == repo)


def _page_limit() -> int:
    raw = os.environ.get(PAGE_LIMIT_ENV, "10")
    if not isinstance(raw, str) or not re.fullmatch(r"[1-9][0-9]{0,1}", raw):
        block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
    limit = int(raw)
    if limit > 50:
        block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
    return limit


def _dispatch_history(api, repo: str, run_id: int, created_at: str) -> list[dict]:
    """Read a complete, filtered GitHub history, or fail closed before dispatch.

    REST pagination is 1-based. A previous failure on any page must count.
    Snapshot changes (count or duplicate IDs) and incomplete pages are unsafe.
    """
    limit = _page_limit()
    prefix = "actions/workflows/" + INTEGRATION + "/runs?"
    filters = {"per_page": str(HISTORY_LIMIT), "event": "workflow_dispatch",
               "branch": "main", "created": ">=" + created_at}
    seen: set[int] = set()
    selected = []
    total = None
    for page in range(1, limit + 1):
        query = urlencode({**filters, "page": str(page)})
        try:
            history = api(prefix + query)
        except (OSError, ValueError, KeyError, TypeError):
            block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
        records = history.get("workflow_runs") if isinstance(history, dict) else None
        count = history.get("total_count") if isinstance(history, dict) else None
        if (type(count) is not int or count < 0
                or not isinstance(records, list)
                or len(records) > HISTORY_LIMIT
                or (total is not None and total != count)):
            block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
        if total is None:
            total = count
            if total > limit * HISTORY_LIMIT:
                block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
        remaining = total - len(seen)
        if remaining < 0 or len(records) != min(HISTORY_LIMIT, remaining):
            block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
        for item in records:
            if not isinstance(item, dict):
                block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
            status, conclusion = item.get("status"), item.get("conclusion")
            if (type(item.get("id")) is not int or item["id"] <= 0
                    or item["id"] in seen
                    or not isinstance(status, str)
                    or status not in PENDING | {"completed"}
                    or (status == "completed"
                        and (not isinstance(conclusion, str)
                             or conclusion not in
                             {"success", "failure", "cancelled", "skipped",
                              "timed_out", "action_required", "neutral"}))
                    or not isinstance(item.get("display_title"), str)
                    or not isinstance(item.get("head_branch"), str)
                    or not isinstance(item.get("path"), str)
                    or not isinstance(item.get("repository"), dict)
                    or not isinstance(item["repository"].get("full_name"), str)):
                block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
            seen.add(item["id"])
            # A matching recovery title with falsified provenance is not
            # permission to omit an attempted recovery from the failure cap.
            if (REPLAY_TITLE.fullmatch(item["display_title"])
                    and not (item.get("event") == "workflow_dispatch"
                             and item["head_branch"] == "main"
                             and item["path"].split("@")[0] == INTEGRATION_PATH
                             and item["repository"]["full_name"] == repo)):
                block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")
            if _trusted_dispatch(item, repo, run_id):
                selected.append(item)
        if len(seen) == total:
            return selected
    block("CONFLICT_RECOVERY_DISPATCH_HISTORY_UNRESOLVED")


def recover(row: dict, run, api, repo: str, *, before_dispatch=None) -> dict:
    branch = row.get("branch")
    match = BRANCH.fullmatch(branch) if isinstance(branch, str) else None
    if not match:
        block("CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED")
    task, digits = match.groups()
    run_id = int(digits)
    created_at = _native_pass(api, repo, run_id, task)

    try:
        raw = run("gh", "pr", "list", "--repo", repo, "--state", "open",
                  "--limit", "100", "--json", "number,headRefName,author")
        candidates = json.loads(raw)
    except (OSError, ValueError, TypeError):
        block("CONFLICT_RECOVERY_OPEN_PRS_UNRESOLVED")
    if not isinstance(candidates, list) or len(candidates) >= 100:
        block("CONFLICT_RECOVERY_OPEN_PRS_UNRESOLVED")
    if any(isinstance(pr, dict) and pr.get("headRefName") == branch
           and (pr.get("author") or {}).get("login") in BOT
           for pr in candidates):
        return {"status": "CONFLICT_INTEGRATION_ALREADY_PUBLISHED",
                "source_run_id": run_id, "task": task}

    records = _dispatch_history(api, repo, run_id, created_at)
    # A trusted prior dispatch already executing is a single-flight guard.
    if any(item["status"] in PENDING for item in records):
        return {"status": "CONFLICT_INTEGRATION_DISPATCH_PENDING",
                "source_run_id": run_id, "task": task}

    completed = sorted((item for item in records if item["status"] == "completed"),
                       key=lambda item: item["id"], reverse=True)
    success_id = next((item["id"] for item in completed
                       if item["conclusion"] == "success"), 0)
    failed = [item for item in completed
              if item["id"] > success_id
              and item["conclusion"] in ("failure", "cancelled")]
    if len(failed) >= _failure_limit():
        return {"status": "BLOCKED",
                "reason": "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED",
                "code": "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED",
                "phase": "CONFLICT_RECOVERY",
                "step": INTEGRATION, "source_run_id": run_id,
                "failed_run_id": failed[0]["id"], "task": task}

    if before_dispatch is not None:
        before_dispatch()
    run("gh", "workflow", "run", INTEGRATION, "--repo", repo,
        "--ref", "main", "-f", "source_run_id=" + str(run_id))
    return {"status": "CONFLICT_INTEGRATION_REDISPATCHED",
            "source_run_id": run_id, "task": task}
