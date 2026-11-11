#!/usr/bin/env python3
"""CP3.5: one command for CP3.4 register→commit→seal→commit→export.

This command commits ONLY the task and generated context on a non-main branch.
No model, hidden-oracle reads, GitHub push, PR, merge or label changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from native_lot_registration import (
    ROOT, WORKER, NativeLotBlocked, ContextBlocked, blocked,
    choose, register_lot, seal_lot, export_lot, git,
)


def _commit_exact(root: Path, paths: list[str], message: str) -> str:
    if not paths or len(set(paths)) != len(paths):
        blocked("CP35_COMMIT_PATH_INVALID")
    for p in paths:
        if p.startswith(("vendor/", "pilot/lf_producers_pinned/", ".github/")):
            blocked("CP35_COMMIT_PATH_DENIED")
    git(root, "add", "--", *paths)
    staged = git(root, "diff", "--cached", "--name-only", "-z")
    # git() text output can represent NUL, but here only ASCII paths from
    # the trusted registration; no user-supplied staging is allowed.
    actual = set(filter(None, staged.split("\x00")))
    if actual != set(paths):
        blocked("CP35_STAGED_SCOPE_DRIFT")
    git(root, "commit", "-m", message, "--only", "--", *paths)
    if git(root, "status", "--porcelain"):
        blocked("CP35_POST_COMMIT_DIRTY")
    return git(root, "rev-parse", "HEAD")


def run(root: Path, request: str, lot_id: str, task_name: str, template: dict,
        holdout: dict, proofs: list[dict]) -> dict:
    if root.resolve() != ROOT.resolve():
        blocked("CP35_REPO_ROOT_MISMATCH")
    branch = git(root, "branch", "--show-current")
    if not branch or branch in ("main", "master") or branch.startswith("lf/native-proposal/"):
        blocked("CP35_UNSAFE_BRANCH")
    if git(root, "status", "--porcelain"):
        blocked("CP35_DIRTY_START")
    # The owner governs the branch; a merged main ancestor is necessary.
    git(root, "merge-base", "--is-ancestor", "origin/main", "HEAD")
    folder, lot, mapped, paths = choose(root, request, lot_id, proofs)
    registration = register_lot(root, folder, lot, mapped, paths,
                                task_name, template, holdout)
    to_commit = registration["context_paths"] + [registration["native_task"]]
    first_sha = _commit_exact(root, to_commit, f"[CP3.4] register native context {task_name}")
    sealed = seal_lot(root, folder, lot, mapped, paths, task_name, template, holdout)
    second_sha = _commit_exact(root, [sealed["native_task"]],
                               f"[CP3.4] seal native task base {task_name}")
    result = export_lot(root, folder, lot, mapped, paths, task_name, template, holdout)
    if result["base_head_sha"] != first_sha or second_sha == first_sha:
        blocked("CP35_BASE_COMMIT_DRIFT")
    return {**result, "registration_commit_sha": first_sha,
            "seal_commit_sha": second_sha,
            "result": "CP35_PREPARED_NO_MODEL_NO_PUSH"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--request-id", required=True)
    ap.add_argument("--lot-id", required=True)
    ap.add_argument("--task-name", required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--holdout-metadata", type=Path, required=True)
    ap.add_argument("--handoff-proof", type=Path, action="append", default=[])
    args = ap.parse_args()
    try:
        template = json.loads(args.template.read_text("utf-8"))
        holdout = json.loads(args.holdout_metadata.read_text("utf-8"))
        proofs = [json.loads(p.read_text("utf-8")) for p in args.handoff_proof]
        outcome = run(args.root, args.request_id, args.lot_id,
                      args.task_name, template, holdout, proofs)
    except (NativeLotBlocked, ContextBlocked, OSError, ValueError, KeyError) as exc:
        # A failure can leave prepared commits. Never reset or repeat blindly.
        print("CP35_BLOCKED:" + str(exc) + ":INSPECT_BRANCH_BEFORE_RETRY", file=sys.stderr)
        return 1
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
