#!/usr/bin/env python3
"""Policy C: bot-only Train admission from trusted main; no PR code execution."""
from __future__ import annotations
# Direct-script entrypoint: resolve the trusted repository root from this file,
# not from the caller's working directory or PYTHONPATH.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[1]))
from pilot.config.project_config import storage_path, storage

import base64
import io
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

# The policy/watchdog are loaded in isolated python -I run_path tests too.
# Resolve this pinned module from the trusted script directory, never cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generated_ci_selection import latest_executed_checks
from native_registration_family import is_native_registration

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
MAX_API_BODY = 5_000_000
CHG_NAME = re.compile(r"standards/changes/(CHG-[0-9]{4})\.json\Z")
RUN_IN_BODY = re.compile(r"\brun:\s*\\?`?(\d{1,18})\\?`?", re.IGNORECASE)
TASK_IN_BODY = re.compile(r"\bTask:\s*\\?`?([a-z][a-z0-9_-]{0,31})\\?`?", re.IGNORECASE)
MAX_PAGES = 10

# Authoritative accepted branch families shared by Policy C, sweep and CI.
BRANCH_RULES = (
    ("registration", "lf/native-registration/", r"lf/native-registration/.+"),
    ("integration", "lf/native-integration/", r"lf/native-integration/.+"),
    ("exam", "lf/exam/", r"lf/exam/[a-z][a-z0-9_-]{0,31}"),
    ("generated-t7", "lf/generated-t7/", r"lf/generated-t7/[0-9a-f]{12}(?:-req-[1-9][0-9]*)?"),
    ("implemented-registry", "lf/implemented-registry/", r"lf/implemented-registry/[0-9a-f]{12}"),
    ("exam-retire", "lf/exam-retire/", r"lf/exam-retire/[a-z][a-z0-9_-]{0,31}-[0-9a-f]{12}"),
    ("request", "lf/request/", r"lf/request/req-[1-9][0-9]*"),
)
BOT_BRANCH_PREFIXES = tuple(item[1] for item in BRANCH_RULES)


def accepted_branch_kind(branch: str) -> str | None:
    if not isinstance(branch, str):
        return None
    for kind, _prefix, pattern in BRANCH_RULES:
        if kind == "registration":
            if is_native_registration(branch):
                return kind
            continue
        if re.fullmatch(pattern, branch):
            return kind
    return None


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


