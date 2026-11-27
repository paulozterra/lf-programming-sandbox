#!/usr/bin/env python3
"""T9.1 independent failed-run watchdog; no execution of code from failed runs."""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[1]))
from pilot.config.project_config import storage_path, storage
import argparse
import json
import os
import re

import sys
from pathlib import Path
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
# The policy/watchdog are loaded in isolated python -I run_path tests too.
# Resolve this pinned module from the trusted script directory, never cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generated_ci_selection import last_executed_ci_run
from native_registration_family import is_native_registration, registration_family

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
    for plan in (storage_path("requests_root", root=root)).glob("req-*/chain_plan.json"):
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
    if (m := re.fullmatch(r"lf-native-([a-z][a-z0-9_-]{0,31})-a[123]-[0-9a-f]{40}", title)):
        task = m.group(1)
    elif (m := re.fullmatch(r"lf-native-(?:req-[1-9][0-9]*-)?([a-z][a-z0-9_-]{0,31})-a[123]", title)):
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


def generated_ci_issue(api, run: dict) -> int | None:
    """Bind failed CI from a generated branch to the original request.

    Bot authorship, branch, and exact run SHA are independently checked
    against the GitHub PR API. Never infer identity from a PR title/body.
    """
    if (str(run.get("path") or "").split("@")[0] != ".github/workflows/ci.yml"
            or run.get("conclusion") not in ("failure", "timed_out")):
        return None
    branch = run.get("head_branch")
    sha = run.get("head_sha")
    if not isinstance(branch, str) or not isinstance(sha, str) or not re.fullmatch(
            r"[0-9a-f]{40}", sha):
        return None
    task = None
    direct = re.fullmatch(r"lf/request/req-([1-9][0-9]*)", branch)
    family, registered_task = registration_family(branch)
    register = family in ("registration", "auxiliary")
    integration = re.fullmatch(
        r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-[1-9][0-9]*", branch)
    t7 = re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch)
    if not any((direct, register, integration, t7)):
        return None
    prs = api.api("GET", f"/pulls?state=all&head=paulozterra:{branch}&per_page=100")
    if not isinstance(prs, list) or len(prs) >= 100:
        return None
    matches = [pr for pr in prs if isinstance(pr, dict)
               and (pr.get("user") or {}).get("login") == "github-actions[bot]"
               and (pr.get("head") or {}).get("ref") == branch
               and (pr.get("head") or {}).get("sha") == sha
               and (pr.get("head") or {}).get("repo", {}).get("full_name") == REPO
               and type(pr.get("number")) is int]
    if len(matches) != 1:
        return None
    if direct:
        return int(direct.group(1))
    if register or integration:
        task = registered_task if register else integration.group(1)
        slugs = request_for_task(task)
        return int(next(iter(slugs))[4:]) if len(slugs) == 1 else None
    files = api.api("GET", f"/pulls/{matches[0]['number']}/files?per_page=100")
    if not isinstance(files, list) or len(files) >= 100:
        return None
    slugs = {m.group(1) for row in files if isinstance(row, dict)
             and (m := re.fullmatch(r"pilot/runs/(req-[1-9][0-9]*)/"
                                     r"(?:analysis|state|lots|chain_plan)[.]json",
                                     str(row.get("filename") or "")))}
    return int(next(iter(slugs))[4:]) if len(slugs) == 1 else None


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


def notification_lifecycle(api, number):
    """A watchdog notice is a request mutation, not merely observation."""
    from pilot.orchestrator.request_lifecycle import request_state, OPEN, inactive_reason, RequestStateError
    try:
        state = request_state(f"req-{number}", lambda path: api.api("GET", "/" + path))
        return None if state == OPEN else inactive_reason(state)
    except RequestStateError:
        return "REQUEST_STATE_UNRESOLVED"


