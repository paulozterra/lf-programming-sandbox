#!/usr/bin/env python3
"""T9.1 independent failed-run watchdog; no execution of code from failed runs."""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = "paulozterra/lf-programming-sandbox"
ROUTES = {
    "T9 issue request intake": "PEDIDO_INTAKE_FALLIDO",
    "ci": "PEDIDO_CI_FALLIDO",
    "CP3.6 chain after Train merge or spent native failure": "PEDIDO_CADENA_FALLIDA",
    "LF policy C auto-integrate": "PEDIDO_POLITICA_C_FALLIDA",
    "T9 request terminal status and intervention report": "PEDIDO_FINALIZE_FALLIDO",
}
TIMEOUT_MINUTES = {
    "T9 issue request intake": 25,
    "CP3.6 chain after Train merge or spent native failure": 40,
    "LF policy C auto-integrate": 27,
    "T9 request terminal status and intervention report": 27,
    "ci": 60,
}
SLUG = re.compile(r"(?:req-|lf/request/req-)([1-9][0-9]*)\b")


def resolve_issue(run: dict) -> int | None:
    """Fail closed: never send a failure to an unrelated issue."""
    candidates = set()
    for key in ("display_title", "head_branch"):
        candidates.update(int(v) for v in SLUG.findall(str(run.get(key) or "")))
    for pr in run.get("pull_requests") or []:
        if isinstance(pr, dict):
            for section in ("head",):
                obj = pr.get(section) or {}
                if isinstance(obj, dict):
                    candidates.update(int(v) for v in SLUG.findall(str(obj.get("ref") or "")))
    if len(candidates) != 1:
        return None
    return next(iter(candidates))


def error_code(run: dict, jobs: list[dict]) -> str:
    name = run.get("name")
    base = run.get("failure_code") or ROUTES.get(name, "PEDIDO_RUTA_FALLIDA")
    # Conservatively stable codes: job outcomes are evidence, not guessed HTTP codes.
    if any(job.get("conclusion") == "timed_out" for job in jobs):
        return "PEDIDO_WORKFLOW_TIMEOUT"
    if run.get("conclusion") == "timed_out":
        return "PEDIDO_WORKFLOW_TIMEOUT"
    return base


def notification(run: dict, jobs: list[dict]) -> tuple[int, str, str] | None:
    if run.get("name") not in ROUTES or run.get("conclusion") not in ("failure", "timed_out"):
        return None
    if run.get("repository", {}).get("full_name") != REPO:
        return None
    issue = resolve_issue(run)
    if issue is None:
        return None
    code = error_code(run, jobs)
    url = run.get("html_url")
    if not isinstance(url, str) or not url.startswith("https://github.com/" + REPO + "/actions/runs/"):
        return None
    return issue, code, url


class Github:
    def __init__(self, token: str):
        if not token:
            raise ValueError("RUTA_NOTIFIER_TOKEN_MISSING")
        self.token = token

    def api(self, method: str, path: str, body=None):
        if not path.startswith("/") or ".." in path:
            raise ValueError("RUTA_NOTIFIER_INVALID_PATH")
        content = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            "https://api.github.com/repos/" + REPO + path, method=method, data=content,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "LF-request-failure-watchdog"})
        with urllib.request.urlopen(req, timeout=25) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("RUTA_NOTIFIER_API_OVERSIZE")
        return json.loads(data) if data else {}

    def pages(self, path):
        result = []
        for page in range(1, 11):
            sep = "&" if "?" in path else "?"
            part = self.api("GET", f"{path}{sep}per_page=100&page={page}")
            if not isinstance(part, list):
                raise ValueError("RUTA_NOTIFIER_INVALID_PAGE")
            result.extend(part)
            if len(part) < 100:
                return result
        raise ValueError("RUTA_NOTIFIER_PAGINATION")


def emit(api: Github, run: dict, jobs: list[dict]) -> str:
    hit = notification(run, jobs)
    if hit is None:
        return "RUTA_NO_ISSUE_ASSOCIATION"
    number, code, url = hit
    issue = api.api("GET", f"/issues/{number}")
    if issue.get("pull_request") or issue.get("state") != "open":
        return "RUTA_ISSUE_NOT_OPEN"
    labels = {x.get("name") for x in issue.get("labels", [])}
    # The issue must have come through the T9 template, not an arbitrary number.
    if "lf-request" not in labels:
        return "RUTA_ISSUE_NOT_LF_REQUEST"
    marker = f"<!-- LF_ROUTE_FAILURE_RUN:{run['id']} -->"
    comments = api.pages(f"/issues/{number}/comments")
    if any(marker in str(c.get("body", "")) for c in comments
           if c.get("user", {}).get("login") == "github-actions[bot]"):
        return "RUTA_ALREADY_NOTIFIED"
    if "lf-request-blocked" not in labels:
        try:
            api.api("POST", f"/issues/{number}/labels",
                    {"labels": ["lf-request-blocked"]})
        except urllib.error.HTTPError as error:
            if error.code != 422:
                raise
            # On first use bootstrap the repository label, then retry.
            try:
                api.api("POST", "/labels", {
                    "name": "lf-request-blocked",
                    "color": "B60205",
                    "description": "La ruta del pedido requiere intervención"})
            except urllib.error.HTTPError as race:
                if race.code != 422:
                    raise
            api.api("POST", f"/issues/{number}/labels",
                    {"labels": ["lf-request-blocked"]})
    api.api("POST", f"/issues/{number}/comments",
            {"body": f"{marker}\nRuta bloqueada: `{code}`.\nCorrida: {url}\n"
                     "El pedido permanece abierto para revisión."})
    return "RUTA_NOTIFIED"


