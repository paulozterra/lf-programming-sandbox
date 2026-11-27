#!/usr/bin/env python3
"""T58: work queue of the automatic independent examiner.

Lists the open ``exam-request`` issues (opened by the route bot) whose task
still has no published hidden exam on ``main`` and no exam PR in flight. Reads
only public data: issue bodies, PR head refs and whether the ciphertext path
exists. It never opens encrypted material.

Output (stdout, JSON): {"schema_version": "LF_EXAMINER_QUEUE_V1",
"pending": [{"issue", "task", "request", "lot", "write_paths", "requirement_ids"}],
"blocked": [...], "in_flight": [...], "stale": [...]}\n``stale``: the task is no longer planned (no matching template on main) or its\nrequest issue is closed; the examiner never writes exams for those.
"""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = _project_Path(__file__).resolve().parents[2]
REPO = "paulozterra/lf-programming-sandbox"
BOT = "github-actions[bot]"
LABEL = "exam-request"
BLOCKED_LABEL = "examiner-blocked"
WORKING_LABEL = "examiner-working"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}")
SLUG = re.compile(r"req-[1-9][0-9]*")
MARKER = re.compile(r"<!-- LF_EXAM_REQUEST_TASK:([a-z][a-z0-9_-]{0,31}) -->")


class QueueBlocked(ValueError):
    pass


def _field(body: str, name: str) -> str | None:
    match = re.search(r"^- " + re.escape(name) + r": `([^`]*)`\s*$", body, re.M)
    return match.group(1) if match else None


def parse_request(issue: dict) -> dict | None:
    """Public fields of one exam-request issue, or None if it is not one."""
    if not isinstance(issue, dict) or issue.get("state") != "open" or "pull_request" in issue:
        return None
    if issue.get("user", {}).get("login") != BOT:
        return None
    labels = {row.get("name") for row in issue.get("labels", []) if isinstance(row, dict)}
    if LABEL not in labels:
        return None
    body = issue.get("body") or ""
    marker = MARKER.search(body)
    task = _field(body, "Task ID")
    slug = _field(body, "Pedido")
    if (not marker or task != marker.group(1) or not TASK.fullmatch(task or "")
            or not SLUG.fullmatch(slug or "")
            or issue.get("title") != f"EXAM_REQUEST: {task}"):
        return None
    try:
        write_paths = json.loads(_field(body, "Rutas de escritura") or "null")
        requirements = json.loads(_field(body, "REQ") or "null")
    except ValueError:
        return None
    if (not isinstance(write_paths, list) or not write_paths
            or not all(isinstance(p, str) for p in write_paths)
            or not isinstance(requirements, list)
            or not all(isinstance(r, str) and r.startswith("REQ-") for r in requirements)):
        return None
    return {"issue": issue.get("number"), "task": task, "request": slug,
            "lot": _field(body, "Lote"), "write_paths": write_paths,
            "requirement_ids": requirements,
            "blocked": BLOCKED_LABEL in labels,
            "working": WORKING_LABEL in labels}


def exam_published(root: Path, task: str) -> bool:
    """Existence of the ciphertext only; never its contents."""
    path = root / "pilot" / "holdouts" / f"{task}.oracle.json.age"
    return path.is_file() and not path.is_symlink()


def pr_in_flight(open_prs: list, task: str) -> bool:
    heads = {pr.get("head", {}).get("ref", "") for pr in open_prs if isinstance(pr, dict)}
    pattern = re.compile(r"(?:lf/)?exam/" + re.escape(task) + r"(?:-[a-z0-9-]+)?")
    return any(pattern.fullmatch(head) for head in heads)


def template_matches(root: Path, row: dict) -> bool:
    """The task must still be planned: its lot template exists on main with the
    same write paths. Requests re-planned or abandoned leave stale issues."""
    path = root / "pilot" / "runs" / row["request"] / "templates" / f"{row['task']}.task.json"
    if path.is_symlink() or not path.is_file():
        return False
    try:
        spec = json.loads(path.read_text("utf-8")).get("task_spec", {})
    except ValueError:
        return False
    return sorted(spec.get("write_path_patterns") or []) == sorted(row["write_paths"])


