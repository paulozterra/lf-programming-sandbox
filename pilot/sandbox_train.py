#!/usr/bin/env python3
"""Merge Train P0: trusted main code, fail closed, GitHub REST only (stdlib)."""
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from sandbox_train_merge import update_branch_locally, BranchConflict
from native_registration_family import PREFIX, registration_family
from orchestrator.stale_exam import pending_retire_pr

REQUIRED = (
    "backend (Maven verify)",
    "frontend (lint, tipos, build)",
    "estándares (catálogo y checks)",
    "infra local (docker compose)",
    "Worker pilot (offline budget, policy, vendor integrity)",
    "native push policy (offline only)",
)
MAX_RESTARTS = 3
WAIT_SECONDS = 1500
POLL_SECONDS = 20
POST_PUSH_VISIBILITY_SECONDS = 60
CI_MISSING_GRACE_SECONDS = 60
# T52: an approved action_required run gets this long, counted from when the
# Train first saw it pending, to start before the single fallback dispatch.
CI_APPROVAL_GRACE_SECONDS = 180
# T52 (review H2): only runs of workflows whose checks the Train requires are
# approved; any other pull_request workflow stays waiting and cannot block.
APPROVABLE_WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/exam-rehearsal.yml")


class TrainError(Exception):
    pass


TRANSIENT_HTTP = (500, 502, 503, 504)
NETWORK_RETRIES = 4


def _api_once(method, path, payload, expected):
    token = os.environ["GH_TOKEN"]
    base = "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sandbox-merge-train-p0",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            raw = response.read()
            obj = json.loads(raw) if raw else {}
            if response.status not in expected:
                raise TrainError(f"Unexpected HTTP {response.status} for {path}")
            return obj
    except urllib.error.HTTPError as exc:
        message = exc.read(800).decode("utf-8", errors="replace")
        raise TrainError(f"HTTP {exc.code} {method} {path}: {message}") from exc


def api(method, path, payload=None, expected=(200,)):
    """GitHub REST with bounded retries for transient failures only.

    Network drops (RemoteDisconnected, resets, timeouts) and 5xx are retried
    with backoff. Merge PUTs are never blindly retried here: the caller
    re-reads PR state first (see merge_with_retry)."""
    retryable = method == "GET"
    for attempt in range(NETWORK_RETRIES):
        try:
            return _api_once(method, path, payload, expected)
        except TrainError as exc:
            code = exc.__cause__.code if isinstance(exc.__cause__, urllib.error.HTTPError) else None
            if not (retryable and code in TRANSIENT_HTTP) or attempt == NETWORK_RETRIES - 1:
                raise
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, OSError):
            if not retryable or attempt == NETWORK_RETRIES - 1:
                raise TrainError(f"NETWORK {method} {path}")
        print(json.dumps({"event": "api_retry", "method": method, "path": path, "attempt": attempt + 1}), flush=True)
        time.sleep(3 * (2 ** attempt))
    raise TrainError(f"NETWORK {method} {path}")


CHECKS_LAG_RETRIES = 12
CHECKS_LAG_SECONDS = 10
# A second run of a required check on the same HEAD (e.g. the pull_request ci
# next to a dispatched ci) can still be running when the merge is attempted.
# GitHub then answers 405 "... is in progress". That is real work, not lag:
# wait for it with its own, longer budget instead of failing after ~2 min.
IN_PROGRESS_WAIT_SECONDS = 1200
IN_PROGRESS_POLL_SECONDS = 20


def open_pulls_for_retirement():
    rows, seen = [], set()
    for page in range(1, 11):
        batch = api("GET", f"/pulls?state=open&per_page=100&page={page}")
        if not isinstance(batch, list) or len(batch) > 100:
            raise TrainError("RETIRE_PR_LIST_INVALID")
        for row in batch:
            if not isinstance(row, dict):
                raise TrainError("RETIRE_PR_LIST_INVALID")
            number = row.get("number")
            if type(number) is not int or number <= 0 or number in seen:
                raise TrainError("RETIRE_PR_LIST_INVALID")
            seen.add(number)
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise TrainError("RETIRE_PR_PAGINATION_LIMIT")


