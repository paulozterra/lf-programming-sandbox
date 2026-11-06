#!/usr/bin/env python3
"""Adversarial offline checks for ex4 lot size, SHA locks and actual PR handoff."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pytest
import ex4_preflight as guard
import task_selector as selector


def _git(root: Path, *args: str):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _seed_handoff(tmp_path: Path, *, message: str = "Merge pull request #123: ex4a lot A repository"):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Offline CI")
    _git(tmp_path, "config", "user.email", "offline@example.invalid")
    (tmp_path/"README.txt").write_text("fixture", encoding="utf-8")
    _git(tmp_path, "add", "README.txt")
    _git(tmp_path, "commit", "-qm", "initial")
    for path in guard.A_FILES:
        output = tmp_path/path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("synthetic fixture only", encoding="utf-8")
        _git(tmp_path, "add", path)
    _git(tmp_path, "commit", "-qm", message)


def test_registered_sha_exact_and_exercises_unchanged():
    assert selector.select("ex4a")["holdout_sha256"] == (
        "cd0e9d7fc73aa92280b162e8c0f3f79d98cd7046b5626737666df97080f2af54")
    assert selector.select("ex4b")["holdout_sha256"] == (
        "8df8ec9858e8dd0078e955b285bac110becc781b55280b17edd9b811d44a900c")
    assert selector.select("ex4a")["spec_sha256"] == selector.EX4_SPEC_SHA
    assert selector.select("ex4b")["spec_sha256"] == selector.EX4_SPEC_SHA
    assert selector.select("exercise-1")["holdout_sha256"] == selector.EX1_SHA
    assert selector.select("exercise-2")["holdout_sha256"] == selector.EX2_SHA


def test_handoff_real_files_plus_numbered_ex4a_pr_commit(tmp_path):
    _seed_handoff(tmp_path)
    assert len(guard.check_handoff(tmp_path)) == 40


def test_handoff_missing_any_file_blocks_without_cost(tmp_path):
    _seed_handoff(tmp_path)
    (tmp_path/guard.A_FILES[1]).unlink()
    with pytest.raises(guard.LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        guard.check_handoff(tmp_path)


def test_handoff_no_pr_provenance_blocks(tmp_path):
    _seed_handoff(tmp_path, message="manual copy ex4a into main")
    with pytest.raises(guard.LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        guard.check_handoff(tmp_path)


def test_handoff_unrelated_pr_blocks(tmp_path):
    _seed_handoff(tmp_path, message="Merge pull request #123: unrelated work")
    with pytest.raises(guard.LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        guard.check_handoff(tmp_path)


def test_lot_a_context_counts_and_prompt_bytes(tmp_path):
    p=tmp_path/"spec.md"
    p.write_bytes(b"abcdef")
    task={"context_path_patterns":["spec.md"],"write_path_patterns":["new.java"]}
    outcome=guard.check_lot_size(tmp_path, task, b"prompt")
    assert outcome == {"total_bytes":12,"context_file_count":1,
                       "write_file_count":1,"status":"LOT_SIZE_PASS"}


def test_intentionally_inflated_lot_blocks_before_model(tmp_path):
    (tmp_path/"oversized.txt").write_bytes(b"X"*240001)
    task={"context_path_patterns":["oversized.txt"],"write_path_patterns":["new.java"]}
    with pytest.raises(guard.LotBlocked, match="LOTE_DEMASIADO_GRANDE"):
        guard.check_lot_size(tmp_path, task, b"prompt")


@pytest.mark.parametrize("contexts,writes", [(13, 1), (1, 7)])
def test_excessive_file_count_blocks(tmp_path, contexts, writes):
    paths=[]
    for index in range(contexts):
        name=f"context-{index}.txt"
        (tmp_path/name).write_bytes(b"x")
        paths.append(name)
    task={"context_path_patterns":paths,
          "write_path_patterns":[f"new-{i}.java" for i in range(writes)]}
    with pytest.raises(guard.LotBlocked, match="LOTE_DEMASIADO_GRANDE"):
        guard.check_lot_size(tmp_path, task, b"x")


def test_ex4b_refuses_missing_visible_controller_test(tmp_path):
    _seed_handoff(tmp_path)
    task={"context_path_patterns":[],"write_path_patterns":[]}
    with pytest.raises(guard.LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        guard.validate_pre_model(tmp_path, "ex4b", task, b"")


@pytest.mark.parametrize("which", ["ex4a", "ex4b"])
def test_tampered_holdout_sha_rejected(tmp_path, monkeypatch, which):
    data=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
    modified=copy.deepcopy(data)
    modified["tasks"][which]["holdout_sha256"]="0"*64
    path=tmp_path/"tasks.json"
    path.write_text(json.dumps(modified),encoding="utf-8")
    monkeypatch.setattr(selector,"CATALOG",path)
    with pytest.raises(selector.TaskBlocked, match="PILOT_EX4_HOLDOUT_SHA_DRIFT"):
        selector.select(which)


def test_no_hidden_oracle_file_is_opened():
    source=Path(guard.__file__).read_text(encoding="utf-8")
    assert "holdout.oracle.json" not in source
    assert "ANTHROPIC_API_KEY" not in source
