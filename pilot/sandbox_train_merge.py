#!/usr/bin/env python3
"""Fail-closed local main->PR merge; only CAMBIOS.md may be regenerated."""
import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CAMBIOS = "standards/CAMBIOS.md"


def no_token_env():
    """Never expose the workflow write token to checked-out PR scripts."""
    return {k: v for k, v in os.environ.items()
            if k not in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN")}


class BranchConflict(Exception):
    pass


def git(root, *args, check=True, env=None):
    result = subprocess.run(["git", *args], cwd=root, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=no_token_env() if env is None else env)
    if check and result.returncode:
        raise BranchConflict("BRANCH_CONFLICT git " + str(args[0]) +
                             ": " + result.stderr.strip()[:350])
    return result


def check_conflicts(root):
    paths = [p for p in git(root, "diff", "--name-only", "--diff-filter=U", "-z").stdout.split("\0") if p]
    if paths and paths != [CAMBIOS]:
        raise BranchConflict("BRANCH_CONFLICT " + ",".join(sorted(paths)))
    return bool(paths)


def check_tooling_unchanged(root, base_ref, expected_head):
    """Do not auto-merge PR-authored policy or Train code, even if merge is clean."""
    changed = git(
        root, "diff", "--name-only", "-z", base_ref + "..." + expected_head,
        "--", "standards/tools/", ":(glob)pilot/sandbox_train*.py"
    ).stdout
    paths = sorted(filter(None, changed.split("\0")))
    if paths:
        raise BranchConflict("BRANCH_CONFLICT_TOOLING_CHANGED " + ",".join(paths))


def prepare_merge(root, base_ref, expected_head):
    """Build a local merge, check C9 against the NEW main parent, never push here."""
    if git(root, "rev-parse", "HEAD").stdout.strip() != expected_head:
        raise BranchConflict("BRANCH_CONFLICT HEAD_CHANGED")
    check_tooling_unchanged(root, base_ref, expected_head)
    attempted = git(root, "merge", "--no-edit", "--no-commit", "--no-ff", base_ref, check=False)
    if attempted.returncode:
        if not check_conflicts(root):
            raise BranchConflict("BRANCH_CONFLICT MERGE_FAILED")
        # regenerate using the combined CHG JSON set; never keep ours/theirs.
        regenerate = subprocess.run([sys.executable, "standards/tools/changes.py", "render"],
                                    cwd=root, text=True, capture_output=True, env=no_token_env())
        if regenerate.returncode:
            raise BranchConflict("BRANCH_CONFLICT CAMBIOS_RENDER_FAILED " +
                                 regenerate.stderr.strip()[:200])
        git(root, "add", "--", CAMBIOS)
        if check_conflicts(root):
            raise BranchConflict("BRANCH_CONFLICT UNRESOLVED")
    else:
        if check_conflicts(root):
            raise BranchConflict("BRANCH_CONFLICT UNEXPECTED_UNMERGED")
    # The derived view belongs to the Train, not to concurrent PRs.
    # Render after combining the CHG JSON files even when Git says
    # 'Already up to date', and stage only this generated view.
    regenerate = subprocess.run([sys.executable, "standards/tools/changes.py", "render"],
                                cwd=root, text=True, capture_output=True,
                                env=no_token_env())
    if regenerate.returncode:
        raise BranchConflict("BRANCH_CONFLICT CAMBIOS_RENDER_FAILED " +
                             regenerate.stderr.strip()[:200])
    git(root, "add", "--", CAMBIOS)
    if check_conflicts(root):
        raise BranchConflict("BRANCH_CONFLICT UNRESOLVED")
    git(root, "diff", "--check")
    git(root, "diff", "--cached", "--check")
    has_merge = (root / ".git" / "MERGE_HEAD").exists()
    dirty = git(root, "diff", "--cached", "--quiet", check=False).returncode != 0
    if has_merge or dirty:
        git(root, "-c", "user.name=sandbox-train[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "--no-verify", "-m",
            "Merge main into PR branch (sandbox-train)" if has_merge
            else "Render CAMBIOS from CHG records (sandbox-train)")
    parents = git(root, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    if has_merge and (len(parents) != 3 or parents[1] != expected_head):
        raise BranchConflict("BRANCH_CONFLICT MERGE_PARENTS_INVALID")
    # Nothing merged and nothing rendered: HEAD is still the verified PR head,
    # which may itself be a merge commit; only a new render commit is checked.
    if not has_merge and dirty and (len(parents) != 2 or parents[1] != expected_head):
        raise BranchConflict("BRANCH_CONFLICT RENDER_PARENTS_INVALID")
    # HEAD is now a merge commit: merge-base(origin/main,HEAD) is current main,
    # so C9 sees only the PR's CHG, not the CHGs newly added on main.
    for command in (("render", "--check"), ("check", "--base", base_ref)):
        result = subprocess.run([sys.executable, "standards/tools/changes.py", *command],
                                cwd=root, text=True, capture_output=True,
                                env=no_token_env())
        if result.returncode:
            raise BranchConflict("BRANCH_CONFLICT CHANGES_" + command[0].upper() +
                                 "_FAILED " + (result.stdout + result.stderr)[-700:])
    return git(root, "rev-parse", "HEAD").stdout.strip()


def configure_bot_identity(root):
    """Identity is local to the temporary clone, independent of runner HOME."""
    git(root, "config", "--local", "user.name", "sandbox-train[bot]")
    git(root, "config", "--local", "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com")


def update_branch_locally(branch, expected_head, expected_main, token, repository):
    """No remote write until local merge + C9 checks succeed."""
    if not branch or branch.startswith("-") or branch == "main":
        raise BranchConflict("BRANCH_CONFLICT INVALID_BRANCH")
    with tempfile.TemporaryDirectory(prefix="sandbox-train-") as directory:
        root = Path(directory)
        git(root, "init", "-q")
        # git merge --no-commit requires an identity even when conflicts occur.
        configure_bot_identity(root)
        remote = "https://github.com/" + repository + ".git"
        git(root, "remote", "add", "origin", remote)
        git(root, "fetch", "--no-tags", "origin",
            "+refs/heads/main:refs/remotes/origin/main",
            "+refs/heads/" + branch + ":refs/remotes/origin/train-target")
        if git(root, "rev-parse", "refs/remotes/origin/main").stdout.strip() != expected_main:
            raise BranchConflict("MAIN_MOVED_RETRY")
        if git(root, "rev-parse", "refs/remotes/origin/train-target").stdout.strip() != expected_head:
            raise BranchConflict("HEAD_MOVED_RETRY")
        git(root, "checkout", "--detach", "-q", expected_head)
        merged_sha = prepare_merge(root, "refs/remotes/origin/main", expected_head)
        # Non-forced push: concurrent branch updates are refused by Git.
        basic = base64.b64encode(("x-access-token:" + token).encode()).decode()
        env = no_token_env()
        env.update({"GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + basic,
                    "GIT_TERMINAL_PROMPT": "0"})
        push = git(root, "push", "origin", "HEAD:refs/heads/" + branch,
                   check=False, env=env)
        if push.returncode:
            raise BranchConflict("PUSH_REJECTED " + push.stderr.strip()[-300:])
        return merged_sha
