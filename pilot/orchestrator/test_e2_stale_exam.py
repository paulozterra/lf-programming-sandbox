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
    (tmp_path / "pilot/holdouts").mkdir(parents=True, exist_ok=True)
    (tmp_path / f"pilot/holdouts/{task}.oracle.json.age").write_bytes(b"\x00\xffsynthetic-age-" + str(n).encode("ascii"))
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


def _pr(n, ref, sha="a" * 40, merged=None, created="2026-11-25T00:00:00Z"):
    return {"number": n, "head": {"ref": ref, "sha": sha}, "merged_at": merged, "created_at": created}


def test_failed_rehearsal_on_latest_registration_is_detected():
    pulls = [_pr(1, "lf/native-registration/t1-" + "a" * 12, sha="b" * 40, created="1"),
             _pr(2, "lf/native-registration/t1-" + "c" * 12, sha="c" * 40, created="2")]
    checks = {"c" * 40: [{"id": 9, "name": "rehearse", "status": "completed",
                          "conclusion": "failure", "started_at": "x"}]}
    found = se.rehearsal_failure(lambda: pulls, lambda sha: checks.get(sha, []), "t1")
    assert found == {"pr": 2, "head_sha": "c" * 40, "job_id": 9}
    checks["c" * 40][0]["conclusion"] = "success"
    assert se.rehearsal_failure(lambda: pulls, lambda sha: checks.get(sha, []), "t1") is None
    assert se.rehearsal_failure(lambda: [], lambda sha: [], "t1") is None


def test_rehearsal_retires_are_capped(tmp_path):
    git = _repo(tmp_path)
    task, dep = "r1backend2", "r1contrato1"

    def retire():
        # Match Train's merge topology; first-parent deletion must be visible.
        git("checkout", "-qb", "retire")
        git("rm", "-q", f"pilot/holdouts/{task}.oracle.json.age")
        git("commit", "-qm", "retire exam")
        git("checkout", "-q", "main")
        git("merge", "--no-ff", "-qm", "Train retirement", "retire")
        git("branch", "-D", "retire")

    _exam(git, tmp_path, task, 1)
    _integrate(git, tmp_path, dep)
    retire()
    assert se.retire_count(tmp_path, task, [dep]) == 0
    _exam(git, tmp_path, task, 2)
    retire()
    assert se.retire_count(tmp_path, task, [dep]) == 1
    _exam(git, tmp_path, task, 3)
    assert se.retire_count(tmp_path, task, [dep]) == 1 < se.MAX_REHEARSAL_RETIRES
    retire()
    assert se.retire_count(tmp_path, task, [dep]) == 2 >= se.MAX_REHEARSAL_RETIRES
    # With no proof of staleness, all retirements consume the budget.
    assert se.retire_count(tmp_path, task, []) == 3
    assert se.retire_count(tmp_path, "other", []) == 0


def test_retire_budget_rejects_shallow_history(tmp_path):
    git = _repo(tmp_path)
    clone = tmp_path.parent / "shallow"
    subprocess.run(["git", "clone", "--depth=1", tmp_path.as_uri(), str(clone)],
                   check=True, capture_output=True)
    with pytest.raises(ValueError, match="EXAM_RETIRE_HISTORY_INCOMPLETE"):
        se.retire_count(clone, "r1backend2", [])


def test_exam_retired_only_after_a_deletion(tmp_path):
    git = _repo(tmp_path)
    assert not se.exam_retired(tmp_path, "r1backend2")          # never existed
    _exam(git, tmp_path, "r1backend2", 1)
    assert not se.exam_retired(tmp_path, "r1backend2")          # present
    git("rm", "-q", "pilot/holdouts/r1backend2.oracle.json.age"); git("commit", "-qm", "retire")
    assert se.exam_retired(tmp_path, "r1backend2")


@pytest.mark.parametrize("rows, expected", [
    ([], None),
    ([{"number": 42, "state": "open", "head": {"ref": "lf/exam-retire/t1-abc"}}], 42),
    ([{"number": 43, "state": "open", "head": {"ref": "lf/exam-retire/t2-abc"}}], None),
])
def test_pending_retire_pr(rows, expected):
    assert se.pending_retire_pr(lambda: rows, "t1") == expected


def test_pending_retire_closed():
    rows = [{"number": 42, "state": "closed", "head": {"ref": "lf/exam-retire/t1-abc"}}]
    assert se.pending_retire_pr(lambda: [p for p in rows if p["state"] == "open"], "t1") is None
    with pytest.raises(ValueError, match="RETIRE_PR_LIST_INVALID"):
        se.pending_retire_pr(lambda: rows, "t1")


def test_pending_retire_api_error():
    def unavailable():
        raise OSError("API unavailable")
    with pytest.raises(OSError):
        se.pending_retire_pr(unavailable, "t1")


def _signal(monkeypatch, rows):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import chain_lots as cl
    calls = []
    monkeypatch.setattr(cl, "listed_exam_requests", lambda: rows)
    monkeypatch.setattr(cl, "run", lambda *a, **k: calls.append(a) or "")
    return cl, calls


def test_retired_exam_signals_retry_once_on_its_open_request(monkeypatch):
    rows = [{"number": 9, "state": "closed", "title": "EXAM_REQUEST: r1backend2", "labels": []},
            {"number": 10, "state": "open", "title": "EXAM_REQUEST: r1backend22", "labels": []},
            {"number": 11, "state": "open", "title": "EXAM_REQUEST: r1backend2",
             "labels": [{"name": "exam-request"}]}]
    cl, calls = _signal(monkeypatch, rows)
    assert cl.signal_exam_retry("r1backend2") == "EXAM_RETRY_SIGNALED"
    assert calls == [("gh", "issue", "edit", "11", "--repo", cl.REPO, "--add-label", "exam-retry")]


@pytest.mark.parametrize("label", ["exam-retry", "examiner-working"])
def test_retry_not_resignaled_while_pending_or_claimed(monkeypatch, label):
    rows = [{"number": 11, "state": "open", "title": "EXAM_REQUEST: r1backend2",
             "labels": [{"name": label}]}]
    cl, calls = _signal(monkeypatch, rows)
    assert cl.signal_exam_retry("r1backend2") == "EXAM_RETRY_ALREADY_SIGNALED" and not calls


def test_retry_signal_is_best_effort(monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import chain_lots as cl
    def boom():
        raise cl.ChainBlocked("EXAM_REQUEST_LIST_UNTRUSTED")
    monkeypatch.setattr(cl, "listed_exam_requests", boom)
    assert cl.signal_exam_retry("r1backend2") == "EXAM_RETRY_SIGNAL_FAILED"
