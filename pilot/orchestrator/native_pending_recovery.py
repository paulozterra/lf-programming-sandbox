"""R1: recover an unstarted native proposal HEAD after Actions pending replacement.

Runs under CP3.6's global serialization. No Worker call, model call, attempt
record, or proposal mutation takes place in this module. All candidate SHAs
are reattested using the existing trusted proposal guard.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Native history retains legacy direct imports from this trusted directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_v08"))

from pilot.config.project_config import storage_path
from pilot.orchestrator.request_lifecycle import RequestStateError
from pilot.worker_v08.native_proposal_push_guard import (
    validate_proposal_only, ProposalPushBlocked,
)
from pilot.worker_v08.native_run_history import _artifact_json, _recognized_run

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
AUTO = re.compile(
    r"lf-native-auto-lf/native-proposal/([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
MANUAL = re.compile(r"lf-native-([a-z][a-z0-9_-]{0,31})-a[123]-([0-9a-f]{40})\Z")
PENDING = re.compile(
    r"lf-native-pending-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
INFRA = re.compile(
    r"lf-native-infra-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
ROUTE = re.compile(
    r"lf-native-route-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")


def replay_decision(task: str, sha: str, rows: list[dict]) -> str:
    """Cancelled can be displaced; skipped means ineligible, never replay."""
    result = "REPLAY"
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("R1_WORKER_HISTORY_INVALID")
        title = str(item.get("display_title") or "")
        match = (AUTO.fullmatch(title) or PENDING.fullmatch(title)
                 or INFRA.fullmatch(title) or ROUTE.fullmatch(title)
                 or MANUAL.fullmatch(title))
        if match is None or match.groups() != (task, sha):
            continue
        status, conclusion = item.get("status"), item.get("conclusion")
        if status in ("queued", "in_progress", "pending", "waiting", "requested"):
            return "WAITING"
        if status != "completed":
            raise ValueError("R1_WORKER_HISTORY_STATUS_UNKNOWN")
        if conclusion in ("success", "failure"):
            return "DELIVERED"
        if conclusion == "skipped":
            result = "SKIPPED"  # Job condition false, not a concurrency loss.
        elif conclusion != "cancelled":
            raise ValueError("R1_WORKER_CONCLUSION_UNKNOWN")
    return result


def recover(head: str, run, api, repo: str, root: Path, *, allowed_task, format_decision=None) -> list[dict]:
    if not SHA.fullmatch(head):
        raise ValueError("R1_WORKER_BASE_INVALID")
    refs = run("git", "ls-remote", "--heads", "origin",
               "refs/heads/lf/native-proposal/*").splitlines()
    if len(refs) > 1000:
        raise ValueError("R1_WORKER_REFS_UNBOUNDED")
    # Filter by authoritative live ownership BEFORE downloading Worker history.
    # Branches without a plan, or with a completed plan, must not trigger
    # expensive history/artifact inspection. Validate every ref first.
    eligible = []
    outcomes = []
    for line in refs:
        fields = line.split()
        if len(fields) != 2 or not SHA.fullmatch(fields[0]):
            raise ValueError("R1_WORKER_REF_INVALID")
        sha, ref = fields
        match = re.fullmatch(r"refs/heads/lf/native-proposal/([a-z][a-z0-9_-]{0,31})", ref)
        if match is None:
            raise ValueError("R1_WORKER_REF_INVALID")
        task = match.group(1)
        try:
            if allowed_task(task):
                eligible.append((task, sha))
        except (ValueError, ProposalPushBlocked, OSError, KeyError) as exc:
            code = str(exc)
            if not re.fullmatch(r"(?:R1_[A-Z0-9_]+|REQUEST_STATE_UNRESOLVED)", code):
                code = "R1_WORKER_TASK_RECOVERY_FAILED"
            outcomes.append({"status": "BLOCKED", "task": task, "reason": code})
    if not eligible:
        return outcomes
    rows = []
    for page in range(1, 11):
        response = api(f"actions/workflows/worker-native.yml/runs?per_page=100&page={page}")
        current = response.get("workflow_runs")
        count = response.get("total_count")
        if (not isinstance(current, list) or type(count) is not int or
                count > 1000 or any(not isinstance(item, dict) for item in current)):
            raise ValueError("R1_WORKER_HISTORY_INCOMPLETE")
        rows.extend(current)
        if len(rows) >= count:
            break
    else:
        raise ValueError("R1_WORKER_HISTORY_INCOMPLETE")
    for task, sha in eligible:
        try:
            path = storage_path("registrations_root", root=root) / (task + ".json")
            if path.is_symlink() or not path.is_file():
                raise ValueError("R1_WORKER_REGISTRATION_MISSING")
            decision = replay_decision(task, sha, rows)
            if decision != "REPLAY":
                continue
            if format_decision is not None:
                state = format_decision(task, sha)
                if state != "CONTINUE":
                    outcomes.append({"status": state, "task": task, "proposal_sha": sha})
                    continue
                # A cancelled redispatch is not an unlimited retry token.
                if any(PENDING.fullmatch(str(x.get("display_title") or "")) and
                       PENDING.fullmatch(str(x.get("display_title") or "")).groups() == (task, sha)
                       for x in rows):
                    outcomes.append({"status": "FORMAT_PENDING_RETRY_EXHAUSTED", "task": task})
                    continue
            # The runner already serializes by task, but a separate in-flight run
            # for the task must be respected even if it references another SHA.
            if any(_recognized_run(item, task) and item.get("status") in
                   ("queued", "in_progress", "pending", "waiting", "requested")
                   for item in rows):
                continue
            run("git", "fetch", "--no-tags", "origin", sha)
            try:
                check = validate_proposal_only(
                    root, sha, main_sha=head, branch="lf/native-proposal/" + task,
                    allow_historical_base=True)
            except ProposalPushBlocked as exc:
                raise ValueError("R1_WORKER_PROPOSAL_UNTRUSTED") from exc
            if check.get("task") != task:
                raise ValueError("R1_WORKER_TASK_MISMATCH")
            # A previous admitted proof needs the full native admission algorithm
            # (including forgiven attempts). Never guess its next attempt number.
            # P1 loss is safe to recover with attempt=1.
            for item in rows:
                if not _recognized_run(item, task) or item.get("status") != "completed":
                    continue
                if type(item.get("id")) is not int:
                    raise ValueError("R1_WORKER_RUN_ID_INVALID")
                token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
                if not token:
                    raise ValueError("R1_WORKER_TOKEN_MISSING")
                # Reuse the sweep's artifact inventory snapshot; archive
                # verification remains the existing strict proof reader.
                from pilot.orchestrator import sweep_api_budget as budget
                proof = (_artifact_json(repo, token, item["id"], inventory_api=api)
                         if budget.current() is not None
                         else _artifact_json(repo, token, item["id"]))
                if proof is not None:
                    outcomes.append({"status": "BLOCKED", "task": task,
                                     "reason": "R1_WORKER_PRIOR_ATTEMPT_REQUIRES_REVIEW"})
                    break
            else:
                run("gh", "workflow", "run", "worker-native.yml", "--repo", repo,
                    "--ref", "main", "-f", "task=" + task,
                    "-f", "proposal_commit_sha=" + sha, "-f", "attempt=1",
                    "-f", "pending_retry=true")
                outcomes.append({"status": "R1_WORKER_PENDING_REDISPATCHED",
                                 "task": task, "proposal_sha": sha})
        except (ValueError, ProposalPushBlocked, OSError, KeyError) as exc:
            code = str(exc)
            if not re.fullmatch(r"(?:R1_[A-Z0-9_]+|REQUEST_STATE_UNRESOLVED)", code):
                code = "R1_WORKER_TASK_RECOVERY_FAILED"
            outcomes.append({"status": "BLOCKED", "task": task, "reason": code})
    return outcomes
