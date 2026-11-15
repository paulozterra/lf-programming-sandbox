"""T11 governed examiner PR provenance; never read encrypted oracle contents."""
from __future__ import annotations
import re

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\\Z")
SLUG = re.compile(r"req-[1-9][0-9]*\\Z")


class ExamBlocked(ValueError):
    pass


def identity(branch, paths):
    match = re.fullmatch(r"lf/exam/([a-z][a-z0-9_-]{0,31})", branch or "")
    if not match or not isinstance(paths, list):
        raise ExamBlocked("EXAM_PR_INVALID")
    task = match.group(1)
    metas = [re.fullmatch(r"pilot/runs/([a-z][a-z0-9_-]{0,63})/claude_meta/"
                          + re.escape(task) + r"[.]json", p)
             for p in paths]
    slugs = [x.group(1) for x in metas if x]
    allowed = {f"pilot/holdouts/{task}.oracle.json.age"}
    if len(slugs) != 1 or len(paths) != 2:
        raise ExamBlocked("EXAM_PR_PATH_NOT_ALLOWED")
    allowed.add(f"pilot/runs/{slugs[0]}/claude_meta/{task}.json")
    if len(set(paths)) != 2 or set(paths) != allowed:
        raise ExamBlocked("EXAM_PR_PATH_NOT_ALLOWED")
    return task, slugs[0]


def verify_issue(api, branch, paths, author):
    task, slug = identity(branch, paths)
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", str(author)):
        raise ExamBlocked("EXAM_AUTHOR_UNTRUSTED")
    if author != "github-actions[bot]":
        perm = api.request("GET", f"/collaborators/{author}/permission")
        if perm.get("permission") not in ("admin", "maintain", "write"):
            raise ExamBlocked("EXAM_AUTHOR_UNTRUSTED")
    issues = api.pages("/issues?state=open&labels=exam-request", None)
    if not isinstance(issues, list) or len(issues) >= 100:
        raise ExamBlocked("EXAM_REQUEST_UNVERIFIED")
    selected = [x for x in issues if isinstance(x, dict)
                and x.get("state") == "open"
                and x.get("user", {}).get("login") == "github-actions[bot]"
                and x.get("title") == f"EXAM_REQUEST: {task}"
                and any(label.get("name") == "exam-request"
                        for label in x.get("labels", []))
                and f"- Pedido: `{slug}`" in x.get("body", "")
                and f"- Task ID: `{task}`" in x.get("body", "")]
    if len(selected) != 1:
        raise ExamBlocked("EXAM_REQUEST_UNVERIFIED")
    return selected[0]["number"]
