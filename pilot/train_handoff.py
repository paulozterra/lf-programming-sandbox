#!/usr/bin/env python3
"""T9.2 trusted Train receipt -> deterministic next workflow.

Never execute a merged PR's source, never dispatch from a push-only event.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request

REPO = "paulozterra/lf-programming-sandbox"
MAP = Path(__file__).with_name("train_handoff_map_v1.json")
CI_GATE = Path(__file__).with_name("train_main_ci_gate_v1.json")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class HandoffBlocked(ValueError):
    pass


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class Github:
    def __init__(self, token: str):
        if not token:
            raise HandoffBlocked("HANDOFF_TOKEN_MISSING")
        self.token = token

    def call(self, method: str, path: str, payload=None):
        if not path.startswith("/") or "//" in path or ".." in path:
            raise HandoffBlocked("HANDOFF_API_PATH_INVALID")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.github.com/repos/" + REPO + path, data=data,
            method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "LF-train-handoff"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise HandoffBlocked("HANDOFF_API_OVERSIZE")
            return json.loads(raw) if raw else {}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise HandoffBlocked("HANDOFF_API_FAILED:" + path) from exc


def route(branch: str, mapping: dict) -> tuple[dict, re.Match[str]] | None:
    if mapping.get("schema_version") != "LF_TRAIN_HANDOFF_MAP_V1":
        raise HandoffBlocked("HANDOFF_MAP_INVALID")
    found = [(item, match) for item in mapping["routes"]
             if (match := re.fullmatch(item["branch_regex"], branch))]
    if len(found) > 1:
        raise HandoffBlocked("HANDOFF_ROUTE_AMBIGUOUS")
    return found[0] if found else None


def verify_merge(pr: dict, commit: dict, number: int, sha: str,
                 *, first_parent: bool = True) -> str:
    if (type(number) is not int or number < 1 or not SHA.fullmatch(sha)
            or pr.get("number") != number or pr.get("merged") is not True
            or pr.get("merge_commit_sha") != sha
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != REPO
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO
            or not isinstance(pr.get("head", {}).get("ref"), str)):
        raise HandoffBlocked("HANDOFF_MERGE_UNTRUSTED")
    parents = commit.get("parents", [])
    if (commit.get("sha") != sha or len(parents) != 2
            or parents[1].get("sha") != pr.get("head", {}).get("sha")
            or commit.get("commit", {}).get("message", "").splitlines()[0]
               != f"Merge PR #{number} via sandbox-train"):
        raise HandoffBlocked("HANDOFF_MERGE_NOT_TRAIN")
    if first_parent:
        head = git("rev-parse", "HEAD")
        if sha not in git("rev-list", "--first-parent", head).splitlines():
            raise HandoffBlocked("HANDOFF_MERGE_NOT_FIRST_PARENT")
    return pr["head"]["ref"]


def validate_request_paths(slug: str, sha: str):
    files = git("diff", "--name-only", sha + "^1", sha).splitlines()
    expected = {f"pilot/runs/{slug}/request.md",
                f"pilot/runs/{slug}/request_meta.json"}
    if set(files) != expected or len(files) != 2:
        raise HandoffBlocked("HANDOFF_REQUEST_PATH_DRIFT")
    meta = json.loads(git("show", f"{sha}:pilot/runs/{slug}/request_meta.json"))
    if meta.get("issue") != int(slug[4:]):
        raise HandoffBlocked("HANDOFF_REQUEST_META_INVALID")


def validate_train_run(api: Github, number: int, train_run_id: int):
    if train_run_id < 1:
        raise HandoffBlocked("HANDOFF_TRAIN_RUN_INVALID")
    # Train triggers handoff before its own job completes. Wait for the actual
    # successful source run, never assume a dispatch is proof of completion.
    for _ in range(30):
        run = api.call("GET", f"/actions/runs/{train_run_id}")
        if (run.get("id") != train_run_id
                or run.get("repository", {}).get("full_name") != REPO
                or (run.get("path") or "").split("@")[0] != ".github/workflows/sandbox-train.yml"
                or run.get("event") not in ("workflow_dispatch", "pull_request")
                or run.get("run_attempt") != 1):
            raise HandoffBlocked("HANDOFF_TRAIN_RUN_UNTRUSTED")
        if run.get("status") == "completed":
            if run.get("conclusion") != "success":
                raise HandoffBlocked("HANDOFF_TRAIN_NOT_GREEN")
            return
        time.sleep(4)
    raise HandoffBlocked("HANDOFF_TRAIN_WAIT_TIMEOUT")


def main_ci_gate_config(path: Path = CI_GATE) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if (config.get("schema_version") != "LF_TRAIN_MAIN_CI_GATE_V1"
            or config.get("workflow") != "ci.yml"
            or config.get("dispatch_ref") != "main"
            or config.get("required_event") != "workflow_dispatch"
            or config.get("required_branch") != "main"
            or type(config.get("wait_seconds")) is not int
            or not 60 <= config["wait_seconds"] <= 1800
            or type(config.get("poll_seconds")) is not int
            or not 1 <= config["poll_seconds"] <= 60):
        raise HandoffBlocked("MAIN_CI_GATE_CONFIG_INVALID")
    return config


def main_ci_run(api: Github, sha: str, config: dict) -> dict | None:
    result = api.call("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100")
    rows = result.get("workflow_runs", [])
    if (not isinstance(rows, list) or type(result.get("total_count")) is not int
            or result["total_count"] > 100):
        raise HandoffBlocked("BASE_NO_VERDE:CI_HISTORY_INVALID")
    eligible = [r for r in rows if
                r.get("head_sha") == sha and r.get("head_branch") == config["required_branch"]
                and r.get("event") in ("push", config["required_event"])
                and (r.get("path") or "").split("@")[0] == ".github/workflows/ci.yml"
                and r.get("repository", {}).get("full_name") == REPO
                and type(r.get("run_attempt")) is int]
    return max(eligible, key=lambda r: (r.get("created_at") or "", r.get("id") or 0),
               default=None)


def ensure_main_ci(api: Github, sha: str, *, required: bool,
                   config: dict | None = None, sleep=time.sleep) -> dict:
    """Dispatch CI via workflow_dispatch; never count a different main SHA.

    A gated successor is forbidden until the exact SHA's latest verified
    workflow_dispatch CI has completed successfully. A failure is terminal
    and contains its own GitHub Actions URL.
    """
    config = config or main_ci_gate_config()
    if not SHA.fullmatch(sha):
        raise HandoffBlocked("BASE_NO_VERDE:SHA_INVALID")
    # A workflow_dispatch on ref main is not pinned by input; never let a
    # concurrently advancing main count as validation of a different commit.
    tip = api.call("GET", "/git/ref/heads/main")
    if tip.get("object", {}).get("sha") != sha:
        raise HandoffBlocked("BASE_NO_VERDE:MAIN_MOVED")
    # Record the previous run before dispatch. Never treat an older success
    # (or failure) as the outcome of the CI that this handoff just launched.
    previous = main_ci_run(api, sha, config)
    previous_id = previous.get("id", 0) if previous else 0
    api.call("POST", "/actions/workflows/ci.yml/dispatches", {"ref": "main"})
    if not required:
        return {"status": "MAIN_CI_DISPATCHED", "sha": sha}
    attempts = (config["wait_seconds"] + config["poll_seconds"] - 1) // config["poll_seconds"]
    last = None
    for attempt in range(attempts):
        run = main_ci_run(api, sha, config)
        if run is not None and type(run.get("id")) is int and run["id"] > previous_id:
            last = run
            if run.get("status") == "completed":
                if run.get("conclusion") == "success":
                    return {"status": "MAIN_CI_GREEN", "sha": sha,
                            "run_id": run["id"], "url": run["html_url"]}
                raise HandoffBlocked("BASE_NO_VERDE:" + str(run.get("html_url") or "CI_NO_URL"))
        if attempt + 1 < attempts:
            sleep(config["poll_seconds"])
    # A completed old run cannot stand in for a missing new dispatch.
    raise HandoffBlocked("BASE_NO_VERDE:" + str(last.get("html_url") if last else "CI_NO_RUN"))


def merged_request_slug(pr: dict, sha: str) -> str:
    """Attribute verified Train merger to one request via its Git delta only."""
    branch = pr["head"]["ref"]
    if re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}", branch):
        changed = git("diff", "--name-only", sha + "^1", sha).splitlines()
        slugs = {m.group(1) for path in changed
                 if (m := re.fullmatch(r"pilot/runs/(req-[1-9][0-9]*)/(?:analysis|state|lots|chain_plan)[.]json", path))}
    else:
        match = (re.fullmatch(r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-[1-9][0-9]*", branch)
                 or re.fullmatch(r"lf/exam/([a-z][a-z0-9_-]{0,31})", branch))
        if not match:
            raise HandoffBlocked("HANDOFF_REQUEST_SCOPE_INVALID")
        task = match.group(1)
        if branch.startswith("lf/exam/"):
            exact = {f"pilot/holdouts/{task}.oracle.json.age"}
            changed = git("diff", "--name-only", sha + "^1", sha).splitlines()
            if len(changed) != 2:
                raise HandoffBlocked("HANDOFF_EXAM_PATH_DRIFT")
            metadata = [p for p in changed if re.fullmatch(
                r"pilot/runs/req-[1-9][0-9]*/claude_meta/"
                + re.escape(task) + r"[.]json", p)]
            if len(metadata) != 1 or set(changed) != exact | {metadata[0]}:
                raise HandoffBlocked("HANDOFF_EXAM_PATH_DRIFT")
        slugs = set()
        for plan in Path("pilot/runs").glob("req-*/chain_plan.json"):
            if plan.is_symlink() or plan.parent.is_symlink():
                continue
            data = json.loads(plan.read_text(encoding="utf-8"))
            if any(isinstance(row, dict) and
                   (row.get("task_name") == task or
                    (isinstance(row.get("task_name"), str) and
                     re.fullmatch(re.escape(row["task_name"]) + r"(?:[2-9]|[1-9][0-9]+)", task)))
                   for row in data.get("bindings", [])):
                slugs.add(plan.parent.name)
    if len(slugs) != 1:
        raise HandoffBlocked("HANDOFF_REQUEST_SCOPE_AMBIGUOUS")
    return slugs.pop()


def comment_analysis_report(api: Github, sha: str, slug: str) -> str:
    from pilot.analysis_report_notification import comment
    return comment(api, sha, slug, git)


def dispatch(api: Github, number: int, sha: str, train_run_id: int,
             mapping: dict):
    pr = api.call("GET", f"/pulls/{number}")
    commit = api.call("GET", f"/commits/{sha}")
    branch = verify_merge(pr, commit, number, sha)
    selected = route(branch, mapping)
    validate_train_run(api, number, train_run_id)
    if selected is None:
        ci = ensure_main_ci(api, sha, required=False)
        from pilot.exam_issue_lifecycle import close_registered
        exam = close_registered(api, sha, branch, git, Path("."))
        return {"status": "NO_HANDOFF", "branch": branch,
                "main_ci": ci, "exam": exam}
    item, match = selected
    if type(item.get("requires_green_base")) is not bool:
        raise HandoffBlocked("HANDOFF_MAP_GATE_UNDEFINED")
    slug_for_stage = (merged_request_slug(pr, sha)
                      if item.get("correlate_request_slug") else None)
    # All Train merges get their own CI. The gate is closed BEFORE CP3.6.
    if item["workflow"] == "chain-lots.yml" and re.fullmatch(
            r"lf/generated-t7/[0-9a-f]{12}", branch):
        comment_analysis_report(api, sha, slug_for_stage)
    ci = ensure_main_ci(api, sha, required=item["requires_green_base"])
    if item["input_kind"] == "slug":
        slug = match.group(1)
        validate_request_paths(slug, sha)
        inputs = {"slug": slug, "merge_sha": sha}
    elif item["input_kind"] == "train_run_id":
        inputs = {"source_run_id": str(train_run_id),
                  "merge_pr": str(number), "request_slug": slug_for_stage,
                  "base_sha": sha}
    elif item["input_kind"] == "integration_pr":
        inputs = {"integration_pr": str(number), "request_slug": slug_for_stage,
                  "base_sha": sha}
    else:
        raise HandoffBlocked("HANDOFF_INPUT_KIND_INVALID")
    api.call("POST", f"/actions/workflows/{item['workflow']}/dispatches",
             {"ref": "main", "inputs": inputs})
    return {"status": "DISPATCHED", "branch": branch,
            "workflow": item["workflow"], "inputs": inputs, "main_ci": ci}


def verify_t7_dispatch(slug: str, sha: str):
    if not re.fullmatch(r"req-[1-9][0-9]*", slug) or not SHA.fullmatch(sha):
        raise HandoffBlocked("HANDOFF_REQUEST_INPUT_INVALID")
    if sha not in git("rev-list", "--first-parent", "HEAD").splitlines():
        raise HandoffBlocked("HANDOFF_REQUEST_NOT_ON_MAIN")
    if not re.fullmatch(r"Merge PR #[1-9][0-9]* via sandbox-train",
                        git("log", "-1", "--format=%s", sha)):
        raise HandoffBlocked("HANDOFF_REQUEST_MERGE_INVALID")
    parents = git("rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 3:
        raise HandoffBlocked("HANDOFF_REQUEST_MERGE_INVALID")
    validate_request_paths(slug, sha)
    if not Path(f"pilot/runs/{slug}/request.md").is_file():
        raise HandoffBlocked("HANDOFF_REQUEST_NOT_IN_MAIN")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", type=int)
    ap.add_argument("--merge-sha")
    ap.add_argument("--train-run-id", type=int)
    ap.add_argument("--verify-t7", action="store_true")
    ap.add_argument("--slug")
    args = ap.parse_args()
    if args.verify_t7:
        verify_t7_dispatch(args.slug or "", args.merge_sha or "")
        return
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise HandoffBlocked("HANDOFF_REPOSITORY_INVALID")
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    result = dispatch(Github(os.environ.get("GH_TOKEN", "")),
                      args.pr, args.merge_sha, args.train_run_id, mapping)
    print(json.dumps(result, sort_keys=True))


def alert_exact_base_block(exc: Exception, number: int | None, sha: str | None):
    """Report a CI-gate block before the handoff workflow itself completes.

    No untrusted PR body is used: notifier verifies this Train PR's merge
    commit and changed request files, then checks the original bot request.
    """
    reason = str(exc)
    if not reason.startswith("BASE_NO_VERDE:"):
        return
    if (type(number) is not int or number < 1 or not isinstance(sha, str)
            or not SHA.fullmatch(sha)):
        return
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id.isdecimal() or os.environ.get("GITHUB_REPOSITORY") != REPO:
        return
    from request_failure_notify import Github as NotifyGithub, emit
    ci_url = reason.split(":", 1)[1]
    run = {"id": int(run_id), "name": f"Train handoff PR {number}",
           "display_title": f"Train handoff PR {number}",
           "path": ".github/workflows/train-handoff.yml",
           "event": "workflow_dispatch", "head_branch": "main",
           "head_sha": sha, "conclusion": "failure",
           "failure_code": "BASE_NO_VERDE",
           "repository": {"full_name": REPO},
           "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}"}
    if ci_url.startswith(f"https://github.com/{REPO}/actions/runs/"):
        run["main_ci_url"] = ci_url
    print("HANDOFF_BASE_ALERT:" + emit(
        NotifyGithub(os.environ.get("GH_TOKEN", "")), run, []))


if __name__ == "__main__":
    try:
        main()
    except (HandoffBlocked, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        try:
            parser = argparse.ArgumentParser(add_help=False)
            parser.add_argument("--pr", type=int)
            parser.add_argument("--merge-sha")
            data, _ = parser.parse_known_args()
            alert_exact_base_block(exc, data.pr, data.merge_sha)
        except Exception as notify_exc:
            print("HANDOFF_BASE_ALERT_FAILED:" + str(notify_exc))
        raise SystemExit("HANDOFF_BLOCKED:" + str(exc)) from exc