def emit(api: Github, run: dict, jobs: list[dict]) -> str:
    # CI for a generated branch can have no issue in its run-name. Resolve
    # its bot PR and committed task/plan before using the standard notifier.
    linked_ci = generated_ci_issue(api, run)
    if linked_ci is not None:
        run = dict(run, head_branch=f"lf/request/req-{linked_ci}")
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
    trusted_origin = run.get("name") != "T9 issue request intake"
    if trusted_origin:
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
    if "lf-request" not in labels and not trusted_origin:
        return "RUTA_ISSUE_NOT_LF_REQUEST"
    # T51: source ID + terminal conclusion is the idempotence key.
    # The existing bot issue comments are the durable store; accept legacy
    # T9.1 markers too, so a rollout cannot re-notify earlier failures.
    conclusion = run.get("conclusion")
    if conclusion not in ("failure", "timed_out"):
        return "RUTA_NO_ISSUE_ASSOCIATION"
    marker = f"<!-- LF_ROUTE_FAILURE_RUN:{run['id']}:{conclusion} -->"
    legacy = f"<!-- LF_ROUTE_FAILURE_RUN:{run['id']} -->"
    comments = api.pages(f"/issues/{number}/comments")
    if any((marker in str(c.get("body", "")) or legacy in str(c.get("body", "")))
           for c in comments if c.get("user", {}).get("login") == "github-actions[bot]"):
        return "RUTA_ALREADY_NOTIFIED"
    stop = notification_lifecycle(api, number)
    if stop:
        return stop
    # T17 only comments on generated PR CI failures; it must not add labels.
    if "lf-request-blocked" not in labels and linked_ci is None:
        try:
            api.api("POST", f"/issues/{number}/labels",
                    {"labels": ["lf-request-blocked"]})
        except urllib.error.HTTPError as error:
            if error.code not in (404, 422):
                raise
            # On first use bootstrap the repository label, then retry.
            stop = notification_lifecycle(api, number)
            if stop:
                return stop
            try:
                api.api("POST", "/labels", {
                    "name": "lf-request-blocked",
                    "color": "B60205",
                    "description": "La ruta del pedido requiere intervención"})
            except urllib.error.HTTPError as race:
                if race.code != 422:
                    raise
            stop = notification_lifecycle(api, number)
            if stop:
                return stop
            api.api("POST", f"/issues/{number}/labels",
                    {"labels": ["lf-request-blocked"]})
    ci_link = run.get("main_ci_url")
    extra = (f"CI exacto de main: {ci_link}\n" if isinstance(ci_link, str)
             and ci_link.startswith("https://github.com/" + REPO + "/actions/runs/") else "")
    stop = notification_lifecycle(api, number)
    if stop:
        return stop
    api.api("POST", f"/issues/{number}/comments",
            {"body": f"{marker}\nRuta bloqueada: `{code}`.\nCorrida: {url}\n"
                     + extra + "El pedido permanece abierto para revisión."})
    ekb_candidate(code, run, number)
    return "RUTA_NOTIFIED"


def ekb_candidate(code: str, run: dict, number: int) -> None:
    """T56: hand the notified failure to the trusted EKB step (file only).

    Written once per newly notified run (the marker above is idempotent), so
    the EKB recurrence count follows real failures. Never blocks notifying."""
    path = os.environ.get("LF_ROUTE_EKB_CANDIDATES")
    if not path or not isinstance(run.get("id"), int):
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"code": code, "run_id": run["id"],
                                     "request": f"req-{number}"}) + "\n")
    except OSError:
        pass


