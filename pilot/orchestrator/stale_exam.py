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
