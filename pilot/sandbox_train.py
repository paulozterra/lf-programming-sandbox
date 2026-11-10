#!/usr/bin/env python3
"""Merge Train P0: trusted main code, fail closed, GitHub REST only (stdlib)."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

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


class TrainError(Exception):
    pass


def api(method, path, payload=None, expected=(200,)):
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
            obj = json.load(response)
            if response.status not in expected:
                raise TrainError(f"Unexpected HTTP {response.status} for {path}")
            return obj
    except urllib.error.HTTPError as exc:
        message = exc.read(800).decode("utf-8", errors="replace")
        raise TrainError(f"HTTP {exc.code} {method} {path}: {message}") from exc


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


def await_checks(number, sha):
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        pr = pr_data(number)
        check_pr(pr)
        if pr["head"]["sha"] != sha:
            return None  # changed: restart against new SHA
        found = checks_for_head(sha)
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


def run(number):
    for attempt in range(MAX_RESTARTS + 1):
        pr = pr_data(number)
        check_pr(pr)
        initial_head = pr["head"]["sha"]
        base = main_sha()
        compare = api("GET", f"/compare/{base}...{initial_head}")
        if compare["behind_by"] > 0:
            print(json.dumps({"event": "update_branch", "pr": number, "head": initial_head, "main": base}), flush=True)
            api("PUT", f"/pulls/{number}/update-branch", {"expected_head_sha": initial_head}, expected=(202,))
            # Wait for GitHub to create the update commit; do not trust older checks.
            end = time.monotonic() + 150
            while time.monotonic() < end:
                time.sleep(5)
                updated = pr_data(number)
                check_pr(updated)
                if updated["head"]["sha"] != initial_head:
                    break
            else:
                raise TrainError("BRANCH_UPDATE_TIMEOUT")
            continue
        if compare["status"] not in ("ahead", "identical"):
            raise TrainError("BRANCH_NOT_MERGEABLE " + compare["status"])
        evidence = await_checks(number, initial_head)
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
            merged = api("PUT", f"/pulls/{number}/merge",
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