def eligible_pr(pr, paths, repo=REPOSITORY, api=None):
    """Pure gate: same repository, bot, allowed branch and safe complete paths."""
    if (not isinstance(pr, dict) or pr.get("state") != "open"
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != repo
            or pr.get("head", {}).get("repo", {}).get("full_name") != repo):
        block("PR_UNTRUSTED")
    branch = pr["head"].get("ref", "")
    generated = branch.startswith(("lf/generated-t7/", "lf/implemented-registry/"))
    kind = accepted_branch_kind(branch)
    examiner = kind == "exam"
    if pr.get("user", {}).get("login") != BOT and not examiner:
        block("PR_AUTHOR_NOT_BOT" if generated else "PR_UNTRUSTED")
    if kind is None:
        block("PR_BRANCH_NOT_ALLOWED")
    if not SHA.fullmatch(pr["head"].get("sha", "")):
        block("PR_HEAD_INVALID")
    if not isinstance(paths, list) or not paths:
        block("PR_PATH_NOT_ALLOWED" if generated else "PR_PATH_PROHIBITED")
    if kind == "exam":
        from pilot.exam_policy import verify_issue, ExamBlocked
        if api is None:
            block("EXAM_REQUEST_UNVERIFIED")
        try:
            verify_issue(api, branch, paths, pr.get("user", {}).get("login"))
        except (ExamBlocked, KeyError, TypeError, AttributeError):
            block("EXAM_REQUEST_UNVERIFIED")
    elif kind == "generated-t7":
        # Only generated per-request evidence, never request.md or code.
        allow = re.compile(
            r"pilot/runs/[a-z][a-z0-9_-]{0,63}/(?:"
            r"analysis[.]json|state[.]json|lots[.]json|reuse_assessment[.]json|"
            r"atomized_inputs[.]json|chain_plan[.]json|ANALYSIS_REPORT[.]md|"
            r"templates/[a-zA-Z0-9_-]+(?:[.]task|[.]skeleton)[.]json)$")
        if any(is_prohibited(p) or not allow.fullmatch(p) for p in paths):
            block("PR_PATH_NOT_ALLOWED")
    elif kind == "implemented-registry":
        if paths != ["pilot/registry/implemented.json"]:
            block("PR_PATH_NOT_ALLOWED")
    elif kind == "exam-retire":
        task = branch.removeprefix("lf/exam-retire/").rsplit("-", 1)[0]
        metas = [p for p in paths if re.fullmatch(
            r"pilot/runs/req-[1-9][0-9]{0,6}/claude_meta/" + re.escape(task) + r"[.]json", p)]
        request = metas[0].split("/")[2] if len(metas) == 1 else None
        from pilot.orchestrator.stale_exam import exam_paths
        if (request is None or f"pilot/holdouts/{task}.oracle.json.age" not in paths
                or not set(paths) <= set(exam_paths(request, task))):
            block("PR_PATH_NOT_ALLOWED")
    elif kind == "request":
        slug = branch.split("/")[-1]
        if sorted(paths) != sorted([
                f"pilot/runs/{slug}/request.md",
                f"pilot/runs/{slug}/request_meta.json"]):
            block("PR_PATH_NOT_ALLOWED")
    elif any(is_prohibited(p) for p in paths):
        block("PR_PATH_PROHIBITED")
    if len(set(paths)) != len(paths):
        block("PR_PATH_DUPLICATE")
    if pr.get("changed_files") != len(paths):
        block("PR_FILES_INCOMPLETE")
    return kind


def validate_checks(checks, head, required=REQUIRED):
    """Only latest GitHub Actions check of each required name on exact HEAD."""
    if not SHA.fullmatch(head) or not isinstance(checks, list):
        block("CHECKS_INVALID")
    found = latest_executed_checks(checks, required, head)
    if len(found) != len(required):
        block("CHECKS_MISSING")
    if any(row.get("status") != "completed" or row.get("conclusion") != "success"
           for row in found.values()):
        block("CHECKS_NOT_GREEN")
    return {name: found[name]["id"] for name in required}


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
                     "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "LF-auto-integrate-policy-C"})
        try:
            with urllib.request.build_opener(SafeRedirect()).open(req, timeout=30) as response:
                # Same bound as the registry reconstruction reader: a page of
                # 100 closed PRs with their bodies exceeds 1.5 MB, which made
                # policy C unable to regenerate the registry at all.
                content = response.read(MAX_API_BODY + 1)
                if len(content) > MAX_API_BODY:
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
    # A rename touches both paths. GitHub's filename alone is insufficient
    # to prove that a generated PR stayed within its closed allowlist.
    if any(r.get("status") in ("renamed", "copied") or
           (r.get("previous_filename") and r["previous_filename"] != r["filename"])
           for r in rows):
        block("PR_PATH_NOT_ALLOWED")
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


def _content(api, path, revision):
    """Fetch exact GitHub blob bytes, never execute code from a PR checkout."""
    response = api.request("GET", "/contents/" + path + "?ref=" + revision)
    if (not isinstance(response, dict) or response.get("type") != "file"
            or response.get("encoding") != "base64"
            or type(response.get("size")) is not int
            or not 0 < response["size"] <= 1_000_000):
        block("GENERATED_CONTENT_DRIFT")
    try:
        raw = base64.b64decode("".join(response["content"].split()), validate=True)
    except (ValueError, UnicodeError, KeyError):
        block("GENERATED_CONTENT_DRIFT")
    if len(raw) != response["size"]:
        block("GENERATED_CONTENT_DRIFT")
    return raw