def notify_global_cp36_sweep(api: Github, run: dict) -> str:
    """Report a failed trusted-main CP3.6 sweep even without one source PR.

    Notification is comment-only; a single reusable route-alert issue is used
    when there are no verifiably affected open LF requests.
    """
    if (route_name(run) != "CP3.6 chain after Train merge or spent native failure"
            or run.get("event") != "workflow_dispatch"
            or run.get("conclusion") not in ("failure", "timed_out")
            or run.get("head_branch") != "main"
            or not re.fullmatch(r"CP3[.]6 [1-9][0-9]*",
                                str(run.get("display_title") or ""))
            or type(run.get("id")) is not int):
        return "RUTA_NOT_GLOBAL_CP36_SWEEP"
    marker = f"<!-- LF_CP36_GLOBAL_SWEEP:{run['id']} -->"
    link = (run.get("html_url") if isinstance(run.get("html_url"), str)
            and run["html_url"].startswith("https://github.com/" + REPO + "/actions/runs/")
            else "https://github.com/" + REPO + "/actions/runs/" + str(run["id"]))
    targets = []
    for issue in api.pages("/issues?state=open&labels=lf-request"):
        if not isinstance(issue, dict) or issue.get("pull_request") or issue.get("state") != "open":
            continue
        number = issue.get("number")
        if type(number) is not int or number <= 0:
            continue
        # A real route request must already be present on trusted main.
        try:
            source = api.api("GET", f"/contents/pilot/runs/req-{number}/request_meta.json?ref=main")
            import base64
            raw = base64.b64decode(source["content"], validate=False)
            meta = json.loads(raw)
        except (KeyError, TypeError, ValueError, urllib.error.HTTPError):
            continue
        if isinstance(meta, dict) and meta.get("issue") == number and not notification_lifecycle(api, number):
            targets.append(number)
    request_targets = set(targets)
    if not targets:
        title = "[LF ROUTE ALERT] CP3.6 global sweep"
        alerts = api.pages("/issues?state=open")
        matches = [x for x in alerts if isinstance(x, dict)
                   and x.get("title") == title and not x.get("pull_request")]
        if matches:
            targets = [matches[0]["number"]]
        else:
            created = api.api("POST", "/issues", {
                "title": title,
                "body": "Alerta única de la ruta LF para fallos globales de CP3.6. "
                        "No contiene datos sensibles ni crea etiquetas."})
            targets = [created["number"]]
    for number in sorted(set(targets)):
        comments = api.pages(f"/issues/{number}/comments")
        if any(marker in str(item.get("body", "")) for item in comments
               if isinstance(item, dict)):
            continue
        if number in request_targets and notification_lifecycle(api, number):
            continue
        api.api("POST", f"/issues/{number}/comments", {
            "body": marker + "\nCP3.6: fallo global del barrido; ningún pedido "
                    "debe quedar sin alerta. Corrida: " + link
                    + "\nSin etiquetas nuevas. Revisar integridad del main y el workflow."})
    return "RUTA_GLOBAL_CP36_NOTIFIED"


