#!/usr/bin/env python3
"""Policy C: bot-only Train admission from trusted main; no PR code execution."""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "paulozterra/lf-programming-sandbox"
BOT = "github-actions[bot]"
READY_LABEL = "ready-to-merge"
HUMAN_COMMENT = "REVISION_HUMANA_REQUERIDA"
REQUIRED = (
    "backend (Maven verify)",
    "frontend (lint, tipos, build)",
    "estándares (catálogo y checks)",
    "infra local (docker compose)",
    "Worker pilot (offline budget, policy, vendor integrity)",
    "native push policy (offline only)",
)
NATIVE_WORKFLOW = ".github/workflows/worker-native.yml"
TRIGGERS = {
    ".github/workflows/ci.yml": "ci",
    ".github/workflows/native-verified-integration.yml": "CP3.5 native verified patch to draft PR",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
CHG_NAME = re.compile(r"standards/changes/(CHG-[0-9]{4})\.json\Z")
RUN_IN_BODY = re.compile(r"\brun:\s*\\?`?(\d{1,18})\\?`?", re.IGNORECASE)
TASK_IN_BODY = re.compile(r"\bTask:\s*\\?`?([a-z][a-z0-9_-]{0,31})\\?`?", re.IGNORECASE)
MAX_PAGES = 10


class PolicyBlocked(ValueError):
    pass


def block(code):
    raise PolicyBlocked(code)


def is_prohibited(path):
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        return True
    if any(part in (".", "..", "") for part in path.split("/")):
        return True
    return path.startswith((
        ".github/", "pilot/holdouts/", "standards/tools/", "vendor/",
        "pilot/orchestrator/", "pilot/sandbox_train", "pilot/auto_integrate",
    ))


def eligible_pr(pr, paths, repo=REPOSITORY):
    """Pure gate: same repository, bot, allowed branch and safe complete paths."""
    if (not isinstance(pr, dict) or pr.get("state") != "open"
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != repo
            or pr.get("head", {}).get("repo", {}).get("full_name") != repo
            or pr.get("user", {}).get("login") != BOT):
        block("PR_UNTRUSTED")
    branch = pr["head"].get("ref", "")
    if branch.startswith("lf/native-registration/") and len(branch) > len("lf/native-registration/"):
        kind = "registration"
    elif branch.startswith("lf/native-integration/") and len(branch) > len("lf/native-integration/"):
        kind = "integration"
    else:
        block("PR_BRANCH_NOT_ALLOWED")
    if not SHA.fullmatch(pr["head"].get("sha", "")):
        block("PR_HEAD_INVALID")
    if not isinstance(paths, list) or not paths or any(is_prohibited(p) for p in paths):
        block("PR_PATH_PROHIBITED")
    if len(set(paths)) != len(paths):
        block("PR_PATH_DUPLICATE")
    if pr.get("changed_files") != len(paths):
        block("PR_FILES_INCOMPLETE")
    return kind


def validate_checks(checks, head):
    """Only latest GitHub Actions check of each required name on exact HEAD."""
    if not SHA.fullmatch(head) or not isinstance(checks, list):
        block("CHECKS_INVALID")
    found = {}
    for row in checks:
        if not isinstance(row, dict) or row.get("name") not in REQUIRED:
            continue
        if (row.get("head_sha") != head
                or row.get("app", {}).get("slug") != "github-actions"
                or not isinstance(row.get("id"), int)):
            continue
        name = row["name"]
        if name not in found or row["id"] > found[name]["id"]:
            found[name] = row
    if len(found) != len(REQUIRED):
        block("CHECKS_MISSING")
    if any(row.get("status") != "completed" or row.get("conclusion") != "success"
           for row in found.values()):
        block("CHECKS_NOT_GREEN")
    return {name: found[name]["id"] for name in REQUIRED}


def native_run_reference(pr_body, chg):
    """CHG and body must independently attest the same successful native run."""
    if not isinstance(pr_body, str) or not isinstance(chg, dict):
        block("INTEGRATION_REFERENCE_MISSING")
    run_ids = RUN_IN_BODY.findall(pr_body)
    tasks = TASK_IN_BODY.findall(pr_body)
    if len(run_ids) != 1 or len(tasks) != 1:
        block("INTEGRATION_BODY_INVALID")
    run_id = int(run_ids[0])
    title = chg.get("title", "")
    reason = chg.get("reason", "")
    if (run_id < 1 or not isinstance(title, str) or not isinstance(reason, str)
            or re.search(r"\brun\s+" + re.escape(str(run_id)) + r"\b", title) is None
            or re.search(r"\bPASS\s+" + re.escape(str(run_id)) + r"\b", reason) is None
            or tasks[0] not in title
            or chg.get("schema_version") != "LF_STANDARD_CHANGE_V1"):
        block("INTEGRATION_CHG_RUN_MISMATCH")
    return run_id, tasks[0]


def validate_native_proof(run, proof, status, run_id, task):
    """Attempt 3 is a human-only exception, never an auto-ready result."""
    if (not isinstance(run, dict) or run.get("id") != run_id
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("repository", {}).get("full_name") != REPOSITORY
            or run.get("head_branch") != "main"
            or run.get("path", "").split("@")[0] != NATIVE_WORKFLOW
            or run.get("event") not in ("workflow_run", "workflow_dispatch")
            or run.get("run_attempt") != 1):
        block("NATIVE_RUN_NOT_TRUSTED")
    if not isinstance(proof, dict) or not isinstance(status, dict):
        block("NATIVE_PROOF_MISSING")
    attempt = proof.get("attempt")
    if (proof.get("run_id") != run_id or proof.get("task_id") != task
            or status.get("task_id") != task or status.get("attempt") != attempt
            or status.get("task_pack_sha256") != proof.get("task_pack_sha256")
            or status.get("status") != "PASS"
            or status.get("schema_version") != "LF_NATIVE_RESULT_SUMMARY_V1"
            or status.get("production_authority") is not False
            or status.get("receipt_authenticated") is not False
            or status.get("authority") != "REAL_SANDBOX_UNAUTHENTICATED"):
        block("NATIVE_PROOF_MISMATCH")
    if attempt == 3:
        block("ATTEMPT_3_REQUIRES_HUMAN")
    if type(attempt) is not int or attempt not in (1, 2):
        block("NATIVE_ATTEMPT_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", str(proof.get("task_pack_sha256", ""))):
        block("NATIVE_PACK_SHA_INVALID")
    return attempt


def verify_trigger(trigger, repo=REPOSITORY):
    if (not isinstance(trigger, dict)
            or trigger.get("status") != "completed"
            or trigger.get("conclusion") != "success"
            or trigger.get("repository", {}).get("full_name") != repo
            or trigger.get("head_repository", {}).get("full_name") != repo
            or trigger.get("run_attempt") != 1
            or trigger.get("event") not in ("pull_request", "workflow_run", "workflow_dispatch")):
        block("TRIGGER_NOT_TRUSTED")
    path = trigger.get("path", "").split("@")[0]
    if path not in TRIGGERS or trigger.get("name") != TRIGGERS[path]:
        block("TRIGGER_WORKFLOW_NOT_ALLOWED")
    if path.endswith("native-verified-integration.yml"):
        if trigger.get("head_branch") != "main" or trigger.get("event") != "workflow_run":
            block("TRIGGER_INTEGRATION_INVALID")
    elif trigger.get("event") not in ("pull_request", "workflow_dispatch"):
        block("TRIGGER_CI_EVENT_INVALID")
    return path

 
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward a GitHub token to artifact-storage redirect hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            block("UNSAFE_API_REDIRECT")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and (urllib.parse.urlsplit(req.full_url).hostname
                                       != urllib.parse.urlsplit(newurl).hostname):
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, token, repository=REPOSITORY):
        if not token or repository != REPOSITORY:
            block("REPOSITORY_OR_TOKEN_INVALID")
        self.token = token
        self.repository = repository

    def request(self, method, path, data=None, *, raw=False):
        if not path.startswith("/") or "//" in path or ".." in path:
            block("API_PATH_INVALID")
        body = None if data is None else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            "https://api.github.com/repos/" + self.repository + path,
            data=body, method=method,
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": "Bearer " + self.token,
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "LF-auto-integrate-policy-C"})
        try:
            with urllib.request.build_opener(SafeRedirect()).open(req, timeout=30) as response:
                content = response.read(1_500_001)
                if len(content) > 1_500_000:
                    block("API_BODY_OVERSIZE")
                return content if raw else (json.loads(content) if content else {})
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError):
            block("API_REQUEST_FAILED:" + method + ":" + path)

    def pages(self, path, field):
        values = []
        for page in range(1, MAX_PAGES + 1):
            delim = "&" if "?" in path else "?"
            answer = self.request("GET", path + delim + "per_page=100&page=" + str(page))
            items = answer.get(field) if field else answer
            if not isinstance(items, list):
                block("API_PAGE_INVALID")
            values.extend(items)
            if len(items) < 100:
                return values
        block("API_PAGINATION_LIMIT")


