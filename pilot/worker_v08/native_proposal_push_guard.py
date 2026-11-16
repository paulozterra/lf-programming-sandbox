"""Fail-closed push gate: proposal commit descends from trusted main, with one JSON change.

Reads only Git objects. Never executes content from the proposal commit.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TASK_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")

class ProposalPushBlocked(ValueError):
    pass

def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)

def validate_proposal_only(control: Path, proposal_sha: str, *, main_sha: str | None = None, branch: str | None = None) -> dict:
    if _SHA40.fullmatch(proposal_sha) is None:
        raise ProposalPushBlocked("NATIVE_PUSH_SHA_INVALID")
    main_sha = main_sha or _git(control, "rev-parse", "HEAD").decode().strip()
    if not _SHA40.fullmatch(main_sha):
        raise ProposalPushBlocked("NATIVE_PUSH_MAIN_INVALID")
    # A proposal submitted before later Train merges remains valid if its
    # original base is an ancestor of current trusted main. Evaluate only
    # the proposal-only delta since that exact shared ancestor.
    if proposal_sha == main_sha:
        raise ProposalPushBlocked("NATIVE_PUSH_NO_PROPOSAL_DELTA")
    try:
        base = _git(control, "merge-base", main_sha, proposal_sha).decode().strip()
    except subprocess.CalledProcessError as exc:
        raise ProposalPushBlocked("NATIVE_PUSH_NOT_DESCENDANT_OF_TRUSTED_MAIN") from exc
    if not _SHA40.fullmatch(base) or base == proposal_sha:
        raise ProposalPushBlocked("NATIVE_PUSH_NOT_DESCENDANT_OF_TRUSTED_MAIN")
    if subprocess.run(["git", "-C", str(control), "merge-base", "--is-ancestor",
                       base, main_sha], check=False,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise ProposalPushBlocked("NATIVE_PUSH_NOT_DESCENDANT_OF_TRUSTED_MAIN")
    raw = _git(control, "diff", "--name-status", "-z", "--no-renames",
               base, proposal_sha)
    fields = raw.split(b"\x00")
    if len(fields) != 3 or fields[-1] != b"" or fields[0] not in (b"A", b"M"):
        raise ProposalPushBlocked("NATIVE_PUSH_SCOPE_INVALID")
    try:
        path = fields[1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProposalPushBlocked("NATIVE_PUSH_SCOPE_INVALID") from exc
    match = re.fullmatch(r"pilot/native_proposals/([a-z][a-z0-9_-]{0,31})\.json", path)
    if match is None:
        raise ProposalPushBlocked("NATIVE_PUSH_SCOPE_INVALID")
    task = match.group(1)
    # Every intervening commit must touch only the same proposal, even if a
    # malicious change was later reverted before the branch tip.
    commits = _git(control, "rev-list", "--reverse", base + ".." + proposal_sha).decode().splitlines()
    if not 1 <= len(commits) <= 50:
        raise ProposalPushBlocked("NATIVE_PUSH_HISTORY_BOUNDS")
    for commit in commits:
        ancestry = _git(control, "rev-list", "--parents", "-n", "1", commit).decode().split()
        if len(ancestry) != 2:
            raise ProposalPushBlocked("NATIVE_PUSH_MERGE_NOT_ALLOWED")
        one = _git(control, "diff", "--name-status", "-z", "--no-renames", ancestry[1], commit).split(b"\x00")
        if len(one) != 3 or one[-1] != b"" or one[0] not in (b"A", b"M") or one[1] != path.encode():
            raise ProposalPushBlocked("NATIVE_PUSH_COMMIT_SCOPE_INVALID")
    if branch is not None and branch != "lf/native-proposal/" + task:
        raise ProposalPushBlocked("NATIVE_PUSH_BRANCH_TASK_MISMATCH")
    registered = "pilot/worker_v08/native_tasks/" + task + ".json"
    registration = _git(control, "ls-tree", base, "--", registered).decode().strip().split()
    if len(registration) < 3 or registration[:2] != ["100644", "blob"]:
        raise ProposalPushBlocked("NATIVE_TASK_UNREGISTERED")
    info = _git(control, "ls-tree", proposal_sha, "--", path).decode().strip().split()
    if len(info) < 3 or info[0] != "100644" or info[1] != "blob":
        raise ProposalPushBlocked("NATIVE_PUSH_PROPOSAL_NOT_REGULAR_FILE")
    raw_json = _git(control, "show", proposal_sha + ":" + path)
    if len(raw_json) > 200_000 or len(raw_json) == 0:
        raise ProposalPushBlocked("NATIVE_PUSH_PROPOSAL_SIZE_INVALID")
    try:
        obj = json.loads(raw_json)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProposalPushBlocked("NATIVE_PUSH_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        raise ProposalPushBlocked("NATIVE_PUSH_JSON_OBJECT_REQUIRED")
    return {"proposal_commit_sha": proposal_sha, "base_commit_sha": base,
            "proposal_path": path, "task": task, "scope_valid": True}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    result = validate_proposal_only(args.control, args.sha, branch=args.branch)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            for key in ("task", "proposal_commit_sha", "proposal_path"):
                stream.write(key + "=" + str(result[key]) + "\n")
            stream.write("secret_task=" + result["task"].upper() + "\n")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    try:
        main()
    except ProposalPushBlocked as exc:
        # Exact machine code, no traceback or untrusted data from the proposal.
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