def verify_exam_retire(api, number, pr, paths):
    """E2: only deletions, and the exam must be stale on trusted main: published
    before one of its lot's dependencies was integrated (same rule as CP3.6)."""
    rows = api.pages(f"/pulls/{number}/files", None)
    if any(not isinstance(r, dict) or r.get("status") != "removed" for r in rows):
        block("EXAM_RETIRE_NOT_DELETION_ONLY")
    task = pr["head"]["ref"].removeprefix("lf/exam-retire/").rsplit("-", 1)[0]
    request = next(p.split("/")[2] for p in paths if "/claude_meta/" in p)
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from pilot.orchestrator.stale_exam import is_stale
    try:
        plan = json.loads((root / f"pilot/runs/{request}/chain_plan.json").read_text("utf-8"))
        lots = json.loads((root / f"pilot/runs/{request}/lots.json").read_text("utf-8"))["lots"]
        by_lot = {b["lot_id"]: b["task_name"] for b in plan["bindings"]}
        lot_id = next(b["lot_id"] for b in plan["bindings"] if b["task_name"] == task)
        lot = next(x for x in lots if x["id"] == lot_id)
        deps = [by_lot[d] for d in lot.get("depends_on", []) if d in by_lot]
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        block("EXAM_RETIRE_LOT_UNRESOLVED")
    if is_stale(root, task, deps):
        return
    # Or: the task's latest registration failed its T40 rehearsal, within the cap.
    from pilot.orchestrator.stale_exam import (rehearsal_failure, retire_count,
                                               MAX_REHEARSAL_RETIRES)
    pulls = lambda: api.request("GET", "/pulls?state=all&sort=created&direction=desc&per_page=100")
    checks = lambda sha: api.pages(f"/commits/{sha}/check-runs", "check_runs")
    if (rehearsal_failure(pulls, checks, task) is None
            or retire_count(root, task, deps) >= MAX_REHEARSAL_RETIRES):
        block("EXAM_RETIRE_NOT_STALE")


