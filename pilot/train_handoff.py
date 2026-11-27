#!/usr/bin/env python3
"""T9.2 trusted Train receipt -> deterministic next workflow.

Never execute a merged PR's source, never dispatch from a push-only event.
"""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[1]))
from pilot.config.project_config import storage_path, storage

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
    jobs = config.get("required_jobs")
    if (config.get("schema_version") != "LF_TRAIN_MAIN_CI_GATE_V1"
            or config.get("workflow") != "ci.yml"
            or config.get("dispatch_ref") != "main"
            or "required_event" in config
            or config.get("accepted_events") != ["push", "workflow_dispatch"]
            or config.get("fallback_event") != "workflow_dispatch"
            or config.get("required_branch") != "main"
            or type(config.get("wait_seconds")) is not int
            or not 60 <= config["wait_seconds"] <= 1800
            or type(config.get("poll_seconds")) is not int
            or not 1 <= config["poll_seconds"] <= 60
            or type(config.get("push_wait_seconds")) is not int
            or not 0 <= config["push_wait_seconds"] <= 900
            or not isinstance(jobs, list) or not jobs
            or len(jobs) != len(set(jobs))
            or not all(isinstance(j, str) and j.strip() == j and j for j in jobs)):
        raise HandoffBlocked("MAIN_CI_GATE_CONFIG_INVALID")
    return config


def main_ci_run(api: Github, sha: str, config: dict,
                events: tuple[str, ...] | None = None) -> dict | None:
    """Latest trusted ci.yml run on main for this exact SHA and accepted events."""
    accepted = tuple(events or config["accepted_events"])
    result = api.call("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100")
    rows = result.get("workflow_runs", [])
    if (not isinstance(rows, list) or type(result.get("total_count")) is not int
            or result["total_count"] > 100):
        raise HandoffBlocked("BASE_NO_VERDE:CI_HISTORY_INVALID")
    eligible = [r for r in rows if isinstance(r, dict) and
                r.get("head_sha") == sha and r.get("head_branch") == config["required_branch"]
                and r.get("event") in accepted
                and (r.get("path") or "").split("@")[0] == ".github/workflows/ci.yml"
                and r.get("repository", {}).get("full_name") == REPO
                and type(r.get("run_attempt")) is int]
    return max(eligible, key=lambda r: (r.get("created_at") or "", r.get("id") or 0),
               default=None)


def required_jobs_green(api: Github, run: dict, config: dict) -> bool:
    """Every configured job ran in this run's latest attempt and succeeded.

    A skipped, missing, duplicated or unfinished required job never counts:
    the CI of a different event must prove the same checks, not fewer.
    """
    result = api.call("GET", f"/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")
    rows = result.get("jobs") if isinstance(result, dict) else None
    if (not isinstance(rows, list) or type(result.get("total_count")) is not int
            or result["total_count"] > 100 or result["total_count"] != len(rows)):
        return False
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            by_name.setdefault(row["name"], []).append(row)
    for name in config["required_jobs"]:
        found = by_name.get(name, [])
        if (len(found) != 1 or found[0].get("status") != "completed"
                or found[0].get("conclusion") != "success"):
            return False
    return True


def _follow_main_ci(api: Github, sha: str, config: dict, event: str,
                    min_id: int, sleep) -> dict:
    """Wait for one exact-SHA run of `event` (id > min_id) to finish green."""
    attempts = (config["wait_seconds"] + config["poll_seconds"] - 1) // config["poll_seconds"]
    last = None
    rerun_requested = False
    attempt = 0
    while attempt < attempts:
        run = main_ci_run(api, sha, config, (event,))
        if run is not None and type(run.get("id")) is int and run["id"] > min_id:
            last = run
            if run.get("status") == "completed":
                if run.get("conclusion") == "success":
                    if not required_jobs_green(api, run, config):
                        # Never approve a run that skipped or lost a required check.
                        raise HandoffBlocked("BASE_NO_VERDE:REQUIRED_JOBS:"
                                             + str(run.get("html_url") or "CI_NO_URL"))
                    return {"status": "MAIN_CI_GREEN", "sha": sha, "event": event,
                            "run_id": run["id"], "url": run["html_url"]}
                # T27.1: transient infrastructure (registry 429/503, runner
                # loss) must not stop the chain. Re-run only the failed jobs
                # of this exact run, once; a real defect fails again.
                if not rerun_requested and run.get("run_attempt", 1) == 1:
                    api.call("POST", f"/actions/runs/{run['id']}/rerun-failed-jobs")
                    rerun_requested = True
                    attempt = 0  # fresh wait budget for the re-run
                    sleep(config["poll_seconds"])
                    continue
                # A failed CI is terminal: never dispatch another to wash it.
                raise HandoffBlocked("BASE_NO_VERDE:" + str(run.get("html_url") or "CI_NO_URL"))
        attempt += 1
        if attempt < attempts:
            sleep(config["poll_seconds"])
    # A completed old run cannot stand in for a missing new dispatch.
    raise HandoffBlocked("BASE_NO_VERDE:" + str(last.get("html_url") if last else "CI_NO_RUN"))