def artifact_json(api, run_id, artifact_name, filename):
    items = api.pages(f"/actions/runs/{run_id}/artifacts", "artifacts")
    found = [a for a in items if a.get("name") == artifact_name and a.get("expired") is False]
    if len(found) != 1 or not isinstance(found[0].get("id"), int):
        block("NATIVE_ARTIFACT_UNAVAILABLE")
    zip_data = api.request("GET", f"/actions/artifacts/{found[0]['id']}/zip", raw=True)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            members = z.infolist()
            expected = ({"attempt-proof.json"} if artifact_name == "native-attempt-proof"
                        else {"cost.json", "feedback.json", "status.json"})
            if len(members) != len(expected) or {m.filename for m in members} != expected:
                block("NATIVE_ARTIFACT_INVENTORY_INVALID")
            for m in members:
                kind = (m.external_attr >> 16) & 0o170000
                if m.is_dir() or kind not in (0, 0o100000) or not 0 < m.file_size <= 32_000:
                    block("NATIVE_ARTIFACT_FILE_INVALID")
            raw = z.read(filename)
            item = json.loads(raw)
            if not isinstance(item, dict):
                block("NATIVE_ARTIFACT_JSON_INVALID")
            return item
    except (zipfile.BadZipFile, OSError, UnicodeError, ValueError, RuntimeError, KeyError):
        block("NATIVE_ARTIFACT_INVALID")