def check_run(api: Github, run: dict) -> str:
    jobs_obj = api.api("GET", f"/actions/runs/{run['id']}/jobs?per_page=100")
    return emit(api, run, jobs_obj.get("jobs", []))


def audit_undispatched_requests(api: Github, all_runs: list[dict], now: datetime) -> list[str]:
    """Identify issues with a bot PR but no CI after a bounded intake interval.

    No alerts on existing successful/pending CI or an issue still awaiting approval.
    """
    results = []
    issues = api.api("GET", "/issues?state=open&labels=lf-request&per_page=100")
    for issue in issues:
        if issue.get("pull_request") or issue.get("state") != "open":
            continue
        n = issue.get("number")
        if type(n) is not int or n < 1:
            continue
        try:
            age = now - datetime.fromisoformat(
                issue["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if age < timedelta(minutes=25) or age > timedelta(hours=24):
            continue
        slug = f"req-{n}"
        branch = f"lf/request/{slug}"
        prs = api.api("GET", f"/pulls?state=all&head=paulozterra:{branch}&per_page=100")
        if not isinstance(prs, list) or not prs:
            continue  # without an admitted PR, no CI dispatch is expected yet
        if any(r.get("name") == "ci" and r.get("head_branch") == branch
               for r in all_runs):
            continue
        # Do not infer absence from the globally truncated run list.
        branch_runs = api.api("GET", f"/actions/workflows/ci.yml/runs?branch={branch}&per_page=5")
        if branch_runs.get("workflow_runs"):
            continue
        intake = [r for r in all_runs if r.get("name") == "T9 issue request intake"
                  and resolve_issue(r) == n]
        if not intake:
            continue
        last = max(intake, key=lambda r: r.get("id", 0))
        # Failure messages use the exact preceding intake run URL.
        run = dict(last, conclusion="failure",
                   failure_code="PEDIDO_CI_NO_DISPARADO")
        results.append(f"{n}:{emit(api, run, [])}")
    return results


def stalled_run(run: dict, now: datetime) -> dict | None:
    name = run.get("name")
    if name not in TIMEOUT_MINUTES or run.get("status") not in (
            "queued", "in_progress", "waiting", "requested", "pending"):
        return None
    try:
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError, TypeError):
        return None
    if now - created < timedelta(minutes=TIMEOUT_MINUTES[name]):
        return None
    return dict(run, conclusion="failure",
                failure_code="PEDIDO_WORKFLOW_SIN_AVANCE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise ValueError("RUTA_NOTIFIER_REPOSITORY_INVALID")
    api = Github(os.environ.get("GH_TOKEN", ""))
    if args.run_id:
        run = api.api("GET", f"/actions/runs/{args.run_id}")
        print(check_run(api, run))
        return
    if not args.sweep:
        raise ValueError("RUTA_NOTIFIER_MODE_REQUIRED")
    # Bot-token initiated workflows may not fire workflow_run; poll as backup.
    limit = datetime.now(timezone.utc) - timedelta(hours=24)
    all_runs = []
    for page in range(1, 5):
        batch = api.api("GET", f"/actions/runs?per_page=100&page={page}")
        items = batch.get("workflow_runs", [])
        all_runs.extend(items)
        if len(items) < 100:
            break
    for state in audit_undispatched_requests(api, all_runs, datetime.now(timezone.utc)):
        print(state)
    now = datetime.now(timezone.utc)
    for run in all_runs:
        stalled = stalled_run(run, now)
        if stalled is not None:
            print(run["id"], check_run(api, stalled))
    for run in all_runs:
        if run.get("name") not in ROUTES or run.get("conclusion") not in ("failure", "timed_out"):
            continue
        stamp = run.get("created_at", "")
        try:
            if datetime.fromisoformat(stamp.replace("Z", "+00:00")) < limit:
                continue
        except ValueError:
            continue
        print(run["id"], check_run(api, run))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print("RUTA_NOTIFICACION_FALLIDA:" + str(exc), file=sys.stderr)
        raise SystemExit(1)