def verify_generated_content(api, pr, paths, kind):
    """Regenerate with TRUSTED main tooling before policy C labels a bot PR."""
    head = pr["head"]["sha"]
    root = Path(__file__).resolve().parents[1]
    main = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()
    # The registry is content-addressed (it changes only when a lot is
    # integrated): its draft is valid while its bytes equal the regeneration
    # on the current trusted main, even if main advanced after the draft.
    # T7 analyses stay bound to the exact main they were generated on.
    if (not SHA.fullmatch(main) or not head or
            (kind != "implemented-registry" and
             not re.fullmatch(re.escape(main[:12]) + r"(?:-req-[1-9][0-9]*)?",
                              pr["head"]["ref"].rsplit("/", 1)[-1]))):
        block("GENERATED_CONTENT_DRIFT")
    # Invoked as a script (python3 pilot/...), so sys.path[0] is pilot/, not
    # the repository root that owns the `pilot` and `analysis` packages.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        if kind == "implemented-registry":
            from pilot.orchestrator.implemented_registry import (
                CLOSED_PULLS, batched_pr_reader, reconstruct)
            ledger = reconstruct(root, main, batched_pr_reader(
                lambda: api.pages("/" + CLOSED_PULLS, None),
                lambda n: api.request("GET", f"/pulls/{n}")))
            raw = _content(api, "pilot/registry/implemented.json", head)
            try:
                proposed = json.loads(raw)
            except ValueError:
                block("GENERATED_CONTENT_DRIFT")
            generated_at = proposed.get("source_main_sha") if isinstance(proposed, dict) else None
            # Same entries as the regeneration on current main, generated on an
            # ancestor of it, and byte-for-byte the canonical serialization.
            ancestor = (isinstance(generated_at, str) and SHA.fullmatch(generated_at)
                        and subprocess.run(["git", "merge-base", "--is-ancestor", generated_at, main],
                                           cwd=root, capture_output=True).returncode == 0)
            canonical = (json.dumps(proposed, sort_keys=True, ensure_ascii=False, indent=2)
                         + "\n").encode("utf-8") if isinstance(proposed, dict) else None
            if (not ancestor or raw != canonical
                    or set(proposed) != set(ledger)
                    or proposed.get("schema_version") != ledger.get("schema_version")
                    or proposed.get("entries") != ledger.get("entries")):
                block("GENERATED_CONTENT_DRIFT")
            return
        if kind != "generated-t7":
            block("GENERATED_CONTENT_DRIFT")
        slugs = sorted({p.split("/")[2] for p in paths})
        from analysis.host.request_catalog import resolve
        from analysis.host.run_a1_a9_fixture import run_f4
        from pilot.orchestrator.analysis_report import render, read_rules
        for slug in slugs:
            path = f"pilot/runs/{slug}/analysis.json"
            if path not in paths:
                block("GENERATED_CONTENT_DRIFT")
            # Read request only from current trusted main; never a PR payload.
            original = subprocess.run(["git", "show", f"{main}:pilot/runs/{slug}/request.md"],
                                      cwd=root, capture_output=True, check=False)
            if original.returncode:
                block("GENERATED_CONTENT_DRIFT")
            _, fixture = resolve(root, original.stdout)
            with tempfile.TemporaryDirectory(prefix="t7-content-check-") as temp:
                staging = Path(temp) / storage()["requests_root"] / slug
                staging.mkdir(parents=True)
                (staging / "request.md").write_bytes(original.stdout)
                run_f4(Path(temp), slug=slug, fixtures=fixture)
                expected = (staging / "analysis.json").read_bytes()
            if _content(api, path, head) != expected:
                block("GENERATED_CONTENT_DRIFT")
            report_path = f"pilot/runs/{slug}/ANALYSIS_REPORT.md"
            reuse_path = f"pilot/runs/{slug}/reuse_assessment.json"
            lot_path = f"pilot/runs/{slug}/lots.json"
            if report_path not in paths or reuse_path not in paths:
                block("GENERATED_CONTENT_DRIFT")
            # A9's JSON was independently regenerated above. The report must
            # be the exact pure projection of JSON blobs in this candidate and
            # metadata committed in trusted main, never textual interpretation
            # from the candidate's Markdown or a model.
            package = json.loads(expected)
            reuse = json.loads(_content(api, reuse_path, head))
            lots = json.loads(_content(api, lot_path, head)) if lot_path in paths else None
            meta_raw = subprocess.run(
                ["git", "show", f"{main}:pilot/runs/{slug}/request_meta.json"],
                cwd=root, capture_output=True, check=False)
            if meta_raw.returncode:
                block("GENERATED_CONTENT_DRIFT")
            meta = json.loads(meta_raw.stdout)
            regenerated = render(package, reuse, lots, meta, original.stdout,
                                 read_rules(fixture, original.stdout))
            if _content(api, report_path, head) != regenerated:
                block("GENERATED_CONTENT_DRIFT")
    except PolicyBlocked:
        raise
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        block("GENERATED_CONTENT_DRIFT")


def verify_issue_request(api, pr, paths):
    """Independent main-side API read; exact SHA bytes are not trusted from CI."""
    from orchestrator.issue_intake import expected_files, allowed_permission
    slug = pr["head"]["ref"].split("/")[-1]
    number = int(slug[4:])
    issue = api.request("GET", f"/issues/{number}")
    author = issue.get("user", {}).get("login", "")
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", author):
        block("PEDIDO_AUTOR_NO_AUTORIZADO")
    permission = api.request("GET", f"/collaborators/{author}/permission")
    if not allowed_permission(permission.get("permission", "")):
        block("PEDIDO_AUTOR_NO_AUTORIZADO")
    try:
        expected = expected_files(issue)
    except ValueError:
        block("PEDIDO_ISSUE_INVALIDO")
    if sorted(paths) != sorted(expected):
        block("PR_PATH_NOT_ALLOWED")
    for path, raw in expected.items():
        if _content(api, path, pr["head"]["sha"]) != raw:
            block("PEDIDO_CONTENIDO_MODIFICADO")