def pr_files(api, number):
    rows = api.pages(f"/pulls/{number}/files", None)
    if any(not isinstance(r, dict) or not isinstance(r.get("filename"), str) for r in rows):
        block("PR_FILES_INVALID")
    return [r["filename"] for r in rows]


def integration_proof(api, pr, paths):
    ids = [m.group(1) for path in paths if (m := CHG_NAME.fullmatch(path))]
    if len(ids) != 1:
        block("INTEGRATION_CHG_MISSING")
    sha = pr["head"]["sha"]
    path = "standards/changes/" + ids[0] + ".json"
    content = api.request("GET", f"/contents/{path}?ref={sha}")
    if (content.get("type") != "file" or content.get("encoding") != "base64"
            or content.get("size", 0) > 32_000):
        block("INTEGRATION_CHG_INVALID")
    try:
        change = json.loads(base64.b64decode("".join(content["content"].split()), validate=True))
    except (ValueError, UnicodeError, KeyError):
        block("INTEGRATION_CHG_INVALID")
    if not isinstance(change, dict) or change.get("change_id") != ids[0]:
        block("INTEGRATION_CHG_INVALID")
    run_id, task = native_run_reference(pr.get("body"), change)
    run = api.request("GET", f"/actions/runs/{run_id}")
    proof = artifact_json(api, run_id, "native-attempt-proof", "attempt-proof.json")
    status = artifact_json(api, run_id, "native-visible-feedback-and-cost", "status.json")
    return validate_native_proof(run, proof, status, run_id, task)


def comment_once(api, pr_number):
    comments = api.pages(f"/issues/{pr_number}/comments", None)
    if any(isinstance(row, dict) and row.get("body") == HUMAN_COMMENT
           and row.get("user", {}).get("login") == BOT for row in comments):
        return
    api.request("POST", f"/issues/{pr_number}/comments", {"body": HUMAN_COMMENT})


def evaluate_one(api, number):
    pr = api.request("GET", f"/pulls/{number}")
    paths = pr_files(api, number)
    kind = eligible_pr(pr, paths)
    head = pr["head"]["sha"]
    if READY_LABEL in {x.get("name") for x in pr.get("labels", [])}:
        return "ALREADY_LABELED"
    if kind == "integration":
        try:
            integration_proof(api, pr, paths)
        except PolicyBlocked as exc:
            if str(exc) == "ATTEMPT_3_REQUIRES_HUMAN":
                comment_once(api, number)
            raise
    checks = api.pages(f"/commits/{head}/check-runs", "check_runs")
    validate_checks(checks, head)
    latest = api.request("GET", f"/pulls/{number}")
    if (latest.get("head", {}).get("sha") != head
            or latest.get("state") != "open"
            or latest.get("draft") != pr.get("draft")
            or latest.get("body") != pr.get("body")
            or latest.get("head", {}).get("ref") != pr["head"].get("ref")
            or latest.get("base", {}).get("ref") != "main"):
        block("PR_CHANGED_BEFORE_LABEL")
    api.request("POST", f"/issues/{number}/labels", {"labels": [READY_LABEL]})
    # GITHUB_TOKEN labels do NOT trigger the pull_request:labeled workflow.
    api.request("POST", "/actions/workflows/sandbox-train.yml/dispatches",
                {"ref": "main", "inputs": {"pr_number": str(number)}})
    return "LABEL_AND_TRAIN_DISPATCHED"


def run(api, trigger, *, numbers=None):
    verify_trigger(trigger)
    candidates = numbers
    if candidates is None:
        pulls = api.pages("/pulls?state=open", None)
        candidates = [row["number"] for row in pulls
                      if isinstance(row, dict) and type(row.get("number")) is int
                      and row.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY
                      and row.get("user", {}).get("login") == BOT
                      and row.get("head", {}).get("ref", "").startswith(
                          ("lf/native-registration/", "lf/native-integration/"))]
    output = []
    for number in candidates:
        try:
            result = evaluate_one(api, number)
        except PolicyBlocked as exc:
            result = "BLOCKED:" + str(exc)
        output.append({"pr": number, "decision": result})
    return output


def main():
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        block("REPOSITORY_INVALID")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        block("EVENT_PATH_MISSING")
    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)
    trigger = event.get("workflow_run")
    verify_trigger(trigger)
    api = GitHub(os.environ.get("GH_TOKEN", ""))
    results = run(api, trigger)
    print(json.dumps({"event": "AUTO_INTEGRATE_POLICY_C", "results": results},
                     sort_keys=True, ensure_ascii=False), flush=True)
    for row in results:
        if row["decision"].startswith("BLOCKED:API_"):
            block("SIDE_EFFECT_API_FAILED")


if __name__ == "__main__":
    try:
        main()
    except (PolicyBlocked, OSError, ValueError, KeyError, TypeError) as exc:
        print("AUTO_INTEGRATE_BLOCKED:" + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
