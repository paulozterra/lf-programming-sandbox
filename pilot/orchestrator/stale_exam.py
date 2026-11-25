"""E2: a hidden exam published before one of its lot's dependencies was
integrated was written against a base that dependency later changed (req-652:
the BACKEND reference predates the CONTRATO lot and fails the T40 rehearsal).

Shared by CP3.6 (detects and opens a retire PR) and policy C (re-verifies the
same condition on trusted main before labelling). Git history only: nothing
here reads, decrypts or infers an exam. Exams written after every dependency
was integrated are never stale, so a retired exam cannot loop.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SLUG = re.compile(r"req-[1-9][0-9]{0,6}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)


def exam_paths(request: str, task: str) -> list[str]:
    if not SLUG.fullmatch(request) or not TASK.fullmatch(task):
        raise ValueError("STALE_EXAM_IDENTITY_INVALID")
    return [f"pilot/holdouts/{task}.oracle.json.age",
            f"pilot/holdouts/{task}.reference.json.age",
            f"pilot/runs/{request}/claude_meta/{task}.json"]


def exam_commit(root: Path, task: str, rev: str = "HEAD") -> str | None:
    """First-parent main commit that last published the task's ciphertext."""
    out = _git(root, "log", "-1", "--first-parent", "--format=%H", rev, "--",
               f"pilot/holdouts/{task}.oracle.json.age")
    sha = out.stdout.strip() if out.returncode == 0 else ""
    return sha if SHA.fullmatch(sha) else None


def integration_commit(root: Path, task: str, rev: str = "HEAD") -> str | None:
    """First-parent CP3.5 merge that integrated a lot's verified native task."""
    out = _git(root, "log", "-1", "--first-parent", "--format=%H",
               "--grep", rf"\[CP3\.5\].*Verified native {re.escape(task)} run [0-9]", rev)
    sha = out.stdout.strip() if out.returncode == 0 else ""
    return sha if SHA.fullmatch(sha) else None


def is_stale(root: Path, task: str, dependency_tasks: list[str], rev: str = "HEAD") -> bool:
    """True when the exam exists and some dependency was integrated after it."""
    if not TASK.fullmatch(task) or not dependency_tasks:
        return False
    published = exam_commit(root, task, rev)
    if published is None:
        return False
    for dep in dependency_tasks:
        if not isinstance(dep, str) or not TASK.fullmatch(dep):
            return False
        merged = integration_commit(root, dep, rev)
        if merged is None:
            continue
        if _git(root, "merge-base", "--is-ancestor", merged, published).returncode != 0:
            return True
    return False


MAX_REHEARSAL_RETIRES = 2


def rehearsal_failure(list_pulls, check_runs, task: str) -> dict | None:
    """Latest registration PR of the task whose T40 'rehearse' check failed.

    list_pulls() -> GitHub pulls (state=all); check_runs(sha) -> check runs.
    Returns {"pr", "head_sha", "job_id"} or None. Public metadata only."""
    prefix = f"lf/native-registration/{task}-"
    rows = [p for p in list_pulls() if isinstance(p, dict)
            and str((p.get("head") or {}).get("ref", "")).startswith(prefix)]
    if not rows:
        return None
    latest = max(rows, key=lambda p: (str(p.get("created_at") or ""), int(p.get("number") or 0)))
    sha = (latest.get("head") or {}).get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        return None
    runs = [c for c in check_runs(sha) if isinstance(c, dict) and c.get("name") == "rehearse"
            and c.get("status") == "completed"]
    if not runs:
        return None
    last = max(runs, key=lambda c: (str(c.get("started_at") or ""), int(c.get("id") or 0)))
    if last.get("conclusion") != "failure":
        return None
    return {"pr": int(latest["number"]), "head_sha": sha, "job_id": int(last["id"])}


def retire_count(root: Path, task: str, dependency_tasks: list[str]) -> int:
    """Count rehearsal-budget retirements using immutable first-parent history.

    A deletion proven stale at its immediate main parent is not a rehearsal
    failure. Unknown deletions consume budget; incomplete history blocks E2.
    Neither PR descriptions nor a recent-PR window can reset this budget.
    """
    if not TASK.fullmatch(task) or any(not TASK.fullmatch(dep)
                                      for dep in dependency_tasks):
        raise ValueError("EXAM_RETIRE_HISTORY_INVALID")
    shallow = _git(root, "rev-parse", "--is-shallow-repository")
    if shallow.returncode or shallow.stdout.strip() != "false":
        raise ValueError("EXAM_RETIRE_HISTORY_INCOMPLETE")
    path = f"pilot/holdouts/{task}.oracle.json.age"
    history = _git(root, "log", "--first-parent", "--diff-merges=first-parent",
                   "--no-patch", "--diff-filter=D", "--format=%H", "HEAD", "--", path)
    if history.returncode:
        raise ValueError("EXAM_RETIRE_HISTORY_INCOMPLETE")
    total = 0
    for sha in history.stdout.splitlines():
        if not SHA.fullmatch(sha):
            raise ValueError("EXAM_RETIRE_HISTORY_INVALID")
        parent = sha + "^1"
        published = exam_commit(root, task, parent)
        stale = False
        if published is not None:
            for dep in dependency_tasks:
                merged = integration_commit(root, dep, parent)
                if merged is not None:
                    relation = _git(root, "merge-base", "--is-ancestor", merged, published)
                    if relation.returncode not in (0, 1):
                        raise ValueError("EXAM_RETIRE_HISTORY_INCOMPLETE")
                    if relation.returncode == 1:
                        stale = True
                        break
        if not stale:
            total += 1
    return total


def exam_retired(root: Path, task: str, rev: str = "HEAD") -> bool:
    """True when the task's ciphertext existed and its last change deleted it."""
    if not TASK.fullmatch(task):
        return False
    path = f"pilot/holdouts/{task}.oracle.json.age"
    if (root / path).exists():
        return False
    out = _git(root, "log", "-1", "--format=%H", "--diff-filter=D", rev, "--", path)
    return out.returncode == 0 and bool(SHA.fullmatch(out.stdout.strip()))


def pending_retire_pr(list_pulls, task: str) -> int | None:
    """Return an open retirement from a complete state=open collection."""
    if not isinstance(task, str) or not TASK.fullmatch(task):
        raise ValueError("STALE_EXAM_IDENTITY_INVALID")
    rows = list_pulls()
    if not isinstance(rows, list):
        raise ValueError("RETIRE_PR_LIST_INVALID")
    pending = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("RETIRE_PR_LIST_INVALID")
        head, number = row.get("head"), row.get("number")
        if (row.get("state") != "open" or not isinstance(head, dict)
                or not isinstance(head.get("ref"), str)
                or type(number) is not int or number <= 0):
            raise ValueError("RETIRE_PR_LIST_INVALID")
        if head["ref"].startswith(f"lf/exam-retire/{task}-"):
            pending.append(number)
    return min(pending) if pending else None
