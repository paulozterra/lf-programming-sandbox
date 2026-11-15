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
    "T7 main request auto-admission (trusted, no model)": "PEDIDO_T7_FALLIDO",
    "T9 issue request intake": "PEDIDO_INTAKE_FALLIDO",
    "ci": "PEDIDO_CI_FALLIDO",
    "CP3.6 chain after Train merge or spent native failure": "PEDIDO_CADENA_FALLIDA",
    "LF policy C auto-integrate": "PEDIDO_POLITICA_C_FALLIDA",
    "T9 request terminal status and intervention report": "PEDIDO_FINALIZE_FALLIDO",
    "CP3.7 pinned PG06-PG14 evidence and H_REPORT": "PEDIDO_EVIDENCIA_FALLIDA",
    "LF Worker native (trusted workflow_run or manual, no API)": "PEDIDO_WORKER_FALLIDO",
    "CP3.5 native verified patch to draft PR": "PEDIDO_INTEGRACION_FALLIDA",
    "T9.2 trusted Train handoff dispatch": "PEDIDO_RELEVO_FALLIDO",
}
TIMEOUT_MINUTES = {
    "T7 main request auto-admission (trusted, no model)": 30,
    "T9 issue request intake": 25,
    "CP3.6 chain after Train merge or spent native failure": 40,
    "LF policy C auto-integrate": 27,
    "T9 request terminal status and intervention report": 27,
    "ci": 60,
    "CP3.7 pinned PG06-PG14 evidence and H_REPORT": 40,
    "LF Worker native (trusted workflow_run or manual, no API)": 40,
    "CP3.5 native verified patch to draft PR": 30,
    "T9.2 trusted Train handoff dispatch": 25,
}
SLUG = re.compile(r"(?:req-|lf/request/req-)([1-9][0-9]*)\b")


def route_name(run: dict) -> str:
    """Use trusted workflow identity, not GitHub's dynamic run-name."""
    path = str(run.get("path") or "").split("@")[0]
    if (path == ".github/workflows/t7-request.yml"
            and run.get("event") in ("workflow_dispatch", "push")):
        return "T7 main request auto-admission (trusted, no model)"
    mapping = {
        ".github/workflows/train-handoff.yml":
            "T9.2 trusted Train handoff dispatch",
        ".github/workflows/chain-lots.yml":
            "CP3.6 chain after Train merge or spent native failure",
        ".github/workflows/pg37-evidence.yml":
            "CP3.7 pinned PG06-PG14 evidence and H_REPORT",
        ".github/workflows/worker-native.yml":
            "LF Worker native (trusted workflow_run or manual, no API)",
        ".github/workflows/native-verified-integration.yml":
            "CP3.5 native verified patch to draft PR",
    }
    if path in mapping:
        return mapping[path]
    return str(run.get("name") or "")


def verified_stage_issue(api, run: dict) -> int | None:
    """Bind stage titles to a trusted merged PR's actual changed paths.

    Never parse arbitrary PR text or a user's suggested issue number. In
    particular CP3.6 PR 177 resolves to req-175 through the verified diff.
    """
    path = str(run.get("path") or "").split("@")[0]
    if path not in (".github/workflows/chain-lots.yml",
                    ".github/workflows/train-handoff.yml"):
        return None
    if run.get("event") != "workflow_dispatch":
        return None
    title = str(run.get("display_title") or "")
    if path == ".github/workflows/train-handoff.yml":
        match = re.fullmatch(r"Train handoff PR ([1-9][0-9]*)", title)
        if match:
            number, claimed = int(match.group(1)), None
        else:
            return None
    else:
        match = re.fullmatch(r"CP3[.]6 (?:req-([1-9][0-9]*) )?PR ([1-9][0-9]*)", title)
        if match is None:
            return None
        claimed, number = match.group(1), int(match.group(2))
    pr = api.api("GET", f"/pulls/{number}")
    if (pr.get("number") != number or pr.get("merged") is not True
            or pr.get("merge_commit_sha") != run.get("head_sha")
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != REPO
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO
            or pr.get("user", {}).get("login") != "github-actions[bot]"):
        return None
    branch = str(pr.get("head", {}).get("ref") or "")
    if not (re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch)
            or re.fullmatch(r"lf/native-integration/[a-z][a-z0-9_-]{0,31}-run-[1-9][0-9]*", branch)):
        return None
    files = api.api("GET", f"/pulls/{number}/files?per_page=100")
    if not isinstance(files, list) or len(files) >= 100:
        return None
    slugs = {m.group(1) for item in files if isinstance(item, dict)
             and (m := re.fullmatch(
                 r"pilot/runs/(req-[1-9][0-9]*)/(?:analysis|state|lots|chain_plan)[.]json",
                 str(item.get("filename") or "")))}
    # An integration PR can change application code only. The task -> slug
    # mapping is independently derived from a pinned plan on main.
    if not slugs and branch.startswith("lf/native-integration/"):
        task = branch[len("lf/native-integration/"):].rsplit("-run-", 1)[0]
        slugs = request_for_task(task)
    if len(slugs) != 1:
        return None
    slug = next(iter(slugs))
    if claimed and slug != f"req-{claimed}":
        return None
    return int(slug[4:])


