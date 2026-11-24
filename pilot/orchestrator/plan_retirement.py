"""Governed retirement of registered but unexecuted plans (CHG-0326).

All external evidence is read by trusted control-plane code. No proposal
branch or PR-authored code is executed. Incomplete collections fail closed.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re
from urllib.parse import quote

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
PLAN = re.compile(r"pilot/(?:runs/([a-z][a-z0-9_-]*)/chain_plan|orchestrator/chain_plans/([a-z][a-z0-9_-]*))[.]json\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class RetirementBlocked(ValueError):
    pass


def fail():
    raise RetirementBlocked("CHAIN_HISTORY_INCOMPLETE")


def tasks_for(plan):
    try:
        rows = plan["bindings"]
        tasks = {row["task_name"] for row in rows}
        if not isinstance(rows, list) or not rows or len(tasks) != len(rows):
            fail()
        if any(not isinstance(task, str) or not TASK.fullmatch(task) for task in tasks):
            fail()
        return tasks
    except (KeyError, TypeError, AttributeError):
        fail()


def registration_paths(request, task):
    return (
        f"pilot/worker_v08/native_tasks/{task}.json",
        f"pilot/runs/{request}/proposal_requests/{task}.task-pack.json",
        f"pilot/runs/{request}/proposal_requests/{task}.proposal-request.json",
        f".lf/worker-context/{task}/",
    )


def artifacts(files, request, task):
    reg, pack, handoff, context = registration_paths(request, task)
    return {p for p in files if p in (reg, pack, handoff) or p.startswith(context)}


def verify_removed(before, after, request, task, *, historical=None):
    """Require the entire registered artifact set to disappear in one transition."""
    old = artifacts(before, request, task)
    if artifacts(after, request, task):
        fail()
    if historical is not None and old != historical:
        fail()
    if old:
        reg, pack, handoff, context = registration_paths(request, task)
        if not {reg, pack, handoff, context + "receipt.json"} <= old:
            fail()
    if f"pilot/native_proposals/{task}.json" in before | after:
        fail()
    return bool(old)


def _date(value):
    if not isinstance(value, str):
        fail()
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            fail()
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        fail()


def _pages(api, route, key=None):
    """Bounded exhaustive pagination, with count and unique identity checks."""
    seen = set()
    expected = None
    for page in range(1, 11):
        sep = "&" if "?" in route else "?"
        response = api(f"{route}{sep}per_page=100&page={page}")
        if key:
            if not isinstance(response, dict):
                fail()
            count, rows = response.get("total_count"), response.get(key)
            if type(count) is not int or not 0 <= count <= 1000:
                fail()
            if expected is not None and count != expected:
                fail()
            expected = count
        else:
            rows = response
        if not isinstance(rows, list) or len(rows) > 100:
            fail()
        for row in rows:
            if not isinstance(row, dict):
                fail()
            identifier = row.get("id") if not route.startswith("commits?") else row.get("sha")
            if ((not isinstance(identifier, str) or not SHA.fullmatch(identifier))
                    if route.startswith("commits?") else type(identifier) is not int) or identifier in seen:
                fail()
            seen.add(identifier)
            yield row
        if len(rows) < 100 or (expected is not None and len(seen) == expected):
            if expected is not None and len(seen) != expected:
                fail()
            return
    fail()


def verify_no_execution(api, tasks, start, end, *, live=False):
    """Check proposal push and Worker histories, and all integration PR states.

    The interval is inclusive so same-second events cannot evade the guard.
    Current proposal refs additionally block a live retirement.
    """
    begin, finish = _date(start), _date(end)
    if begin > finish:
        fail()
    # GitHub's filtered run search is capped at 1000; _pages rejects truncation.
    created = quote(begin.isoformat().replace("+00:00", "Z") + ".." +
                    finish.isoformat().replace("+00:00", "Z"), safe="")
    for workflow in ("worker-native-trigger.yml", "worker-native.yml"):
        for row in _pages(api, f"actions/workflows/{workflow}/runs?created={created}", "workflow_runs"):
            branch, title = row.get("head_branch"), row.get("display_title")
            if not isinstance(branch, str) or not isinstance(title, str):
                fail()
            if not begin <= _date(row.get("created_at")) <= finish:
                fail()
            if workflow == "worker-native-trigger.yml":
                if not branch.startswith("lf/native-proposal/"):
                    fail()
                if any(branch == "lf/native-proposal/" + task for task in tasks):
                    fail()
            else:
                # Every native run is relevant, including skipped/failed/queued.
                if any(re.search(r"(?<![a-z0-9_])" + re.escape(task) +
                                 r"(?![a-z0-9_])", title) for task in tasks):
                    fail()
                # Unknown title shape is incomplete evidence, not a negative.
                if not title.startswith("lf-native-"):
                    fail()
    # No search-index dependency: enumerate PRs, including closed/unmerged.
    for row in _pages(api, "pulls?state=all&sort=created&direction=desc"):
        branch = row.get("head", {}).get("ref")
        if not isinstance(branch, str):
            fail()
        if begin <= _date(row.get("created_at")) <= finish and any(
                branch.startswith(f"lf/native-integration/{task}-run-")
                or branch == f"lf/native-proposal/{task}" for task in tasks):
            fail()
    if live:
        for task in sorted(tasks):
            for prefix in ("lf/native-proposal/", "lf/native-integration/"):
                refs = api("git/matching-refs/heads/" + prefix + task)
                if not isinstance(refs, list):
                    fail()
                for row in refs:
                    name = row.get("ref") if isinstance(row, dict) else None
                    if not isinstance(name, str):
                        fail()
                    if name == "refs/heads/" + prefix + task or name.startswith(
                            "refs/heads/" + prefix + task + "-run-"):
                        fail()


def _tree(api, sha):
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        fail()
    obj = api(f"git/trees/{sha}?recursive=1")
    if not isinstance(obj, dict) or obj.get("truncated") is not False:
        fail()
    rows = obj.get("tree")
    if not isinstance(rows, list):
        fail()
    result = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            fail()
        if row.get("type") == "blob":
            if row["path"] in result:
                fail()
            result.add(row["path"])
    return result


def _plan(api, path, sha):
    obj = api(f"contents/{path}?ref={sha}")
    try:
        if obj["encoding"] != "base64":
            fail()
        return json.loads(base64.b64decode(obj["content"]))
    except (KeyError, TypeError, ValueError):
        fail()


def validate_train_retirement(api, base, head, files):
    """Run on trusted Train before a merge, using exact base/head trees."""
    if not isinstance(files, list):
        fail()
    plans = []
    for row in files:
        if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
            fail()
        match = PLAN.fullmatch(row["filename"])
        if match and row.get("status") == "removed":
            plans.append((match.group(1) or match.group(2), row["filename"]))
        if row.get("status") == "renamed" and PLAN.fullmatch(row.get("previous_filename", "")):
            fail()
    if not plans:
        # Registration removals are only permitted with their plan removal.
        if any(row.get("status") in ("removed", "renamed") and
               (row.get("previous_filename", row["filename"]).startswith(
                   ("pilot/worker_v08/native_tasks/", ".lf/worker-context/"))
                or "/proposal_requests/" in row.get("previous_filename", row["filename"]))
               for row in files):
            fail()
        return
    before, after = _tree(api, base), _tree(api, head)
    for request, path in plans:
        if path not in before or path in after:
            fail()
        tasks = tasks_for(_plan(api, path, base))
        if not any(artifacts(before, request, task) for task in tasks):
            continue  # Legacy unregistered retirement remains governed by CHG-0291.
        for task in tasks:
            verify_removed(before, after, request, task)
        # Earliest visible commit of this plan path is conservative (includes
        # previous plan lifetimes); a missing or truncated history blocks.
        commits = list(_pages(api, "commits?sha=" + base + "&path=" + quote(path, safe="")))
        if not commits:
            fail()
        start = min(_date(row.get("commit", {}).get("committer", {}).get("date"))
                    for row in commits).isoformat()
        verify_no_execution(api, tasks, start, datetime.now(timezone.utc).isoformat(), live=True)
