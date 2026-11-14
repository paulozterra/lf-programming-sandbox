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
import urllib.error
import urllib.request

REPO = "paulozterra/lf-programming-sandbox"
MAP = Path(__file__).with_name("train_handoff_map_v1.json")
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


def dispatch(api: Github, number: int, sha: str, train_run_id: int,
             mapping: dict):
    pr = api.call("GET", f"/pulls/{number}")
    commit = api.call("GET", f"/commits/{sha}")
    branch = verify_merge(pr, commit, number, sha)
    selected = route(branch, mapping)
    if selected is None:
        return {"status": "NO_HANDOFF", "branch": branch}
    validate_train_run(api, number, train_run_id)
    item, match = selected
    if item["input_kind"] == "slug":
        slug = match.group(1)
        validate_request_paths(slug, sha)
        inputs = {"slug": slug, "merge_sha": sha}
    elif item["input_kind"] == "train_run_id":
        inputs = {"source_run_id": str(train_run_id),
                  "merge_pr": str(number)}
    elif item["input_kind"] == "integration_pr":
        inputs = {"integration_pr": str(number)}
    else:
        raise HandoffBlocked("HANDOFF_INPUT_KIND_INVALID")
    api.call("POST", f"/actions/workflows/{item['workflow']}/dispatches",
             {"ref": "main", "inputs": inputs})
    return {"status": "DISPATCHED", "branch": branch,
            "workflow": item["workflow"], "inputs": inputs}


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


if __name__ == "__main__":
    try:
        main()
    except (HandoffBlocked, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit("HANDOFF_BLOCKED:" + str(exc)) from exc