def request_number(slug: str) -> int:
    return int(slug.split("-", 1)[1])


def build_queue(issues: list, open_prs: list, root: Path = ROOT,
                open_requests: set[int] | None = None,
                suspended_requests: set[int] | None = None) -> dict:
    """open_requests: numbers of request issues still open (None = not checked)."""
    if not isinstance(issues, list) or not isinstance(open_prs, list):
        raise QueueBlocked("EXAMINER_QUEUE_UNVERIFIED")
    seen: dict[str, dict] = {}
    pending, blocked, in_flight, duplicates, stale, suspended = [], [], [], [], [], []
    for issue in issues:
        row = parse_request(issue)
        if row is None:
            continue
        if row["task"] in seen:
            duplicates.append(row["task"])
            continue
        seen[row["task"]] = row
        if exam_published(root, row["task"]):
            continue
        if suspended_requests is not None and request_number(row["request"]) in suspended_requests:
            row.pop("blocked"), row.pop("working")
            suspended.append(row)
            continue
        if (not template_matches(root, row)
                or (open_requests is not None
                    and request_number(row["request"]) not in open_requests)):
            row.pop("blocked"), row.pop("working")
            stale.append(row)
            continue
        working = row.pop("working")
        if row.pop("blocked"):
            blocked.append(row)
        elif working or pr_in_flight(open_prs, row["task"]):
            in_flight.append(row)
        else:
            pending.append(row)
    key = lambda r: (r["request"], r["issue"] or 0)
    return {"schema_version": "LF_EXAMINER_QUEUE_V1",
            "pending": sorted(pending, key=key),
            "blocked": sorted(blocked, key=key),
            "in_flight": sorted(in_flight, key=key),
            "stale": sorted(stale, key=key),
            "suspended": sorted(suspended, key=key),
            "duplicates": sorted(set(duplicates))}


def _gh_pages(path: str) -> list:
    out = subprocess.run(["gh", "api", "--paginate", path], check=True,
                         capture_output=True, text=True).stdout
    rows: list = []
    # --paginate concatenates JSON arrays: "[...][...]".
    decoder, index = json.JSONDecoder(), 0
    while index < len(out):
        while index < len(out) and out[index].isspace():
            index += 1
        if index >= len(out):
            break
        value, index = decoder.raw_decode(out, index)
        if not isinstance(value, list):
            raise QueueBlocked("EXAMINER_QUEUE_UNVERIFIED")
        rows.extend(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=REPO)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="checkout of current main (ciphertext existence)")
    args = parser.parse_args()
    try:
        issues = _gh_pages(f"repos/{args.repo}/issues?state=open&labels={LABEL}&per_page=100")
        prs = _gh_pages(f"repos/{args.repo}/pulls?state=open&per_page=100")
        slugs = {row["request"] for row in map(parse_request, issues) if row}
        from pilot.orchestrator.request_lifecycle import request_state, OPEN, SUSPENDING, SUSPENDED
        def lifecycle_api(path):
            return json.loads(subprocess.run(
                ["gh", "api", f"repos/{args.repo}/{path}"],
                check=True, capture_output=True, text=True, timeout=30).stdout)
        open_requests, suspended_requests = set(), set()
        for slug in sorted(slugs):
            state = request_state(slug, lifecycle_api, root=args.root)
            if state == OPEN:
                open_requests.add(request_number(slug))
            elif state in (SUSPENDING, SUSPENDED):
                suspended_requests.add(request_number(slug))
        print(json.dumps(build_queue(issues, prs, args.root, open_requests, suspended_requests),
                         ensure_ascii=False, indent=1))
    except (QueueBlocked, subprocess.CalledProcessError, ValueError) as exc:
        print(json.dumps({"status": "EXAMINER_QUEUE_UNVERIFIED",
                          "detail": str(exc).splitlines()[0][:200]}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