def ensure_main_ci(api: Github, sha: str, *, required: bool,
                   config: dict | None = None, sleep=time.sleep,
                   clock=time.monotonic) -> dict:
    """Validate the exact merge SHA on main; dispatch CI only as a fallback.

    T52: a Train merge pushed with TRAIN_PUSH_TOKEN (PR #337) already starts
    ci.yml on push. Reuse that run for the exact SHA; dispatch once only if no
    push run appears by a real push_wait_seconds deadline (e.g. a GITHUB_TOKEN
    merge, the CHG-0113 case). A failed push CI blocks; it is never replaced.
    Renaming a job in ci.yml requires updating required_jobs in the gate
    config (test_t52_main_ci enforces the correspondence).
    """
    config = config or main_ci_gate_config()
    if not SHA.fullmatch(sha):
        raise HandoffBlocked("BASE_NO_VERDE:SHA_INVALID")
    # A workflow_dispatch on ref main is not pinned by input; never let a
    # concurrently advancing main count as validation of a different commit.
    tip = api.call("GET", "/git/ref/heads/main")
    if tip.get("object", {}).get("sha") != sha:
        raise HandoffBlocked("BASE_NO_VERDE:MAIN_MOVED")
    # Monotonic deadline: the last probe happens at or after the deadline,
    # never one poll early (review H3).
    deadline = clock() + (config["push_wait_seconds"] if required else 0)
    while True:
        push_run = main_ci_run(api, sha, config, ("push",))
        if push_run is not None:
            break
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleep(min(config["poll_seconds"], remaining))
    if push_run is not None:
        if not required:
            return {"status": "MAIN_CI_PUSH_OBSERVED", "sha": sha,
                    "run_id": push_run.get("id")}
        return _follow_main_ci(api, sha, config, "push", 0, sleep)
    # Fallback: record the previous run before dispatch. Never treat an older
    # success (or failure) as the outcome of the CI this handoff launches.
    previous = main_ci_run(api, sha, config)
    previous_id = previous.get("id", 0) if previous else 0
    api.call("POST", "/actions/workflows/ci.yml/dispatches", {"ref": "main"})
    if not required:
        return {"status": "MAIN_CI_DISPATCHED", "sha": sha}
    return _follow_main_ci(api, sha, config, config["fallback_event"],
                           previous_id, sleep)


def merged_request_slug(pr: dict, sha: str) -> str:
    """Attribute verified Train merger to one request via its Git delta only."""
    branch = pr["head"]["ref"]
    if re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch):
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
                r"pilot/runs/[a-z][a-z0-9_-]{0,63}/claude_meta/"
                + re.escape(task) + r"[.]json", p)]
            if len(metadata) != 1 or set(changed) != exact | {metadata[0]}:
                raise HandoffBlocked("HANDOFF_EXAM_PATH_DRIFT")
        slugs = set()
        for plan in storage_path("requests_root", root=Path.cwd()).glob("*/chain_plan.json"):
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


