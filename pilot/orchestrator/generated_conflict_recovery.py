"""T17.4: retire verified bot-generated PRs blocked by a changed main.

Only API metadata and trusted-main workflow logs are inspected; never checkout
or execute a generated branch. Train evidence must bind BOTH PR and head SHA.
"""
from __future__ import annotations

import json
import re

from pilot.auto_integrate import BOT, accepted_branch_kind

SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE_BOT = {BOT, "app/github-actions", "github-actions"}
GENERATED = {"registration", "integration", "implemented-registry", "generated-t7"}
TRAIN_CONFLICT = re.compile(r"TRAIN_BLOCKED BRANCH_CONFLICT(?:\s|$)")
TRAIN_LINK = re.compile(r'\{[^\n]{0,700}"event":\s*"local_merge_and_render"[^\n]{0,700}\}')


def _train_conflict(log: str, number: int, sha: str) -> bool:
    if not isinstance(log, str) or len(log) > 2_000_000 or not TRAIN_CONFLICT.search(log):
        return False
    for match in TRAIN_LINK.finditer(log):
        try:
            item = json.loads(match.group())
        except ValueError:
            continue
        if item.get("pr") == number and item.get("head") == sha:
            return True
    return False


def retire_conflicted_generated(head: str, run, api, repo: str) -> list[dict]:
    """Return retired PR metadata; callers regenerate from trusted current main.

    All changes use caller-provided run/api boundaries for CP3.6 offline tests.
    A failed Train log alone cannot retire a different PR on the same SHA.
    """
    rows = json.loads(run("gh", "pr", "list", "--repo", repo,
                          "--state", "open", "--limit", "100",
                          "--json", "number,headRefName,headRefOid,author"))
    if not isinstance(rows, list) or len(rows) >= 100:
        raise ValueError("CONFLICT_RECOVERY_PR_LIST_INVALID")
    eligible = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        number, branch, sha = row.get("number"), row.get("headRefName"), row.get("headRefOid")
        kind = accepted_branch_kind(branch)
        if (kind not in GENERATED or type(number) is not int or number < 1
                or not SHA.fullmatch(str(sha))
                or (row.get("author") or {}).get("login") not in SAFE_BOT):
            continue
        detail = api(f"pulls/{number}")
        if (detail.get("number") != number or detail.get("state") != "open"
                or detail.get("merged") is True
                or (detail.get("user") or {}).get("login") not in SAFE_BOT
                or (detail.get("head") or {}).get("sha") != sha
                or (detail.get("head") or {}).get("ref") != branch
                or (detail.get("head") or {}).get("repo", {}).get("full_name") != repo
                or (detail.get("base") or {}).get("ref") != "main"):
            continue
        labeled = any(isinstance(label, dict) and label.get("name") == "ready-to-merge"
                      for label in detail.get("labels", []))
        eligible.append((number, branch, sha, kind,
                         detail.get("mergeable_state") == "dirty", labeled))

    # Only consult Train runs if the PR isn't already provably dirty.
    unknown = [(n, b, sha, k) for n, b, sha, k, dirty, labeled in eligible
               if not dirty and labeled]
    failures = []
    if unknown:
        response = api("actions/workflows/sandbox-train.yml/runs?per_page=100")
        runs = response.get("workflow_runs")
        if not isinstance(runs, list):
            raise ValueError("CONFLICT_RECOVERY_TRAIN_LIST_INVALID")
        failures = [r for r in runs if isinstance(r, dict)
                    and r.get("event") == "workflow_dispatch"
                    and r.get("status") == "completed" and r.get("conclusion") == "failure"
                    and r.get("head_branch") == "main" and type(r.get("id")) is int]
        failures.sort(key=lambda r: (r.get("created_at", ""), r["id"]), reverse=True)
        failures = failures[:20]

    evidence = {}
    for f in failures:
        log = run("gh", "run", "view", str(f["id"]), "--repo", repo, "--log")
        for number, _branch, sha, _kind in unknown:
            if (number, sha) not in evidence and _train_conflict(log, number, sha):
                evidence[(number, sha)] = f["id"]

    retired = []
    for number, branch, sha, kind, dirty, _labeled in eligible:
        if not dirty and (number, sha) not in evidence:
            continue
        reason = ("GitHub mergeable_state=dirty" if dirty else
                  "Train BRANCH_CONFLICT #" + str(evidence[(number, sha)]))
        run("gh", "pr", "close", str(number), "--repo", repo, "--delete-branch",
            "--comment", "T17.4: " + reason + ". PR generado obsoleto frente a main "
            + head[:12] + "; se retira para regeneración desde main actual.")
        retired.append({"number": number, "branch": branch, "sha": sha,
                        "kind": kind, "reason": reason})
    return retired
