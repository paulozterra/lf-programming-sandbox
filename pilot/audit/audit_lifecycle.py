"""D22 R1: exclusive historical-audit authorization, not functional admission."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import re

from pilot.audit.historical_evidence import committed_base, ref_path
from pilot.orchestrator import request_lifecycle as life

BOT = "github-actions[bot]"
AUDIT_BRANCH = re.compile(r"audit-(req-[1-9][0-9]*)\Z")
AUDIT_PATH = re.compile(r"pilot/runs/[^/]+/audit(?:/|$)")


def deny(code="AUDIT_SCOPE_UNVERIFIED"):
    raise life.RequestStateError(code)


def is_audit_scope(branch, paths):
    return (isinstance(branch, str) and branch.startswith("audit-")
            or any(isinstance(p, str) and AUDIT_PATH.match(p) for p in paths))


def scope(request, paths):
    prefix = f"pilot/runs/{request}/audit/"
    if (not life.REQUEST.fullmatch(request) or not isinstance(paths, list)
            or not paths or len(set(paths)) != len(paths)):
        deny()
    try:
        if any(not isinstance(p, str) or not p.startswith(prefix)
               or ref_path(p) != p or p.endswith("/") for p in paths):
            deny()
    except ValueError:
        deny()
    if not {prefix + "audit_input_v2.json", prefix + "report.json"}.issubset(paths):
        deny()
    return prefix


def strict_json(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                deny("AUDIT_INPUT_UNVERIFIED")
            obj[k] = v
        return obj
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        deny("AUDIT_INPUT_UNVERIFIED")
    return value


def require_audit_issue(number, repo, api, *, root: Path = life.ROOT,
                        expected_request=None, expected_project=None):
    """Fresh bot reservation + existing T46 closing-commit/authority proof."""
    from pilot.audit.auditor_job import parse_issue
    try:
        if (type(number) is not int or number <= 0 or not isinstance(repo, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)):
            deny()
        issue = api(f"issues/{number}")
        if issue.get("number") != number or issue.get("pull_request"):
            deny()
        request, project, data = parse_issue(issue)
        if (not life.REQUEST.fullmatch(request) or
                issue.get("title") != f"[AUDIT][{project}] {request}" or
                data.get("repository") != repo or
                (expected_request is not None and request != expected_request) or
                (expected_project is not None and project != expected_project)):
            deny()
        life.require_finalized_audit(request, api, root=root)
        committed_base(root, {"audit_context": {"source_revision": data.get("base_commit")}},
                       data, f"pilot/runs/{request}/audit")
        # The proof can take time; recheck the reservation and live state.
        latest = api(f"issues/{number}")
        if (latest.get("number") != number or latest.get("pull_request")
                or latest.get("title") != issue.get("title")
                or parse_issue(latest) != (request, project, data)):
            deny("AUDIT_PROVENANCE_UNVERIFIED")
        life.require_finalized_audit(request, api, root=root)
        return request, project, data
    except life.RequestStateError:
        raise
    except Exception as exc:
        raise life.RequestStateError("AUDIT_PROVENANCE_UNVERIFIED") from exc


def verify_audit_tree(api, head, prefix, files):
    """Bind added paths to regular blobs at HEAD; no symlinks/submodules."""
    result = api(f"git/trees/{head}?recursive=1")
    relative = False
    if result.get("truncated") is True:
        # Large repositories use only the request's audit subtree.
        revision = head
        for segment in prefix.rstrip("/").split("/"):
            tree = api(f"git/trees/{revision}")
            if tree.get("truncated") is not False:
                deny()
            matches = [row for row in tree["tree"] if row.get("path") == segment]
            if (len(matches) != 1 or matches[0].get("type") != "tree"
                    or matches[0].get("mode") != "040000"
                    or not life.SHA40.fullmatch(matches[0].get("sha", ""))):
                deny()
            revision = matches[0]["sha"]
        result = api(f"git/trees/{revision}?recursive=1")
        relative = True
    if result.get("truncated") is not False or not isinstance(result.get("tree"), list):
        deny()
    actual = {}
    for row in result["tree"]:
        name = prefix + row["path"] if relative else row["path"]
        if not name.startswith(prefix):
            continue
        if row.get("type") == "tree" and row.get("mode") == "040000":
            continue
        if (name in actual or row.get("type") != "blob"
                or row.get("mode") not in ("100644", "100755")
                or not life.SHA40.fullmatch(row.get("sha", ""))):
            deny()
        actual[name] = row["sha"]
    if actual != {f["filename"]: f["sha"] for f in files}:
        deny()


def _blob_json(api, sha):
    if not isinstance(sha, str) or not life.SHA40.fullmatch(sha):
        deny()
    obj = api(f"git/blobs/{sha}")
    if (obj.get("sha") != sha or obj.get("encoding") != "base64"
            or not isinstance(obj.get("content"), str)):
        deny()
    raw = base64.b64decode("".join(obj["content"].splitlines()), validate=True)
    if obj.get("size") != len(raw):
        deny()
    return strict_json(raw)


def require_audit_pr(pr, api, *, root: Path = life.ROOT, expected_paths=None):
    """Only a same-repo bot audit PR, bound to one finalized reservation.
    Re-read PR and all changed paths, no rename/deletion or mixed scope.
    T46 is separately required on the exact HEAD before landing.
    """
    try:
        number = pr.get("number")
        if type(number) is not int or number <= 0:
            deny()
        fresh = api(f"pulls/{number}")
        head, base = fresh.get("head", {}), fresh.get("base", {})
        branch, sha = head.get("ref", ""), head.get("sha", "")
        repo = base.get("repo", {}).get("full_name")
        match = AUDIT_BRANCH.fullmatch(branch)
        if (fresh.get("number") != number or fresh.get("state") != "open"
                or fresh.get("merged") is not False or fresh.get("draft") is not False
                or fresh.get("user", {}).get("login") != BOT
                or not match or not life.SHA40.fullmatch(sha)
                or not repo or head.get("repo", {}).get("full_name") != repo
                or base.get("ref") != "main"
                or pr.get("head", {}).get("sha") != sha
                or pr.get("head", {}).get("ref") != branch
                or pr.get("body") != fresh.get("body")):
            deny()
        request = match.group(1)
        body = fresh.get("body") or ""
        marker = re.match(r"^Auditoría automática del pedido `(req-[1-9][0-9]*)` \(issue #([1-9][0-9]*)\)\. ", body)
        if not marker or marker.group(1) != request:
            deny()
        files = []
        for page in range(1, 11):
            batch = api(f"pulls/{number}/files?per_page=100&page={page}")
            if not isinstance(batch, list) or len(batch) > 100:
                deny()
            files.extend(batch)
            if len(batch) < 100:
                break
        else:
            deny()
        if (type(fresh.get("changed_files")) is not int
                or len(files) != fresh["changed_files"]
                or any(f.get("status") != "added" or f.get("previous_filename") for f in files)):
            deny()
        paths = [f["filename"] for f in files]
        prefix = scope(request, paths)
        if expected_paths is not None and (len(expected_paths) != len(paths)
                                            or set(expected_paths) != set(paths)):
            deny()
        _request, project, data = require_audit_issue(
            int(marker.group(2)), repo, api, root=root, expected_request=request)
        if fresh.get("title") != f"[AUDIT][{project}] {request}":
            deny()
        verify_audit_tree(api, sha, prefix, files)
        by_path = {f["filename"]: f["sha"] for f in files}
        if _blob_json(api, by_path[prefix + "audit_input_v2.json"]) != data:
            deny("AUDIT_INPUT_UNVERIFIED")
        report = _blob_json(api, by_path[prefix + "report.json"])
        ctx = report.get("audit_context", {})
        if (ctx.get("source_revision") != data["base_commit"]
                or ctx.get("promotion_authorized") is not False):
            deny("AUDIT_PROVENANCE_UNVERIFIED")
        latest = api(f"pulls/{number}")
        if (latest.get("number") != number or latest.get("state") != "open"
                or latest.get("draft") is not False or latest.get("merged") is not False
                or latest.get("head", {}).get("sha") != sha
                or latest.get("head", {}).get("ref") != branch
                or latest.get("head", {}).get("repo", {}).get("full_name") != repo
                or latest.get("base", {}).get("ref") != "main"
                or latest.get("base", {}).get("repo", {}).get("full_name") != repo
                or latest.get("user", {}).get("login") != BOT
                or latest.get("body") != body or latest.get("title") != fresh.get("title")
                or latest.get("changed_files") != len(paths)):
            deny()
        life.require_finalized_audit(request, api, root=root)
        return request, project, data
    except life.RequestStateError:
        raise
    except Exception as exc:
        raise life.RequestStateError("AUDIT_PROVENANCE_UNVERIFIED") from exc


def latest_audit_run(api, head):
    """Existing T46 workflow evidence, pinned to exact candidate HEAD."""
    if not isinstance(head, str) or not life.SHA40.fullmatch(head):
        deny()
    try:
        rows = life._paged(api, f"actions/workflows/audit-stage.yml/runs?head_sha={head}",
                           "workflow_runs")
        exact = [r for r in rows if r.get("head_sha") == head]
        return max(exact, key=lambda r: r["id"]) if exact else None
    except life.RequestStateError:
        raise
    except Exception as exc:
        raise life.RequestStateError("AUDIT_STAGE_UNVERIFIED") from exc


def require_audit_check(api, head):
    latest = latest_audit_run(api, head) or {}
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        deny("AUDIT_STAGE_NOT_GREEN")
