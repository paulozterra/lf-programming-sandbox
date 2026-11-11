"""Offline-only tests. No holdout body, secrets, provider or model calls."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lot_preflight import (
    LOT_A, LotBlocked, check_handoff, check_size as _check_size, sha_registration,
)


def git(root: Path, *argv: str):
    return subprocess.run(["git", "-C", str(root), *argv], check=True,
                          capture_output=True, text=True).stdout


def repo(tmp_path: Path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "symbolic-ref", "HEAD", "refs/heads/main")
    git(tmp_path, "config", "user.name", "Pilot Test")
    git(tmp_path, "config", "user.email", "pilot@example.invalid")
    (tmp_path / "README.md").write_text("fictional sandbox", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial fixtures")
    return tmp_path


def check_size(root, task, *, prompt):
    payload = dict(task)
    payload.setdefault("base_head_sha", git(root, "rev-parse", "main").strip())
    return _check_size(root, payload, prompt=prompt)


def make_file(root: Path, name: str, data: str = "fixture"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def test_lot_a_registered_sha_and_lot_b_distinct():
    rows = {"tasks": {
        "ex4a": {"holdout_sha256": "cd0e9d7fc73aa92280b162e8c0f3f79d98cd7046b5626737666df97080f2af54"},
        "ex4b": {"holdout_sha256": "8df8ec9858e8dd0078e955b285bac110becc781b55280b17edd9b811d44a900c"},
    }}
    assert sha_registration("ex4a", rows) != sha_registration("ex4b", rows)


@pytest.mark.parametrize("name", ("ex4a", "ex4b"))
def test_tampered_sha_is_rejected(name):
    rows = {"tasks": {name: {"holdout_sha256": "0" * 64}}}
    with pytest.raises(LotBlocked, match="LOTE_HOLDOUT_SHA_DRIFT"):
        sha_registration(name, rows)


def test_inflated_context_bytes_block_before_model(tmp_path):
    root = repo(tmp_path)
    make_file(root, "large.txt", "x" * 240_001)
    git(root, "add", "large.txt")
    git(root, "commit", "-qm", "base with large context")
    with pytest.raises(LotBlocked, match="LOTE_DEMASIADO_GRANDE"):
        check_size(root, {"context_path_patterns": ["large.txt"],
                          "write_path_patterns": [LOT_A[0]]}, prompt="system")


def test_more_than_thirty_two_context_files_block(tmp_path):
    root = repo(tmp_path)
    for i in range(33):
        make_file(root, f"apps/service/c{i}.txt")
    git(root, "add", ".")
    git(root, "commit", "-qm", "33 context files")
    with pytest.raises(LotBlocked, match="LOTE_DEMASIADO_GRANDE"):
        check_size(root, {"context_path_patterns": ["apps/service/*.txt"],
                          "write_path_patterns": [LOT_A[0]]}, prompt="x")


def test_more_than_six_write_files_block(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(LotBlocked, match="LOTE_DEMASIADO_GRANDE"):
        check_size(root, {"context_path_patterns": ["README.md"],
                          "write_path_patterns": [LOT_A[0]] * 7}, prompt="x")


def test_missing_lot_a_blocks(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        check_handoff(root)


def test_unattributed_lot_a_blocks(tmp_path):
    root = repo(tmp_path)
    for path in LOT_A:
        make_file(root, path)
    git(root, "add", ".")
    git(root, "commit", "-qm", "local manual files without PR")
    with pytest.raises(LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        check_handoff(root)


def test_lot_a_commit_with_real_pr_provenance_passes(tmp_path):
    root = repo(tmp_path)
    for path in LOT_A:
        make_file(root, path)
    git(root, "add", ".")
    git(root, "commit", "-qm", "Merge pull request #42 from owner/ex4a-patch",
        "-m", "PR 2: ex4a lote A verified patch")
    sha = git(root, "rev-parse", "HEAD").strip()
    assert check_handoff(root) == sha


def test_tracked_small_scope_passes(tmp_path):
    root = repo(tmp_path)
    result = check_size(root, {"context_path_patterns": ["README.md"],
                               "write_path_patterns": [LOT_A[0]]}, prompt="worker prompt")
    assert result["context_files"] == 1
    assert result["write_files"] == 1
    assert 0 < result["bytes"] < 240_000

def test_generic_tsx_and_sql_writes_are_allowed(tmp_path):
    root = repo(tmp_path)
    for path in ("apps/web/src/page.tsx", "db/migrations/V2__new.sql"):
        assert check_size(root, {
            "context_path_patterns": ["README.md"],
            "write_path_patterns": [path]}, prompt="")["write_files"] == 1


def test_generic_handoff_task_owned_and_missing(tmp_path):
    from lot_preflight import check_task
    root = repo(tmp_path)
    task = {"base_head_sha": git(root, "rev-parse", "HEAD").strip(),
            "context_path_patterns": ["README.md"],
            "write_path_patterns": ["apps/web/src/page.tsx"],
            "handoff": {"previous_lot": "lot_a",
                        "expected_files": ["apps/web/src/lib/lot-a.ts"]}}
    with pytest.raises(LotBlocked, match="HANDOFF_LOT_A_MISSING"):
        check_task(root, task)
    make_file(root, "apps/web/src/lib/lot-a.ts")
    git(root, "add", ".")
    git(root, "commit", "-qm", "lot_a produced")
    task["base_head_sha"] = git(root, "rev-parse", "HEAD").strip()
    assert check_task(root, task)["context_files"] == 1


def test_generic_limits_for_all_areas(tmp_path):
    from lot_preflight import check_task
    root = repo(tmp_path)
    for ext, prefix in ((".java", "apps/service/src/main/java/"),
                        (".tsx", "apps/web/src/"), (".sql", "db/migrations/")):
        task = {"base_head_sha": git(root, "rev-parse", "HEAD").strip(),
                "context_path_patterns": ["README.md"],
                "write_path_patterns": [prefix + "N" + str(i) + ext for i in range(7)]}
        with pytest.raises(LotBlocked, match="LOTE_DEMASIADO_GRANDE"):
            check_task(root, task)

def test_base_blob_exists_without_worktree_file(tmp_path):
    root = repo(tmp_path)
    make_file(root, "apps/svc/base-only.ts", "committed contents")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base file")
    base = git(root, "rev-parse", "HEAD").strip()
    (root / "apps/svc/base-only.ts").unlink()
    task = {"base_head_sha": base,
            "context_path_patterns": ["apps/svc/base-only.ts"],
            "write_path_patterns": ["apps/svc/new.ts"]}
    assert _check_size(root, task, prompt="")["context_files"] == 1


def test_uncommitted_worktree_file_not_in_base_blocks(tmp_path):
    root = repo(tmp_path)
    make_file(root, "apps/svc/working-only.ts", "untracked")
    task = {"base_head_sha": git(root, "rev-parse", "HEAD").strip(),
            "context_path_patterns": ["apps/svc/working-only.ts"],
            "write_path_patterns": ["apps/svc/new.ts"]}
    with pytest.raises(LotBlocked, match="LOTE_CONTEXTO_FALTANTE"):
        _check_size(root, task, prompt="")


def test_globs_deterministic_and_empty_pattern_blocks(tmp_path):
    root = repo(tmp_path)
    for name in ("ReminderB.java", "ReminderA.java"):
        make_file(root, "apps/svc/reminder/" + name, "class Test {}")
    git(root, "add", ".")
    git(root, "commit", "-qm", "two Java sources")
    task = {"base_head_sha": git(root, "rev-parse", "HEAD").strip(),
            "context_path_patterns": ["apps/svc/reminder/*.java"],
            "write_path_patterns": ["apps/svc/New.java"]}
    assert _check_size(root, task, prompt="") == _check_size(root, task, prompt="")
    assert _check_size(root, task, prompt="")["context_files"] == 2
    task["context_path_patterns"] = ["apps/svc/missing/*.java"]
    with pytest.raises(LotBlocked, match="LOTE_CONTEXTO_FALTANTE"):
        _check_size(root, task, prompt="")


def test_base_invalid_or_not_ancestor_of_main(tmp_path):
    root = repo(tmp_path)
    task = {"base_head_sha": "f" * 40, "context_path_patterns": ["README.md"],
            "write_path_patterns": ["apps/svc/New.java"]}
    with pytest.raises(LotBlocked, match="LOTE_BASE_INVALIDA"):
        _check_size(root, task, prompt="")
    original = git(root, "rev-parse", "HEAD").strip()
    git(root, "checkout", "-qb", "foreign")
    make_file(root, "apps/svc/foreign.java", "unrelated")
    git(root, "add", ".")
    git(root, "commit", "-qm", "foreign")
    task["base_head_sha"] = git(root, "rev-parse", "HEAD").strip()
    git(root, "checkout", "-q", "main")
    with pytest.raises(LotBlocked, match="LOTE_BASE_INVALIDA"):
        _check_size(root, task, prompt="")
    assert original == git(root, "rev-parse", "HEAD").strip()


def test_ex8_original_globs_expand_to_twenty_one_base_files():
    root = Path(__file__).resolve().parents[2]
    registered = json.loads((root / "pilot/worker_v08/native_tasks/ex8.json").read_text())
    from lot_preflight import check_task
    result = check_task(root, registered)
    assert result["context_files"] == 21
    assert result["bytes"] <= 240_000


def test_ex8b_base_preflight_still_passes():
    root = Path(__file__).resolve().parents[2]
    registered = json.loads((root / "pilot/worker_v08/native_tasks/ex8b.json").read_text())
    from lot_preflight import check_task
    result = check_task(root, registered)
    assert result["context_files"] == 11
