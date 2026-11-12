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


def merge_with_retry(number, head, payload):
    """GitHub may still report required checks as 'expected' a few seconds
    after they completed, and a merge PUT can lose its connection. Re-read the
    PR before every retry; never merge a different HEAD."""
    for attempt in range(CHECKS_LAG_RETRIES):
        try:
            return api("PUT", f"/pulls/{number}/merge", payload)
        except TrainError as exc:
            text = str(exc)
            lag = "HTTP 405" in text and "required status check" in text
            server = any(f"HTTP {c} " in text for c in TRANSIENT_HTTP) or text.startswith("NETWORK ")
            if not (lag or server) or attempt == CHECKS_LAG_RETRIES - 1:
                raise
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, OSError):
            if attempt == CHECKS_LAG_RETRIES - 1:
                raise TrainError("NETWORK PUT merge")
        current = api("GET", f"/pulls/{number}")
        if current.get("merged") and current.get("merge_commit_sha"):
            return {"merged": True, "sha": current["merge_commit_sha"]}
        if current["head"]["sha"] != head:
            raise TrainError("HEAD_CHANGED_DURING_MERGE_RETRY")
        print(json.dumps({"event": "merge_retry", "attempt": attempt + 1}), flush=True)
        time.sleep(CHECKS_LAG_SECONDS)
    raise TrainError("MERGE_RETRY_EXHAUSTED")


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
                and run.get("head_repository", {}).get("full_name") == os.environ["GITHUB_REPOSITORY"]):
            try:
                api("POST", f"/actions/runs/{run['id']}/approve", {}, expected=(200, 201, 204))
                print(json.dumps({"event": "approved_pending_run", "run": run["id"], "head": sha}), flush=True)
            except TrainError as exc:
                print(json.dumps({"event": "approve_pending_run_failed", "run": run["id"], "reason": str(exc)[:200]}), flush=True)


def ci_workflow_runs_for_head(sha):
    """Only an actual ci.yml run on the exact commit can suppress dispatch."""
    runs = []
    page = 1
    while True:
        result = api("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100&page={page}")
        batch = result["workflow_runs"]
        runs.extend(run for run in batch if run.get("head_sha") == sha
                    and run.get("event") in ("pull_request", "push", "workflow_dispatch")
                    and run.get("status") != "action_required")
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


def await_checks(number, sha, dispatched_heads=None):
    dispatched_heads = dispatched_heads if dispatched_heads is not None else set()
    start = time.monotonic()
    deadline = start + WAIT_SECONDS
    while time.monotonic() < deadline:
        pr = pr_data(number)
        check_pr(pr)
        if pr["head"]["sha"] != sha:
            return None  # changed: restart against new SHA
        # Bot pushes may create only an action_required run, which cannot supply
        # the six checks. After a bounded grace period, dispatch once per SHA.
        if (sha not in dispatched_heads
                and time.monotonic() - start >= CI_MISSING_GRACE_SECONDS
                and not ci_workflow_runs_for_head(sha)):
            dispatch_updated_head_ci(pr["head"]["ref"], sha)
            dispatched_heads.add(sha)
            print(json.dumps({"event": "ci_missing_fallback_dispatch", "head": sha}), flush=True)
        approve_pending_runs(sha)
        found = {name: value for name, value in checks_for_head(sha).items()
                 if name not in TRAIN_OWN_CHECKS}
        failed = [name for name in REQUIRED if name in found and found[name]["conclusion"] not in (None, "success")]
        if failed:
            raise TrainError("CHECK_FAILED " + json.dumps({name: found[name] for name in failed}))
        missing = [name for name in REQUIRED if name not in found or found[name]["status"] != "completed"]
        if not missing:
            # Any completed failing GitHub Actions check on this SHA is blocking.
            extra_bad = {name: value for name, value in found.items()
                         if name not in REQUIRED and value["status"] == "completed"
                         and value["conclusion"] not in ("success", "skipped", "neutral")}
            if extra_bad:
                raise TrainError("EXTRA_CHECK_FAILED " + json.dumps(extra_bad))
            return {name: found[name] for name in REQUIRED}
        print(json.dumps({"event": "waiting_checks", "head": sha, "missing": missing}), flush=True)
        time.sleep(POLL_SECONDS)
    raise TrainError("CHECK_WAIT_TIMEOUT")


def dispatch_updated_head_ci(branch, sha):
    """GITHUB_TOKEN update-branch suppresses push/PR CI; explicitly dispatch it."""
    api("POST", "/actions/workflows/ci.yml/dispatches",
        {"ref": branch}, expected=(204,))
    print(json.dumps({"event": "dispatch_ci_after_update", "branch": branch,
                      "head_sha": sha}), flush=True)


def run(number):
    dispatched_heads = set()
    prepared_heads = set()
    for attempt in range(MAX_RESTARTS + 1):
        pr = ready_if_labeled_draft(number, pr_data(number))
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
                    dispatch_updated_head_ci(updated["head"]["ref"], merged_head)
                    dispatched_heads.add(merged_head)
                continue
            # Already current and the derived view is unchanged: use this
            # validated HEAD without another push or a new Actions run.
        if compare["status"] not in ("ahead", "identical"):
            raise TrainError("BRANCH_NOT_MERGEABLE " + compare["status"])
        evidence = await_checks(number, initial_head, dispatched_heads)
        if evidence is None:
            continue
        latest = pr_data(number)
        check_pr(latest)
        if latest["head"]["sha"] != initial_head or main_sha() != base:
            print(json.dumps({"event": "sha_or_main_moved", "attempt": attempt + 1}), flush=True)
            continue
        if latest.get("mergeable") is False:
            raise TrainError("PR_NOT_MERGEABLE")
        try:
            merged = merge_with_retry(number, initial_head,
                                      {"sha": initial_head, "merge_method": "merge",
                                       "commit_title": f"Merge PR #{number} via sandbox-train"})
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
