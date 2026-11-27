"""T20: one CI redispatch per *unchanged* HEAD of an open bot PR.

Operates on trusted-main GitHub metadata only. An authenticated PR comment is
the durable attempt ledger, so even a later sweep or failed dispatch cannot
loop indefinitely. No labels, branch changes or PR edits are made.
"""
from __future__ import annotations

import json
import re

from pilot.auto_integrate import BOT, accepted_branch_kind
from pilot.generated_ci_selection import last_executed_ci_run

SHA = re.compile(r"[0-9a-f]{40}\Z")
MARK = re.compile(r"<!-- LF_T20_CI_RETRY:([1-9][0-9]*):([0-9a-f]{40}):([1-9][0-9]*) -->")
MAX = 100


def _listed(run, repo):
    result = json.loads(run("gh", "pr", "list", "--repo", repo, "--state",
                            "open", "--limit", "100",
                            "--json", "number,headRefName,headRefOid,author"))
    return result if isinstance(result, list) and len(result) < MAX else []


def _comment_rows(run, repo, number, api_list=None):
    # Production CP3.6 passes its separately validated paginated list transport.
    # The run fallback exists for isolated historical T20 offline fixtures.
    raw = (api_list(f"issues/{number}/comments") if api_list is not None
           else json.loads(run("gh", "api",
                  f"repos/{repo}/issues/{number}/comments?per_page=100")))
    if not isinstance(raw, list) or len(raw) >= MAX:
        raise ValueError("CI_RETRY_COMMENT_LEDGER_UNAVAILABLE")
    return raw


def _marker(rows, number, sha):
    for row in rows:
        if not isinstance(row, dict) or (row.get("user") or {}).get("login") != BOT:
            continue
        for match in MARK.finditer(str(row.get("body") or "")):
            if int(match.group(1)) == number and match.group(2) == sha:
                return int(match.group(3))
    return None


def _route_issue(request, route_ok, api):
    if not re.fullmatch(r"req-[1-9][0-9]*", request) or not route_ok(request):
        return None
    number = int(request[4:])
    issue = api(f"issues/{number}")
    if (issue.get("number") != number or issue.get("state") != "open"
            or issue.get("pull_request")
            or "lf-request" not in {label.get("name") for label in issue.get("labels", [])}):
        return None
    return number


def _linked_request(run, api, repo, number, branch, all_plans, route_ok,
                    api_list=None):
    candidates = set()
    direct = re.fullmatch(r"lf/request/(req-[1-9][0-9]*)", branch)
    if direct:
        candidates.add(direct.group(1))
    # PR file list is sourced from the authenticated GitHub PR, not its title.
    try:
        files = (api_list(f"pulls/{number}/files") if api_list is not None
                 else json.loads(run("gh", "api",
                      f"repos/{repo}/pulls/{number}/files?per_page=100")))
    except (ValueError, RuntimeError):
        files = []
    if isinstance(files, list) and len(files) < MAX:
        for item in files:
            if isinstance(item, dict):
                path = str(item.get("filename") or "")
                match = re.fullmatch(r"pilot/runs/(req-[1-9][0-9]*)/.*", path)
                if match:
                    candidates.add(match.group(1))
    # Some native integration PRs only change app sources and their registry.
    if branch.startswith(("lf/native-registration/", "lf/native-integration/")):
        tasks = set()
        for request, _lots, _state, bindings in all_plans:
            for entry in bindings.values():
                if isinstance(entry, dict) and isinstance(entry.get("task_name"), str):
                    task = entry["task_name"]
                    if task in branch:
                        tasks.add(request)
        candidates.update(tasks)
    if len(candidates) != 1:
        return None
    return _route_issue(next(iter(candidates)), route_ok, api)


def _notify_exhausted(run, api, repo, number, branch, sha, source, latest,
                      all_plans, route_ok, api_list=None, *, allow_pr=None):
    issue = _linked_request(run, api, repo, number, branch, all_plans,
                            route_ok, api_list)
    if issue is None:
        return "CI_RETRY_ISSUE_UNMAPPED"
    marker = f"<!-- LF_T20_CI_RETRY_EXHAUSTED:{number}:{sha} -->"
    rows = _comment_rows(run, repo, issue, api_list)
    if any(marker in str(row.get("body") or "")
           for row in rows if isinstance(row, dict)
           and (row.get("user") or {}).get("login") == BOT):
        return "CI_RETRY_ALREADY_NOTIFIED"
    link = f"https://github.com/{repo}/actions/runs/{latest['id']}"
    body = (marker + "\nCI del PR de bot #" + str(number) +
            " sigue rojo tras UN reintento controlado por HEAD " + sha +
            " (corrida original " + str(source) + ", reintento " + link + "). "
            "CI_RETRY_EXHAUSTED: requiere revisión del fallo de infraestructura "
            "o del job; CP3.6 no reintentará de nuevo ese HEAD. Sin etiquetas.")
    if allow_pr is not None and not allow_pr(number, branch):
        return "REQUEST_INACTIVE"
    run("gh", "issue", "comment", str(issue), "--repo", repo, "--body", body)
    return "CI_RETRY_ISSUE_NOTIFIED"


