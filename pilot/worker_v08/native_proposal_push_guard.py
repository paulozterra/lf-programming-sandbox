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

# Import only trusted-main scope policy; never import untrusted proposal code.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator"))
from native_write_scope import validate_write_paths, WriteScopeError

TASK_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")

class ProposalPushBlocked(ValueError):
    pass

def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)

def patch_applies(control: Path, base: str, patch: str) -> bool:
    """git apply --check of the patch against `base` in a throwaway index."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory(prefix="t38-") as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        if subprocess.run(["git", "-C", str(control), "read-tree", base], env=env,
                          capture_output=True).returncode:
            return False
        patch_file = Path(tmp) / "p.patch"
        patch_file.write_text(patch, "utf-8")
        return subprocess.run(["git", "-C", str(control), "apply", "--cached", "--check",
                               str(patch_file)], env=env, capture_output=True).returncode == 0


def validate_proposal_only(control: Path, proposal_sha: str, *, main_sha: str | None = None, branch: str | None = None, allow_historical_base: bool = False) -> dict:
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
    if (not _SHA40.fullmatch(base) or base == proposal_sha
            or (not allow_historical_base and base != main_sha)):
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
    # The same write scope that the generator issued must be admissible to
    # CP3.5; fail before a proposal can spend a native attempt.
    try:
        registered_task = json.loads(_git(control, "show", main_sha + ":" + registered))
        validate_write_paths(registered_task["task_spec"]["write_path_patterns"])
    except (OSError, KeyError, ValueError, TypeError, WriteScopeError) as exc:
        raise ProposalPushBlocked("NATIVE_TASK_SCOPE_UNSAFE") from exc
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
    # T38: a patch that cannot be applied to the registered base never reaches
    # the Worker, so it cannot spend an attempt. Checked against an index built
    # from the base tree; nothing from the proposal is executed or checked out.
    patch = (obj.get("proposal") or {}).get("patch") if isinstance(obj.get("proposal"), dict) else None
    task_base = (registered_task.get("task_spec") or {}).get("base_head_sha")
    if (isinstance(patch, str) and isinstance(task_base, str) and _SHA40.fullmatch(task_base)
            and subprocess.run(["git", "-C", str(control), "cat-file", "-e", task_base + "^{commit}"],
                               capture_output=True).returncode == 0):
        # An unavailable base keeps the previous behaviour (the Worker decides).
        if not patch_applies(control, task_base, patch):
            raise ProposalPushBlocked("NATIVE_PUSH_PATCH_NOT_APPLICABLE")
    return {"proposal_commit_sha": proposal_sha, "base_commit_sha": base,
            "proposal_path": path, "task": task, "scope_valid": True}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch")
    parser.add_argument("--allow-historical-base", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    result = validate_proposal_only(args.control, args.sha, branch=args.branch,
                                    allow_historical_base=args.allow_historical_base)
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
