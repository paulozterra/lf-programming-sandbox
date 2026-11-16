"""T17.4: retire verified bot-generated PRs blocked by a changed main.

Only API metadata and trusted-main workflow logs are inspected; never checkout
or execute a generated branch. Train evidence must bind BOTH PR and head SHA.
"""
from __future__ import annotations

import json
import re

from pilot.auto_integrate import BOT, accepted_branch_kind
from pilot.native_registration_family import registration_family

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



# Only two trusted and specific mechanical contract CI failures permit
# retirement; other red checks must remain for ordinary owner inspection.
CI_DERIVED_T2 = re.compile(
    r"T2_CONCRETE_CASE_IN_PRODUCTION:contracts/[a-z][a-z0-9-]*\.openapi\.yaml:")
CI_DERIVED_GEN = re.compile(
    r"git diff --exit-code -- frontend/src/lib/api/generated")


def _provably_stale_generated_client(number: int, api_list) -> bool:
    """A new OpenAPI contract *must* add an index export. No CI log needed.

    The PR is already authenticated as a bot-owned CP3.5 integration on the
    exact reported head SHA. Never inspect/execute its source files.
    """
    response = api_list("pulls/" + str(number) + "/files")
    if not isinstance(response, list) or len(response) >= 100:
        return False
    added = {row.get("filename") for row in response if isinstance(row, dict)
             and row.get("status") == "added"
             and isinstance(row.get("filename"), str)
             and re.fullmatch(r"contracts/[a-z][a-z0-9-]*[.]openapi[.]yaml",
                              row["filename"])}
    touched = {row.get("filename") for row in response if isinstance(row, dict)}
    # An added product contract *always* changes the official generated index.
    return bool(added) and "frontend/src/lib/api/generated/index.ts" not in touched


def _ci_derived_failure(number: int, branch: str, sha: str, run, api, repo: str) -> str | None:
    if not re.fullmatch(
            r"lf/native-integration/[a-z][a-z0-9_-]{0,31}-run-[1-9][0-9]*", branch):
        return None
    response = api("actions/workflows/ci.yml/runs?head_sha=" + sha + "&per_page=100")
    rows = response.get("workflow_runs")
    if not isinstance(rows, list):
        raise ValueError("INTEGRATION_CI_HISTORY_INVALID")
    for candidate in rows:
        if (not isinstance(candidate, dict)
                or candidate.get("head_sha") != sha
                or candidate.get("head_branch") != branch
                or candidate.get("status") != "completed"
                or candidate.get("conclusion") != "failure"
                or candidate.get("run_attempt") != 1
                or candidate.get("event") not in ("pull_request", "workflow_dispatch")
                or (candidate.get("path") or "").split("@")[0] != ".github/workflows/ci.yml"
                or (candidate.get("repository") or {}).get("full_name") != repo
                or type(candidate.get("id")) is not int):
            continue
        jobs = api("actions/runs/" + str(candidate["id"]) + "/jobs?per_page=100")
        entries = jobs.get("jobs")
        if not isinstance(entries, list):
            continue
        failed = {j.get("name") for j in entries if isinstance(j, dict)
                  and j.get("conclusion") == "failure"}
        if not failed.intersection({
                "Worker pilot (offline budget, policy, vendor integrity)",
                "frontend (lint, tipos, build)"}):
            continue
        log = run("gh", "run", "view", str(candidate["id"]),
                  "--repo", repo, "--log")
        if not isinstance(log, str) or len(log) > 2_000_000:
            continue
        if ("Worker pilot (offline budget, policy, vendor integrity)" in failed
                and CI_DERIVED_T2.search(log)):
            return "CI_DERIVED_T2 run " + str(candidate["id"])
        if ("frontend (lint, tipos, build)" in failed
                and CI_DERIVED_GEN.search(log)
                and "Process completed with exit code 1" in log):
            return "CI_DERIVED_GEN_API run " + str(candidate["id"])
    return None


def retire_conflicted_generated(head: str, run, api, repo: str, api_list=None) -> list[dict]:
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
        if isinstance(branch, str) and branch.startswith("lf/native-registration/"):
            family, _task = registration_family(branch)
            if family == "invalid":
                continue
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

    # Transport cannot be invented from object-only API. Production passes
    # the typed collection reader; old callers without integration candidates
    # may still exercise conflict-only recovery.
    if api_list is None:
        def api_list(_path):
            raise ValueError("GITHUB_LIST_TRANSPORT_REQUIRED")

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
        reason = ("GitHub mergeable_state=dirty" if dirty else
                  "Train BRANCH_CONFLICT #" + str(evidence[(number, sha)])
                  if (number, sha) in evidence else None)
        if reason is None and kind == "integration":
            # Missing generated export for a *new* contract is a deterministic
            # CI failure even when Actions is awaiting approval (action_required).
            # For modified existing contracts, require exact red CI evidence.
            if _provably_stale_generated_client(number, api_list):
                reason = "CI_DERIVED_GEN_API_STALE"
            else:
                reason = _ci_derived_failure(number, branch, sha, run, api, repo)
        if reason is None:
            continue
        run("gh", "pr", "close", str(number), "--repo", repo, "--delete-branch",
            "--comment", "T17.4/T25: " + reason + ". PR generado retirado, "
            "se conserva el PASS nativo original y se regenerará desde main.")
        retired.append({"number": number, "branch": branch, "sha": sha,
                        "kind": kind, "reason": reason})
    return retired