def guard_pending_retirement(branch):
    if not isinstance(branch, str) or not branch:
        raise TrainError("POLICY_C_REGISTRATION_IDENTITY_INVALID")
    if not branch.startswith(PREFIX):
        return
    family, task = registration_family(branch)
    if family == "auxiliary":
        return
    if family != "registration":
        raise TrainError("POLICY_C_REGISTRATION_IDENTITY_INVALID")
    try:
        retire = pending_retire_pr(open_pulls_for_retirement, task)
    except Exception as exc:
        raise TrainError(f"POLICY_C_RETIRO_API_ERROR task={task}") from exc
    if retire is not None:
        raise TrainError(f"POLICY_C_RETIRO_PENDIENTE task={task} retire_pr=#{retire}")


def merge_with_retry(number, head, payload, *, branch, clock=None, sleep=None, lifecycle_guard=None):
    """GitHub may still report required checks as 'expected' a few seconds
    after they completed, a required check may still be running on the same
    HEAD, and a merge PUT can lose its connection. Re-read the PR before every
    retry; never merge a different HEAD."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    lag_attempts = 0
    in_progress_deadline = None
    while True:
        guard_pending_retirement(branch)
        if lifecycle_guard is not None:
            lifecycle_guard()
        try:
            return api("PUT", f"/pulls/{number}/merge", payload)
        except TrainError as exc:
            text = str(exc)
            lowered = text.lower()
            # GitHub capitalises "Required status check ..."; match case-insensitively.
            required = "HTTP 405" in text and "required status check" in lowered
            running = required and "in progress" in lowered
            server = any(f"HTTP {c} " in text for c in TRANSIENT_HTTP) or text.startswith("NETWORK ")
            if running:
                if in_progress_deadline is None:
                    in_progress_deadline = clock() + IN_PROGRESS_WAIT_SECONDS
                if clock() >= in_progress_deadline:
                    raise TrainError("REQUIRED_CHECK_STILL_IN_PROGRESS")
                delay = IN_PROGRESS_POLL_SECONDS
            elif required or server:
                lag_attempts += 1
                if lag_attempts >= CHECKS_LAG_RETRIES:
                    raise
                delay = CHECKS_LAG_SECONDS
            else:
                raise
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, OSError):
            lag_attempts += 1
            if lag_attempts >= CHECKS_LAG_RETRIES:
                raise TrainError("NETWORK PUT merge")
            delay = CHECKS_LAG_SECONDS
        current = api("GET", f"/pulls/{number}")
        if current.get("merged") and current.get("merge_commit_sha"):
            return {"merged": True, "sha": current["merge_commit_sha"]}
        if current["head"]["sha"] != head:
            raise TrainError("HEAD_CHANGED_DURING_MERGE_RETRY")
        print(json.dumps({"event": "merge_retry", "lag_attempts": lag_attempts,
                          "waiting_in_progress": in_progress_deadline is not None}), flush=True)
        sleep(delay)


def graphql(query: str, variables: dict) -> dict:
    """GitHub GraphQL with the same workflow token as REST."""
    token = os.environ["GH_TOKEN"]
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request("https://api.github.com/graphql", data=body, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sandbox-merge-train-p0",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            if response.status != 200:
                raise TrainError("GRAPHQL_HTTP_" + str(response.status))
            result = json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
        raise TrainError("GRAPHQL_REQUEST_FAILED") from exc
    if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("data"), dict):
        raise TrainError("GRAPHQL_RESPONSE_INVALID")
    return result["data"]


def pr_data(number):
    return api("GET", f"/pulls/{number}")


def main_sha():
    return api("GET", "/git/ref/heads/main")["object"]["sha"]


def check_pr(pr):
    if pr["state"] != "open" or pr["draft"]:
        raise TrainError("PR_CLOSED_OR_DRAFT")
    if pr["base"]["ref"] != "main":
        raise TrainError("BASE_NOT_MAIN")
    if pr["head"]["repo"]["full_name"] != os.environ["GITHUB_REPOSITORY"]:
        raise TrainError("FORK_REJECTED")
    if pr["head"]["ref"] == "main":
        raise TrainError("HEAD_IS_MAIN")
    if "ready-to-merge" not in {x["name"] for x in pr["labels"]}:
        raise TrainError("LABEL_MISSING")


def ready_if_labeled_draft(number, pr):
    """Transition only an eligible same-repo labeled draft; never bypass policy."""
    if not pr["draft"]:
        return pr
    # Reject closed, forked or unlabeled drafts BEFORE invoking GraphQL.
    if pr["state"] != "open":
        raise TrainError("PR_CLOSED_OR_DRAFT")
    if pr["head"]["repo"]["full_name"] != os.environ["GITHUB_REPOSITORY"]:
        raise TrainError("FORK_REJECTED")
    if "ready-to-merge" not in {x["name"] for x in pr["labels"]}:
        raise TrainError("PR_CLOSED_OR_DRAFT")
    if pr["base"]["ref"] != "main" or pr["head"]["ref"] == "main":
        check_pr(pr)  # fail closed; draft never receives a merge exemption
    node_id = pr.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise TrainError("DRAFT_READY_FAILED")
    mutation = ("mutation MarkReady($id: ID!) { "
                "markPullRequestReadyForReview(input: {pullRequestId: $id}) "
                "{ pullRequest { id isDraft } } }")
    try:
        result = graphql(mutation, {"id": node_id})
        changed = result["markPullRequestReadyForReview"]["pullRequest"]
        if changed.get("id") != node_id or changed.get("isDraft") is not False:
            raise ValueError("mutation did not make PR ready")
        updated = pr_data(number)
        if updated.get("draft") is not False:
            raise ValueError("REST PR still draft")
        check_pr(updated)
        return updated
    except (TrainError, ValueError, KeyError, TypeError) as exc:
        # Absolutely no continuation after failed/ambiguous transition.
        raise TrainError("DRAFT_READY_FAILED") from exc


def checks_for_head(sha):
    found = {}
    page = 1
    while True:
        result = api("GET", f"/commits/{sha}/check-runs?per_page=100&page={page}")
        runs = result["check_runs"]
        for run in runs:
            # Only GitHub Actions checks, never stale SHA or foreign app conclusions.
            if run["head_sha"] != sha or run["app"]["slug"] != "github-actions":
                continue
            name = run["name"]
            if name not in found or run["id"] > found[name]["id"]:
                found[name] = {"id": run["id"], "status": run["status"], "conclusion": run["conclusion"]}
        if len(runs) < 100:
            break
        page += 1
        if page > 10:
            raise TrainError("CHECK_PAGINATION_LIMIT")
    return found


TRAIN_OWN_CHECKS = {"merge"}  # this workflow's own job; earlier failed Train runs must not block


def approve_pending_runs(sha):
    """Train-pushed commits are authored by github-actions[bot]; in a public
    repo their pull_request runs wait in 'action_required' and leave the
    required checks as 'expected'. The labeled PR is already owner-approved
    (same-repo, non-fork, checked by check_pr), so approve those runs."""
    try:
        result = api("GET", f"/actions/runs?head_sha={sha}&status=action_required&per_page=100")
    except Exception as exc:  # best effort: never block the Train on this helper
        print(json.dumps({"event": "approve_pending_list_failed", "reason": str(exc)[:200]}), flush=True)
        return
    for run in result.get("workflow_runs", []):
        if (run.get("head_sha") == sha and run.get("event") == "pull_request"
                and (run.get("path") or "").split("@")[0] in APPROVABLE_WORKFLOWS
                and run.get("head_repository", {}).get("full_name") == os.environ["GITHUB_REPOSITORY"]):
            try:
                api("POST", f"/actions/runs/{run['id']}/approve", {}, expected=(200, 201, 204))
                print(json.dumps({"event": "approved_pending_run", "run": run["id"], "head": sha}), flush=True)
            except TrainError as exc:
                print(json.dumps({"event": "approve_pending_run_failed", "run": run["id"], "reason": str(exc)[:200]}), flush=True)


# T40 capa 1: a PR that registers a lot or changes an exam must also carry a
# successful exam rehearsal (reference through the real Worker).
REHEARSAL_CHECK = "rehearse"
REHEARSAL_PATHS = re.compile(
    r"pilot/(?:worker_v08/native_tasks/[a-z][a-z0-9_-]{0,31}\.json"
    r"|holdouts/[a-z][a-z0-9_-]{0,31}\.(?:oracle|reference)\.json\.age)\Z")


def needs_rehearsal(number):
    page, names = 1, []
    while True:
        batch = api("GET", f"/pulls/{number}/files?per_page=100&page={page}")
        names.extend(f.get("filename", "") for f in batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 30:
            raise TrainError("PR_FILES_PAGINATION_LIMIT")
    return any(REHEARSAL_PATHS.fullmatch(n) for n in names)


def rehearsal_runs_for_head(sha):
    result = api("GET", f"/actions/workflows/exam-rehearsal.yml/runs?head_sha={sha}&per_page=100")
    return [r for r in result["workflow_runs"] if r.get("head_sha") == sha
            and r.get("status") != "action_required"]


def dispatch_rehearsal(branch, sha):
    api("POST", "/actions/workflows/exam-rehearsal.yml/dispatches",
        {"ref": branch, "inputs": {"task": ""}}, expected=(204,))
    print(json.dumps({"event": "dispatch_exam_rehearsal", "branch": branch,
                      "head_sha": sha}), flush=True)


def ci_workflow_runs_for_head(sha, pending_approval=False):
    """Exact-commit ci.yml runs.

    By default, only runs that can supply checks (never action_required).
    With pending_approval=True, only same-repo pull_request runs waiting in
    action_required: approvable, so they suppress the fallback dispatch (T52).
    """
    runs = []
    page = 1
    while True:
        result = api("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100&page={page}")
        batch = result["workflow_runs"]
        for run in batch:
            if run.get("head_sha") != sha:
                continue
            waiting = run.get("status") == "action_required"
            if pending_approval:
                if (waiting and run.get("event") == "pull_request"
                        and run.get("head_repository", {}).get("full_name")
                        == os.environ["GITHUB_REPOSITORY"]):
                    runs.append(run)
            elif (not waiting and run.get("event")
                  in ("pull_request", "push", "workflow_dispatch")):
                runs.append(run)
        if len(batch) < 100:
            break
        page += 1
        if page > 10:
            raise TrainError("CI_RUN_PAGINATION_LIMIT")
    return runs


def wait_for_pushed_head(number, merged_head):
    """GitHub PR REST metadata can lag a successful bot push."""
    deadline = time.monotonic() + POST_PUSH_VISIBILITY_SECONDS
    while True:
        updated = pr_data(number)
        check_pr(updated)
        if updated["head"]["sha"] == merged_head:
            return updated
        if time.monotonic() >= deadline:
            raise TrainError("POST_PUSH_HEAD_VISIBILITY_TIMEOUT")
        print(json.dumps({"event": "waiting_post_push_pr_head", "expected": merged_head,
                          "observed": updated["head"]["sha"]}), flush=True)
        time.sleep(5)


# A completed successful CI can leave an individual check stuck in GitHub.
# Never synthesize a successful check: ask Actions to rerun the exact job.
CHECK_RECOVERY_GRACE_SECONDS = 180


def recover_inconsistent_ci_job(sha, missing, found, recovery_attempts):
    """Return an explicit outcome; only REQUESTED consumes the recovery budget."""
    key = ("check_recovery", sha)
    if key in recovery_attempts:
        return "RECOVERY_SKIPPED:BUDGET_USED"
    if len(missing) != 1:
        return "RECOVERY_SKIPPED:MULTIPLE_CHECKS"
    if missing[0] not in REQUIRED:
        return "RECOVERY_SKIPPED:NOT_CI_CHECK"
    name = missing[0]
    runs = ci_workflow_runs_for_head(sha)
    if ci_workflow_runs_for_head(sha, pending_approval=True):
        return "RECOVERY_SKIPPED:CI_PENDING_APPROVAL"
    if not runs:
        return "RECOVERY_SKIPPED:CI_MISSING"
    if any(r.get("head_sha") != sha for r in runs):
        return "RECOVERY_SKIPPED:CI_HEAD_MISMATCH"
    if any(r.get("status") != "completed" for r in runs):
        return "RECOVERY_SKIPPED:CI_RUNNING"
    latest = max(runs, key=lambda r: (r["id"], r.get("run_attempt", 1)))
    if latest.get("head_repository", {}).get("full_name") != os.environ["GITHUB_REPOSITORY"]:
        return "RECOVERY_SKIPPED:CI_FOREIGN_REPO"
    if latest.get("conclusion") != "success":
        return "RECOVERY_SKIPPED:CI_NOT_SUCCESS"
    jobs = api("GET", f"/actions/runs/{latest['id']}/jobs?filter=latest&per_page=100")
    rows = jobs.get("jobs", [])
    if jobs.get("total_count") != len(rows) or len(rows) >= 100:
        return "RECOVERY_SKIPPED:JOBS_INCOMPLETE"
    matches = [j for j in rows if j.get("name") == name]
    if len(matches) != 1:
        return "RECOVERY_SKIPPED:JOB_NOT_UNIQUE"
    job = matches[0]
    check = found.get(name)
    if (job.get("head_sha") != sha or job.get("run_id") != latest["id"] or
            job.get("conclusion") != "success" or
            job.get("status") not in ("completed", "in_progress") or
            not isinstance(job.get("id"), int)):
        return "RECOVERY_SKIPPED:JOB_EVIDENCE_INVALID"
    # Fail closed when the check itself is absent: the ID link is mandatory.
    if check is None:
        return "RECOVERY_SKIPPED:CHECK_ABSENT"
    if (check.get("conclusion") not in (None, "success") or
            check.get("status") == "completed" or
            not (job.get("check_run_url") or "").endswith("/" + str(check["id"]))):
        return "RECOVERY_SKIPPED:CHECK_EVIDENCE_INVALID"
    # Consume budget before POST: an ambiguous response must not cause another mutation.
    recovery_attempts.add(key)
    print(json.dumps({"event": "ci_check_recovery_requested", "head": sha,
                      "run": latest["id"], "job": job["id"], "check": name,
                      "job_status": job["status"], "observed_check": check}), flush=True)
    try:
        api("POST", f"/actions/jobs/{job['id']}/rerun", {}, expected=(201, 202, 204))
    except TrainError as exc:
        raise TrainError("CHECK_RECOVERY_POST_FAILED " + json.dumps(
            {"head": sha, "job": job["id"], "check": name})) from exc
    return "RECOVERY_REQUESTED"


def await_checks(number, sha, dispatched_heads=None, *, lifecycle_guard=None):
    dispatched_heads = dispatched_heads if dispatched_heads is not None else set()
    required = REQUIRED + ((REHEARSAL_CHECK,) if needs_rehearsal(number) else ())
    start = time.monotonic()
    deadline = start + WAIT_SECONDS
    pending_since = None  # first time an approvable CI run was seen (review H1)
    inconsistent_since = None
    last_missing = None
    recovery_reason = None
    logged_reasons = set()
    found = {}
    while time.monotonic() < deadline:
        pr = pr_data(number)
        check_pr(pr)
        if pr["head"]["sha"] != sha:
            return None  # changed: restart against new SHA
        # T52: approve first. A bot push may create an action_required run; once
        # approved it supplies the checks, so it must not trigger a second CI.
        if lifecycle_guard is not None:
            lifecycle_guard(number, pr)
        approve_pending_runs(sha)
        elapsed = time.monotonic() - start
        if (sha not in dispatched_heads and elapsed >= CI_MISSING_GRACE_SECONDS
                and not ci_workflow_runs_for_head(sha)):
            # Dispatch once per SHA only if nothing is usable and nothing is
            # approvable, or an approved run never started within its grace.
            pending = ci_workflow_runs_for_head(sha, pending_approval=True)
            now = time.monotonic()
            if pending and pending_since is None:
                pending_since = now
            if not pending or now - pending_since >= CI_APPROVAL_GRACE_SECONDS:
                if lifecycle_guard is not None:
                    lifecycle_guard(number, pr)
                dispatch_updated_head_ci(pr["head"]["ref"], sha)
                dispatched_heads.add(sha)
                print(json.dumps({"event": "ci_missing_fallback_dispatch", "head": sha,
                                  "pending_approval": [r.get("id") for r in pending]}),
                      flush=True)
            else:
                print(json.dumps({"event": "ci_pending_approval_awaited", "head": sha,
                                  "runs": [r.get("id") for r in pending]}), flush=True)
        if (REHEARSAL_CHECK in required and ("rehearsal", sha) not in dispatched_heads
                and time.monotonic() - start >= CI_MISSING_GRACE_SECONDS
                and not rehearsal_runs_for_head(sha)):
            if lifecycle_guard is not None:
                lifecycle_guard(number, pr)
            dispatch_rehearsal(pr["head"]["ref"], sha)
            dispatched_heads.add(("rehearsal", sha))
        found = {name: value for name, value in checks_for_head(sha).items()
                 if name not in TRAIN_OWN_CHECKS}
        failed = [name for name in required if name in found and found[name]["conclusion"] not in (None, "success")]
        if failed:
            raise TrainError("CHECK_FAILED " + json.dumps({name: found[name] for name in failed}))
        missing = [name for name in required if name not in found or
                   found[name]["status"] != "completed" or found[name]["conclusion"] != "success"]
        if not missing:
            # Any completed failing GitHub Actions check on this SHA is blocking.
            extra_bad = {name: value for name, value in found.items()
                         if name not in required and value["status"] == "completed"
                         and value["conclusion"] not in ("success", "skipped", "neutral")}
            if extra_bad:
                raise TrainError("EXTRA_CHECK_FAILED " + json.dumps(extra_bad))
            return {name: found[name] for name in required}
        if missing != last_missing:
            inconsistent_since = time.monotonic()
            last_missing = missing
        if time.monotonic() - inconsistent_since < CHECK_RECOVERY_GRACE_SECONDS:
            recovery_reason = "RECOVERY_SKIPPED:GRACE_NOT_MET"
        elif len(missing) != 1:
            recovery_reason = "RECOVERY_SKIPPED:MULTIPLE_CHECKS"
        elif missing[0] not in REQUIRED:
            recovery_reason = "RECOVERY_SKIPPED:NOT_CI_CHECK"
        elif any(v["status"] == "completed" and v["conclusion"] not in
                 ("success", "skipped", "neutral") for n, v in found.items()
                 if n not in missing):
            recovery_reason = "RECOVERY_SKIPPED:EXTRA_CHECK_FAILED"
        else:
            # Re-read PR authorization and exact HEAD before recovery.
            current = pr_data(number)
            check_pr(current)
            if current["head"]["sha"] != sha:
                return None
            recovery_reason = recover_inconsistent_ci_job(sha, missing, found, dispatched_heads)
        if recovery_reason.startswith("RECOVERY_SKIPPED:") and recovery_reason not in logged_reasons:
            logged_reasons.add(recovery_reason)
            print(json.dumps({"event": "ci_check_recovery_skipped", "head": sha,
                              "missing": missing, "reason": recovery_reason}), flush=True)
        print(json.dumps({"event": "waiting_checks", "head": sha, "missing": missing,
                          "observed": {name: found.get(name) for name in missing},
                          "recovery_attempted": ("check_recovery", sha) in dispatched_heads}), flush=True)
        time.sleep(POLL_SECONDS)
    if ("check_recovery", sha) in dispatched_heads:
        raise TrainError("CHECK_RECOVERY_TIMEOUT " + json.dumps({"head": sha, "missing": last_missing}))
    detail = {"head": sha, "missing": last_missing, "reason": recovery_reason}
    # A successful conclusion with a nonterminal status is contradictory.
    # Ordinary slow/missing CI must retain CHECK_WAIT_TIMEOUT.
    contradictory = any(n in REQUIRED and found.get(n, {}).get("conclusion") == "success"
                        and found[n]["status"] != "completed" for n in (last_missing or []))
    if contradictory:
        raise TrainError("CHECK_INCONSISTENT_UNRECOVERED " + json.dumps(detail))
    print(json.dumps({"event": "ci_check_wait_timeout", **detail}), flush=True)
    raise TrainError("CHECK_WAIT_TIMEOUT")


def dispatch_updated_head_ci(branch, sha):
    """GITHUB_TOKEN update-branch suppresses push/PR CI; explicitly dispatch it."""
    api("POST", "/actions/workflows/ci.yml/dispatches",
        {"ref": branch}, expected=(204,))
    print(json.dumps({"event": "dispatch_ci_after_update", "branch": branch,
                      "head_sha": sha}), flush=True)


def guard_request_lifecycle(number, pr, *, files=None):
    from pathlib import Path
    from orchestrator.request_lifecycle import (
        require_pr_open, RequestStateError, CONTROL_PATH, read_control,
        validate_control_transition, verify_owner_transition, verify_drain, SUSPENDED,
    )
    reader = lambda route: api("GET", "/" + route)
    try:
        if files is None:
            files = []
            for page in range(1, 11):
                rows = api("GET", f"/pulls/{number}/files?per_page=100&page={page}")
                if not isinstance(rows, list):
                    raise RequestStateError("REQUEST_STATE_UNRESOLVED")
                files.extend(rows)
                if len(rows) < 100:
                    break
            else:
                raise RequestStateError("REQUEST_STATE_UNRESOLVED")
        if len(files) != pr.get("changed_files"):
            raise RequestStateError("REQUEST_STATE_UNRESOLVED")
        paths = []
        for row in files:
            if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
                raise RequestStateError("REQUEST_STATE_UNRESOLVED")
            paths.append(row["filename"])
            if row.get("previous_filename"):
                paths.append(row["previous_filename"])
        require_pr_open(pr["head"]["ref"], paths, reader, root=Path(__file__).resolve().parents[1])
        if CONTROL_PATH in paths:
            previous = read_control(reader)
            current = read_control(reader, pr["head"]["sha"])
            slug = validate_control_transition(previous, current, number)
            verify_owner_transition(reader, pr, slug,
                                    previous.get(slug, {}).get("state", "ACTIVE"),
                                    current[slug]["state"])
            if current[slug]["state"] == SUSPENDED:
                run_id = os.environ.get("GITHUB_RUN_ID", "")
                verify_drain(reader, slug, previous[slug],
                             current_train_id=int(run_id) if run_id.isdecimal() else None)
            if any(path != CONTROL_PATH and path != "standards/CAMBIOS.md"
                   and not re.fullmatch(r"standards/changes/CHG-[0-9]{4,}[.]json", path)
                   for path in paths):
                raise RequestStateError("REQUEST_STATE_UNRESOLVED")
    except RequestStateError as exc:
        raise TrainError(str(exc)) from exc


def guard_registry_merge(pr):
    """An owner label never substitutes for the global ledger's historical proof."""
    if not pr["head"]["ref"].startswith("lf/implemented-registry/"):
        return
    from pilot.auto_integrate import GitHub, eligible_pr, pr_files, verify_generated_content, REPOSITORY, PolicyBlocked
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if local != main_sha():
        raise TrainError("REGISTRY_MAIN_DRIFT")
    reader = GitHub(os.environ["GH_TOKEN"], REPOSITORY)
    try:
        paths = pr_files(reader, pr["number"])
        kind = eligible_pr(pr, paths, api=reader)
        if kind != "implemented-registry":
            raise TrainError("REGISTRY_SCOPE_INVALID")
        verify_generated_content(reader, pr, paths, kind)
    except PolicyBlocked as exc:
        raise TrainError(str(exc)) from exc


