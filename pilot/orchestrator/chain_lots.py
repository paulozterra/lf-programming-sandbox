#!/usr/bin/env python3
"""CP3.6 trusted Train/native-run event consumer.

Works from clean trusted main, never from proposal-branch code. A verified
integration merge releases successors only via preparation draft PRs; owner
alone labels and the Train alone merges. Three spent failed attempts produce
an immediate BLOCKED receipt plus a governed draft state PR (not a direct main
write). Missing manifests, evidence and encrypted holdouts fail closed.
"""
from __future__ import annotations

# Direct-script entrypoint: resolve the trusted repository root from this file,
# not from the caller's working directory or PYTHONPATH.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import argparse
from datetime import datetime, timezone
import time
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from contextlib import nullcontext
import pilot.orchestrator.sweep_api_budget as budget

from pilot.orchestrator.request_lifecycle import request_state, require_open, RequestStateError, OPEN, inactive_reason
from chain_contract import (ChainBlocked, BLOCK_CODE, FORMAT_BLOCK_CODE, attest_merge, blocked_state,
                            progress, validate_plan, verified_failures, deny)
from native_lot_registration import canonical
from native_verified_integration import IntegrationBlocked, next_chg
from generated_branch_standards import synchronize
from pilot.orchestrator.task_pack_publication import verify_published_pair, legacy_artifact_reference, regenerate_pack_from_registered_base, TaskPackBlocked
from pilot.orchestrator.native_submission_contract import enrich_request, is_current
from generated_conflict_recovery import retire_conflicted_generated
from pilot.orchestrator.bot_ci_retry import retry_failed_bot_prs
from pilot.orchestrator.native_infra_retry import retry_native_infra
from pilot.orchestrator.native_pending_recovery import recover as recover_pending_worker
from pilot.orchestrator.native_route_recovery import sweep as recover_route_defects
from pilot.orchestrator.native_integration_replay import recover as replay_native_integration
from pilot.orchestrator.native_integration_replay import recover_unstarted as recover_unstarted_integration
from pilot.worker_v08.native_feedback_delivery import recover_sweep as recover_native_feedback
from pilot.generated_ci_selection import last_executed_ci_run
from native_lot_binding import next_ready
from t4_admission import AdmissionBlocked, require_green_base, missing_exam, public_exam_request, registration_variant, protected_test_conflict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot/worker_v08"))

ROOT = Path(__file__).resolve().parents[2]
from pilot.config.project_config import ProjectConfigError, storage, storage_path, template_path_pattern, repo_storage
REPO = "paulozterra/lf-programming-sandbox"
TRAIN = ".github/workflows/sandbox-train.yml"
NATIVE = ".github/workflows/worker-native.yml"
CI = ".github/workflows/ci.yml"
MERGE_MESSAGE = re.compile(r"Merge PR #([1-9][0-9]*) via sandbox-train")
SAFE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


