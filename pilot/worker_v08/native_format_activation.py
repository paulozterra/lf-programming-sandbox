"""Governed task-scoped format activation, initially disabled.

The only enrollment authority is trusted main, never a proposal, workflow
input, label, or environment variable. Each enrollment is anchored to the
actual merge of its owner-reviewed activation PR.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
from pathlib import Path

from native_format_admission import ROOT, SHA40, load_registration, parse_worker_task
from native_format_preflight import _select
from pilot.config.project_config import active_project, load
import native_format_history as history

POLICY = "pilot/worker_v08/native_format_activation.json"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SCHEMA = "LF_NATIVE_FORMAT_ACTIVATION_V1"


def parse_policy(raw):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("FORMAT_ACTIVATION_POLICY_INVALID")
            obj[key] = value
        return obj
    data = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(data, dict) or set(data) != {"schema_version", "tasks"}
            or data["schema_version"] != SCHEMA or not isinstance(data["tasks"], dict)
            or any(not TASK.fullmatch(k) or type(v) is not int or v <= 816
                   for k, v in data["tasks"].items())):
        raise ValueError("FORMAT_ACTIVATION_POLICY_INVALID")
    return data["tasks"]


def policy_at_root(root=ROOT):
    # Resolve the trusted code tree, not an untrusted proposal checkout.
    path = root / POLICY
    if path.is_symlink() or not path.is_file():
        raise ValueError("FORMAT_ACTIVATION_POLICY_MISSING")
    current = parse_policy(path.read_text("utf-8"))
    verify_policy_history(root, current)
    return current


def assert_append_only(previous, current):
    if any(current.get(task) != number for task, number in previous.items()):
        raise ValueError("FORMAT_ACTIVATION_HISTORY_REWRITE")


def verify_policy_history(root, current):
    # Both native and CP3.6 check out full trusted main. CI checks the same
    # append-only invariant on the candidate merge, before the Train.
    shallow = subprocess.check_output(["git", "-C", str(root), "rev-parse",
                                       "--is-shallow-repository"], timeout=10).strip()
    if shallow != b"false":
        raise ValueError("FORMAT_ACTIVATION_HISTORY_INCOMPLETE")
    commits = subprocess.check_output(["git", "-C", str(root), "log", "--first-parent",
                                       "--full-history", "--format=%H", "HEAD", "--", POLICY],
                                      timeout=20).decode("ascii").splitlines()
    if not commits or len(commits) > 1000:
        raise ValueError("FORMAT_ACTIVATION_HISTORY_INCOMPLETE")
    # Walk oldest to newest: a removal followed by restoration is also a
    # rewrite, not a valid reset of the task's rejection ledger.
    prior = {}
    for sha in reversed(commits):
        next_policy = git_policy(root, sha)
        assert_append_only(prior, next_policy)
        prior = next_policy
    assert_append_only(prior, current)


def eligible(control, task, policy):
    if task not in policy:
        return False
    raw, _ = load_registration(control, task)
    spec = parse_worker_task(raw)
    config = load(active_project(root=control), root=control)
    if _select(spec, config) is None:
        # Enrollment of a non-Spotless task is an owner configuration error,
        # not authorization to change its historical acceptance.
        raise ValueError("FORMAT_ACTIVATION_NO_REGISTERED_SPOTLESS")
    return True


def boundary(api, task, policy):
    number = policy[task]
    pr = api(f"pulls/{number}")
    repo = history.REPO
    sha = pr.get("merge_commit_sha") or ""
    history.require(pr.get("number") == number and pr.get("merged") is True
                    and SHA40.fullmatch(sha) is not None
                    and pr.get("base", {}).get("ref") == "main"
                    and pr.get("base", {}).get("repo", {}).get("full_name") == repo
                    and pr.get("head", {}).get("repo", {}).get("full_name") == repo,
                    "FORMAT_ACTIVATION_PR_UNVERIFIED")
    value = api(f"contents/{POLICY}?ref={sha}")
    history.require(value.get("type") == "file" and value.get("encoding") == "base64"
                    and type(value.get("size")) is int and 0 < value["size"] <= 64000,
                    "FORMAT_ACTIVATION_COMMIT_UNVERIFIED")
    raw = base64.b64decode("".join(value["content"].splitlines()), validate=True)
    history.require(len(raw) == value["size"] and parse_policy(raw).get(task) == number,
                    "FORMAT_ACTIVATION_COMMIT_UNVERIFIED")
    activated = history.stamp(pr.get("merged_at"))
    history.require(activated >= history.cutover(api), "FORMAT_ACTIVATION_BEFORE_FEATURE")
    return activated


def git_policy(control, sha):
    if not SHA40.fullmatch(sha):
        raise ValueError("FORMAT_ACTIVATION_WORKFLOW_SHA_INVALID")
    raw = subprocess.check_output(["git", "-C", str(control), "show", sha + ":" + POLICY],
                                  timeout=20)
    return parse_policy(raw)


def select(control, task, workflow_sha, api):
    current = policy_at_root(control)
    original = git_policy(control, workflow_sha)
    assert_append_only(original, current)
    if not eligible(control, task, original):
        from pilot.orchestrator.lot_recovery import for_successor
        if for_successor(control, task):
            raise ValueError("LOT_RECOVERY_FORMAT_ACTIVATION_REQUIRED")
        return False
    boundary(api, task, original)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    a = parser.parse_args()
    api = lambda route: history._api(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"], route)
    enabled = select(a.control, a.task, a.workflow_sha, api)
    with a.github_output.open("a") as stream:
        stream.write("enabled=" + ("true" if enabled else "false") + "\n")
    print("FORMAT_ACTIVATION_ENABLED" if enabled else "FORMAT_ACTIVATION_DISABLED")


if __name__ == "__main__":
    main()