def run(number):
    dispatched_heads = set()
    prepared_heads = set()
    for attempt in range(MAX_RESTARTS + 1):
        candidate = pr_data(number)
        guard_request_lifecycle(number, candidate)
        pr = ready_if_labeled_draft(number, candidate)
        check_pr(pr)
        initial_head = pr["head"]["sha"]
        base = main_sha()
        compare = api("GET", f"/compare/{base}...{initial_head}")
        if initial_head not in prepared_heads and (
                compare["behind_by"] > 0 or compare["status"] in ("ahead", "identical")):
            print(json.dumps({"event": "local_merge_and_render", "pr": number, "head": initial_head, "main": base}), flush=True)
            try:
                merged_head = update_branch_locally(
                    pr["head"]["ref"], initial_head, base,
                    os.environ["GH_TOKEN"], os.environ["GITHUB_REPOSITORY"])
            except BranchConflict as exc:
                if str(exc) in ("MAIN_MOVED_RETRY", "HEAD_MOVED_RETRY"):
                    print(json.dumps({"event": "ref_moved_retry", "reason": str(exc)}), flush=True)
                    continue
                raise TrainError(str(exc)) from exc
            prepared_heads.add(merged_head)
            if merged_head != initial_head:
                # A GitHub-token push does not schedule pull_request/push workflows.
                # Verify propagated SHA, then dispatch checks for the new HEAD.
                updated = wait_for_pushed_head(number, merged_head)
                if merged_head not in dispatched_heads:
                    guard_request_lifecycle(number, updated)
                    dispatch_updated_head_ci(updated["head"]["ref"], merged_head)
                    dispatched_heads.add(merged_head)
                continue
            # Already current and the derived view is unchanged: use this
            # validated HEAD without another push or a new Actions run.
        if compare["status"] not in ("ahead", "identical"):
            raise TrainError("BRANCH_NOT_MERGEABLE " + compare["status"])
        guard_request_lifecycle(number, pr)
        evidence = await_checks(number, initial_head, dispatched_heads,
                                lifecycle_guard=guard_request_lifecycle)
        if evidence is None:
            continue
        latest = pr_data(number)
        check_pr(latest)
        if latest["head"]["sha"] != initial_head or main_sha() != base:
            print(json.dumps({"event": "sha_or_main_moved", "attempt": attempt + 1}), flush=True)
            continue
        if latest.get("mergeable") is False:
            raise TrainError("PR_NOT_MERGEABLE")
        # Compare is pinned to exact main and PR HEAD. A truncated file list
        # cannot authorize a deletion. The trusted guard never runs PR code.
        from pilot.orchestrator.plan_retirement import (
            validate_train_retirement, RetirementBlocked,
        )
        try:
            files = compare.get("files")
            if not isinstance(files, list) or len(files) >= 300:
                raise RetirementBlocked("CHAIN_HISTORY_INCOMPLETE")
            validate_train_retirement(lambda route: api("GET", "/" + route),
                                      base, initial_head, files)
        except RetirementBlocked as exc:
            raise TrainError(str(exc)) from exc
        def before_merge():
            if main_sha() != base:
                raise TrainError("MAIN_MOVED_BEFORE_MERGE_RETRY")
            guard_request_lifecycle(number, latest)
            guard_registry_merge(latest)
        try:
            merged = merge_with_retry(number, initial_head,
                                      {"sha": initial_head, "merge_method": "merge",
                                       "commit_title": f"Merge PR #{number} via sandbox-train"},
                                      branch=latest["head"]["ref"],
                                      lifecycle_guard=before_merge)
        except TrainError as exc:
            # Main may have moved between last read and merge; restart safely.
            if main_sha() != base or pr_data(number)["head"]["sha"] != initial_head:
                print(json.dumps({"event": "merge_race_restart", "reason": str(exc)[:250]}), flush=True)
                continue
            raise
        if not merged.get("merged"):
            raise TrainError("MERGE_NOT_CONFIRMED")
        merge_sha = merged["sha"]
        commit = api("GET", f"/commits/{merge_sha}")
        if len(commit["parents"]) != 2:
            raise TrainError("MERGE_COMMIT_PARENT_COUNT_INVALID")
        receipt = {"event": "MERGED", "pr": number, "head_sha": initial_head,
                   "main_before": base, "merge_sha": merge_sha,
                   "merge_method": "merge", "checks": evidence}
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True), flush=True)
        with open(os.environ.get("TRAIN_RECEIPT", "sandbox-train-receipt.json"), "w", encoding="utf-8") as file:
            json.dump(receipt, file, ensure_ascii=False, indent=2, sort_keys=True)
        return
    raise TrainError("RESTART_LIMIT_EXCEEDED")


def main():
    raw = os.environ.get("TRAIN_PR", "")
    if not re.fullmatch(r"[1-9][0-9]{0,7}", raw):
        raise TrainError("INVALID_PR_NUMBER")
    run(int(raw))


if __name__ == "__main__":
    try:
        main()
    except (TrainError, KeyError, urllib.error.URLError) as exc:
        print("TRAIN_BLOCKED " + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
