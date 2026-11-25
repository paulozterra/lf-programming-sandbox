"""E2 on a synthetic first-parent history: an exam published before a
dependency's CP3.5 integration is stale; one written after is not."""
import subprocess
from pathlib import Path

import pytest

from pilot.orchestrator import stale_exam as se


def _repo(tmp_path):
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True,
                              text=True).stdout.strip()
    git("init", "-q", "-b", "main"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (tmp_path / "pilot/holdouts").mkdir(parents=True)
    (tmp_path / "a.txt").write_text("0"); git("add", "."); git("commit", "-qm", "base")
    return git


def _exam(git, tmp_path, task, n):
    (tmp_path / f"pilot/holdouts/{task}.oracle.json.age").write_text(str(n))
    git("add", "."); git("commit", "-qm", f"exam({task}) v{n}")


def _integrate(git, tmp_path, task):
    (tmp_path / "a.txt").write_text(task); git("add", ".")
    git("commit", "-qm", f"Merge PR #1 [CP3.5][CHG-0001] Verified native {task} run 123")


def test_exam_before_dependency_integration_is_stale(tmp_path):
    git = _repo(tmp_path)
    _exam(git, tmp_path, "r1backend2", 1)
    _integrate(git, tmp_path, "r1contrato1")
    assert se.is_stale(tmp_path, "r1backend2", ["r1contrato1"])


def test_exam_written_after_dependencies_is_never_stale(tmp_path):
    git = _repo(tmp_path)
    _integrate(git, tmp_path, "r1contrato1")
    _exam(git, tmp_path, "r1backend2", 2)
    assert not se.is_stale(tmp_path, "r1backend2", ["r1contrato1"])


def test_no_exam_no_dependencies_or_pending_dependency_is_not_stale(tmp_path):
    git = _repo(tmp_path)
    assert not se.is_stale(tmp_path, "r1backend2", ["r1contrato1"])     # no exam
    _exam(git, tmp_path, "r1backend2", 1)
    assert not se.is_stale(tmp_path, "r1backend2", [])                   # root lot
    assert not se.is_stale(tmp_path, "r1backend2", ["r1contrato1"])     # dep not integrated
    assert not se.is_stale(tmp_path, "r1backend2", ["../bad"])


def test_exam_paths_are_exactly_the_three_exam_files():
    assert se.exam_paths("req-1", "r1backend2") == [
        "pilot/holdouts/r1backend2.oracle.json.age",
        "pilot/holdouts/r1backend2.reference.json.age",
        "pilot/runs/req-1/claude_meta/r1backend2.json"]
    with pytest.raises(ValueError):
        se.exam_paths("req-1", "../x")