def request_for_task(task: str) -> set[str]:
    """Resolve a registered task only through committed request plans."""
    from pathlib import Path
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
        return set()
    root = Path(__file__).resolve().parents[1]
    slugs = set()
    for plan in (root / "pilot/runs").glob("req-*/chain_plan.json"):
        if plan.is_symlink() or plan.parent.is_symlink():
            continue
        try:
            records = json.loads(plan.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for row in records.get("bindings", []):
            registered = row.get("task_name") if isinstance(row, dict) else None
            if isinstance(registered, str) and (registered == task or
                    re.fullmatch(re.escape(registered) + r"(?:[2-9]|[1-9][0-9]+)", task)):
                slugs.add(plan.parent.name)
    return slugs


def task_stage_issue(run: dict) -> int | None:
    """Bind worker and integration run titles to committed chain-plan tasks.

    The task is not a user-written PR title: it is the workflow's versioned
    run-name expression, and the matching plan must be unique.
    """
    path = str(run.get("path") or "").split("@")[0]
    title = str(run.get("display_title") or "")
    if path == ".github/workflows/native-verified-integration.yml":
        if not title.startswith("CP3.5 "):
            return None
        title = title[6:]
    elif path != ".github/workflows/worker-native.yml":
        return None
    task = None
    if (m := re.fullmatch(r"lf-native-(?:req-[1-9][0-9]*-)?([a-z][a-z0-9_-]{0,31})-a[123]", title)):
        task = m.group(1)
    elif (m := re.fullmatch(r"lf-native-auto-lf/native-proposal/([a-z][a-z0-9_-]{0,31})-[0-9a-f]{40}", title)):
        task = m.group(1)
    if task is None:
        return None
    slugs = request_for_task(task)
    if len(slugs) != 1:
        return None
    return int(next(iter(slugs))[4:])


def verified_pg37_issue(api, run: dict) -> int | None:
    """Correlate CP3.7 to one bot-produced analysis PR via its source branch."""
    if str(run.get("path") or "").split("@")[0] != ".github/workflows/pg37-evidence.yml":
        return None
    title = str(run.get("display_title") or "")
    branch = title.removeprefix("CP3.7 ")
    if not re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch):
        return None
    prs = api.api("GET", f"/pulls?state=all&head=paulozterra:{branch}&per_page=100")
    if not isinstance(prs, list) or len(prs) >= 100:
        return None
    # The PR *list* endpoint does not guarantee a 'merged' boolean.
    # Fetch the exact PR detail before trusting its Train provenance.
    candidates = [row for row in prs if
                  row.get("head", {}).get("ref") == branch
                  and row.get("user", {}).get("login") == "github-actions[bot]"
                  and type(row.get("number")) is int]
    if len(candidates) != 1:
        return None
    pr = api.api("GET", f"/pulls/{candidates[0]['number']}")
    if (pr.get("merged") is not True
            or pr.get("head", {}).get("ref") != branch
            or pr.get("user", {}).get("login") != "github-actions[bot]"
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != REPO
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO):
        return None
    files = api.api("GET", f"/pulls/{pr['number']}/files?per_page=100")
    if not isinstance(files, list) or len(files) >= 100:
        return None
    slugs = {m.group(1) for item in files if isinstance(item, dict)
             and (m := re.fullmatch(
                 r"pilot/runs/(req-[1-9][0-9]*)/(?:analysis|state|lots|chain_plan)[.]json",
                 str(item.get("filename") or "")))}
    return int(next(iter(slugs))[4:]) if len(slugs) == 1 else None


