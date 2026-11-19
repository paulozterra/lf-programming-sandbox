#!/usr/bin/env python3
"""T9.2 bounded per-merge watchdog; no reliance on GitHub schedule delivery."""
from __future__ import annotations
from pilot.config.project_config import storage_path, storage
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

from request_failure_notify import Github, REPO, emit
from native_registration_family import registration_family

CONFIG = Path(__file__).with_name("request_stage_thresholds_v1.json")
SRC = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")


class StageBlocked(ValueError):
    pass


def git(*parts: str) -> str:
    return subprocess.run(["git", "-C", str(SRC), *parts], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True).stdout.strip()


def stage_config(path: Path = CONFIG) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema_version") != "LF_REQUEST_STAGE_THRESHOLDS_V1"
            or {x["stage"] for x in data.get("stages", [])}
               != {"REQUEST_MERGED", "ANALYSIS_MERGED", "INTEGRATION_MERGED"}
            or any(type(x.get("minutes")) is not int or not 1 <= x["minutes"] <= 60
                   for x in data["stages"])):
        raise StageBlocked("STAGE_CONFIG_INVALID")
    return {row["stage"]: row for row in data["stages"]}


def request_slugs(pr: dict, merge_sha: str) -> tuple[str, list[str]] | None:
    """Derive scope from trusted first-parent merge delta, not PR description."""
    branch = pr.get("head", {}).get("ref", "")
    # Auxiliary registration-family merges are not user-visible request stages.
    if registration_family(branch)[0] in ("registration", "auxiliary"):
        return None
    if m := re.fullmatch(r"lf/request/(req-[1-9][0-9]*)", branch):
        return "REQUEST_MERGED", [m.group(1)]
    paths = git("diff", "--name-only", merge_sha + "^1", merge_sha).splitlines()
    if re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch):
        slugs = sorted({m.group(1) for p in paths
                        if (m := re.fullmatch(r"pilot/runs/(req-[1-9][0-9]*)/(?:state[.]json|analysis[.]json|lots[.]json|chain_plan[.]json)", p))})
        return ("ANALYSIS_MERGED", slugs) if slugs else None
    m = re.fullmatch(r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-[1-9][0-9]*", branch)
    if not m:
        return None
    task = m.group(1)
    slugs = []
    for plan in (storage_path("requests_root", root=SRC)).glob("req-*/chain_plan.json"):
        if plan.is_symlink() or plan.parent.is_symlink():
            continue
        if not re.fullmatch(r"req-[1-9][0-9]*", plan.parent.name):
            continue
        data = json.loads(plan.read_text(encoding="utf-8"))
        if any(isinstance(x, dict) and (
                   x.get("task_name") == task or
                   (isinstance(x.get("task_name"), str) and
                    re.fullmatch(re.escape(x["task_name"]) + r"(?:[2-9]|[1-9][0-9]+)", task)))
               for x in data.get("bindings", [])):
            slugs.append(plan.parent.name)
    return ("INTEGRATION_MERGED", sorted(set(slugs))) if slugs else None


def expected_title(stage: str, number: int, slug: str) -> str:
    return f"T7 {slug}" if stage == "REQUEST_MERGED" else f"CP3.6 {slug} PR {number}"


def next_run_seen(api: Github, stage: str, number: int,
                  slug: str, merged_at: str, config: dict) -> bool:
    expected = config[stage]["expected_workflow"]
    file = "t7-request.yml" if stage == "REQUEST_MERGED" else "chain-lots.yml"
    result = api.api("GET", f"/actions/workflows/{file}/runs?per_page=100")
    title = expected_title(stage, number, slug)
    historical = f"CP3.6 PR {number}"
    return any(
        ((str(row.get("path") or "").split("@")[0] == ".github/workflows/" + file)
         or (not row.get("path") and row.get("name") == expected))
        and row.get("display_title") in
            ((title, historical) if stage != "REQUEST_MERGED" else (title,))
        and row.get("created_at", "") >= merged_at
        for row in result.get("workflow_runs", []))


def evaluate(api: Github, number: int, sha: str, train_run_id: int,
             now: datetime, config: dict) -> tuple[str, int]:
    pr = api.api("GET", f"/pulls/{number}")
    if (pr.get("number") != number or pr.get("merged") is not True
            or pr.get("merge_commit_sha") != sha
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO
            or not SHA.fullmatch(sha)):
        raise StageBlocked("STAGE_SOURCE_UNTRUSTED")
    scope = request_slugs(pr, sha)
    if scope is None:
        return "NOT_REQUEST_STAGE", 0
    stage, slugs = scope
    if not slugs:
        return "STAGE_REQUEST_UNRESOLVED", 0
    source = api.api("GET", f"/actions/runs/{train_run_id}")
    if (source.get("id") != train_run_id
            or source.get("repository", {}).get("full_name") != REPO
            or (source.get("path") or "").split("@")[0] != ".github/workflows/sandbox-train.yml"
            or source.get("conclusion") != "success"):
        raise StageBlocked("STAGE_TRAIN_UNTRUSTED")
    stamp = pr.get("merged_at")
    if not isinstance(stamp, str):
        raise StageBlocked("STAGE_MERGE_TIMESTAMP_INVALID")
    merged = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    age_minutes = (now - merged).total_seconds() / 60
    waiting, notifications = 0, 0
    for slug in slugs:
        issue_number = int(slug[4:])
        issue = api.api("GET", f"/issues/{issue_number}")
        if issue.get("state") != "open":
            continue  # historical/discarded requests never replayed
        if next_run_seen(api, stage, number, slug, stamp, config):
            continue
        waiting += 1
        if age_minutes < config[stage]["minutes"]:
            continue
        synthetic = {
            "id": train_run_id, "name": "ci", "conclusion": "failure",
            "repository": {"full_name": REPO},
            "head_branch": f"lf/request/{slug}",
            "failure_code": config[stage]["missing_code"],
            "html_url": source["html_url"],
        }
        result = emit(api, synthetic, [])
        print(json.dumps({"issue": issue_number, "stage": stage, "result": result}))
        if result in ("RUTA_NOTIFIED", "RUTA_ALREADY_NOTIFIED"):
            notifications += 1
    if notifications:
        return "STAGE_STALLED_NOTIFIED", 0
    if waiting:
        return "STAGE_AWAITING_NEXT_RUN", max(0, int(config[stage]["minutes"] - age_minutes + 1))
    return "STAGE_NEXT_RUN_FOUND", 0


def watch(api: Github, number: int, sha: str, train_run_id: int,
          config: dict, *, sleep=time.sleep, clock=lambda: datetime.now(timezone.utc)):
    """Wait only for this successful Train merge; never rely on scheduled events."""
    for _ in range(42):
        status, remaining = evaluate(api, number, sha, train_run_id, clock(), config)
        print(json.dumps({"pr": number, "status": status}))
        if status != "STAGE_AWAITING_NEXT_RUN":
            return status
        sleep(min(90, max(5, remaining * 60)))
    raise StageBlocked("STAGE_WATCH_BUDGET_EXCEEDED")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--merge-sha", required=True)
    p.add_argument("--train-run-id", type=int, required=True)
    p.add_argument("--watch", action="store_true")
    a = p.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise StageBlocked("STAGE_REPOSITORY_INVALID")
    api = Github(os.environ.get("GH_TOKEN", ""))
    config = stage_config()
    if a.watch:
        watch(api, a.pr, a.merge_sha, a.train_run_id, config)
    else:
        print(evaluate(api, a.pr, a.merge_sha, a.train_run_id,
                       datetime.now(timezone.utc), config))


if __name__ == "__main__":
    try:
        main()
    except (StageBlocked, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit("PEDIDO_STAGE_WATCH_BLOCKED:" + str(exc)) from exc
