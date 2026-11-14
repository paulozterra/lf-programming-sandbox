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
    "CP3.6 chain after Train merge or spent native failure": "PEDIDO_CADENA_FALLIDA",
    "LF policy C auto-integrate": "PEDIDO_POLITICA_C_FALLIDA",
    "T9 request terminal status and intervention report": "PEDIDO_FINALIZE_FALLIDO",
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
    base = ROUTES.get(name, "PEDIDO_RUTA_FALLIDA")
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
        api.api("POST", f"/issues/{number}/labels",
                {"labels": ["lf-request-blocked"]})
    api.api("POST", f"/issues/{number}/comments",
            {"body": f"{marker}\nRuta bloqueada: \`{code}\`.\nCorrida: {url}\n"
                     "El pedido permanece abierto para revisión."})
    return "RUTA_NOTIFIED"


def check_run(api: Github, run: dict) -> str:
    jobs_obj = api.api("GET", f"/actions/runs/{run['id']}/jobs?per_page=100")
    return emit(api, run, jobs_obj.get("jobs", []))


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