def retry_failed_bot_prs(head, run, api, repo, all_plans, route_ok,
                         api_list=None, *, allow_pr=None):
    """Call once after global main/CI integrity gates, including empty sweeps."""
    outcomes = []
    for row in _listed(run, repo):
        if not isinstance(row, dict):
            continue
        number, branch, sha = row.get("number"), row.get("headRefName"), row.get("headRefOid")
        if (type(number) is not int or number < 1
                or not isinstance(branch, str)
                or accepted_branch_kind(branch) is None
                or not SHA.fullmatch(str(sha))
                or (row.get("author") or {}).get("login") != BOT):
            continue
        if allow_pr is not None and not allow_pr(number, branch):
            outcomes.append({"pr": number, "status": "REQUEST_CLOSED"})
            continue
        try:
            detail = api(f"pulls/{number}")
            if (detail.get("number") != number or detail.get("state") != "open"
                    or detail.get("merged") is True
                    or (detail.get("user") or {}).get("login") != BOT
                    or (detail.get("head") or {}).get("sha") != sha
                    or (detail.get("head") or {}).get("ref") != branch
                    or (detail.get("head") or {}).get("repo", {}).get("full_name") != repo
                    or (detail.get("base") or {}).get("ref") != "main"
                    or (detail.get("base") or {}).get("repo", {}).get("full_name") != repo):
                continue
            response = api(f"actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100")
            records = response.get("workflow_runs")
            if (not isinstance(records, list) or type(response.get("total_count")) is not int
                    or response["total_count"] >= MAX):
                outcomes.append({"pr": number, "status": "BLOCKED",
                                 "reason": "CI_RETRY_RUNS_INCOMPLETE"})
                continue
            eligible = [r for r in records if isinstance(r, dict)
                        and r.get("head_sha") == sha and r.get("head_branch") == branch
                        and r.get("event") in ("pull_request", "workflow_dispatch", "push")
                        and (r.get("path") or "").split("@")[0] == ".github/workflows/ci.yml"]
            latest = last_executed_ci_run(eligible)
            if latest is None or latest.get("status") != "completed" and latest.get("status") != "in_progress":
                continue
            rows = _comment_rows(run, repo, number, api_list)
            original = _marker(rows, number, sha)
            if original is not None:
                status = "CI_RETRY_ALREADY_RECORDED"
                # Do not declare retry failure until a NEW executed run of
                # this exact SHA has finished after the original failing run.
                if (latest.get("status") == "completed"
                        and latest.get("conclusion") in ("failure", "timed_out")
                        and type(latest.get("id")) is int and latest["id"] > original):
                    status = _notify_exhausted(
                        run, api, repo, number, branch, sha, original,
                        latest, all_plans, route_ok, api_list, allow_pr=allow_pr)
                outcomes.append({"pr": number, "head_sha": sha, "status": status})
                continue
            if (latest.get("status") != "completed"
                    or latest.get("conclusion") not in ("failure", "timed_out")
                    or type(latest.get("id")) is not int):
                continue
            # Recheck immutable HEAD immediately before placing the marker.
            current = api(f"pulls/{number}")
            if ((current.get("head") or {}).get("sha") != sha
                    or current.get("state") != "open"):
                outcomes.append({"pr": number, "status": "CI_RETRY_HEAD_MOVED"})
                continue
            origin = latest["id"]
            marker = f"<!-- LF_T20_CI_RETRY:{number}:{sha}:{origin} -->"
            if allow_pr is not None and not allow_pr(number, branch):
                continue
            run("gh", "pr", "comment", str(number), "--repo", repo,
                "--body", marker + "\nT20: único reintento CI por HEAD " +
                sha + ". Corrida previa fallida #" + str(origin) + ". No se modifican "
                "archivos ni etiquetas.")
            # The comment is the durable one-attempt ledger even when dispatch
            # fails. A future sweep will not duplicate an uncertain dispatch.
            if allow_pr is not None and not allow_pr(number, branch):
                continue
            run("gh", "workflow", "run", "ci.yml", "--repo", repo,
                "--ref", branch, "-f", f"pr_number={number}",
                "-f", f"pr_sha={sha}")
            outcomes.append({"pr": number, "head_sha": sha,
                             "status": "CI_RETRY_DISPATCHED", "source_run_id": origin})
        except (ValueError, KeyError, TypeError) as exc:
            outcomes.append({"pr": number, "status": "BLOCKED",
                             "reason": "CI_RETRY_LOCAL_ERROR"})
    return outcomes