def _optional_exam_close(api: Github, sha: str, branch: str, number: int) -> str:
    """Exam bookkeeping must never block trusted main CI or CP3.6 sweep.

    Log the exact scoped error to the merged PR, not an unrelated Issue.
    A failed comment must likewise not prevent downstream dispatch.
    """
    from pilot.native_registration_family import registration_family
    from pilot.exam_issue_lifecycle import close_registered
    family, _task = registration_family(branch)
    if family != "registration":
        return "NO_EXAM_REGISTRATION"
    try:
        return close_registered(api, sha, branch, git, Path("."))
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", code):
            code = "EXAM_CLOSE_UNAVAILABLE"
        print("EXAM_CLOSE_NONBLOCKING:" + code)
        try:
            api.call("POST", f"/issues/{number}/comments", {
                "body": ("Train handoff: cierre secundario de exam-request no completado "
                         f"({code}) tras merge de `{branch}`. "
                         "No se bloquea CI main ni el sweep CP3.6.")
            })
        except Exception:
            print("EXAM_CLOSE_COMMENT_UNAVAILABLE")
        return "EXAM_CLOSE_NONBLOCKING:" + code


def dispatch_chain_sweep(api: Github, sha: str) -> dict:
    """After a verified Train merge and exact-main green CI, resume all chains."""
    if not SHA.fullmatch(sha):
        raise HandoffBlocked("CHAIN_SWEEP_SHA_INVALID")
    inputs = {"sweep": "true", "base_sha": sha}
    api.call("POST", "/actions/workflows/chain-lots.yml/dispatches",
             {"ref": "main", "inputs": inputs})
    return {"workflow": "chain-lots.yml", "inputs": inputs}


def dispatch(api: Github, number: int, sha: str, train_run_id: int,
             mapping: dict):
    pr = api.call("GET", f"/pulls/{number}")
    commit = api.call("GET", f"/commits/{sha}")
    branch = verify_merge(pr, commit, number, sha)
    selected = route(branch, mapping)
    validate_train_run(api, number, train_run_id)
    if selected is None:
        ci = ensure_main_ci(api, sha, required=True)
        exam = _optional_exam_close(api, sha, branch, number)
        sweep = dispatch_chain_sweep(api, sha)
        return {"status": "SWEEP_DISPATCHED", "branch": branch,
                "main_ci": ci, "exam": exam, "sweep": sweep}
    item, match = selected
    if type(item.get("requires_green_base")) is not bool:
        raise HandoffBlocked("HANDOFF_MAP_GATE_UNDEFINED")
    slug_for_stage = (merged_request_slug(pr, sha)
                      if item.get("correlate_request_slug") else None)
    from pilot.orchestrator.request_lifecycle import request_state, OPEN, inactive_reason
    request = match.group(1) if item["input_kind"] == "slug" else slug_for_stage
    def current():
        if not request:
            raise HandoffBlocked("HANDOFF_REQUEST_SCOPE_UNRESOLVED")
        return request_state(request, lambda path: api.call("GET", "/" + path))
    # All Train merges get their own CI. The gate is closed BEFORE CP3.6.
    if current() == OPEN and item["workflow"] == "chain-lots.yml" and re.fullmatch(
            r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch):
        comment_analysis_report(api, sha, slug_for_stage)
    # Every Train merge, including feat/*, is CI-gated before a sweep.
    ci = ensure_main_ci(api, sha, required=True)
    if item["input_kind"] == "slug":
        slug = match.group(1)
        validate_request_paths(slug, sha)
        inputs = {"slug": slug, "merge_sha": sha}
    elif item["input_kind"] == "train_run_id":
        inputs = {"source_run_id": str(train_run_id),
                  "merge_pr": str(number), "request_slug": slug_for_stage,
                  "base_sha": sha}
        if re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch):
            inputs["new_plan_request"] = slug_for_stage
    elif item["input_kind"] == "integration_pr":
        inputs = {"integration_pr": str(number), "request_slug": slug_for_stage,
                  "base_sha": sha}
    else:
        raise HandoffBlocked("HANDOFF_INPUT_KIND_INVALID")
    state = current()
    if state != OPEN:
        sweep = dispatch_chain_sweep(api, sha)
        return {"status": inactive_reason(state), "branch": branch,
                "main_ci": ci, "sweep": sweep}
    api.call("POST", f"/actions/workflows/{item['workflow']}/dispatches",
             {"ref": "main", "inputs": inputs})
    sweep = dispatch_chain_sweep(api, sha)
    return {"status": "DISPATCHED", "branch": branch,
            "workflow": item["workflow"], "inputs": inputs,
            "main_ci": ci, "sweep": sweep}


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