def notify_t20_retry_exhaustion(api: Github, run: dict) -> str:
    """Report a failed second CI from an authenticated one-HEAD bot retry.

    The first failed run is not exhaustion. The HEAD and latest *executed*
    CI are independently matched, and labels are never changed.
    """
    if ((str(run.get("path") or "").split("@")[0] != ".github/workflows/ci.yml")
            or run.get("event") != "workflow_dispatch"
            or run.get("status") != "completed"
            or run.get("conclusion") not in ("failure", "timed_out")
            or type(run.get("id")) is not int
            or not re.fullmatch(r"[0-9a-f]{40}", str(run.get("head_sha") or ""))):
        return "T20_NOT_RETRY_EXHAUSTION"
    sha, branch = run["head_sha"], str(run.get("head_branch") or "")
    if not branch.startswith("lf/"):
        return "T20_NOT_RETRY_EXHAUSTION"
    prs = api.api("GET", "/pulls?state=open&head=paulozterra:" + branch + "&per_page=100")
    if not isinstance(prs, list) or len(prs) >= 100:
        return "T20_RETRY_PR_NOT_VERIFIED"
    matched = [p for p in prs if isinstance(p, dict)
               and (p.get("user") or {}).get("login") == "github-actions[bot]"
               and (p.get("head") or {}).get("sha") == sha
               and (p.get("head") or {}).get("ref") == branch
               and (p.get("head") or {}).get("repo", {}).get("full_name") == REPO
               and (p.get("base") or {}).get("ref") == "main"
               and type(p.get("number")) is int]
    if len(matched) != 1:
        return "T20_NOT_RETRY_EXHAUSTION"
    pr = matched[0]["number"]
    # Only a bot-authored retry marker can authorize an exhaustion alert.
    comments = api.pages(f"/issues/{pr}/comments")
    marker = re.compile(
        r"<!-- LF_T20_CI_RETRY:" + str(pr) + ":" + sha +
        r":([1-9][0-9]*) -->")
    origins = [int(m.group(1)) for row in comments if isinstance(row, dict)
               and (row.get("user") or {}).get("login") == "github-actions[bot]"
               for m in marker.finditer(str(row.get("body") or ""))]
    if len(set(origins)) != 1 or run["id"] <= origins[0]:
        return "T20_NOT_RETRY_EXHAUSTION"
    runs = api.api("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100")
    rows = runs.get("workflow_runs")
    if (not isinstance(rows, list) or type(runs.get("total_count")) is not int
            or runs["total_count"] >= 100):
        return "T20_RETRY_RUNS_UNVERIFIED"
    latest = last_executed_ci_run([
        row for row in rows if isinstance(row, dict)
        and row.get("head_sha") == sha and row.get("head_branch") == branch
        and row.get("event") in ("workflow_dispatch", "pull_request", "push")
        and (row.get("path") or "").split("@")[0] == ".github/workflows/ci.yml"])
    if latest is None or latest.get("id") != run["id"]:
        return "T20_RETRY_SUPERSEDED"
    # Match the issue from the bot PR's changed filenames, never from its
    # title, body, or a caller-controlled issue number.
    files = api.api("GET", f"/pulls/{pr}/files?per_page=100")
    if not isinstance(files, list) or len(files) >= 100:
        return "T20_RETRY_ISSUE_UNMAPPED"
    slugs = {m.group(1) for item in files if isinstance(item, dict)
             and (m := re.fullmatch(
                 r"pilot/runs/(req-[1-9][0-9]*)/.*",
                 str(item.get("filename") or "")))}
    if len(slugs) != 1:
        return "T20_RETRY_ISSUE_UNMAPPED"
    slug = next(iter(slugs))
    number = int(slug[4:])
    import base64
    try:
        metadata = api.api("GET", f"/contents/pilot/runs/{slug}/request_meta.json?ref=main")
        raw = base64.b64decode(metadata["content"], validate=False)
        source = json.loads(raw)
    except (KeyError, TypeError, ValueError, urllib.error.HTTPError):
        return "T20_RETRY_ISSUE_UNVERIFIED"
    if not isinstance(source, dict) or source.get("issue") != number:
        return "T20_RETRY_ISSUE_UNVERIFIED"
    issue = api.api("GET", f"/issues/{number}")
    if (issue.get("number") != number or issue.get("state") != "open"
            or issue.get("pull_request")
            or "lf-request" not in {l.get("name") for l in issue.get("labels", [])}):
        return "T20_RETRY_ISSUE_UNVERIFIED"
    done = f"<!-- LF_T20_CI_RETRY_EXHAUSTED:{pr}:{sha} -->"
    if any(done in str(row.get("body") or "")
           for row in api.pages(f"/issues/{number}/comments")
           if isinstance(row, dict)
           and (row.get("user") or {}).get("login") == "github-actions[bot]"):
        return "T20_RETRY_EXHAUSTION_ALREADY_NOTIFIED"
    body = (done + "\nCI_RETRY_EXHAUSTED: CI del PR del bot #" + str(pr) +
            " volvió a fallar tras el único reintento por HEAD " + sha +
            ". Corrida fallida: https://github.com/" + REPO +
            "/actions/runs/" + str(run["id"]) +
            ". No se volverá a despachar para ese HEAD. "
            "Revisar infraestructura/Playwright; no se agregaron etiquetas.")
    stop = notification_lifecycle(api, number)
    if stop:
        return stop
    api.api("POST", f"/issues/{number}/comments", {"body": body})
    return "T20_RETRY_EXHAUSTION_NOTIFIED"


