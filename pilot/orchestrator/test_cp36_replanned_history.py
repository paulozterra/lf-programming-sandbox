"""Regression proofs for governed first-parent chain-plan re-planning."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator.chain_contract import ChainBlocked

PLAN = "pilot/runs/req-391/chain_plan.json"
OLD = "req391oldinfra"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def init_repo(root: Path) -> None:
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("fixture")
    git(root, "add", ".")
    git(root, "commit", "-m", "Seed")


def old_plan(root: Path, task: str = OLD) -> None:
    path = root / PLAN
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bindings": [{"task_name": task}]}))


def train(root: Path, number: int, change, message: str | None = None) -> str:
    branch = f"test-pr-{number}"
    git(root, "checkout", "-b", branch)
    change()
    git(root, "add", "-A")
    git(root, "commit", "-m", f"Test PR {number}")
    git(root, "checkout", "main")
    git(root, "merge", "--no-ff", branch, "-m",
        message or f"Merge PR #{number} via sandbox-train")
    return git(root, "rev-parse", "HEAD")


def current_adds(root: Path) -> list[str]:
    return git(root, "log", "--first-parent", "--diff-filter=A",
               "--format=%H", "--", PLAN).splitlines()


def pr_receipt(merges: dict[int, str]):
    def receive(path: str) -> dict:
        n = int(path.rsplit("/", 1)[-1])
        return {"merged": True, "merge_commit_sha": merges[n],
                "base": {"ref": "main"},
                "head": {"ref": f"lf/native-integration/{OLD}-run-123"}}
    return receive


def test_single_plan_addition_is_unchanged(tmp_path: Path) -> None:
    init_repo(tmp_path)
    initial = train(tmp_path, 301, lambda: old_plan(tmp_path))
    assert chain_lots._active_plan_origin("req-391", PLAN, current_adds(tmp_path),
                                           tmp_path, 100) == initial


def test_clean_governed_replan_selects_latest_addition(tmp_path: Path) -> None:
    init_repo(tmp_path)
    first = train(tmp_path, 301, lambda: old_plan(tmp_path))
    deleted = train(tmp_path, 302, lambda: (tmp_path / PLAN).unlink())
    latest = train(tmp_path, 303, lambda: old_plan(tmp_path, "req391newinfra"))
    with patch.object(chain_lots, "api", side_effect=pr_receipt({302: deleted})):
        assert chain_lots._active_plan_origin("req-391", PLAN, current_adds(tmp_path),
                                               tmp_path, 100) == latest
    assert first != latest


def test_replan_with_old_registration_fails_closed(tmp_path: Path) -> None:
    init_repo(tmp_path)
    train(tmp_path, 301, lambda: old_plan(tmp_path))
    record = tmp_path / f"pilot/worker_v08/native_tasks/{OLD}.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "Old lot already registered")
    deleted = train(tmp_path, 302, lambda: (tmp_path / PLAN).unlink())
    train(tmp_path, 303, lambda: old_plan(tmp_path, "req391newinfra"))
    with patch.object(chain_lots, "api", side_effect=pr_receipt({302: deleted})):
        with pytest.raises(ChainBlocked, match="CHAIN_HISTORY_INCOMPLETE"):
            chain_lots._active_plan_origin("req-391", PLAN, current_adds(tmp_path),
                                           tmp_path, 100)


def test_replan_with_old_integration_fails_closed(tmp_path: Path) -> None:
    init_repo(tmp_path)
    train(tmp_path, 301, lambda: old_plan(tmp_path))
    marker = tmp_path / "integrated.txt"
    integrated = train(tmp_path, 399, lambda: marker.write_text("native"),
                       "Merge PR #399 via sandbox-train\n\n[CP3.5] Verified native")
    deleted = train(tmp_path, 302, lambda: (tmp_path / PLAN).unlink())
    train(tmp_path, 303, lambda: old_plan(tmp_path, "req391newinfra"))
    with patch.object(chain_lots, "api", side_effect=pr_receipt({302: deleted, 399: integrated})):
        with pytest.raises(ChainBlocked, match="CHAIN_HISTORY_INCOMPLETE"):
            chain_lots._active_plan_origin("req-391", PLAN, current_adds(tmp_path),
                                           tmp_path, 100)


def test_second_add_without_first_parent_retirement_fails_closed(tmp_path: Path) -> None:
    init_repo(tmp_path)
    train(tmp_path, 301, lambda: old_plan(tmp_path))
    latest = git(tmp_path, "rev-parse", "HEAD")
    older = git(tmp_path, "rev-parse", "HEAD^")
    with patch.object(chain_lots, "run") as command:
        command.side_effect = [
            latest + "\n" + older,  # first-parent rev-list
            "",                       # no first-parent deletions
        ]
        with pytest.raises(ChainBlocked, match="CHAIN_HISTORY_INCOMPLETE"):
            chain_lots._active_plan_origin("req-391", PLAN, [latest, older],
                                           tmp_path, 100)


def test_replan_with_untrusted_deletion_fails_closed(tmp_path: Path) -> None:
    init_repo(tmp_path)
    train(tmp_path, 301, lambda: old_plan(tmp_path))
    (tmp_path / PLAN).unlink()
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "Manual delete not via Train")
    train(tmp_path, 303, lambda: old_plan(tmp_path, "req391newinfra"))
    with pytest.raises(ChainBlocked, match="CHAIN_HISTORY_INCOMPLETE"):
        chain_lots._active_plan_origin("req-391", PLAN, current_adds(tmp_path),
                                       tmp_path, 100)