def resolve_issue(run: dict) -> int | None:
    """Only system-derived issue references; never mine arbitrary PR titles."""
    candidates = set()
    branch = re.fullmatch(r"lf/request/req-([1-9][0-9]*)",
                          str(run.get("head_branch") or ""))
    if branch:
        candidates.add(int(branch.group(1)))
    for pr in run.get("pull_requests") or []:
        if not isinstance(pr, dict):
            continue
        head = pr.get("head") or {}
        if not isinstance(head, dict):
            continue
        remote = head.get("repo") or {}
        if isinstance(remote, dict) and remote.get("full_name") not in (None, REPO):
            continue
        match = re.fullmatch(r"lf/request/req-([1-9][0-9]*)",
                             str(head.get("ref") or ""))
        if match:
            candidates.add(int(match.group(1)))
    title = str(run.get("display_title") or "")
    # The intake's run-name comes directly from github.event.issue.number.
    if run.get("name") == "T9 issue request intake":
        match = re.fullmatch(r"T9 intake req-([1-9][0-9]*)", title)
    elif route_name(run) == "T7 main request auto-admission (trusted, no model)":
        # workflow_dispatch title T7 <slug> is generated by the trusted
        # workflow from inputs.slug. Never mine arbitrary user-controlled titles.
        trusted_path = (str(run.get("path") or "").split("@")[0]
                        == ".github/workflows/t7-request.yml")
        name = str(run.get("name") or "")
        consistent = name == title or name == "T7 main request auto-admission (trusted, no model)"
        match = (re.fullmatch(r"T7 req-([1-9][0-9]*)", title)
                 if run.get("event") == "workflow_dispatch" and trusted_path
                 and consistent else None)
    elif route_name(run) == "CP3.6 chain after Train merge or spent native failure":
        match = re.fullmatch(r"CP3[.]6 req-([1-9][0-9]*) PR [1-9][0-9]*", title)
    elif run.get("name") == "LF policy C auto-integrate":
        match = re.fullmatch(r"Policy C lf/request/req-([1-9][0-9]*)", title)
    else:
        match = None
    if match:
        candidates.add(int(match.group(1)))
    return next(iter(candidates)) if len(candidates) == 1 else None


def error_code(run: dict, jobs: list[dict]) -> str:
    name = route_name(run)
    base = run.get("failure_code") or ROUTES.get(name, "PEDIDO_RUTA_FALLIDA")
    # Conservatively stable codes: job outcomes are evidence, not guessed HTTP codes.
    if any(job.get("conclusion") == "timed_out" for job in jobs):
        return "PEDIDO_WORKFLOW_TIMEOUT"
    if run.get("conclusion") == "timed_out":
        return "PEDIDO_WORKFLOW_TIMEOUT"
    return base