def check_run(api: Github, run: dict) -> str:
    # T51 fast path: a successful/nonterminal source has no failure to
    # notify; avoid jobs, CI history, issue pages and global sweeps.
    if run.get("conclusion") not in ("failure", "timed_out"):
        return "RUTA_SOURCE_NOT_FAILED"
    exhausted = notify_t20_retry_exhaustion(api, run)
    if exhausted not in ("T20_NOT_RETRY_EXHAUSTION", "T20_RETRY_SUPERSEDED"):
        return exhausted
    # A webhook/scheduled sweep may see a later unexecuted action_required
    # event on the same generated PR SHA. Notify from the latest *executed*
    # CI only; never mark a newer successful PR as failed.
    branch = str(run.get("head_branch") or "")
    sha = str(run.get("head_sha") or "")
    generated = (
        is_native_registration(branch)
        or re.fullmatch(r"lf/native-integration/[a-z][a-z0-9_-]{0,31}-run-[1-9][0-9]*", branch)
        or re.fullmatch(r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?", branch)
        or re.fullmatch(r"lf/request/req-[1-9][0-9]*", branch)
    )
    if (generated and route_name(run) == "ci"
            and re.fullmatch(r"[0-9a-f]{40}", sha)):
        response = api.api("GET", f"/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=100")
        rows = response.get("workflow_runs", [])
        if (not isinstance(rows, list) or response.get("total_count", 101) > 100):
            return "RUTA_CI_EVIDENCIA_INCOMPLETA"
        latest = last_executed_ci_run([
            row for row in rows if isinstance(row, dict)
            and row.get("head_branch") == branch and row.get("head_sha") == sha
            and row.get("event") in ("workflow_dispatch", "pull_request", "push")])
        if latest is None or latest.get("id") != run.get("id"):
            return "RUTA_CI_SUPERADA_O_NO_EJECUTADA"
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
    outcome = emit(api, run, jobs_obj.get("jobs", []))
    if outcome == "RUTA_NO_ISSUE_ASSOCIATION":
        fallback = notify_global_cp36_sweep(api, run)
        if fallback != "RUTA_NOT_GLOBAL_CP36_SWEEP":
            return fallback
    return outcome


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


def result_class(result: str) -> str:
    if result == "RUTA_SOURCE_NOT_FAILED":
        return "RUTA_SOURCE_NOT_FAILED"
    if "ALREADY" in result or "DEDUP" in result or "SUPERSEDED" in result:
        return "DEDUPED"
    return "PROCESSED"


def arrival_record(source_run_id: int | None, run: dict | None, result: str) -> dict:
    """T52: one line per activation, to learn which arrival path really fires."""
    watchdog = os.environ.get("GITHUB_RUN_ID", "")
    path = str((run or {}).get("path") or "").split("@")[0]
    record = {
        "schema": "LF_WATCHDOG_ARRIVAL_V1",
        "watchdog_run_id": int(watchdog) if watchdog.isdigit() else None,
        "source_run_id": source_run_id,
        "source_workflow": path or (run or {}).get("name"),
        "arrival": os.environ.get("GITHUB_EVENT_NAME") or "unknown",
        "result": result,
        "result_class": "SWEEP" if source_run_id is None else result_class(result),
    }
    print("LF_WATCHDOG_ARRIVAL " + json.dumps(record, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write("| watchdog | source | workflow | arrival | result |\n"
                             "|---|---|---|---|---|\n"
                             f"| {record['watchdog_run_id']} | {source_run_id} | "
                             f"{record['source_workflow']} | {record['arrival']} | "
                             f"{record['result_class']} ({result}) |\n")
        except OSError:
            pass  # Observability never blocks notification.
    return record


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
        result = check_run(api, run)
        print(result)
        arrival_record(args.run_id, run, result)
        return
    if not args.sweep:
        raise ValueError("RUTA_NOTIFIER_MODE_REQUIRED")
    arrival_record(None, None, "SWEEP")
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