def run(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    # One consistent open-PR snapshot across recovery phases. Invalidate it
    # after writes so newly generated drafts remain visible within this run.
    active = budget.current()
    budget.invalidate_prs(args)
    if active is not None and not getattr(active, "_fetching_prs", False):
        def fetch_pr_listing(query):
            active._fetching_prs = True
            try:
                return run(*query, cwd=cwd, check=check)
            finally:
                active._fetching_prs = False
        cached = budget.pr_list(args, fetch_pr_listing)
        if cached is not None:
            return cached
    # The existing run() seam stays injectable for offline T12/T25 tests.
    # Only idempotent gh api GETs are retried; POSTs must not be replayed.
    api_get = len(args) >= 3 and args[:2] == ("gh", "api") and args[2] != "-X"
    attempts = 3 if api_get else 1
    for attempt in range(attempts):
        if active is not None and args and args[0] == "gh":
            active.record()
        try:
            p = subprocess.run(list(args), cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            if api_get and attempt + 1 < attempts:
                time.sleep(2 ** attempt)
                continue
            if api_get:
                raise ValueError("GITHUB_TRANSITORIO:API") from None
            deny("COMMAND_UNAVAILABLE")
        if not check or p.returncode == 0:
            return p.stdout.strip()
        if api_get:
            stderr = p.stderr or ""
            match = re.search(r"(?<![0-9])(?:HTTP[ /:]*)?([45][0-9]{2})(?![0-9])", stderr)
            status = int(match.group(1)) if match else None
            if status is not None and status != 429 and not 500 <= status <= 599:
                raise ValueError(f"GITHUB_HTTP_{status}:API") from None
            transient = (status == 429 or status is not None and 500 <= status <= 599
                         or bool(re.search(
                             r"(?i)(timed? out|connection reset|connection refused|"
                             r"could not resolve host|temporary failure|TLS handshake)",
                             stderr)))
            if transient:
                if attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
                raise ValueError("GITHUB_TRANSITORIO:API") from None
        command = Path(args[1] if args[0] in ("python3", "lf-python", "python")
                       and len(args) > 1 else args[0]).name
        tail = (p.stderr or "").splitlines()
        last = tail[-1].strip() if tail else ""
        match = re.search(r"(CP35_BLOCKED|TEMPLATE_WORKER_SCHEMA_INVALID):([A-Z0-9_:-]{1,120})", last)
        detail = (match.group(1) + ":" + match.group(2).rstrip(":")
                  if match else "STDERR_REDACTED" if last else "NO_STDERR")
        deny("COMMAND_FAILED:" + command + ":" + detail)
    raise ValueError("GITHUB_TRANSITORIO:API")


def github_api_raw(path: str) -> str:
    """Read via injectable transport, with bounded retries and safe errors."""
    return run("gh", "api", f"repos/{REPO}/{path}")


def api(path: str) -> dict:
    def fetch():
        raw = github_api_raw(path)
        try:
            parsed = json.loads(raw)
        except ValueError:
            deny("GITHUB_RESPONSE_INVALID")
        events = re.fullmatch(r"issues/[1-9][0-9]*/events\?per_page=100&page=[1-9][0-9]*", path)
        if not isinstance(parsed, list if events else dict):
            deny("GITHUB_RESPONSE_INVALID")
        return parsed
    # Mutable authorization inputs must not be memoized across effects.
    if (re.fullmatch(r"(issues|pulls)/[1-9][0-9]*", path)
            or path.startswith("contents/pilot/orchestrator/request_lifecycle_control.json?")
            or re.fullmatch(r"issues/[1-9][0-9]*/events\?per_page=100&page=[1-9][0-9]*", path)):
        return fetch()
    return budget.read(path, fetch)


def lifecycle_api(path: str):
    """Authorization reads must never reuse the sweep budget's cached snapshot."""
    return api(path)


def api_list(path: str, *, max_pages: int = 10) -> list[dict]:
    """GitHub REST collection, validated in the real list shape.

    Never coerce list replies into object replies. Fail closed when the last
    page is full, the response changes type, or pagination is incomplete.
    Each request uses a bounded explicit page, not an untrusted Link URL.
    """
    if (not isinstance(path, str) or not path or not 1 <= max_pages <= 10
            or "page=" in path or "per_page=" in path):
        deny("GITHUB_LIST_PAGINATION_INVALID")
    result: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        separator = "&" if "?" in path else "?"
        endpoint = f"{path}{separator}per_page=100&page={page}"
        raw = github_api_raw(endpoint)
        try:
            parsed = json.loads(raw)
        except ValueError:
            deny("GITHUB_LIST_RESPONSE_INVALID")
        if (not isinstance(parsed, list)
                or any(not isinstance(item, dict) for item in parsed)
                or len(parsed) > 100):
            deny("GITHUB_LIST_RESPONSE_INVALID")
        # Request only trusted paginated GitHub collections; repeat pages
        # cannot be accepted as evidence that the listing is complete.
        fingerprint = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        if parsed and fingerprint in seen:
            deny("GITHUB_LIST_PAGINATION_INVALID")
        seen.add(fingerprint)
        result.extend(parsed)
        if len(parsed) < 100:
            return result
    deny("GITHUB_LIST_PAGINATION_LIMIT")


def check_main() -> str:
    head = run("git", "rev-parse", "HEAD")
    if (head != run("git", "rev-parse", "origin/main")
            or head != run("git", "ls-remote", "origin", "refs/heads/main").split()[0]
            or run("git", "status", "--porcelain")):
        deny("MAIN_DRIFT")
    return head


def event_kind(event_run_id: int, head: str) -> str:
    event = api(f"actions/runs/{event_run_id}")
    path = (event.get("path") or "").split("@")[0]
    if (event.get("id") != event_run_id or event.get("status") != "completed"
            or type(event.get("run_attempt")) is not int
            or event["run_attempt"] < 1
            or (path != CI and event["run_attempt"] != 1)
            or event.get("repository", {}).get("full_name") != REPO):
        deny("SOURCE_WORKFLOW_UNTRUSTED")
    # The Train is triggered by pull_request:labeled, so the source
    # workflow's head_branch is the PR branch, NOT main. We verify the
    # resulting merge on current main independently below.
    if path == TRAIN and event.get("conclusion") == "success":
        if event.get("event") not in ("pull_request", "workflow_dispatch"):
            deny("TRAIN_SOURCE_EVENT_INVALID")
        if (event.get("event") == "workflow_dispatch"
                and event.get("head_branch") != "main"):
            deny("TRAIN_SOURCE_BRANCH_INVALID")
        return "TRAIN"
    # The Train merge and main CI run concurrently. Reconcile again when
    # exact-main CI finishes: an early BASE_NO_VERDE must not permanently
    # strand a root lot or require a manual workflow dispatch.
    if (path == CI and event.get("head_branch") == "main"
            and event.get("head_sha") == head
            and event.get("event") in ("push", "workflow_dispatch")
            and event.get("conclusion") in ("success", "failure")):
        return "TRAIN"
    # Native Worker always checks out trusted main; fail closed on drift.
    if (path == NATIVE and event.get("conclusion") == "failure"
            and event.get("head_branch") == "main"
            and event.get("event") in ("workflow_run", "workflow_dispatch")):
        return "NATIVE_FAIL"
    return "IRRELEVANT"


def main_ci_decision(head: str) -> str:
    """Missing/running CI is neutral; only a completed failed CI is red."""
    response = api("actions/workflows/ci.yml/runs?head_sha=" + head + "&per_page=100")
    rows, count = response.get("workflow_runs"), response.get("total_count")
    if not isinstance(rows, list) or type(count) is not int or count > 100:
        deny("BASE_NO_VERDE")
    eligible = [row for row in rows if isinstance(row, dict)
                and row.get("head_sha") == head
                and row.get("head_branch") == "main"
                and row.get("event") in ("push", "workflow_dispatch")
                and (row.get("path") or "").split("@")[0] == CI
                and row.get("repository", {}).get("full_name") == REPO
                and type(row.get("run_attempt")) is int]
    if not eligible:
        return "WAITING_MAIN_CI"
    latest = max(eligible, key=lambda row: (row.get("created_at") or "",
                                            row.get("id") or 0))
    if latest.get("status") != "completed":
        if latest.get("status") == "queued":
            timestamp = latest.get("created_at")
            try:
                started = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - started).total_seconds()
            except (ValueError, TypeError, AttributeError):
                age = 0
            if age >= 600:
                jobs = api(f"actions/runs/{latest['id']}/jobs?per_page=100")
                if (isinstance(jobs.get("jobs"), list)
                        and jobs.get("total_count") == 0):
                    # Only a queued push can be retried. A queued dispatch
                    # represents the one replacement; never spawn another.
                    if latest.get("event") == "push":
                        try:
                            run("gh", "api", "-X", "POST",
                                f"repos/{REPO}/actions/runs/{latest['id']}/cancel")
                        except (ChainBlocked, OSError):
                            pass  # Cancellation best effort; dispatch remains bounded.
                        run("gh", "workflow", "run", "ci.yml", "--repo", REPO,
                            "--ref", "main")
                    return "GITHUB_CI_ATASCADO"
        return "WAITING_MAIN_CI"
    if latest.get("conclusion") != "success":
        deny("BASE_NO_VERDE")
    return "GREEN"


def sweep_request_enabled(request: str) -> bool:
    """Only open, non-discarded issue-backed requests can be resumed."""
    return request_state(request, lifecycle_api, root=ROOT) == OPEN


def merged_integration(head: str) -> tuple[dict, set[str]]:
    message = run("git", "log", "-1", "--format=%s")
    found = MERGE_MESSAGE.fullmatch(message)
    if found is None:
        deny("HEAD_NOT_TRAIN_MERGE")
    parents = run("git", "rev-list", "--parents", "-n", "1", head).split()
    if len(parents) != 3 or parents[0] != head:
        deny("HEAD_NOT_TWO_PARENT_MERGE")
    pr = api(f"pulls/{int(found.group(1))}")
    if pr.get("merge_commit_sha") != head or pr.get("head", {}).get("ref", "").startswith(
            "lf/native-integration/") is False:
        deny("NOT_NATIVE_INTEGRATION")
    changed = set(run("git", "diff", "--name-only", parents[1], head).splitlines())
    return pr, changed


def validated_manual_integration(number: int, head: str) -> str:
    """Accept only a Train merge on the trusted first-parent main ancestry."""
    if type(number) is not int or number <= 0:
        deny("INTEGRATION_PR_INVALID")
    pr = api(f"pulls/{number}")
    sha = pr.get("merge_commit_sha")
    branch = pr.get("head", {}).get("ref", "")
    if (pr.get("number") != number or pr.get("merged") is not True
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not re.fullmatch(r"lf/native-integration/[a-z][a-z0-9_-]{0,31}-run-[1-9][0-9]*", branch)
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != REPO
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO):
        deny("MANUAL_INTEGRATION_PR_UNTRUSTED")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", sha, head],
                            cwd=ROOT, capture_output=True, timeout=120)
    if result.returncode:
        deny("MANUAL_INTEGRATION_NOT_ANCESTOR")
    if sha not in set(run("git", "rev-list", "--first-parent", "HEAD").splitlines()):
        deny("MANUAL_INTEGRATION_NOT_TRAIN")
    if run("git", "log", "-1", "--format=%s", sha) != (
            f"Merge PR #{number} via sandbox-train"):
        deny("MANUAL_INTEGRATION_NOT_TRAIN")
    parents = run("git", "rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 3 or parents[0] != sha:
        deny("MANUAL_INTEGRATION_NOT_TRAIN")
    return sha


def plans() -> list[tuple[str, dict, dict, dict]]:
    # Legacy CP3.6 plans remain where originally written. T7 generated
    # evidence PRs are restricted to pilot/runs/<slug>/, so they publish
    # chain_plan.json inside their own request folder.
    sources = {}
    legacy = storage_path("chain_plans_root", root=ROOT)
    if legacy.exists():
        for file in sorted(legacy.glob("*.json")):
            if file.is_symlink() or not SAFE_ID.fullmatch(file.stem):
                deny("CHAIN_PLAN_PATH_INVALID")
            sources[file.stem] = file
    runs = storage_path("requests_root", root=ROOT)
    if runs.exists():
        for file in sorted(runs.glob("*/chain_plan.json")):
            request = file.parent.name
            if file.is_symlink() or file.parent.is_symlink() or not SAFE_ID.fullmatch(request):
                deny("CHAIN_PLAN_PATH_INVALID")
            if request in sources and sources[request].read_bytes() != file.read_bytes():
                deny("CHAIN_PLAN_DRIFT")
            sources.setdefault(request, file)
    rows = []
    for request, file in sorted(sources.items()):
        folder = storage_path("requests_root", root=ROOT) / request
        if folder.is_symlink():
            deny("CHAIN_RUN_SYMLINK")
        for path in (folder / "lots.json", folder / "state.json"):
            if not path.is_file() or path.is_symlink():
                deny("CHAIN_INPUT_MISSING")
        plan = json.loads(file.read_text("utf-8"))
        lots = json.loads((folder / "lots.json").read_text("utf-8"))
        state = json.loads((folder / "state.json").read_text("utf-8"))
        if state.get("stage") not in ("LOTS_PLANNED", "BLOCKED", "CHAIN_COMPLETE_CANDIDATE"):
            deny("CHAIN_STAGE_INVALID")
        if state.get("lots_sha256") != hashlib.sha256(canonical(lots)).hexdigest():
            deny("CHAIN_STATE_LOTS_DRIFT")
        bindings = validate_plan(plan, lots, request)
        rows.append((request, lots, state, bindings))
    return rows


def _active_plan_origin(request: str, path: str, additions: list[str],
                        root: Path, max_commits: int) -> str:
    """Prove prior plans were retired by Train before native work began."""
    if len(additions) == 1:
        return additions[0]
    if any(not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in additions):
        deny("CHAIN_HISTORY_INCOMPLETE")
    first = additions[-1]
    first_parents = run("git", "rev-list", "--parents", "-n", "1", first,
                        cwd=root).split()
    if not first_parents or first_parents[0] != first:
        deny("CHAIN_HISTORY_INCOMPLETE")
    since = f"{first}^..HEAD" if len(first_parents) > 1 else "HEAD"
    history = run("git", "rev-list", "--first-parent",
                  f"--max-count={max_commits + 1}", since,
                  cwd=root).splitlines()
    if len(history) > max_commits or len(set(history)) != len(history):
        deny("CHAIN_HISTORY_INCOMPLETE")
    position = {sha: i for i, sha in enumerate(history)}
    if len(set(additions)) != len(additions) or any(sha not in position for sha in additions):
        deny("CHAIN_HISTORY_INCOMPLETE")
    deletions = run("git", "log", "--first-parent", "--diff-filter=D",
                    "--format=%H", "--", path, cwd=root).splitlines()
    if len(set(deletions)) != len(deletions) or any(sha not in position for sha in deletions):
        deny("CHAIN_HISTORY_INCOMPLETE")
    if any(position[sha] < position[additions[0]] for sha in deletions):
        deny("CHAIN_HISTORY_INCOMPLETE")
    for newer, older in zip(additions, additions[1:]):
        n, o = position[newer], position[older]
        if n >= o:
            deny("CHAIN_HISTORY_INCOMPLETE")
        retirements = [sha for sha in deletions if n < position[sha] < o]
        if len(retirements) != 1:
            deny("CHAIN_HISTORY_INCOMPLETE")
        deleted = retirements[0]
        message = run("git", "log", "-1", "--format=%s", deleted, cwd=root)
        match = MERGE_MESSAGE.fullmatch(message)
        parents = run("git", "rev-list", "--parents", "-n", "1", deleted,
                      cwd=root).split()
        if not match or len(parents) != 3 or parents[0] != deleted:
            deny("CHAIN_HISTORY_INCOMPLETE")
        pr = api(f"pulls/{int(match.group(1))}")
        if (pr.get("merged") is not True or pr.get("merge_commit_sha") != deleted
                or pr.get("base", {}).get("ref") != "main"):
            deny("CHAIN_HISTORY_INCOMPLETE")
        actual_diff = run("git", "diff", "--name-status", parents[1], deleted,
                          "--", path, cwd=root).splitlines()
        if actual_diff != ["D\t" + path]:
            deny("CHAIN_HISTORY_INCOMPLETE")
        try:
            old_plan = json.loads(run("git", "show", f"{older}:{path}", cwd=root))
            bindings = old_plan["bindings"]
            if not isinstance(bindings, list) or not bindings:
                deny("CHAIN_HISTORY_INCOMPLETE")
            tasks = {item["task_name"] for item in bindings}
            if (len(tasks) != len(bindings)
                    or any(not SAFE_ID.fullmatch(task) for task in tasks)):
                deny("CHAIN_HISTORY_INCOMPLETE")
        except (ValueError, KeyError, TypeError, AttributeError):
            deny("CHAIN_HISTORY_INCOMPLETE")
        # Old plans may have registered but never executed lots.  All
        # registration artifacts must be deleted in the same Train merge.
        from pilot.orchestrator import plan_retirement as retirement
        interval = f"{older}^..{newer}^"
        before = set(run("git", "ls-tree", "-r", "--name-only", parents[1],
                         cwd=root).splitlines())
        after = set(run("git", "ls-tree", "-r", "--name-only", deleted,
                        cwd=root).splitlines())
        registered = False
        try:
            for task in tasks:
                watched = retirement.registration_paths(request, task)
                touched = set(run("git", "log", "--first-parent", "--format=",
                                  "--name-only", interval, "--", *watched,
                                  cwd=root).splitlines()) - {""}
                registered |= retirement.verify_removed(
                    before, after, request, task, historical=touched)
                if run("git", "log", "--first-parent", "--format=%H", interval,
                       "--", f"pilot/native_proposals/{task}.json", cwd=root):
                    deny("CHAIN_HISTORY_INCOMPLETE")
            if registered:
                start = run("git", "show", "-s", "--format=%cI", older, cwd=root)
                end = run("git", "show", "-s", "--format=%cI", deleted, cwd=root)
                def read(route):
                    return json.loads(github_api_raw(route))
                retirement.verify_no_execution(read, tasks, start, end)
        except (retirement.RetirementBlocked, OSError, ValueError, TypeError, KeyError):
            deny("CHAIN_HISTORY_INCOMPLETE")
        merges = run("git", "log", "--first-parent", "--format=%H%x09%s",
                     interval, cwd=root).splitlines()
        for entry in merges:
            if "\t" not in entry:
                deny("CHAIN_HISTORY_INCOMPLETE")
            sha, subject = entry.split("\t", 1)
            found = MERGE_MESSAGE.fullmatch(subject)
            if not found:
                continue
            body = run("git", "log", "-1", "--format=%B", sha, cwd=root)
            if "[CP3.5]" not in body or "Verified native" not in body:
                continue
            integration = api(f"pulls/{int(found.group(1))}")
            branch = integration.get("head", {}).get("ref", "")
            if not isinstance(branch, str):
                deny("CHAIN_HISTORY_INCOMPLETE")
            if any(branch.startswith(f"lf/native-integration/{task}-run-")
                   for task in tasks):
                deny("CHAIN_HISTORY_INCOMPLETE")
    return additions[0]


def first_parent_merges(request: str, *, root: Path = ROOT,
                        max_commits: int | None = None) -> list[tuple[str, dict, set[str]]]:
    """All first-parent integrations since this request's plan was introduced.

    A truncated or ambiguous history is never evidence of dependency disorder.
    """
    if not SAFE_ID.fullmatch(request):
        deny("CHAIN_HISTORY_INCOMPLETE")
    if max_commits is None:
        raw = os.environ.get("CP36_CHAIN_HISTORY_MAX_COMMITS", "2000")
        if not raw.isdecimal() or not 1 <= int(raw) <= 10000:
            deny("CHAIN_HISTORY_INCOMPLETE")
        max_commits = int(raw)
    if type(max_commits) is not int or not 1 <= max_commits <= 10000:
        deny("CHAIN_HISTORY_INCOMPLETE")
    paths = [f"{repo_storage()['requests_root']}/{request}/chain_plan.json",
             f"{repo_storage()['chain_plans_root']}/{request}.json"]
    origins = []
    for path in paths:
        if not (root / path).is_file():
            continue
        candidates = run("git", "log", "--first-parent", "--diff-filter=A",
                         "--format=%H", "--", path, cwd=root).splitlines()
        if not candidates:
            deny("CHAIN_HISTORY_INCOMPLETE")
        origins.append(_active_plan_origin(request, path, candidates,
                                           root, max_commits))
    if len(origins) != 1:
        deny("CHAIN_HISTORY_INCOMPLETE")
    origin = origins[0]
    # origin^..HEAD includes origin; never silently truncate a valid chain.
    parents = run("git", "rev-list", "--parents", "-n", "1", origin,
                  cwd=root).split()
    if not parents or parents[0] != origin:
        deny("CHAIN_HISTORY_INCOMPLETE")
    since = f"{origin}^..HEAD" if len(parents) > 1 else "HEAD"
    revisions = run("git", "log", "--first-parent",
                    f"--max-count={max_commits + 1}",
                    "--format=%H%x09%s", since, cwd=root).splitlines()
    if not revisions or len(revisions) > max_commits:
        deny("CHAIN_HISTORY_INCOMPLETE")
    if not any(record.startswith(origin + "\t") for record in revisions):
        deny("CHAIN_HISTORY_INCOMPLETE")
    results = []
    for record in revisions:
        try:
            sha, message = record.split("\t", 1)
        except ValueError:
            deny("GIT_HISTORY_INVALID")
        match = MERGE_MESSAGE.fullmatch(message)
        if not match:
            continue
        # Avoid unaudited broad PR scans and unnecessary GitHub API calls.
        body = run("git", "log", "-1", "--format=%B", sha, cwd=root)
        if "[CP3.5]" not in body or "Verified native" not in body:
            continue
        pr = api(f"pulls/{int(match.group(1))}")
        if pr.get("head", {}).get("ref", "").startswith("lf/native-integration/"):
            parents = run("git", "rev-list", "--parents", "-n", "1", sha, cwd=root).split()
            if len(parents) != 3 or parents[0] != sha:
                deny("MERGE_PARENT_INVALID")
            changes = set(run("git", "diff", "--name-only",
                              parents[1], sha, cwd=root).splitlines())
            results.append((sha, pr, changes))
    return list(reversed(results))


def completed_lots(lots: dict, bindings: dict, history: list[tuple]) -> dict:
    result = {}
    for sha, pr, changed in history:
        # Ignore other explicitly bound chains, but reject spoofed integration
        # for a task belonging to this chain.
        branch = pr.get("head", {}).get("ref", "")
        if not any(re.fullmatch(
                r"lf/native-integration/" + re.escape(row["task_name"])
                + r"(?:(?:[2-9]|[1-9][0-9]+))?-run-[1-9][0-9]*", branch)
                for row in bindings.values()):
            continue
        lot_id, receipt = attest_merge(sha, pr, lots, bindings, changed)
        if lot_id in result:
            deny("DUPLICATE_LOT_MERGE")
        lot = next(item for item in lots["lots"] if item["id"] == lot_id)
        if not set(lot["depends_on"]).issubset(result):
            deny("OUT_OF_ORDER_MERGE")
        for path in receipt["expected_files"]:
            # Preserve the injectable git seam for hermetic tests.
            try:
                run("git", "cat-file", "-e", sha + ":" + path)
            except (ChainBlocked, OSError, ValueError):
                deny("CHAIN_EXPECTED_FILE_MISSING:" + path)
        result[lot_id] = receipt
    return result


def failed_lots(bindings: dict) -> dict[str, list[int]]:
    # The upstream native_run_history proof-reader handles signed artifact
    # redirects without passing credentials to storage and never opens oracles.
    from native_run_history import _artifact_json, _recognized_run
    from pilot.worker_v08.native_route_defect import verified_migration
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        deny("GITHUB_TOKEN_MISSING")
    result = {}
    for page in range(1, 11):
        response = api(f"actions/workflows/worker-native.yml/runs?per_page=100&page={page}")
        if response.get("total_count", 0) > 1000:
            deny("RUN_HISTORY_TOO_LARGE")
        if page == 1:
            history = []
        history.extend(response.get("workflow_runs", []))
        if len(history) >= response.get("total_count", 0):
            break
    else:
        deny("RUN_HISTORY_INCOMPLETE")
    for lot, binding in bindings.items():
        task = binding["task_name"]
        failures = [r for r in history if _recognized_run(r, task)
                    and r.get("conclusion") == "failure"]
        proofs = {}
        for entry in failures:
            proof = _artifact_json(REPO, token, entry["id"])
            proofs[entry["id"]] = proof
        registration = storage_path("registrations_root", root=ROOT) / (task + ".json")
        migration = None
        if registration.is_file() and not registration.is_symlink():
            try:
                migration = verified_migration(
                    ROOT, task, json.loads(registration.read_text("utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                migration = None
        defects = ({migration["source_run_id"]: migration["legacy_task_pack_sha256"]}
                   if migration is not None else {})
        # T32: governed examiner-defect forgiveness (exact runs, replaced exam).
        from pilot.worker_v08.native_examiner_defect import verified_examiner_defects
        try:
            examiner = verified_examiner_defects(
                ROOT, task, json.loads(registration.read_text("utf-8")))
        except (OSError, ValueError):
            examiner = {}
        # T37: governed route-tool-defect forgiveness.
        from pilot.worker_v08.native_route_tool_defect import verified_route_tool_defects
        from pilot.worker_v08.native_intake_defect import verified_intake_defects
        try:
            reg_record = json.loads(registration.read_text("utf-8"))
            for verify in (verified_route_tool_defects, verified_intake_defects):
                for run_id, row in verify(ROOT, task, reg_record).items():
                    examiner.setdefault(run_id, row)
        except (OSError, ValueError):
            pass
        for run_id, row in examiner.items():
            if any(r.get("id") == run_id and _recognized_run(
                    r, task, sha=row["proposal_commit_sha"]) for r in failures):
                defects.setdefault(run_id, row["task_pack_sha256"])
        result[lot] = verified_failures(task, failures, proofs,
                                       route_defects=defects)
    return result


def chg(root: Path, number: int, request: str, reason: str,
        changed: list[str]) -> Path:
    ident = f"CHG-{number:04d}"
    payload = {
        "schema_version": "LF_STANDARD_CHANGE_V1",
        "change_id": ident,
        "title": f"CP3.6: encadenamiento gobernado {request}",
        "change_class": "ADDITIVE",
        "trigger": {"kind": "OWNER", "reference": "Paulo 2026-11-11 CP3.6 encadenamiento automático"},
        "reason": reason,
        "artifacts": [],
        "affected": {"rule_ids": [], "term_ids": [],
                     "paths": sorted(set(changed + [f"standards/changes/{ident}.json",
                                                   "standards/CAMBIOS.md"]))},
        "existing_code_impact": {"mode": "NEW_OR_MODIFIED_ONLY",
                                 "baseline_ref": "standards/baseline/",
                                 "expected_direction": "NON_INCREASING"},
        "security_pin_invalidation": {"invalidates": False, "affected_artifacts": []},
        "requested_by": "agent:gpt", "approved_by": "paulozterra",
        "evidence": {"pr_url": ""},
    }
    path = root / f"standards/changes/{ident}.json"
    if path.exists():
        deny("CHG_EXISTS")
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", "utf-8")
    return path


def draft(root: Path, branch: str, request: str, paths: list[str],
          reason: str, title: str) -> dict:
    # Caller has already committed the prepared native task on this branch.
    require_open(request, lifecycle_api, root=ROOT)
    number = next_chg(root)
    entry = chg(root, number, request, reason, paths)
    run("git", "add", "--", *paths, str(entry.relative_to(root)), cwd=root)
    kind = "registration" if branch.startswith("lf/native-registration/") else "registry"
    synchronize(root, kind, chg_file=entry.relative_to(root).as_posix())
    run("git", "commit", "-m", f"[CP3.6][CHG-{number:04d}] {title}", cwd=root)
    from native_verified_integration import confirm_class_after_commit
    confirm_class_after_commit(root, entry)
    if run("git", "ls-remote", "origin", "refs/heads/main", cwd=root).split()[0] != run("git", "merge-base", "origin/main", "HEAD", cwd=root):
        deny("MAIN_MOVED_BEFORE_DRAFT")
    require_open(request, lifecycle_api, root=ROOT)
    run("git", "push", "--set-upstream", "origin", branch, cwd=root)
    body = (f"CP3.6 · {reason}\n\n"
            f"CHG-{number:04d}; revisión independiente Claude, "
            f"Paulo decide ready-to-merge, Train fusiona. "
            f"No merge ni etiqueta automáticos.")
    require_open(request, lifecycle_api, root=ROOT)
    url = run("gh", "pr", "create", "--repo", REPO, "--base", "main",
              "--head", branch, "--draft",
              "--title", f"[DRAFT][CP3.6][CHG-{number:04d}] {title}",
              "--body", body, cwd=root)
    document = json.loads(entry.read_text("utf-8"))
    document["evidence"]["pr_url"] = url
    entry.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", "utf-8")
    synchronize(root, kind, chg_file=entry.relative_to(root).as_posix())
    run("git", "commit", "-m", "[CP3.6] link reviewable draft evidence", cwd=root)
    run("python3", "standards/tools/changes.py", "check", "--base", "origin/main", cwd=root)
    require_open(request, lifecycle_api, root=ROOT)
    run("git", "push", "origin", branch, cwd=root)
    require_open(request, lifecycle_api, root=ROOT)
    run("gh", "workflow", "run", "ci.yml", "--repo", REPO, "--ref", branch, cwd=root)
    return {"draft_pr": url, "head_sha": run("git", "rev-parse", "HEAD", cwd=root)}


def worktree(base: str, branch: str, callback):
    with tempfile.TemporaryDirectory(prefix="cp36-") as temp:
        directory = Path(temp) / "checkout"
        run("git", "worktree", "add", "--detach", str(directory), base)
        try:
            run("git", "switch", "-c", branch, cwd=directory)
            return callback(directory)
        finally:
            run("git", "worktree", "remove", "--force", str(directory))


def close_stale_drafts(prefix: str, current: str) -> list[int]:
    """Close bot drafts generated for an older main; they can never pass the
    exact-main content check, and leaving them open blocks regeneration."""
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO, "--state", "open",
                          "--limit", "100", "--json", "number,headRefName,author"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    closed = []
    for item in rows:
        ref = str(item.get("headRefName", "")) if isinstance(item, dict) else ""
        login = str((item.get("author") or {}).get("login", "")) if isinstance(item, dict) else ""
        if (ref.startswith(prefix) and ref != prefix + current
                and login in ("app/github-actions", "github-actions[bot]", "github-actions")):
            run("gh", "pr", "close", str(int(item["number"])), "--repo", REPO, "--delete-branch",
                "--comment", "Superado: main avanzó a " + current + "; se regenera sobre el main actual.")
            closed.append(int(item["number"]))
    return closed


def close_failed_old_registration_drafts(task: str, head: str) -> list[int]:
    """T17 sweep: retire only bot Drafts broken by the old CHG renderer.

    A red CI alone is insufficient: the PR must have a CHG but omit the
    derived CAMBIOS view. A failing unrelated test must remain reviewable.
    No proposed source branch is executed or checked out.
    """
    prefix = f"lf/native-registration/{task}-"
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO,
                          "--state", "open", "--limit", "100",
                          "--json", "number,headRefName,headRefOid,author,isDraft"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    retired = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        branch, sha = row.get("headRefName"), row.get("headRefOid")
        if (not isinstance(branch, str) or not branch.startswith(prefix)
                or not re.fullmatch(re.escape(prefix) + r"[0-9a-f]{12}", branch)
                or not isinstance(sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", sha)
                or row.get("isDraft") is not True
                or (row.get("author") or {}).get("login") not in
                   ("github-actions[bot]", "app/github-actions", "github-actions")):
            continue
        number = row.get("number")
        if type(number) is not int or number < 1:
            deny("PENDING_DRAFT_ID_INVALID")
        ci = api("actions/workflows/ci.yml/runs?head_sha=" + sha + "&per_page=100")
        runs = ci.get("workflow_runs")
        if not isinstance(runs, list) or ci.get("total_count", 101) > 100:
            deny("PENDING_DRAFT_CI_INVALID")
        eligible = [r for r in runs if isinstance(r, dict)
                    and r.get("head_sha") == sha and r.get("head_branch") == branch
                    and r.get("event") in ("pull_request", "workflow_dispatch", "push")]
        latest = last_executed_ci_run(eligible)
        if latest is None or latest.get("status") != "completed" or latest.get("conclusion") != "failure":
            continue
        files = api_list(f"pulls/{number}/files")
        if not isinstance(files, list) or len(files) >= 100:
            deny("PENDING_DRAFT_FILES_UNVERIFIED")
        names = {x.get("filename") for x in files if isinstance(x, dict)}
        # Old-generator fingerprint: a real CHG with no matching derived view.
        if (not any(isinstance(p, str) and
                    re.fullmatch(r"standards/changes/CHG-[0-9]{4}[.]json", p)
                    for p in names)
                or "standards/CAMBIOS.md" in names):
            continue
        run("gh", "pr", "close", str(number), "--repo", REPO, "--delete-branch",
            "--comment", "T17: CI rojo y CHG sin vista CAMBIOS; borrador obsoleto. "
            "La cadena regenera el registro sobre main verificado " + head[:12] + ".")
        retired.append(number)
    return retired


def conflicted_request(row: dict, all_plans: list) -> str | None:
    """Find original request only from immutable main plans or a verified T7 diff."""
    branch = row["branch"]
    if row["kind"] == "generated-t7":
        files = api_list(f"pulls/{row['number']}/files")
        if not isinstance(files, list) or len(files) >= 100:
            deny("CONFLICT_T7_FILES_INVALID")
        slugs = {match.group(1) for file in files if isinstance(file, dict)
                 if (match := re.fullmatch(
                     re.escape(storage()["requests_root"]) + r"/(req-[1-9][0-9]*)/"
                     r"(?:analysis|state|lots|chain_plan)[.]json",
                     str(file.get("filename", ""))))}
        return next(iter(slugs)) if len(slugs) == 1 else None
    if row["kind"] in ("registration", "integration"):
        task = (branch.removeprefix("lf/native-registration/").rsplit("-", 1)[0]
                if row["kind"] == "registration" else
                re.sub(r"-run-[1-9][0-9]*$", "",
                       branch.removeprefix("lf/native-integration/")))
        matches = {request for request, _lots, _state, bindings in all_plans
                   if any(binding.get("task_name") == task
                          for binding in bindings.values())}
        return next(iter(matches)) if len(matches) == 1 else None
    return None


def comment_unrecoverable_conflict(row: dict, all_plans: list, reason: str) -> None:
    """Watchdog-style issue notice, with no labels and no inferred issue ID."""
    request = conflicted_request(row, all_plans)
    if not request or not re.fullmatch(r"req-[1-9][0-9]*", request):
        return
    require_open(request, lifecycle_api, root=ROOT)
    number = int(request[4:])
    issue = api(f"issues/{number}")
    if (issue.get("number") != number or issue.get("pull_request")
            or issue.get("state") != "open"
            or "lf-request" not in {x.get("name") for x in issue.get("labels", [])}):
        return
    marker = f"<!-- LF_CONFLICT_RECOVERY:{row['number']}:{row['sha']} -->"
    comments = api_list(f"issues/{number}/comments")
    if not isinstance(comments, list) or len(comments) >= 100:
        deny("CONFLICT_RECOVERY_COMMENTS_INVALID")
    if any(marker in str(comment.get("body", ""))
           for comment in comments if isinstance(comment, dict)
           and (comment.get("user") or {}).get("login") == "github-actions[bot]"):
        return
    run("gh", "issue", "comment", str(number), "--repo", REPO, "--body",
        marker + "\nT17.4 watchdog: PR generado #" + str(row["number"])
        + " retirado por conflicto con main. Regeneración no automática ("
        + reason + "); requiere revisión del pedido. Sin etiquetas.")


def notify_failed_conflict_replay(row: dict, all_plans: list,
                                  failed_run_id: int) -> None:
    """Reuse verified issue + bot-comment mechanism; dedupe by failed run ID.

    A failed notice is best effort; the recovery result stays BLOCKED.
    """
    request = conflicted_request(row, all_plans)
    if (request is None or not re.fullmatch(r"req-[1-9][0-9]*", request)
            or type(failed_run_id) is not int or failed_run_id <= 0):
        return
    try:
        require_open(request, lifecycle_api, root=ROOT)
        number = int(request[4:])
        issue = api(f"issues/{number}")
        if (issue.get("number") != number or issue.get("pull_request")
                or issue.get("state") != "open"
                or "lf-request" not in {x.get("name") for x in issue.get("labels", [])}):
            return
        marker = f"<!-- LF_CP36_CP35_FAILED:{failed_run_id} -->"
        comments = api_list(f"issues/{number}/comments")
        if (not isinstance(comments, list) or len(comments) >= 100
                or any(not isinstance(c, dict) for c in comments)):
            return
        if any(marker in str(c.get("body", ""))
               for c in comments
               if (c.get("user") or {}).get("login") == "github-actions[bot]"):
            return
        run("gh", "issue", "comment", str(number), "--repo", REPO,
            "--body", marker + "\nCP3.6 BLOCKED: "
            "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED. "
            "La recuperación CP3.5 del PASS nativo no se repetirá "
            f"automáticamente. Corrida fallida #{failed_run_id}; "
            "requiere revisión. Sin etiquetas.")
    except (ChainBlocked, ValueError, KeyError, OSError, TypeError):
        # Notice is best effort; never unblock a recovery from notification IO.
        return


def regenerate_conflicted(row: dict, head: str, all_plans: list) -> dict:
    """Recreate from trusted main only; never execute or reuse old PR code."""
    kind, branch = row["kind"], row["branch"]
    if kind != "implemented-registry":
        request = conflicted_request(row, all_plans)
        if request is None:
            raise RequestStateError("REQUEST_STATE_UNRESOLVED")
        current = request_state(request, lifecycle_api, root=ROOT)
        if current != OPEN:
            return {"status": inactive_reason(current), "request": request}
    if kind == "registration":
        # The existing ready-lot loop regenerates this branch *after* retirement
        # in the current sweep, using next_chg from current main.
        return {"status": "CONFLICT_REGISTRATION_RETIRED"}
    if kind == "implemented-registry":
        return {"status": "CONFLICT_REGISTRY_REBUILT",
                "registry": sync_implemented_registry(head)}
    if kind == "generated-t7":
        request = conflicted_request(row, all_plans)
        if request is None:
            comment_unrecoverable_conflict(row, all_plans, "T7_REQUEST_AMBIGUOUS")
            return {"status": "CONFLICT_REGEN_BLOCKED", "reason": "T7_REQUEST_AMBIGUOUS"}
        from pilot.auto_integrate import original_request_merge
        source = original_request_merge(request, ROOT)
        run("gh", "workflow", "run", "t7-request.yml", "--repo", REPO,
            "--ref", "main", "-f", "slug=" + request,
            "-f", "merge_sha=" + source, "-f", "rerun=true")
        return {"status": "CONFLICT_T7_REDISPATCHED", "request": request}
    if kind == "integration":
        from pilot.orchestrator.conflict_integration_replay import recover
        return recover(row, run, api, REPO)
    comment_unrecoverable_conflict(row, all_plans, "NO_TRUSTED_REGENERATOR")
    return {"status": "CONFLICT_REGEN_BLOCKED", "reason": "NO_TRUSTED_REGENERATOR"}


def pending_draft(prefix: str) -> bool:
    """Do not create another draft for the same task/request after main moves."""
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO,
                          "--state", "open", "--limit", "100",
                          "--json", "headRefName"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    return any(isinstance(item, dict) and
               str(item.get("headRefName", "")).startswith(prefix)
               for item in rows)


# One CP3.6 Python process can enter exam admission twice for the root lot:
# plan publication and ready-lot admission. Never rely on immediate REST
# read-after-write visibility to prevent duplicate creation.
_EXAM_RUN_CACHE: dict[str, dict] = {}


EXAM_RETRY_LABEL = "exam-retry"


def exam_issue_marker(task: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
        deny("EXAM_REQUEST_TASK_INVALID")
    return f"<!-- LF_EXAM_REQUEST_TASK:{task} -->"


def exam_key(request: str, binding: dict) -> str:
    task = binding["task_name"]
    exam_issue_marker(task)
    if not re.fullmatch(r"req-[1-9][0-9]*", request):
        deny("EXAM_REQUEST_KEY_INVALID")
    path = binding.get("template_path")
    if not isinstance(path, str) or not re.fullmatch(
            template_path_pattern(request, root=ROOT).pattern, path):
        deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
    template = ROOT / path
    if template.is_symlink() or not template.is_file():
        deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
    try:
        content = json.loads(template.read_text("utf-8"))
        spec = content.get("task_spec") if isinstance(content, dict) else None
        if not isinstance(spec, dict):
            deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
        version = hashlib.sha256(canonical(spec)).hexdigest()
        # Pre-T47 registrations lack a verifiable original-template stamp.
        legacy_record = storage_path("registrations_root", root=ROOT) / (task + ".json")
        if legacy_record.is_symlink():
            deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
        if legacy_record.is_file():
            recorded = json.loads(legacy_record.read_text("utf-8"))
            if not isinstance(recorded, dict):
                deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
            stamped = recorded.get("template_sha256")
            if stamped is None and "template_path" not in recorded:
                version = "legacy"
            elif (not isinstance(stamped, str)
                  or not re.fullmatch(r"[0-9a-f]{64}", stamped)
                  or not isinstance(recorded.get("template_path"), str)):
                deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
    except ProjectConfigError:
        raise
    except (OSError, ValueError, TypeError):
        deny("EXAM_REQUEST_TEMPLATE_UNRESOLVED")
    return f"LF_EXAM_REQUEST_KEY:{request}:{task}:{version}"


def exam_request_matches(rows: list, task: str, request: str,
                         key: str | None = None) -> list:
    marker = exam_issue_marker(task)
    title = "EXAM_REQUEST: " + task
    if not isinstance(rows, list):
        deny("EXAM_REQUEST_LIST_UNTRUSTED")
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            deny("EXAM_REQUEST_LIST_UNTRUSTED")
        body = row.get("body")
        if row.get("title") != title and marker not in str(body):
            continue
        if (row.get("title") != title or not isinstance(body, str)
                or f"- Task ID: `{task}`" not in body
                or f"- Pedido: `{request}`" not in body
                or (marker not in body and "Solicitud automática de examen independiente (T4)." not in body)):
            deny("EXAM_REQUEST_IDENTITY_CONFLICT")
        keys = re.findall(r"<!-- (LF_EXAM_REQUEST_KEY:[^<>\s]+) -->", body)
        if len(keys) > 1:
            deny("EXAM_REQUEST_IDENTITY_CONFLICT")
        if key is not None and keys and keys[0] != key:
            continue  # New template version is independently examinable.
        matches.append(row)
    return matches


def exam_issue_state(row: dict) -> tuple[str, str]:
    return (str(row.get("state", "")).lower(),
            str(row.get("state_reason") or row.get("stateReason") or "").lower())


def choose_exam_issue(matches: list, registered: bool) -> tuple[str, dict | None]:
    ordered = sorted(matches, key=lambda row: row.get("number", 0))
    if any(type(row.get("number")) is not int or row["number"] <= 0
           for row in ordered):
        deny("EXAM_REQUEST_LIST_UNTRUSTED")
    opened = [row for row in ordered if exam_issue_state(row)[0] == "open"]
    if len(opened) > 1:
        return "EXAM_REQUEST_DUPLICATE_OPEN", opened[0]
    completed = [row for row in ordered
                 if exam_issue_state(row) == ("closed", "completed")]
    if registered and completed:
        return "EXAM_ALREADY_REGISTERED", completed[0]
    if opened:
        return "EXAMEN_PENDIENTE", opened[0]
    if ordered and all(exam_issue_state(row) in
                       (("closed", "not_planned"), ("closed", "duplicate"))
                       for row in ordered):
        return "EXAM_REQUEST_PREVIOUSLY_DISCARDED", ordered[0]
    if ordered:
        return "EXAM_REQUEST_CLOSED_UNVERIFIED", ordered[0]
    return "CREATE_EXAM_REQUEST", None


def listed_exam_requests() -> list:
    # api_list uses authenticated GitHub REST, not delayed code/issue search.
    # A full last page or invalid/truncated response fails closed.
    try:
        rows = api_list("issues?state=all&labels=exam-request")
    except (ChainBlocked, ValueError, OSError):
        deny("EXAM_REQUEST_LIST_UNTRUSTED")
    if not isinstance(rows, list):
        deny("EXAM_REQUEST_LIST_UNTRUSTED")
    return rows


def exam_notice(request: str, key: str, reason: str, number: int | None = None) -> None:
    """Best-effort deduped typed notice, never permission to publish again."""
    marker = f"<!-- LF_EXAM_NOTICE:{key}:{reason} -->"
    try:
        require_open(request, lifecycle_api, root=ROOT)
        original = api("issues/" + request[4:])
        if (original.get("number") != int(request[4:])
                or original.get("state") != "open"):
            return
        comments = api_list("issues/" + request[4:] + "/comments")
        if any(marker in str(c.get("body", "")) for c in comments):
            return
        run("gh", "issue", "comment", request[4:], "--repo", REPO, "--body",
            marker + "\nCP3.6 BLOCKED: " + reason + " para " + key +
            (f"; exam_issue=#{number}" if number else ""))
    except (ChainBlocked, OSError, ValueError, KeyError, TypeError, AttributeError):
        pass


def reconcile_exam_duplicates(matches: list, request: str, key: str) -> dict:
    opened = sorted((r for r in matches if exam_issue_state(r)[0] == "open"),
                    key=lambda row: row["number"])
    original = opened[0]
    for duplicate in opened[1:]:
        n = duplicate["number"]
        # Comment first; if either step fails, caller must block (no create).
        run("gh", "issue", "comment", str(n), "--repo", REPO,
            "--body", f"Duplicado de #{original['number']} para {key}. "
                      f"Se conserva la solicitud original.")
        run("gh", "api", "-X", "PATCH", f"repos/{REPO}/issues/{n}",
            "-f", "state=closed", "-f", "state_reason=duplicate")
    exam_notice(request, key, "EXAM_REQUEST_DUPLICATE_OPEN", original["number"])
    return original

def complete_registered_exam_requests(request: str, bindings: dict) -> list[int]:
    """Reconcile only after the actual registration is in trusted main.

    Ciphertext is never read. A draft registration is insufficient to close
    an open request; only an existing native_tasks record on main qualifies.
    """
    registered = []
    for binding in bindings.values():
        task = binding["task_name"]
        record = storage_path("registrations_root", root=ROOT) / (task + ".json")
        if record.is_symlink():
            deny("EXAM_REGISTRATION_SYMLINK")
        if record.is_file() and not missing_exam(ROOT, task):
            registered.append(task)
    if not registered:
        return []
    issues = listed_exam_requests()
    closed = []
    for task in sorted(set(registered)):
        for row in exam_request_matches(issues, task, request):
            if exam_issue_state(row)[0] != "open":
                continue
            number = row.get("number")
            if type(number) is not int or number <= 0:
                deny("EXAM_REQUEST_LIST_UNTRUSTED")
            require_open(request, lifecycle_api, root=ROOT)
            run("gh", "issue", "close", str(number), "--repo", REPO,
                "--reason", "completed")
            closed.append(number)
    return closed


def request_missing_exam(request: str, binding: dict, lot: dict) -> dict:
    """Single publication per (request, task, canonical template) per process."""
    task = binding["task_name"]
    try:
        require_open(request, lifecycle_api, root=ROOT)
    except RequestStateError as exc:
        return {"status": (str(exc) if str(exc) in ("REQUEST_CLOSED", "REQUEST_SUSPENDED")
                           else "BLOCKED"), "reason_code": str(exc), "task": task}
    try:
        key = exam_key(request, binding)
    except (ChainBlocked, ValueError):
        exam_notice(request, f"LF_EXAM_REQUEST_KEY:{request}:{task}:legacy",
                    "EXAM_REQUEST_TEMPLATE_UNRESOLVED")
        return {"status": "BLOCKED", "reason_code": "EXAM_REQUEST_TEMPLATE_UNRESOLVED",
                "task": task}
    if key in _EXAM_RUN_CACHE:
        return dict(_EXAM_RUN_CACHE[key])
    title, body = public_exam_request(ROOT, request, binding, lot)
    body += "\n\n" + exam_issue_marker(task) + "\n<!-- " + key + " -->\n"
    try:
        matches = exam_request_matches(listed_exam_requests(), task, request, key)
        registration = storage_path("registrations_root", root=ROOT) / (task + ".json")
        if registration.is_symlink():
            deny("EXAM_REGISTRATION_SYMLINK")
        outcome, found = choose_exam_issue(matches, registration.is_file())
        if outcome == "EXAM_REQUEST_DUPLICATE_OPEN":
            found = reconcile_exam_duplicates(matches, request, key)
            result = {"status": "BLOCKED",
                      "reason_code": "EXAM_REQUEST_DUPLICATE_OPEN",
                      "task": task, "exam_issue": found["number"]}
            _EXAM_RUN_CACHE[key] = dict(result)
            return result
        if outcome == "EXAM_ALREADY_REGISTERED":
            result = {"status": outcome, "task": task, "exam_issue": found["number"]}
        elif outcome == "EXAMEN_PENDIENTE":
            result = {"status": "BLOCKED", "reason_code": outcome,
                      "task": task, "exam_issue": found["number"]}
        elif outcome != "CREATE_EXAM_REQUEST":
            exam_notice(request, key, outcome, found["number"] if found else None)
            result = {"status": "BLOCKED", "reason_code": outcome,
                      "task": task, **({"exam_issue": found["number"]} if found else {})}
        else:
            labels = json.loads(run("gh", "label", "list", "--repo", REPO,
                                    "--search", "exam-request", "--limit", "100",
                                    "--json", "name"))
            if not isinstance(labels, list) or len(labels) >= 100:
                deny("EXAM_REQUEST_LABELS_UNTRUSTED")
            if not any(isinstance(row, dict) and row.get("name") == "exam-request"
                       for row in labels):
                run("gh", "label", "create", "exam-request", "--repo", REPO,
                    "--description", "Independent encrypted examination requested",
                    "--color", "D4C5F9")
            created = run("gh", "issue", "create", "--repo", REPO,
                          "--title", title, "--body", body, "--label", "exam-request")
            match = re.search(r"/issues/([1-9][0-9]*)\s*$", created)
            if not match:
                deny("EXAM_REQUEST_CREATE_RECEIPT_INVALID")
            result = {"status": "BLOCKED", "reason_code": "EXAMEN_PENDIENTE",
                      "task": task, "exam_issue": int(match.group(1))}
        _EXAM_RUN_CACHE[key] = dict(result)
        return result
    except (ChainBlocked, ValueError, OSError) as exc:
        reason = str(exc)
        typed = re.findall(r"EXAM_REQUEST_[A-Z0-9_]+", reason)
        code = (typed[-1] if typed else
                "EXAM_REQUEST_LIST_UNTRUSTED"
                if any(term in reason for term in
                       ("GITHUB_LIST_", "GITHUB_RESPONSE_")) else
                "EXAM_REQUEST_UNRESOLVED")
        exam_notice(request, key, code)
        result = {"status": "BLOCKED", "reason_code": code, "task": task}
        _EXAM_RUN_CACHE[key] = dict(result)
        return result


def request_all_lot_exams(request: str, lots: dict, bindings: dict) -> list[dict]:
    """Request the exams of lots without dependencies at LOTS_PLANNED.

    Opening an exam request is not permission to register its lot: CP3.6
    still gates each successor on integrated predecessor receipts and its
    own encrypted holdout/metadata, checked again by admit_registration.
    """
    planned = {lot["id"]: lot for lot in lots["lots"]}
    if set(planned) != set(bindings):
        deny("EXAM_PLAN_BINDING_INCOMPLETE")
    outcomes = []
    for lot_id in sorted(planned):
        # An exam is written against current main. A lot with dependencies
        # gets its exam request at admission (admit_registration), once those
        # dependencies are integrated; requested earlier, its reference would
        # be built on a base its predecessors still change (req-652 BACKEND).
        if planned[lot_id].get("depends_on"):
            continue
        bound = bindings[lot_id]
        task = bound["task_name"]
        if missing_exam(ROOT, task):
            outcomes.append({"request": request, "lot_id": lot_id,
                             **request_missing_exam(request, bound, planned[lot_id])})
    return outcomes


def admit_registration(request: str, binding: dict, lot: dict, head: str) -> dict | None:
    """Inspect admission before any generated commit or native preparation."""
    try:
        require_open(request, lifecycle_api, root=ROOT)
    except RequestStateError as exc:
        return {"status": (str(exc) if str(exc) in ("REQUEST_CLOSED", "REQUEST_SUSPENDED")
                           else "BLOCKED"), "reason_code": str(exc)}
    require_green_base(head, api)
    protected_test_conflict(ROOT, lot, binding)
    if missing_exam(ROOT, binding["task_name"]):
        return request_missing_exam(request, binding, lot)
    return None


def regenerate_template(root: Path, request: str, binding: dict, completed: dict,
                        stored: dict) -> dict:
    """Current-generator template for a pending lot (T26).

    Files changed by already-integrated lots of the same request are allowed
    to drift from the analysis-time reuse hashes. Task identity and holdout
    binding stay those of the original plan.
    """
    folder = storage_path("requests_root", root=root) / request
    lots_path = folder / "lots.json"
    if not lots_path.is_file() or lots_path.is_symlink():
        deny("TEMPLATE_REGENERATION_INPUT_MISSING")
    orchestrator = str(root / "pilot/orchestrator")
    if orchestrator not in sys.path:
        sys.path.insert(0, orchestrator)
    import generate_chain
    drift = {path for proof in completed.values()
             for path in proof.get("expected_files", []) if isinstance(path, str)}
    try:
        result = generate_chain.generate(
            str(root), request, json.loads(lots_path.read_text("utf-8")),
            persist=False, allow_source_drift=drift)
    except ValueError as exc:
        code = str(exc).split(":", 1)[0]
        deny("TEMPLATE_REGENERATION_FAILED:" + (code if re.fullmatch(r"[A-Z0-9_]{1,80}", code)
                                                 else "INVALID"))
    fresh = result["templates"].get(binding["template_path"])
    if not isinstance(fresh, dict) or not isinstance(fresh.get("task_spec"), dict):
        deny("TEMPLATE_REGENERATION_TASK_MISSING")
    if fresh["task_spec"].get("task_id") != stored["task_spec"].get("task_id"):
        deny("TEMPLATE_REGENERATION_IDENTITY_CHANGED")
    if fresh != stored:
        (root / binding["template_path"]).write_bytes(generate_chain.canonical(fresh))
    return fresh


def publish_pending_plan_refresh(request: str, binding: dict, completed: dict,
                                 head: str) -> dict | None:
    """T26: a pending lot is never registered from a stale plan or template.

    Recompute the request's pending lots (affected tests, current generator)
    in a throwaway worktree. If anything changes, publish it as an auxiliary
    bot PR (lf/native-registration/plan-<task>-<sha>) and wait; the lot is
    registered by a later sweep, once main carries the refreshed plan.
    """
    from pending_plan_refresh import refresh as refresh_pending_plan, PlanRefreshBlocked
    task = binding["task_name"]
    branch = f"lf/native-registration/plan-{task}-{head[:12]}"
    # A plan draft built on an older main can never match the current plan.
    close_stale_drafts(f"lf/native-registration/plan-{task}-", head[:12])
    if (pending_draft(f"lf/native-registration/plan-{task}-")
            or run("git", "ls-remote", "--heads", "origin", branch)):
        return {"status": "PLAN_REFRESH_PENDING", "task": task, "branch": branch}
    def create(root: Path):
        try:
            changed = refresh_pending_plan(root, request, completed)
        except PlanRefreshBlocked as exc:
            deny(str(exc))
        if not changed:
            return None
        review = draft(root, branch, request, changed,
                       "T26: refresh pending lots with the current planner/generator "
                       "(affected project tests in scope, current acceptance commands); "
                       "task identity and exams unchanged.",
                       f"pending plan refresh before registering {task}")
        return {"status": "PLAN_REFRESH_DRAFT", "task": task, "paths": changed, **review}
    return worktree(head, branch, create)


def open_heads_with(prefix: str) -> list[str]:
    """Open PR head branches starting with prefix (same listing as pending_draft)."""
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO,
                          "--state", "open", "--limit", "100",
                          "--json", "headRefName"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    return [str(item.get("headRefName", "")) for item in rows if isinstance(item, dict)
            and str(item.get("headRefName", "")).startswith(prefix)]


def close_registration_drafts(task: str, comment: str) -> list[int]:
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO, "--state", "open",
                          "--limit", "100", "--json", "number,headRefName,author"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    closed = []
    for item in rows:
        ref = str(item.get("headRefName", "")) if isinstance(item, dict) else ""
        login = str((item.get("author") or {}).get("login", "")) if isinstance(item, dict) else ""
        if (ref.startswith(f"lf/native-registration/{task}-")
                and login in ("app/github-actions", "github-actions[bot]", "github-actions")):
            run("gh", "pr", "close", str(int(item["number"])), "--repo", REPO, "--delete-branch",
                "--comment", comment)
            closed.append(int(item["number"]))
    return closed


def rehearsal_reason(task: str, failed: dict) -> str:
    """Public verdict line of the failed rehearsal job (command names only)."""
    try:
        logs = github_api_raw(f"actions/jobs/{failed['job_id']}/logs")
    except Exception:
        return "REHEARSAL_FAIL"
    text = logs.decode("utf-8", "replace") if isinstance(logs, bytes) else str(logs)
    found = re.findall(re.escape(task) + r": (REHEARSAL_FAIL:[\w ./:=,-]{1,300})", text)
    return found[-1] if found else "REHEARSAL_FAIL"


def signal_exam_retry(task: str) -> str:
    """Event for the examiner routine: label the open exam request of a task
    whose exam was retired with `exam-retry` (GitHub `labeled` event), so it is
    rewritten in minutes instead of waiting for the hourly backup run. The
    examiner removes the label when it claims the task. Best effort."""
    try:
        for issue in listed_exam_requests():
            if (isinstance(issue, dict) and issue.get("state") == "open"
                    and str(issue.get("title", "")) == "EXAM_REQUEST: " + task):
                labels = {str(l.get("name")) for l in issue.get("labels", []) if isinstance(l, dict)}
                if EXAM_RETRY_LABEL in labels or "examiner-working" in labels:
                    return "EXAM_RETRY_ALREADY_SIGNALED"
                run("gh", "issue", "edit", str(int(issue["number"])), "--repo", REPO,
                    "--add-label", EXAM_RETRY_LABEL)
                return "EXAM_RETRY_SIGNALED"
    except (ChainBlocked, ValueError, OSError, subprocess.SubprocessError):
        return "EXAM_RETRY_SIGNAL_FAILED"
    return "EXAM_RETRY_NO_OPEN_REQUEST"


def retire_stale_exam(request: str, task: str, head: str, reason: str | None = None) -> dict:
    """Open one bot PR deleting exactly the stale exam's files; close the
    registration drafts built on it. Policy C re-verifies staleness on main."""
    from stale_exam import exam_paths
    prefix = f"lf/exam-retire/{task}-"
    if pending_draft(prefix):
        return {"status": "EXAM_STALE_RETIRING"}
    closed = close_registration_drafts(
        task, "Examen retirado (E2): se reescribe sobre el main actual y la tarea se "
              "registrará con el examen nuevo.")
    branch = prefix + head[:12]
    def create(root: Path):
        present = [p for p in exam_paths(request, task) if (root / p).is_file()]
        if not present:
            return {"status": "EXAM_STALE_NOTHING_TO_RETIRE"}
        run("git", "rm", "-q", "--", *present, cwd=root)
        run("git", "commit", "-m", f"[E2] retiro de examen desactualizado {task}", cwd=root)
        current_main = run("git", "ls-remote", "origin", "refs/heads/main", cwd=root).split()[0]
        if current_main != head:
            deny("MAIN_MOVED_BEFORE_DRAFT")
        run("git", "push", "--set-upstream", "origin", branch, cwd=root)
        why = (f"su referencia falla el ensayo T40 ({reason})" if reason
               else "se publicó antes de integrar una dependencia del lote")
        url = run("gh", "pr", "create", "--repo", REPO, "--base", "main", "--head", branch,
                  "--title", f"[E2] retiro de examen {task} ({request})",
                  "--body", "Elimina solo el examen cifrado, su referencia y su metadata: " + why
                  + ". Política C verifica la condición; el examinador automático lo reescribe "
                  "sobre la base real.", cwd=root)
        if reason:
            for issue in listed_exam_requests():
                if (isinstance(issue, dict) and issue.get("state") == "open"
                        and str(issue.get("title", "")).endswith(task)):
                    run("gh", "issue", "comment", str(int(issue["number"])), "--repo", REPO,
                        "--body", "Examen retirado (E2): la referencia no pasa el ensayo T40 en la "
                        f"base actual — `{reason}`. Reescribir el examen y su referencia "
                        "considerando ese comando visible.", cwd=root)
        run("gh", "workflow", "run", "ci.yml", "--repo", REPO, "--ref", branch, cwd=root)
        return {"status": "EXAM_STALE_RETIRE_PROPOSED", "retire_pr": url, "closed_registrations": closed}
    return worktree(head, branch, create)


def prepare_successor(request: str, binding: dict, completed: dict, head: str) -> dict:
    task = binding["task_name"]
    refreshed = publish_pending_plan_refresh(request, binding, completed, head)
    if refreshed is not None:
        return refreshed
    branch = f"lf/native-registration/{task}-{head[:12]}"
    if pending_draft(f"lf/native-registration/{task}-") or run("git", "ls-remote", "--heads", "origin", branch):
        return {"status": "ALREADY_PREPARED", "branch": branch}
    def process(root: Path):
        folder = root / "pilot/orchestrator"
        template_path = root / binding["template_path"]
        metadata_path = root / binding["holdout_metadata_path"]
        for file in (template_path, metadata_path):
            if not file.is_file() or file.is_symlink():
                deny("PREPARATION_INPUT_MISSING")
        template = json.loads(template_path.read_text("utf-8"))
        if not isinstance(template, dict) or not isinstance(template.get("task_spec"), dict):
            deny("PREPARATION_TEMPLATE_INVALID")
        # T26: never register a pending lot from a template written by an
        # older generator. Regenerate it from the request's committed inputs
        # with the current generator; persist the refreshed template in this
        # same registration branch so main and the registered task agree.
        template = regenerate_template(root, request, binding, completed, template)
        # Bind to NEW merged main; no stale sha from a prior lot.
        from native_lot_registration import canonical
        spec = template["task_spec"]
        spec["base_head_sha"] = head
        # Suffix attempts have an independent immutable native task identity.
        if task != binding.get("original_task_name", task):
            spec["task_id"] = "LF-WORKER-NATIVE-" + task.upper()
        # source snapshot is computed by prepare_native_lot before registration.
        from native_verified_integration import command
        sys.path.insert(0, str(root / "vendor/programming-agent/src"))
        from programming_agent_runner.hashutil import source_snapshot_sha256
        spec["source_snapshot_sha256"] = source_snapshot_sha256(root)
        # Pending templates from before T16 may contain the one unsupported
        # tracing field. Normalize only that exact historical value and
        # re-validate against the real Worker parser before invoking CP3.5.
        from worker_template_contract import normalize_legacy_registration_template
        template = normalize_legacy_registration_template(template, binding["area"])
        template_json = Path(tempfile.mkdtemp(prefix="cp36-template-")) / "task.json"
        try:
            template_json.write_bytes(canonical(template))
            with tempfile.TemporaryDirectory(prefix="cp36-proofs-") as proofs_temp:
                args = []
                for lot_id, proof in sorted(completed.items()):
                    file = Path(proofs_temp) / (lot_id + ".json")
                    file.write_bytes(canonical({k: proof[k] for k in
                        ("lot_id", "merge_sha", "expected_files")}))
                    args.extend(["--handoff-proof", str(file)])
                command_line = [
                    "python3", "pilot/orchestrator/prepare_native_lot.py",
                    "--root", str(root), "--request-id", request,
                    "--lot-id", binding["lot_id"], "--task-name", task,
                    "--template", str(template_json),
                    "--source-template", binding["template_path"],
                    "--holdout-metadata", str(metadata_path), *args]
                raw = run(*command_line, cwd=root)
                prepared = json.loads(raw)
        finally:
            template_json.unlink(missing_ok=True)
            template_json.parent.rmdir()
        if prepared.get("result") != "CP35_PREPARED_NO_MODEL_NO_PUSH":
            deny("PREPARATION_NOT_VERIFIED")
        artifact_dir = os.environ.get("CP36_PACK_OUT")
        if artifact_dir:
            import shutil
            selected = storage_path("requests_root", root=root) / request / "proposal_requests"
            destination = Path(artifact_dir)
            destination.mkdir(parents=True, exist_ok=True)
            for suffix in (".task-pack.json", ".proposal-request.json"):
                file = selected / (task + suffix)
                if not file.is_file() or file.is_symlink():
                    deny("EXPORTED_PACK_MISSING")
                shutil.copyfile(file, destination / file.name)
        # T18: commit both deterministic Worker artifacts alongside the
        # registration, rather than publishing them only as an Actions artifact.
        pack_paths = verify_published_pair(root, request, task,
                                           prepared["task_pack_sha256"])
        # CP3.5 commits registered context on this branch; the two export
        # files are still untracked until draft() stages the exact allowlist.
        paths = sorted(set(run("git", "diff", "--name-only", "origin/main", "HEAD",
                               cwd=root).splitlines()) | set(pack_paths))
        if not paths or f"{storage()['registrations_root']}/{task}.json" not in paths:
            deny("PREPARED_TASK_DIFF_INVALID")
        review = draft(root, branch, request, paths,
                       f"Registration from main {head} for lot {binding['lot_id']}; "
                       f"task {task}; base {prepared['base_head_sha']}; "
                       f"generated by prepare_native_lot.py; no model.",
                       f"native registration {task}")
        return {"status": "DRAFT_PREPARED", "task": task, **review,
                "task_pack_sha256": prepared["task_pack_sha256"]}
    return worktree(head, branch, process)


def route_request_metadata(request: str) -> bool:
    """Only T9 bot-registered req-N inputs may receive T18 repair."""
    if not re.fullmatch(r"req-[1-9][0-9]*", request):
        return False
    path = storage_path("requests_root", root=ROOT) / request / "request_meta.json"
    if path.is_symlink() or not path.is_file():
        return False
    try:
        metadata = json.loads(path.read_text("utf-8"))
    except (ValueError, UnicodeError, OSError):
        return False
    if (not isinstance(metadata, dict)
            or metadata.get("issue") != int(request[4:])
            or not isinstance(metadata.get("author"), str)
            or not metadata["author"]):
        return False
    # The request provenance itself must originate from the trusted bot
    # commit, not an unverified file merely placed in pilot/runs/.
    history = run("git", "log", "-1", "--format=%ae",
                  "--", path.relative_to(ROOT).as_posix())
    return history.strip() == "41898282+github-actions[bot]@users.noreply.github.com"


GLOBAL_SWEEP_ERRORS = frozenset({
    "BASE_NO_VERDE", "CHAIN_SWEEP_BASE_INVALID", "MAIN_DRIFT",
    "MAIN_NOT_CURRENT", "HEAD_NOT_TRAIN_MERGE",
    "HEAD_NOT_TWO_PARENT_MERGE", "TRUSTED_RUN_ENV_REQUIRED",
    "MANUAL_INTEGRATION_OUTSIDE_HISTORY", "SOURCE_WORKFLOW_UNTRUSTED",
})


def safe_failure_code(exc: Exception) -> str:
    """Preserve machine-readable detail, never a URL, path, token or response body."""
    raw = str(exc)
    # T50: only this trusted, bounded relative path may appear in a code.
    prefix = "CP36_CHAIN_EXPECTED_FILE_MISSING:"
    if raw.startswith(prefix):
        path = raw[len(prefix):]
        if (len(path) <= 180
                and re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                and not path.startswith("/")
                and ".." not in Path(path).parts):
            return raw
    if re.fullmatch(r"[A-Z][A-Z0-9_:]{1,100}", raw):
        return raw
    # CP3.6's own command wrapper emits a trusted basename plus a bounded
    # diagnostic class. Preserve it verbatim; never pass arbitrary stderr.
    if re.fullmatch(
        r"CP36_COMMAND_FAILED:[A-Za-z0-9_.-]{1,80}:"
        r"(?:STDERR_REDACTED|NO_STDERR|CP35_BLOCKED:[A-Z0-9_:-]{1,100})",
        raw,
    ):
        return raw
    status = getattr(exc, "code", None)
    status_part = f":{status}" if type(status) is int and 100 <= status <= 599 else ""
    kind = type(exc).__name__
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,50}", kind):
        kind = "Exception"
    return "CP36_LOCAL_FAILURE:" + kind + status_part


def _failure_step(code: str, phase: str) -> str:
    """Safe step identifier only, not arbitrary exception or stderr content."""
    if code.startswith("CP36_COMMAND_FAILED:"):
        match = re.fullmatch(r"CP36_COMMAND_FAILED:([A-Za-z0-9_.-]{1,80}):.*", code)
        if match:
            return match.group(1)
    if code.startswith("CONFLICT_RECOVERY_"):
        return "native-verified-integration.yml"
    return re.sub(r"[^A-Z0-9_]", "_", phase.upper())[:64]


def sweep_recovery_block(phase: str, exc: Exception, *,
                         pr: int | None = None) -> dict:
    """An unbound recovery failure never kills an independent healthy chain.

    Only audited globally fatal integrity errors are propagated.
    """
    raw = str(exc)
    code = safe_failure_code(exc)
    if code in GLOBAL_SWEEP_ERRORS:
        raise exc
    result = {"status": "BLOCKED", "phase": phase, "reason": code,
              "code": code, "step": _failure_step(code, phase)}
    if pr is not None:
        result["pr"] = pr
    return result


def per_request_block(request: str, phase: str, exc: Exception) -> dict:
    """Contain a local failure and notify only the verified issue; no labels."""
    raw = str(exc)
    code = safe_failure_code(exc)
    if code in GLOBAL_SWEEP_ERRORS:
        raise exc
    if code in ("REQUEST_STATE_UNRESOLVED", "REQUEST_CLOSED"):
        return {"request": request, "status": "BLOCKED", "phase": phase,
                "reason": code, "code": code}
    if re.fullmatch(r"req-[1-9][0-9]*", request) and route_request_metadata(request):
        try:
            number = int(request[4:])
            issue = api(f"issues/{number}")
            if (issue.get("number") == number and issue.get("state") == "open"
                    and not issue.get("pull_request")
                    and "lf-request" in {x.get("name") for x in issue.get("labels", [])}):
                marker = f"<!-- LF_CP36_LOCAL:{phase}:{code}:{request} -->"
                comments = api_list(f"issues/{number}/comments")
                if isinstance(comments, list) and len(comments) < 100 and not any(
                    marker in str(c.get("body", "")) for c in comments
                    if isinstance(c, dict) and (c.get("user") or {}).get("login")
                    == "github-actions[bot]"):
                    run("gh", "issue", "comment", str(number), "--repo", REPO,
                        "--body", marker + "\\nCP3.6 BLOCKED: " + code
                        + " durante " + phase + ". La ruta continúa con otros pedidos.")
        except (ChainBlocked, ValueError, KeyError, OSError):
            # Reporting is best effort; the request stays locally blocked.
            pass
    return {"request": request, "status": "BLOCKED", "phase": phase,
            "reason": code, "code": code, "step": _failure_step(code, phase)}


def publish_missing_registered_pack(request: str, task: str, head: str) -> dict | None:
    """T18: legacy registrations are repaired, never registered a second time.

    The historical CP3.6 artifact is authenticated against the immutable
    registration and exact-base re-export before any PR is published.
    """
    if (not re.fullmatch(r"req-[1-9][0-9]*", request)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task)):
        deny("TASK_PACK_SCOPE_INVALID")
    record = storage_path("registrations_root", root=ROOT) / (task + ".json")
    if record.is_symlink() or not record.is_file():
        return None
    pack_dir = storage_path("requests_root", root=ROOT) / request / "proposal_requests"
    paths = [f"{storage()['requests_root']}/{request}/proposal_requests/{task}{suffix}"
             for suffix in (".task-pack.json", ".proposal-request.json")]
    existing = [(ROOT / path).exists() or (ROOT / path).is_symlink()
                for path in paths]
    if all(existing):
        return None
    if any(existing):
        deny("TASK_PACK_PARTIAL_PUBLICATION")
    prefix = f"lf/native-registration/pack-{task}-"
    if pending_draft(prefix):
        return {"status": "TASK_PACK_REPAIR_PENDING", "task": task}
    branch = prefix + head[:12]
    if run("git", "ls-remote", "--heads", "origin", branch):
        return {"status": "TASK_PACK_REPAIR_PENDING", "task": task}
    try:
        reference = legacy_artifact_reference(ROOT, request, task, record, run, REPO)
        def create(root: Path):
            published = regenerate_pack_from_registered_base(
                root, request, task, reference)
            review = draft(root, branch, request, published,
                           "T18 repair exact registered Worker package from the pinned base; "
                           "the original native registration remains unchanged.",
                           f"repair task pack {task}")
            return {"status": "TASK_PACK_REPAIR_DRAFT", "task": task,
                    "task_pack_sha256": reference["task_pack_sha256"], **review}
        return worktree(head, branch, create)
    except TaskPackBlocked as exc:
        reason = str(exc)
        if reason == "TASK_PACK_HASH_MISMATCH":
            comment_task_pack_mismatch(request, task)
        deny(reason)


def publish_legacy_submission_contract(request: str, task: str, head: str) -> dict | None:
    """T19 metadata-only bot draft; never edit an existing task pack or registration."""
    from pilot.orchestrator.task_pack_publication import verify_published_pair
    if not re.fullmatch(r"req-[1-9][0-9]*", request) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
        deny("NATIVE_SUBMISSION_SCOPE_INVALID")
    relative = f"{storage()['requests_root']}/{request}/proposal_requests/{task}.proposal-request.json"
    source = ROOT / relative
    record_path = ROOT / f"{storage()['registrations_root']}/{task}.json"
    pack_path = ROOT / f"{storage()['requests_root']}/{request}/proposal_requests/{task}.task-pack.json"
    if not source.is_file() or source.is_symlink() or not pack_path.is_file() or pack_path.is_symlink():
        return None  # T18's missing-package repair handles this case.
    if record_path.is_symlink() or not record_path.is_file():
        return None
    old = json.loads(source.read_text("utf-8"))
    spec = json.loads(record_path.read_text("utf-8"))["task_spec"]
    verify_published_pair(ROOT, request, task, old["task_pack_sha256"])
    if is_current(old, spec):
        return None
    branch = f"lf/native-registration/envelope-{task}-{head[:12]}"
    if (pending_draft(f"lf/native-registration/envelope-{task}-")
            or run("git", "ls-remote", "--heads", "origin", branch)):
        return {"status": "SUBMISSION_CONTRACT_PENDING", "task": task}
    def create(root: Path):
        original = (root / relative).read_bytes()
        updated = canonical(enrich_request(old, spec))
        if original == updated:
            return {"status": "SUBMISSION_CONTRACT_CURRENT", "task": task}
        (root / relative).write_bytes(updated)
        review = draft(root, branch, request, [relative],
                       "T19: publish exact Worker envelope submission instructions; "
                       "native task, task pack and task_pack_sha256 unchanged.",
                       f"native proposal submission contract {task}")
        return {"status": "SUBMISSION_CONTRACT_DRAFT", "task": task,
                "task_pack_sha256": old["task_pack_sha256"], **review}
    return worktree(head, branch, create)


def comment_task_pack_mismatch(request: str, task: str) -> None:
    """Fail-closed, idempotent, comment only on verified original LF issue."""
    issue_number = int(request[4:])
    issue = api(f"issues/{issue_number}")
    if (issue.get("number") != issue_number or issue.get("state") != "open"
            or issue.get("pull_request")
            or "lf-request" not in {label.get("name") for label in issue.get("labels", [])}):
        return
    marker = "<!-- LF_TASK_PACK_HASH_MISMATCH:" + task + " -->"
    comments = api_list(f"issues/{issue_number}/comments")
    if not isinstance(comments, list) or len(comments) >= 100:
        deny("TASK_PACK_ISSUE_COMMENTS_INVALID")
    if any(marker in str(row.get("body", "")) for row in comments
           if isinstance(row, dict) and
           (row.get("user") or {}).get("login") == "github-actions[bot]"):
        return
    run("gh", "issue", "comment", str(issue_number), "--repo", REPO,
        "--body", marker + "\nTASK_PACK_HASH_MISMATCH: no se publica el paquete de "
        + task + ". La regeneración desde la base registrada no coincide "
        + "con el paquete original; requiere revisión. Sin re-registro ni etiquetas.")


def complete_candidate_state(state: dict, completed: dict, lots: dict) -> dict:
    """Persist source-verified completion, never a T9 terminal close by itself."""
    expected = {lot["id"] for lot in lots["lots"]}
    if (not expected or set(completed) != expected
            or state.get("stage") not in ("LOTS_PLANNED", "BLOCKED", "CHAIN_COMPLETE_CANDIDATE")
            or any(not isinstance(row.get("merge_sha"), str)
                   or not re.fullmatch(r"[0-9a-f]{40}", row["merge_sha"])
                   for row in completed.values())):
        deny("CHAIN_COMPLETION_UNVERIFIED")
    value = dict(state, stage="CHAIN_COMPLETE_CANDIDATE",
                 completed_lot_ids=sorted(expected),
                 completed_merge_shas={key: completed[key]["merge_sha"]
                                       for key in sorted(expected)},
                 production_authority=False, handoff_allowed=False,
                 downstream_authorized=False)
    value.pop("blocked_lot_ids", None)
    value.pop("reason_code", None)
    return value


def reconcile_complete_chain(request: str, state: dict, lots: dict,
                             completed: dict, head: str, *, sweep: bool) -> dict:
    """Only the route retires superseded bot BLOCKED drafts; main changes via Train."""
    if not sweep:
        return {"status": "CHAIN_COMPLETE_CANDIDATE"}
    retired = close_stale_drafts(f"lf/chain-blocked/{request}-", head[:12])
    if state["stage"] == "CHAIN_COMPLETE_CANDIDATE":
        return {"status": "CHAIN_COMPLETE_CANDIDATE", "retired_blocked_prs": retired}
    prefix = f"lf/chain-complete/{request}-"
    # Like CP3.7 evidence drafts: a bot candidate anchored to an older main
    # (e.g. conflicting after other merges) is superseded, then regenerated.
    close_stale_drafts(prefix, head[:12])
    if pending_draft(prefix):
        return {"status": "CHAIN_COMPLETE_DRAFT_PENDING", "retired_blocked_prs": retired}
    branch = prefix + head[:12]
    def prepare(root: Path):
        target = storage_path("requests_root", root=root) / request / "state.json"
        target.write_bytes(canonical(complete_candidate_state(state, completed, lots)))
        review = draft(root, branch, request, [target.relative_to(root).as_posix()],
                       "First-parent Train history verifies every lot integrated; "
                       "candidate only until H_REPORT and registry on main",
                       f"CHAIN_COMPLETE_CANDIDATE {request}")
        return {"status": "CHAIN_COMPLETE_DRAFT", **review}
    return {"retired_blocked_prs": retired, **worktree(head, branch, prepare)}


def block_request(request: str, state: dict, result: dict, head: str) -> dict:
    branch = f"lf/chain-blocked/{request}-{head[:12]}"
    if pending_draft(f"lf/chain-blocked/{request}-") or run("git", "ls-remote", "--heads", "origin", branch):
        return {"status": "BLOCKED_ALREADY_RECORDED", "branch": branch}
    reason_code = result["reason_code"]
    def process(root: Path):
        target = storage_path("requests_root", root=root) / request / "state.json"
        target.write_bytes(canonical(blocked_state(state, result)))
        review = draft(root, branch, request, [target.relative_to(root).as_posix()],
                       reason_code + " after three Actions-proven " +
                       ("unique format rejections" if reason_code == FORMAT_BLOCK_CODE else "failed attempts") + "; "
                       "state update requires owner-reviewed Train merge.",
                       f"BLOCKED {request} ({reason_code})")
        return {"status": "BLOCKED_PENDING_OWNER_MERGE", "reason_code": reason_code,
                **review}
    return worktree(head, branch, process)



def draft_implemented_registry(root: Path, branch: str, head: str) -> dict:
    """Trusted CP3.6 publishes one generated JSON, without CHG or manual label."""
    path = "pilot/registry/implemented.json"
    run("git", "add", "--", path, cwd=root)
    synchronize(root, "registry")
    if not run("git", "diff", "--cached", "--name-only", cwd=root).strip() == path:
        deny("REGISTRY_CHANGED_PATHS_INVALID")
    run("git", "commit", "-m", "[CP3.6] generated implementation registry", cwd=root)
    current_main = run("git", "ls-remote", "origin", "refs/heads/main", cwd=root).split()[0]
    if current_main != head:
        deny("MAIN_MOVED_BEFORE_DRAFT")
    run("git", "push", "--set-upstream", "origin", branch, cwd=root)
    url = run("gh", "pr", "create", "--repo", REPO, "--base", "main",
              "--head", branch, "--draft",
              "--title", "[DRAFT][CP3.6] registro generado de implementaciones",
              "--body", "Únicamente pilot/registry/implemented.json. Política C verifica "
              "regeneración idéntica en main y aplica etiqueta por bot; Train fusiona.",
              cwd=root)
    run("gh", "workflow", "run", "ci.yml", "--repo", REPO, "--ref", branch, cwd=root)
    return {"draft_pr": url, "head_sha": run("git", "rev-parse", "HEAD", cwd=root)}


def same_registry_entries(raw: bytes | None, ledger: dict) -> bool:
    """A registry draft is still current when its entries equal the regeneration
    on the current main; source_main_sha only records where it was generated."""
    try:
        value = json.loads(raw) if raw is not None else None
    except ValueError:
        return False
    return (isinstance(value, dict)
            and value.get("schema_version") == ledger.get("schema_version")
            and value.get("entries") == ledger.get("entries"))


def open_bot_drafts(prefix: str) -> list[str]:
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO, "--state", "open",
                          "--limit", "100", "--json", "headRefName,author"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    return [str(item["headRefName"]) for item in rows
            if isinstance(item, dict) and str(item.get("headRefName", "")).startswith(prefix)
            and str((item.get("author") or {}).get("login", "")) in
                ("app/github-actions", "github-actions[bot]", "github-actions")]


def draft_file(ref: str, path: str) -> bytes | None:
    """Exact blob bytes of a file on a bot branch (data only, never executed)."""
    import base64
    from urllib.parse import quote
    try:
        data = api(f"contents/{path}?ref={quote(ref, safe='')}")
        if data.get("type") != "file" or data.get("encoding") != "base64":
            return None
        return base64.b64decode("".join(str(data.get("content", "")).split()), validate=True)
    except (ValueError, TypeError):
        return None


def sync_implemented_registry(head: str) -> dict:
    """CP3.6 trusted main merge consumer is the sole registry writer.

    It stages the ledger in a Draft PR: Train-only main remains enforced.
    No labels or direct main writes. Historical seed uses the same derivation.
    """
    from implemented_registry import reconstruct, save
    from implemented_registry import CLOSED_PULLS, batched_pr_reader
    result = reconstruct(ROOT, head, batched_pr_reader(
        lambda: api_list(CLOSED_PULLS, max_pages=10), lambda number: api(f"pulls/{number}")))
    current = ROOT / "pilot/registry/implemented.json"
    old = json.loads(current.read_text("utf-8")) if current.exists() else None
    if old is not None and old.get("entries") == result["entries"]:
        return {"status": "REGISTRY_CURRENT"}
    branch = "lf/implemented-registry/" + head[:12]
    # The registry is content-addressed: it changes only when a lot is
    # integrated, not with every main commit. A draft whose bytes equal the
    # regeneration on the current main stays open for policy C and Train;
    # only a draft with different content is superseded.
    keep = [ref for ref in open_bot_drafts("lf/implemented-registry/")
            if same_registry_entries(draft_file(ref, "pilot/registry/implemented.json"), result)]
    if keep:
        return {"status": "REGISTRY_PENDING_REVIEW", "draft": keep[0]}
    close_stale_drafts("lf/implemented-registry/", head[:12])
    if pending_draft("lf/implemented-registry/"):
        return {"status": "REGISTRY_PENDING_REVIEW"}
    def create(root: Path):
        if not save(root, result):
            return {"status": "REGISTRY_CURRENT"}
        return draft_implemented_registry(root, branch, head)
    return {"status": "REGISTRY_DRAFT", **worktree(head, branch, create)}


def verify_new_plan(request: str, merge_pr: int, sha: str) -> None:
    """Side-effect gate: exact generated-T7 Train merge, not an old plan."""
    if (not re.fullmatch(r"req-[1-9][0-9]*", request)
            or type(merge_pr) is not int or merge_pr < 1):
        deny("EXAM_PLAN_PROVENANCE_INVALID")
    pr = api(f"pulls/{merge_pr}")
    if (pr.get("merged") is not True or pr.get("merge_commit_sha") != sha
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO
            or not re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}",
                                pr.get("head", {}).get("ref", ""))):
        deny("EXAM_PLAN_PROVENANCE_INVALID")
    changed = set(run("git", "diff", "--name-only", sha + "^1", sha).splitlines())
    if f"{storage()['requests_root']}/{request}/chain_plan.json" not in changed:
        deny("EXAM_PLAN_PROVENANCE_INVALID")
    metadata = json.loads((storage_path("requests_root", root=ROOT) / request /
                           "request_meta.json").read_text("utf-8"))
    if metadata.get("issue") != int(request[4:]):
        deny("EXAM_PLAN_PROVENANCE_INVALID")
    require_green_base(sha, api)


def process(event_run_id: int | None = None, integration_pr: int | None = None,
            new_plan_request: str | None = None,
            new_plan_pr: int | None = None, *,
            sweep: bool = False, base_sha: str | None = None,
            require_ci: bool = False) -> list[dict]:
    head = check_main()
    if sweep and (base_sha != head or not re.fullmatch(r"[0-9a-f]{40}", base_sha or "")):
        deny("CHAIN_SWEEP_BASE_INVALID")
    manual_sha = (validated_manual_integration(integration_pr, head)
                  if integration_pr is not None else None)
    kind = ("TRAIN" if sweep or manual_sha is not None
            else event_kind(event_run_id, head))
    if kind == "IRRELEVANT":
        return [{"status": "IGNORED_SOURCE_EVENT"}]
    # Production entrypoint always checks CI before mutating anything.
    # Older offline process() fixtures exercise logic without GitHub API.
    if kind == "TRAIN" and (sweep or require_ci):
        ci_status = main_ci_decision(head)
        if ci_status != "GREEN":
            return [{"status": ci_status, "head_sha": head}]
    all_plans = plans()
    owners = {}
    complete_tasks = set()
    for request, _lots, _state, bindings in all_plans:
        for binding in bindings.values():
            task = binding.get("task_name") if isinstance(binding, dict) else None
            if isinstance(task, str):
                owners.setdefault(task, set()).add(request)
                if _state.get("stage") == "CHAIN_COMPLETE_CANDIDATE":
                    complete_tasks.add(task)

    def pending_task_live(task: str) -> bool:
        # Do not inspect old proposal refs without a plan or after a verified
        # completion. Other recovery phases retain the normal task_live gate.
        if task not in owners:
            return False
        if len(owners[task]) != 1:
            return task_live(task)  # preserve fail-closed ambiguous ownership
        if task in complete_tasks:
            return False
        return task_live(task)

    def task_live(task: str) -> bool:
        candidates = owners.get(task, set())
        # An old proposal branch with no active plan is not a route failure.
        # Ambiguous ownership must still fail closed for this task alone.
        if not candidates:
            return False
        if len(candidates) != 1:
            raise RequestStateError("REQUEST_STATE_UNRESOLVED")
        return request_state(next(iter(candidates)), lifecycle_api, root=ROOT) == OPEN

    def candidate_live(row: dict) -> bool:
        if row["kind"] == "implemented-registry":
            return True
        request = conflicted_request(row, all_plans)
        if request is None:
            raise RequestStateError("REQUEST_STATE_UNRESOLVED")
        return request_state(request, lifecycle_api, root=ROOT) == OPEN

    # Global conflict retirement runs before ALREADY_PREPARED / ALREADY_LABELED
    # can hide a Train failure, including when no owner plans are active.
    retired = []
    recovery_failures = []
    kept = []
    if sweep:
        try:
            with budget.phase("T17_4_RETIRE"):
                recovered = retire_conflicted_generated(
                    head, run, api, REPO, api_list,
                    allow_candidate=candidate_live)
            for entry in recovered:
                if entry.get("status") in ("BLOCKED", "REQUEST_CLOSED"):
                    recovery_failures.append(entry)
                elif entry.get("status") == "KEPT":
                    kept.append(entry)
                else:
                    retired.append(entry)
        except (ChainBlocked, IntegrationBlocked, AdmissionBlocked,
                OSError, ValueError, KeyError, TypeError) as exc:
            recovery_failures.append(sweep_recovery_block("T17_4_RETIRE", exc))
    # R1: a periodic sweep can replace the event that would have published
    # the first-parent registry. Recover that same idempotent draft from main,
    # but preserve the no-op guarantee when there are no owner chain plans.
    with budget.phase("REGISTRY"):
        registry_status = (sync_implemented_registry(head)
                           if kind == "TRAIN" and (not sweep or bool(all_plans))
                           else None)
    # Each recovery is a separate trust boundary. A local failure may not
    # short-circuit later recoveries or per-request planning.
    repair_outcomes = list(recovery_failures) + kept
    if sweep:
        from pilot.orchestrator.native_format_recovery import Recovery as FormatRecovery
        format_recovery = FormatRecovery(run, api, REPO, ROOT)
        def format_task_live(task):
            # Only registered, actively owned tasks can have format evidence.
            # Do not query Actions for plans still awaiting registration.
            registration = storage_path("registrations_root", task + ".json", root=ROOT)
            return (registration.is_file() and not registration.is_symlink()
                    and format_recovery.enabled(task) and task_live(task))
        recoveries = (
            ("T20_BOT_CI_RETRY",
             lambda: retry_failed_bot_prs(
                 head, run, api, REPO, all_plans, route_request_metadata,
                 api_list,
                 allow_pr=lambda number, branch: candidate_live({
                     "number": number, "branch": branch,
                     "kind": ("generated-t7" if branch.startswith(
                         "lf/generated-t7/") else
                         "registration" if branch.startswith(
                             "lf/native-registration/") else
                         "integration" if branch.startswith(
                             "lf/native-integration/") else
                         "implemented-registry")}))),
            ("R1_WORKER_PENDING",
             lambda: recover_pending_worker(
                 head, run, api, REPO, ROOT, allowed_task=pending_task_live,
                 format_decision=format_recovery.pending_decision)
             if owners else []),
            ("T20_NATIVE_INFRA",
             lambda: retry_native_infra(
                 head, run, api, REPO, ROOT, allowed_task=task_live,
                 format_decision=format_recovery.decision)),
            ("T22_FEEDBACK",
             lambda: recover_native_feedback(run, api, REPO, ROOT)),
            ("FORMAT_FEEDBACK",
             lambda: format_recovery.recover_feedback(format_task_live)
             if any(format_task_live(task) for task in owners) else []),
            ("T23_ROUTE",
             lambda: recover_route_defects(
                 head, run, api, REPO, ROOT, worktree, draft, pending_draft,
                 api_list=api_list, allowed_task=task_live,
                 format_decision=format_recovery.decision)),
        )
        for phase, action in recoveries:
            try:
                with budget.phase(phase):
                    repair_outcomes.extend(action())
            except (ChainBlocked, IntegrationBlocked, AdmissionBlocked,
                    OSError, ValueError, KeyError, TypeError) as exc:
                repair_outcomes.append(sweep_recovery_block(phase, exc))
    # T25: T17.4 retired a mechanically red integration and its remote
    # branch. Its one trusted CP3.5 re-dispatch is owned by
    # regenerate_conflicted, not by historical T24 replay.
    ci_retired_tasks = {
        match.group(1) for row in retired
        if row.get("kind") == "integration"
        for match in [re.fullmatch(
            r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-[1-9][0-9]*",
            row.get("branch", ""))] if match
    }
    # T24.1: dispatch an already-PASS Worker integration before per-lot
    # progress. Isolate each request: one corrupted scope must never hold
    # back a different request's attested CP3.5 replay.
    if sweep:
        for request, _lots, _state, bindings in all_plans:
            try:
                if not route_request_metadata(request):
                    continue
                current = request_state(request, lifecycle_api, root=ROOT)
                if current != OPEN:
                    repair_outcomes.append({"request": request,
                                            "status": inactive_reason(current)})
                    continue
                tasks = {value.get("task_name") for value in bindings.values()
                         if isinstance(value, dict)
                         and isinstance(value.get("task_name"), str)} - ci_retired_tasks
                for outcome in replay_native_integration(
                        head, run, api, REPO, ROOT, allowed_tasks=tasks):
                    repair_outcomes.append({"request": request, **outcome})
                for outcome in recover_unstarted_integration(
                        head, run, api, REPO, ROOT, allowed_tasks=tasks):
                    repair_outcomes.append({"request": request, **outcome})
            except (ChainBlocked, IntegrationBlocked, AdmissionBlocked,
                    OSError, ValueError, KeyError) as exc:
                repair_outcomes.append(
                    per_request_block(request, "INTEGRATION_REPLAY", exc))
    if sweep:
        for request, _lots, _state, bindings in all_plans:
            if not route_request_metadata(request):
                repair_outcomes.append({"request": request,
                                        "status": "SKIPPED_NOT_ROUTE_REQUEST"})
                continue
            try:
                current = request_state(request, lifecycle_api, root=ROOT)
                if current != OPEN:
                    repair_outcomes.append({"request": request,
                                            "status": inactive_reason(current)})
                    continue
            except RequestStateError:
                repair_outcomes.append({"request": request, "status": "BLOCKED",
                                        "reason_code": "REQUEST_STATE_UNRESOLVED"})
                continue
            for task in sorted({item.get("task_name") for item in bindings.values()
                                if isinstance(item, dict)
                                and isinstance(item.get("task_name"), str)}):
                try:
                    fixed = publish_missing_registered_pack(request, task, head)
                    if fixed is not None:
                        repair_outcomes.append({"request": request, **fixed})
                    # Existing published packs need only a metadata upgrade.
                    # This is separate from native registration and never
                    # changes the stored Worker task nor its package SHA.
                    if fixed is None:
                        upgraded = publish_legacy_submission_contract(request, task, head)
                        if upgraded is not None:
                            repair_outcomes.append({"request": request, **upgraded})
                except (ChainBlocked, IntegrationBlocked, AdmissionBlocked,
                        OSError, ValueError, KeyError) as exc:
                    repair_outcomes.append(per_request_block(request, "PACK_REPAIR", exc))
    conflict_outcomes = list(repair_outcomes)
    for stale in retired:
        try:
            outcome = regenerate_conflicted(stale, head, all_plans)
            if (outcome.get("status") == "BLOCKED"
                    and outcome.get("code") == "CONFLICT_RECOVERY_CP35_PREVIOUSLY_FAILED"):
                notify_failed_conflict_replay(stale, all_plans, outcome["failed_run_id"])
            conflict_outcomes.append({"pr": stale["number"], "branch": stale["branch"],
                                      "kind": stale["kind"], **outcome})
        except (ChainBlocked, IntegrationBlocked, AdmissionBlocked,
                OSError, ValueError, KeyError) as exc:
            request = conflicted_request(stale, all_plans)
            if request:
                block = per_request_block(request, "CONFLICT_RECOVERY", exc)
            else:
                block = sweep_recovery_block("CONFLICT_RECOVERY", exc,
                                             pr=stale["number"])
            block["pr"] = stale["number"]
            block["branch"] = stale["branch"]
            conflict_outcomes.append(block)
    if not all_plans:
        return conflict_outcomes or [{"status": "NO_OWNER_REGISTERED_CHAIN_PLANS",
                 **({"registry": registry_status} if registry_status else {})}]
    # History must be scoped to each plan; one damaged plan must not
    # prevent independent requests from proceeding.
    # Historical first-parent commits are the proof. Reconcile all merged
    # native integrations so an unrelated Train merge between the source
    # event and this job cannot silently lose a successor.
    if new_plan_request is not None:
        if kind != "TRAIN" or manual_sha is not None or new_plan_pr is None:
            deny("EXAM_PLAN_PROVENANCE_INVALID")
        verify_new_plan(new_plan_request, new_plan_pr, head)
        if not any(request == new_plan_request and state.get("stage") == "LOTS_PLANNED"
                   for request, lots, state, bindings in all_plans):
            deny("EXAM_PLAN_NOT_READY")
    outcomes = list(conflict_outcomes)
    for request, lots, state, bindings in all_plans:
        try:
            with budget.phase("CHAIN"):
                outcomes.extend(process_one_plan(
                    request, lots, state, bindings, head, kind, sweep,
                    new_plan_request, manual_sha, first_parent_merges(request),
                    **({"format_exhausted": format_recovery.exhausted_tasks}
                       if sweep and format_recovery.exhausted_tasks else {})))
        except (ChainBlocked, IntegrationBlocked, AdmissionBlocked,
                OSError, ValueError, KeyError) as exc:
            outcomes.append(per_request_block(request, "CHAIN", exc))
    if registry_status is not None and registry_status.get("status") == "REGISTRY_DRAFT":
        outcomes.append(registry_status)
    return outcomes or [{"status": "NO_RELEASE_OR_BLOCK"}]


def process_one_plan(request, lots, state, bindings, head, kind, sweep,
                     new_plan_request, manual_sha, history, *, format_exhausted=()) -> list[dict]:
    outcomes = []
    try:
        current = request_state(request, lifecycle_api, root=ROOT)
    except RequestStateError:
        return [{"request": request, "status": "BLOCKED",
                 "reason_code": "REQUEST_STATE_UNRESOLVED"}]
    if current != OPEN:
        return [{"request": request, "status": inactive_reason(current)}]
    # Historical Train receipts take precedence over attempt exhaustion.
    # Resolve completion before exam re-requests or the failed Worker ledger.
    completed = completed_lots(lots, bindings, history)
    if manual_sha is not None and not any(
            proof["merge_sha"] == manual_sha for proof in completed.values()):
        return outcomes
    if len(completed) == len(lots["lots"]):
        outcomes.append({"request": request, **reconcile_complete_chain(
            request, state, lots, completed, head, sweep=sweep and kind == "TRAIN")})
        return outcomes
    if state.get("stage") == "CHAIN_COMPLETE_CANDIDATE":
        deny("CHAIN_COMPLETION_HISTORY_REGRESSED")
    if state.get("stage") == "BLOCKED":
        outcomes.append({"request": request, "status": "ALREADY_BLOCKED"})
        return outcomes
    format_lots = sorted(lot for lot, binding in bindings.items()
                         if lot not in completed and binding["task_name"] in format_exhausted)
    if format_lots:
        result = {"stage":"BLOCKED", "reason_code":FORMAT_BLOCK_CODE,
                  "blocked_lot_ids":format_lots, "ready_lot_ids":[],
                  "production_authority":False,"handoff_allowed":False}
        return [{"request":request, **block_request(request,state,result,head)}]
    # Only the Train-merged native registration can complete its exam
    # issue. A ciphertext already on main permits draft preparation first.
    if kind == "TRAIN":
        closed = complete_registered_exam_requests(request, bindings)
        if closed:
            outcomes.append({"request": request, "status": "EXAM_ALREADY_REGISTERED",
                             "closed_exam_issues": closed})
    if request == new_plan_request or sweep:
        outcomes.extend(request_all_lot_exams(request, lots, bindings))
    failures = failed_lots(bindings)
    result = progress(lots, completed, failures, bindings)
    if result["stage"] == "BLOCKED":
        outcomes.append({"request": request, **block_request(request, state, result, head)})
        return outcomes
    if kind != "TRAIN":
        return outcomes
    for lot_id in result["ready_lot_ids"]:
        lot = next(x for x in lots["lots"] if x["id"] == lot_id)
        if not set(lot["depends_on"]).issubset(completed):
            continue
        task = bindings[lot_id]["task_name"]
        # Only public/source and template drift can require a new attempt.
        # Never overwrite a registered task or reuse an old examiner SHA.
        registered = storage_path("registrations_root", root=ROOT) / (task + ".json")
        if registered.exists() or registered.is_symlink():
            def relevant_base_diff(base_sha: str) -> set[str]:
                run("git", "merge-base", "--is-ancestor", base_sha, head)
                return set(run("git", "diff", "--name-only", base_sha, head).splitlines())
            candidate = registration_variant(
                ROOT, task, bindings[lot_id]["template_path"],
                relevant_base_diff)
        else:
            candidate = task
        if candidate is None:
            continue
        chosen = dict(bindings[lot_id], task_name=candidate,
                      original_task_name=task, lot_id=lot_id,
                      area=lot["area"])
        if candidate != task:
            metadata = Path(chosen["holdout_metadata_path"])
            chosen["holdout_metadata_path"] = str(
                metadata.with_name(candidate + metadata.suffix))
        if sweep:
            retired = close_failed_old_registration_drafts(candidate, head)
            if retired:
                outcomes.append({"request": request, "lot_id": lot_id,
                                 "status": "STALE_REGISTRATION_RETIRED",
                                 "closed_prs": retired})
        # E2: an exam published before a dependency was integrated was written
        # against a base that dependency changed; retire it (governed PR) so
        # the automatic examiner rewrites it on current main.
        from stale_exam import is_stale
        dependency_tasks = [bindings[d]["task_name"] for d in lot["depends_on"] if d in bindings]
        if candidate == task and is_stale(ROOT, task, dependency_tasks):
            outcomes.append({"request": request, "lot_id": lot_id,
                             **retire_stale_exam(request, task, head)})
            continue
        # E2: a fresh exam whose reference fails its T40 rehearsal is retired
        # too (at most MAX_REHEARSAL_RETIRES per task); the examiner is told
        # which public visible command failed.
        if candidate == task and pending_draft(f"lf/native-registration/{candidate}-"):
            from stale_exam import rehearsal_failure, retire_count, MAX_REHEARSAL_RETIRES
            # The 100 most recent PRs: a live request's registration and retire
            # PRs are always among them (full history is not needed here).
            closed_pulls = lambda: json.loads(github_api_raw(
                "pulls?state=all&sort=created&direction=desc&per_page=100"))
            try:
                failed = rehearsal_failure(closed_pulls, lambda sha: api(
                    f"commits/{sha}/check-runs?per_page=100").get("check_runs", []), task)
                retires = retire_count(ROOT, task, dependency_tasks) if failed is not None else 0
            except Exception:
                # Recovery only: if GitHub cannot be read, retire nothing.
                failed = None
            if failed is not None and retires < MAX_REHEARSAL_RETIRES:
                outcomes.append({"request": request, "lot_id": lot_id,
                                 **retire_stale_exam(request, task, head,
                                                     reason=rehearsal_reason(task, failed))})
                continue
        if pending_draft(f"lf/native-registration/{candidate}-"):
            from stale_exam import exam_retired
            if candidate == task and exam_retired(ROOT, task):
                # Its exam was retired (E2): the draft points to a removed
                # holdout. Close it so admission requests and binds the new exam.
                outcomes.append({"request": request, "lot_id": lot_id,
                                 "status": "REGISTRATION_WITHOUT_EXAM_CLOSED",
                                 "closed_prs": close_registration_drafts(
                                     task, "El examen de esta tarea fue retirado (E2); "
                                           "se registrará con el examen nuevo.")})
                continue
            outcomes.append({"request": request, "lot_id": lot_id,
                             "status": "ALREADY_PREPARED"})
            continue
        if candidate == task and pending_draft(f"lf/exam-retire/{task}-"):
            # Never prepare a registration on an exam whose retire is pending.
            outcomes.append({"request": request, "lot_id": lot_id,
                             "status": "EXAM_STALE_RETIRING"})
            continue
        admission = admit_registration(request, chosen, lot, head)
        if admission is not None:
            from stale_exam import exam_retired
            if candidate == task and exam_retired(ROOT, task):
                admission = {**admission, "exam_retry": signal_exam_retry(task)}
            outcomes.append({"request": request, "lot_id": lot_id, **admission})
            continue
        outcomes.append({"request": request, "lot_id": lot_id,
                         **prepare_successor(request, chosen, completed, head)})
    return outcomes




def main() -> int:
    _EXAM_RUN_CACHE.clear()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--integration-pr", type=int)
    parser.add_argument("--new-plan-request")
    parser.add_argument("--new-plan-pr", type=int)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--base-sha")
    args = parser.parse_args()
    try:
        if (os.environ.get("GITHUB_REPOSITORY") != REPO
                or not os.environ.get("GH_TOKEN")
                or (args.sweep and (args.source_run_id is not None
                    or args.integration_pr is not None
                    or args.new_plan_request is not None
                    or args.new_plan_pr is not None))
                or (not args.sweep and args.base_sha is not None)
                or (not args.sweep and args.integration_pr is None and
                    (args.source_run_id is None or args.source_run_id <= 0))
                or (not args.sweep and args.integration_pr is not None and
                    (args.integration_pr <= 0 or args.source_run_id is not None))):
            deny("TRUSTED_RUN_ENV_REQUIRED")
        with (budget.session() if args.sweep else nullcontext()):
            print(json.dumps(process(args.source_run_id, args.integration_pr,
                                     args.new_plan_request, args.new_plan_pr,
                                     sweep=args.sweep, base_sha=args.base_sha,
                                     require_ci=True), sort_keys=True))
    except (ChainBlocked, IntegrationBlocked, AdmissionBlocked, OSError, ValueError, KeyError) as exc:
        code = safe_failure_code(exc)
        if args.sweep and code.startswith("GITHUB_TRANSITORIO:"):
            # Produce a structured retry signal even before plan discovery.
            print(json.dumps([{"status": "BLOCKED", "phase": "GLOBAL",
                               "reason": code}], sort_keys=True))
            return 0
        print(code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
