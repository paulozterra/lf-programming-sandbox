"""Offline Git-tree negative cases for native proposal-only push preflight."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

import pytest

from native_proposal_push_guard import validate_proposal_only, ProposalPushBlocked


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def create_repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    (repo/"README").write_text("trusted\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "main")
    base=git(repo,"rev-parse","HEAD")
    git(repo, "checkout", "-qb", "lf/native-proposal/ex6")
    proposal=repo/"pilot/native_proposals/ex6.json"
    proposal.parent.mkdir(parents=True)
    proposal.write_text(json.dumps({"proposal":"safe"}))
    git(repo,"add","-A")
    git(repo,"commit","-qm","proposal")
    return repo,base,git(repo,"rev-parse","HEAD")


def test_single_json_commit_allowed(tmp_path):
    repo,base,head=create_repository(tmp_path)
    result=validate_proposal_only(repo,head,main_sha=base)
    assert result["scope_valid"] is True
    assert result["proposal_commit_sha"]==head


def test_extra_file_blocks(tmp_path):
    repo,base,_=create_repository(tmp_path)
    (repo/"unexpected.py").write_text("print('not executed')")
    git(repo,"add","-A")
    git(repo,"commit","-qm","bad extra")
    with pytest.raises(ProposalPushBlocked,match="NATIVE_PUSH_SCOPE_INVALID"):
        validate_proposal_only(repo,git(repo,"rev-parse","HEAD"),main_sha=base)


def test_unrelated_branch_blocks(tmp_path):
    repo,base,_=create_repository(tmp_path)
    git(repo,"checkout","-q",base)
    git(repo,"checkout","-qb","other")
    (repo/"pilot/native_proposals/ex6.json").write_text("{}")
    git(repo,"add","-A")
    git(repo,"commit","-qm","unrelated")
    head=git(repo,"rev-parse","HEAD")
    # The unrelated branch happens to descend from main: its name is enforced
    # by workflow trigger and native_run_history, not this pure Git gate.
    assert validate_proposal_only(repo,head,main_sha=base)["scope_valid"]


def test_symlink_blocks(tmp_path):
    repo,base,_=create_repository(tmp_path)
    path=repo/"pilot/native_proposals/ex6.json"
    path.unlink()
    path.symlink_to("../../README")
    git(repo,"add","-A")
    git(repo,"commit","-qm","symlink")
    with pytest.raises(ProposalPushBlocked,match="NATIVE_PUSH_PROPOSAL_NOT_REGULAR_FILE"):
        validate_proposal_only(repo,git(repo,"rev-parse","HEAD"),main_sha=base)


def test_invalid_json_blocks(tmp_path):
    repo,base,_=create_repository(tmp_path)
    (repo/"pilot/native_proposals/ex6.json").write_text("{not-json")
    git(repo,"add","-A")
    git(repo,"commit","-qm","invalid json")
    with pytest.raises(ProposalPushBlocked,match="NATIVE_PUSH_JSON_INVALID"):
        validate_proposal_only(repo,git(repo,"rev-parse","HEAD"),main_sha=base)


def test_non_descendant_main_blocks(tmp_path):
    repo,base,head=create_repository(tmp_path)
    git(repo,"checkout","-q",base)
    (repo/"README").write_text("main moved\n")
    git(repo,"add","-A")
    git(repo,"commit","-qm","main advanced")
    advanced=git(repo,"rev-parse","HEAD")
    with pytest.raises(ProposalPushBlocked,match="NATIVE_PUSH_NOT_DESCENDANT"):
        validate_proposal_only(repo,head,main_sha=advanced)