def notification(run: dict, jobs: list[dict]) -> tuple[int, str, str] | None:
    if route_name(run) not in ROUTES or run.get("conclusion") not in ("failure", "timed_out"):
        return None
    if run.get("repository", {}).get("full_name") != REPO:
        return None
    head_repo = run.get("head_repository") or {}
    if (isinstance(head_repo, dict) and head_repo.get("full_name") not in (None, REPO)):
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
    # For post-Train stages, the run's branch is main; use the real merged
    # PR's files instead of pretending main is an lf/request/ branch.
    stage = route_name(run)
    path = str(run.get("path") or "").split("@")[0]
    if (path in (".github/workflows/chain-lots.yml",
                 ".github/workflows/train-handoff.yml")
            and run.get("event") == "workflow_dispatch"):
        linked = verified_stage_issue(api, run)
        if linked is None:
            return "RUTA_NO_ISSUE_ASSOCIATION"
        run = dict(run, head_branch=f"lf/request/req-{linked}")
    elif path in (".github/workflows/worker-native.yml",
                    ".github/workflows/native-verified-integration.yml"):
        linked = task_stage_issue(run)
        if linked is None:
            return "RUTA_NO_ISSUE_ASSOCIATION"
        run = dict(run, head_branch=f"lf/request/req-{linked}")
    elif path == ".github/workflows/pg37-evidence.yml":
        linked = verified_pg37_issue(api, run)
        if linked is None:
            return "RUTA_NO_ISSUE_ASSOCIATION"
        run = dict(run, head_branch=f"lf/request/req-{linked}")
    hit = notification(run, jobs)
    if hit is None:
        return "RUTA_NO_ISSUE_ASSOCIATION"
    number, code, url = hit
    if run.get("name") != "T9 issue request intake":
        # Branch-title strings alone are insufficient: verify the original
        # lf/request/ PR was created by the trusted bot, including after merge.
        prs = api.api("GET", f"/pulls?state=all&head=paulozterra:lf/request/req-{number}&per_page=100")
        if not isinstance(prs, list) or not any(
                isinstance(pr, dict) and isinstance(pr.get("user"), dict)
                and pr["user"].get("login") == "github-actions[bot]"
                and isinstance(pr.get("head"), dict)
                and pr["head"].get("ref") == f"lf/request/req-{number}"
                for pr in prs):
            return "RUTA_PR_ORIGEN_NO_CONFIABLE"
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
            if error.code not in (404, 422):
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
    ci_link = run.get("main_ci_url")
    extra = (f"CI exacto de main: {ci_link}\n" if isinstance(ci_link, str)
             and ci_link.startswith("https://github.com/" + REPO + "/actions/runs/") else "")
    api.api("POST", f"/issues/{number}/comments",
            {"body": f"{marker}\nRuta bloqueada: `{code}`.\nCorrida: {url}\n"
                     + extra + "El pedido permanece abierto para revisión."})
    return "RUTA_NOTIFIED"


def check_run(api: Github, run: dict) -> str:
    jobs_obj = api.api("GET", f"/actions/runs/{run['id']}/jobs?per_page=100")
    if (route_name(run) in ("CP3.6 chain after Train merge or spent native failure",
                                "T9.2 trusted Train handoff dispatch")
            and run.get("conclusion") == "failure"
            and re.fullmatch(r"[0-9a-f]{40}", str(run.get("head_sha") or ""))):
        # Mirror t4_admission's exact-SHA requirement. Absence/failed CI
        # is a real BASE_NO_VERDE prerequisite; never invent green status.
        sha = run["head_sha"]
        base = api.api("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100")
        rows = base.get("workflow_runs", [])
        eligible = [row for row in rows if isinstance(row, dict)
                    and row.get("head_sha") == sha
                    and row.get("head_branch") == "main"
                    and row.get("event") in ("push", "workflow_dispatch")]
        if not eligible or max(eligible, key=lambda r: (r.get("created_at", ""), r.get("id", 0))).get("conclusion") != "success":
            latest = max(eligible, key=lambda r: (r.get("created_at", ""), r.get("id", 0)), default=None)
            run = dict(run, failure_code="BASE_NO_VERDE",
                       main_ci_url=(latest or {}).get("html_url"))
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
        if not isinstance(prs, list) or not any(
                isinstance(pr, dict) and isinstance(pr.get("user"), dict)
                and pr["user"].get("login") == "github-actions[bot]"
                and isinstance(pr.get("head"), dict)
                and pr["head"].get("ref") == branch
                for pr in prs):
            continue  # never infer an admitted request from an arbitrary PR
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
    name = route_name(run)
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
        if route_name(run) not in ROUTES or run.get("conclusion") not in ("failure", "timed_out"):
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
