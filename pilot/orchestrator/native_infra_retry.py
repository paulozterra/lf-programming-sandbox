"""T21: one trusted-main redispatch of pre-admission native infrastructure failures.

No proposal branch is updated. The workflow_dispatch run records the exact
SHA in its GitHub run-name, so a subsequent serialized CP3.6 sweep observes
an existing retry and never submits the same SHA again.
"""
from __future__ import annotations

from pilot.orchestrator.request_lifecycle import RequestStateError

import re

from pilot.worker_v08.native_proposal_push_guard import (
    ProposalPushBlocked, validate_proposal_only,
)

SHA = re.compile(r"[0-9a-f]{40}\Z")
AUTO = re.compile(r"lf-native-auto-lf/native-proposal/([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
INFRA_STEP = "Install pinned shared Python acceptance runtime (T13)"
MAX = 100


def retry_native_infra(head, run, api, repo, control, *, allowed_task=None, format_decision=None):
    response = api("actions/workflows/worker-native.yml/runs?per_page=100")
    rows = response.get("workflow_runs")
    if (not isinstance(rows, list) or type(response.get("total_count")) is not int
            or len(rows) > MAX):
        return [{"status": "NATIVE_INFRA_RETRY_HISTORY_INCOMPLETE"}]
    # GitHub's run-name is a durable dispatch ledger: manual retry titles
    # include the exact proposal SHA. Check every run, not just failures.
    done = set()
    candidates = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("display_title") or "")
        manual = re.fullmatch(
            r"lf-native-infra-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})", title)
        if manual and item.get("event") == "workflow_dispatch":
            done.add((manual.group(1), manual.group(2)))
        match = AUTO.fullmatch(title)
        if (match and item.get("event") == "workflow_run"
                and item.get("status") == "completed"
                and item.get("conclusion") == "failure"
                and type(item.get("id")) is int):
            key = (match.group(1), match.group(2))
            candidates.setdefault(key, []).append(item)
    outcomes = []
    for (task, sha), originals in sorted(candidates.items()):
        try:
            live = allowed_task(task) if allowed_task is not None else True
        except RequestStateError:
            outcomes.append({"task": task, "status": "BLOCKED",
                             "reason": "REQUEST_STATE_UNRESOLVED"})
            continue
        if not live:
            outcomes.append({"task": task, "status": "REQUEST_CLOSED"})
            continue
        if (task, sha) in done or not SHA.fullmatch(sha):
            continue
        try:
            format_state = format_decision(task, sha) if format_decision is not None else "CONTINUE"
        except (ValueError, OSError, KeyError, TypeError):
            outcomes.append({"task": task, "status": "BLOCKED", "reason": "FORMAT_HISTORY_UNRESOLVED"})
            continue
        if format_state not in ("CONTINUE", "FORMAT_INFRA_RETRY"):
            outcomes.append({"task": task, "status": format_state, "proposal_sha": sha})
            continue
        # Only one initial failure, never a later Worker result for the same
        # proposal HEAD. Even a successful run supersedes the candidate.
        matching = [x for x in rows if isinstance(x, dict)
                    and x.get("display_title", "").endswith(sha)]
        latest = max(matching, key=lambda x: x.get("id", 0))
        original = max(originals, key=lambda x: x["id"])
        if latest.get("id") != original["id"]:
            continue
        jobs = api(f"actions/runs/{original['id']}/jobs?per_page=100")
        jobrows = jobs.get("jobs")
        if (not isinstance(jobrows, list) or len(jobrows) != 1
                or type(jobs.get("total_count")) is not int
                or jobs["total_count"] != 1):
            continue
        job = jobrows[0]
        steps = job.get("steps", [])
        if format_state != "FORMAT_INFRA_RETRY" and (job.get("name") != "native" or not isinstance(steps, list)
                or not any(s.get("name") == INFRA_STEP and s.get("conclusion") == "failure"
                           for s in steps if isinstance(s, dict))
                or any(s.get("name") == "Admit task and registered base (fail closed until Claude registers ex6)" and
                       s.get("conclusion") != "skipped" for s in steps if isinstance(s, dict))):
            continue
        branch = "lf/native-proposal/" + task
        remote = run("git", "ls-remote", "origin", "refs/heads/" + branch).split()
        if len(remote) != 2 or remote[0] != sha or remote[1] != "refs/heads/" + branch:
            continue
        # Verify SHA, branch, historical trusted base and registered task,
        # without executing any proposal code.
        run("git", "fetch", "--no-tags", "origin", sha)
        try:
            check = validate_proposal_only(control, sha, main_sha=head, branch=branch,
                                           allow_historical_base=True)
        except ProposalPushBlocked:
            continue
        if check["task"] != task:
            continue
        run("gh", "workflow", "run", "worker-native.yml", "--repo", repo,
            "--ref", "main", "-f", "task=" + task,
            "-f", "proposal_commit_sha=" + sha, "-f", "attempt=1",
            "-f", "infra_retry=true")
        outcomes.append({"status": "NATIVE_INFRA_RETRY_DISPATCHED",
                         "task": task, "proposal_sha": sha,
                         "source_run_id": original["id"]})
    return outcomes
