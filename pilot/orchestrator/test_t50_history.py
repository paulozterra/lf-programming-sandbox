"""T50: request-scoped first-parent history with real temporary git repositories."""
import os
import subprocess
from pathlib import Path

import pytest

from pilot.orchestrator import chain_lots as cl
from chain_contract import ChainBlocked


def git(root, *args, check=True):
    p = subprocess.run(["git", *args], cwd=root, text=True,
                       capture_output=True)
    if check and p.returncode:
        raise AssertionError(f"git {args}: {p.stderr}")
    return p.stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "T50")
    git(tmp_path, "config", "user.email", "t50@example.invalid")
    plan = tmp_path / "pilot/runs/req-186/chain_plan.json"
    plan.parent.mkdir(parents=True)
    plan.write_text("{}")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "Owner registered chain plan")
    def local_run(*args, cwd=tmp_path, check=True):
        p = subprocess.run(list(args), cwd=cwd, text=True, capture_output=True)
        if check and p.returncode:
            raise ChainBlocked("CP36_COMMAND_FAILED")
        return p.stdout.strip()
    monkeypatch.setattr(cl, "run", local_run)
    monkeypatch.setattr(cl, "ROOT", tmp_path)
    return tmp_path


def merge(repo, number, task, filename):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-b", f"feature-{number}")
    target = repo / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(number))
    git(repo, "add", filename)
    git(repo, "commit", "-m", f"Native integration {number}")
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "--no-edit", "-m",
        f"Merge PR #{number} via sandbox-train\n\n[CP3.5] Verified native integration",
        f"feature-{number}")
    sha = git(repo, "rev-parse", "HEAD")
    return sha, {"number": number, "merged": True, "merge_commit_sha": sha,
        "base": {"ref": "main", "repo": {"full_name": cl.REPO}},
        "head": {"ref": f"lf/native-integration/{task}-run-{number}",
                 "repo": {"full_name": cl.REPO}}}


def chain():
    files = ["app/contract.txt", "app/backend.txt", "app/frontend.txt"]
    rows = [{"id": f"SOL-00{i}", "depends_on": [] if i == 1 else [f"SOL-00{i-1}"],
             "write_paths": [file]} for i, file in enumerate(files, 1)]
    bindings = {r["id"]: {"task_name": f"req186{area}{i}"}
                for i, (r, area) in enumerate(zip(rows,
                   ["contrato", "backend", "frontend"]), 1)}
    return {"lots": rows}, bindings


def test_req186_contract_older_than_75_commits(repo, monkeypatch):
    lots, bindings = chain()
    metadata = {}
    sha, metadata[501] = merge(repo, 501, "req186contrato1", "app/contract.txt")
    for i in range(83):
        git(repo, "commit", "--allow-empty", "-m", f"Unrelated Train event {i}")
    _, metadata[502] = merge(repo, 502, "req186backend2", "app/backend.txt")
    _, metadata[503] = merge(repo, 503, "req186frontend3", "app/frontend.txt")
    monkeypatch.setattr(cl, "api", lambda route: metadata[int(route.split("/")[-1])])
    history = cl.first_parent_merges("req-186", root=repo)
    assert len(history) == 3 and history[0][0] == sha
    assert set(cl.completed_lots(lots, bindings, history)) == {
        "SOL-001", "SOL-002", "SOL-003"}


def test_real_reverse_order_is_out_of_order(repo, monkeypatch):
    lots, bindings = chain()
    _, first = merge(repo, 502, "req186backend2", "app/backend.txt")
    _, second = merge(repo, 501, "req186contrato1", "app/contract.txt")
    monkeypatch.setattr(cl, "api", lambda route: {502: first, 501: second}
                        [int(route.split("/")[-1])])
    with pytest.raises(ChainBlocked, match="OUT_OF_ORDER_MERGE"):
        cl.completed_lots(lots, bindings, cl.first_parent_merges("req-186", root=repo))


def test_unlocatable_origin_and_limit_fail_closed(repo):
    (repo / "pilot/runs/req-186/chain_plan.json").unlink()
    with pytest.raises(ChainBlocked, match="CHAIN_HISTORY_INCOMPLETE"):
        cl.first_parent_merges("req-186", root=repo)
    (repo / "pilot/runs/req-186/chain_plan.json").write_text("{}")
    for i in range(3):
        git(repo, "commit", "--allow-empty", "-m", f"Unrelated {i}")
    with pytest.raises(ChainBlocked, match="CHAIN_HISTORY_INCOMPLETE"):
        cl.first_parent_merges("req-186", root=repo, max_commits=2)


def test_missing_expected_file_code_includes_relative_path(repo, monkeypatch):
    lots, bindings = chain()
    _, pr = merge(repo, 501, "req186contrato1", "app/contract.txt")
    monkeypatch.setattr(cl, "api", lambda _route: pr)
    real_run = cl.run
    def missing(*args, **kwargs):
        if args[:3] == ("git", "cat-file", "-e"):
            raise ChainBlocked("CP36_COMMAND_FAILED")
        return real_run(*args, **kwargs)
    monkeypatch.setattr(cl, "run", missing)
    with pytest.raises(ChainBlocked, match=r"CHAIN_EXPECTED_FILE_MISSING:app/contract.txt"):
        cl.completed_lots(lots, bindings, cl.first_parent_merges("req-186", root=repo))