def comment_once(api, pr_number):
    comments = api.pages(f"/issues/{pr_number}/comments", None)
    if any(isinstance(row, dict) and row.get("body") == HUMAN_COMMENT
           and row.get("user", {}).get("login") == BOT for row in comments):
        return
    api.request("POST", f"/issues/{pr_number}/comments", {"body": HUMAN_COMMENT})


def stale_generated_origin(branch: str, main: str) -> bool:
    match = re.fullmatch(r"lf/generated-t7/([0-9a-f]{12})(?:-req-[1-9][0-9]*)?",
                         branch)
    if not match or not SHA.fullmatch(main):
        block("GENERATED_CONTENT_DRIFT")
    return match.group(1) != main[:12]


def original_request_merge(slug: str, root: Path) -> str:
    # The immutable request.md was introduced by an earlier Train merge.
    # Re-check that introduction and its first-parent history before dispatch.
    if not re.fullmatch(r"req-[1-9][0-9]*", slug):
        block("GENERATED_REQUEST_SCOPE_INVALID")
    history = subprocess.run(
        ["git", "log", "--first-parent", "--format=%H", "--",
         f"pilot/runs/{slug}/request.md"], cwd=root,
        capture_output=True, text=True, check=True).stdout.splitlines()
    if len(history) != 1 or not SHA.fullmatch(history[0]):
        block("GENERATED_REQUEST_MERGE_UNVERIFIED")
    sha = history[0]
    summary = subprocess.run(["git", "show", "-s", "--format=%s", sha],
                             cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    if not re.fullmatch(r"Merge PR #[1-9][0-9]* via sandbox-train", summary):
        block("GENERATED_REQUEST_MERGE_UNVERIFIED")
    return sha


def recover_stale_generated(api, pr, paths):
    # Old generated content may be correct for its own base. The current main
    # changes its meaning; never label or merge that old content unchanged.
    root = Path(__file__).resolve().parents[1]
    main = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()
    branch = pr["head"]["ref"]
    if not stale_generated_origin(branch, main):
        return None
    ref = api.request("GET", "/git/ref/heads/main").get("object", {}).get("sha")
    if ref != main:
        block("MAIN_DRIFT")
    slugs = sorted({p.split("/")[2] for p in paths})
    if len(slugs) != 1 or not re.fullmatch(r"req-[1-9][0-9]*", slugs[0]):
        block("GENERATED_REQUEST_SCOPE_INVALID")
    slug = slugs[0]
    if branch.endswith("-req-" + slug[4:]) is False and re.search(r"-req-[1-9][0-9]*$", branch):
        block("GENERATED_REQUEST_SCOPE_INVALID")
    source = original_request_merge(slug, root)
    number = pr["number"]
    # The open PR is closed before a fresh rerun. The action is audit-visible,
    # and the workflow dispatch uses only trusted main and original source.
    api.request("PATCH", f"/pulls/{number}", {"state": "closed"})
    api.request("POST", f"/issues/{number}/comments",
                {"body": f"T12: Análisis obsoleto tras avance de main a `{main}`. "
                         f"Se cierra este candidato y se vuelve a ejecutar T7 "
                         f"para `{slug}` desde el pedido original `{source}`."})
    api.request("POST", "/actions/workflows/t7-request.yml/dispatches",
                {"ref": "main", "inputs": {"slug": slug, "merge_sha": source,
                                            "rerun": "true"}})
    return "STALE_CLOSED_T7_REDISPATCHED"


def owner_labeled_after_last_train(api, number):
    """True if the latest ready-to-merge label on this PR was applied by a
    repository admin (a human owner, never the bot) and no Train run was
    dispatched for the PR since then. The Train itself re-checks policy."""
    events = api.pages(f"/issues/{number}/events", None)
    labels = [e for e in events if isinstance(e, dict) and e.get("event") == "labeled"
              and (e.get("label") or {}).get("name") == READY_LABEL]
    if not labels:
        return False
    last = labels[-1]
    actor = (last.get("actor") or {}).get("login", "")
    if actor == BOT or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", actor):
        return False
    permission = api.request("GET", f"/collaborators/{actor}/permission")
    if permission.get("permission") != "admin":
        return False
    since = last.get("created_at", "")
    runs = api.request("GET", "/actions/workflows/sandbox-train.yml/runs?event=workflow_dispatch&per_page=100")
    for run in runs.get("workflow_runs", []):
        if (run.get("created_at", "") >= since
                and run.get("display_title") == f"sandbox-train PR #{number}"):
            return False
    return True



TRAIN_REDISPATCH_LIMIT = 3  # Train dispatches per label before human review


def _last_ready_label(api, number):
    events = api.pages(f"/issues/{number}/events", None)
    labels = [e for e in events if isinstance(e, dict) and e.get("event") == "labeled"
              and (e.get("label") or {}).get("name") == READY_LABEL]
    return labels[-1] if labels else None


def _train_runs_since(api, number, since):
    runs = api.request("GET", "/actions/workflows/sandbox-train.yml/runs?event=workflow_dispatch&per_page=100")
    rows = [run for run in runs.get("workflow_runs", [])
            if isinstance(run, dict) and run.get("created_at", "") >= since
            and run.get("display_title") == f"sandbox-train PR #{number}"
            and type(run.get("id")) is int]
    return sorted(rows, key=lambda run: run["id"])


def labeled_train_recovery(api, number):
    """R4 (CHG-0250): a ready-to-merge label applied by policy C must reach a
    Train run. The Train concurrency group keeps one pending run, so a later
    dispatch can REPLACE (cancel) the pending one; a failed dispatch POST also
    leaves the label behind. Without this, policy C answers ALREADY_LABELED
    forever. Decision only from the Train history since the latest label:
    none -> dispatch; queued/in progress -> wait; cancelled -> re-dispatch
    (bounded); failure/other -> typed block for human review. The Train
    re-verifies PR HEAD, checks and mergeability before merging."""
    last = _last_ready_label(api, number)
    if last is None:
        return "ALREADY_LABELED"
    actor = (last.get("actor") or {}).get("login", "")
    if actor != BOT:
        return "ALREADY_LABELED"  # human labels keep the T42 owner path
    runs = _train_runs_since(api, number, last.get("created_at", ""))
    if runs:
        latest = runs[-1]
        if latest.get("status") != "completed":
            return "ALREADY_LABELED"
        conclusion = latest.get("conclusion")
        if conclusion == "success":
            block("TRAIN_SUCCEEDED_PR_STILL_OPEN")
        if conclusion != "cancelled":
            block("TRAIN_FAILED_REQUIRES_REVIEW")
        if len(runs) >= TRAIN_REDISPATCH_LIMIT:
            block("TRAIN_REDISPATCH_LIMIT")
    api.request("POST", "/actions/workflows/sandbox-train.yml/dispatches",
                {"ref": "main", "inputs": {"pr_number": str(number)}})
    return "TRAIN_REDISPATCHED_CANCELLED" if runs else "TRAIN_REDISPATCHED_MISSING"


def evaluate_one(api, number):
    pr = api.request("GET", f"/pulls/{number}")
    paths = pr_files(api, number)
    kind = eligible_pr(pr, paths, api=api)
    head = pr["head"]["sha"]
    if kind == "request":
        verify_issue_request(api, pr, paths)
    if kind == "generated-t7":
        recovery = recover_stale_generated(api, pr, paths)
        if recovery:
            return recovery
    if READY_LABEL in {x.get("name") for x in pr.get("labels", [])}:
        # T42: an owner's label on a bot PR (e.g. the attempt-3 human gate)
        # triggers no pull_request workflow, so dispatch the Train once.
        if kind == "integration" and owner_labeled_after_last_train(api, number):
            api.request("POST", "/actions/workflows/sandbox-train.yml/dispatches",
                        {"ref": "main", "inputs": {"pr_number": str(number)}})
            return "OWNER_LABEL_TRAIN_DISPATCHED"
        return labeled_train_recovery(api, number)
    if kind in ("generated-t7", "implemented-registry"):
        verify_generated_content(api, pr, paths, kind)
    if kind == "exam-retire":
        verify_exam_retire(api, number, pr, paths)
    if kind == "integration":
        try:
            integration_proof(api, pr, paths)
        except PolicyBlocked as exc:
            if str(exc) == "ATTEMPT_3_REQUIRES_HUMAN":
                comment_once(api, number)
            raise
    checks = api.pages(f"/commits/{head}/check-runs", "check_runs")
    if kind == "implemented-registry":
        # The trusted content check above just passed on current main. If the
        # PR's own byte-equality CI check failed earlier (e.g. it ran before a
        # fix reached main), re-run it instead of waiting for a human.
        rerun = registry_check_rerun(checks, head)
        if rerun is not None:
            api.request("POST", f"/actions/jobs/{rerun}/rerun")
            return "REGISTRY_CHECK_RERUN_REQUESTED"
    required = (REQUIRED + ("T7 generated content byte equality",)
                if kind in ("generated-t7", "implemented-registry") else
                REQUIRED + ("T9 request content byte equality",) if kind == "request"
                else REQUIRED)
    validate_checks(checks, head, required)
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


MAX_REGISTRY_CHECK_FAILURES = 3


def registry_check_rerun(checks, head):
    """Job id to re-run when the latest byte-equality check failed, at most
    MAX_REGISTRY_CHECK_FAILURES failures per head; None otherwise."""
    rows = [c for c in checks if isinstance(c, dict)
            and c.get("name") == "T7 generated content byte equality"
            and c.get("head_sha") == head and c.get("status") == "completed"
            and c.get("conclusion") in ("success", "failure")]
    if not rows:
        return None
    latest = max(rows, key=lambda c: (str(c.get("started_at") or ""), int(c.get("id") or 0)))
    failures = sum(1 for c in rows if c.get("conclusion") == "failure")
    if latest.get("conclusion") != "failure" or failures >= MAX_REGISTRY_CHECK_FAILURES:
        return None
    return int(latest["id"]) if type(latest.get("id")) is int else None


def run(api, trigger, *, numbers=None, scheduled=False):
    # A scheduled sweep has no triggering run to verify; every candidate is
    # still re-checked by evaluate_one (bot author, branch, paths, exact-HEAD CI).
    if not scheduled:
        verify_trigger(trigger)
    candidates = numbers
    if candidates is None:
        pulls = api.pages("/pulls?state=open", None)
        candidates = [row["number"] for row in pulls
                      if isinstance(row, dict) and type(row.get("number")) is int
                      and row.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY
                      and (row.get("user", {}).get("login") == BOT
                           or row.get("head", {}).get("ref", "").startswith("lf/exam/"))
                      and accepted_branch_kind(
                          row.get("head", {}).get("ref", "")) is not None]
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
    scheduled = os.environ.get("GITHUB_EVENT_NAME") in ("schedule", "workflow_dispatch")
    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)
    trigger = None if scheduled else event.get("workflow_run")
    if not scheduled:
        verify_trigger(trigger)
    api = GitHub(os.environ.get("GH_TOKEN", ""))
    results = run(api, trigger, scheduled=scheduled)
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
