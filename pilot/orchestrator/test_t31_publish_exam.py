import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_exam as pe  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BIG = "x = 1\n" + "# filler line to exceed one Worker argument\n" * 200 + "print('HOLDOUT_PASS')\n"


def test_chunks_respect_worker_argument_limit():
    parts = pe.chunks(BIG)
    assert len(parts) > 1 and "".join(parts) == BIG
    assert all(len(p.encode()) <= 4096 for p in parts)


def test_worker_loader_accepts_built_oracle():
    raw = pe.build_oracle(BIG, name="holdout", family="f", version="v1",
                          timeout=60, max_output=8000)
    pe.worker_load(raw, ROOT)


def test_worker_loader_rejects_single_oversized_argument():
    # The exact defect of req186frontend3 v1: whole script in one argument.
    raw = json.dumps({"commands": [{"argv": [*pe.EXEC_PREFIX, BIG],
                      "max_output_bytes": 8000, "name": "holdout",
                      "timeout_seconds": 60}], "family": "f",
                      "schema_version": 1, "version": "v1"}).encode()
    with pytest.raises(pe.ExamBlocked, match="EXAM_WORKER_LOADER_REJECTED"):
        pe.worker_load(raw, ROOT)


def test_worker_loader_rejects_probable_secret_in_oracle_chunk():
    # Benign synthetic assignment, deliberately long enough to trip the
    # vendor's secret scanner; no real credential is used.
    raw = pe.build_oracle('password=abcdefghijklmnop\\nfail("EXAM_A")\\n',
                          name="holdout", family="f", version="v1",
                          timeout=30, max_output=8000)
    with pytest.raises(pe.ExamBlocked, match="EXAM_WORKER_LOADER_REJECTED"):
        pe.worker_load(raw, ROOT)


def _case(tmp_path):
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    (work / "src/value.txt").write_text("0")
    import subprocess
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    script = ("import sys\n"
              "v=open('src/value.txt').read().strip()\n"
              "sys.exit(0 if v=='42' else 1)\n")
    raw = pe.build_oracle(script, name="holdout", family="f", version="v1",
                          timeout=30, max_output=8000)
    ref = tmp_path / "ref/src"
    ref.mkdir(parents=True)
    (ref / "value.txt").write_text("42")
    return work, raw, tmp_path / "ref"


def test_reference_passes_and_mutants_must_fail(tmp_path):
    work, raw, ref = _case(tmp_path)
    muts = tmp_path / "mut"
    (muts / "off_by_one/src").mkdir(parents=True)
    (muts / "off_by_one/src/value.txt").write_text("41")
    result = pe.exercise(raw, work, ref, sorted(muts.iterdir()), sys.executable)
    assert result == {"reference": True, "off_by_one": False}
    assert (work / "src/value.txt").read_text() == "0"  # worktree untouched


def test_oracle_runs_without_untracked_local_state(tmp_path):
    # The req186frontend3 v3 defect: the exam relied on local node_modules,
    # which the Worker's clean command workspace does not have.
    work, _, ref = _case(tmp_path)
    (work / "node_modules").mkdir()
    (work / "node_modules/dep.txt").write_text("installed locally only")
    script = ("import os,sys\n"
              "sys.exit(0 if os.path.exists('node_modules/dep.txt') else 1)\n")
    raw = pe.build_oracle(script, name="holdout", family="f", version="v1",
                          timeout=30, max_output=8000)
    with pytest.raises(pe.ExamBlocked, match="EXAM_REFERENCE_DOES_NOT_PASS"):
        pe.exercise(raw, work, ref, [], sys.executable)


def test_surviving_mutant_blocks(tmp_path):
    work, raw, ref = _case(tmp_path)
    muts = tmp_path / "mut"
    (muts / "same/src").mkdir(parents=True)
    (muts / "same/src/value.txt").write_text("42")
    with pytest.raises(pe.ExamBlocked, match="EXAM_MUTANTS_SURVIVE:same"):
        pe.exercise(raw, work, ref, sorted(muts.iterdir()), sys.executable)


def test_failing_reference_blocks(tmp_path):
    work, raw, _ = _case(tmp_path)
    bad = tmp_path / "bad/src"
    bad.mkdir(parents=True)
    (bad / "value.txt").write_text("7")
    with pytest.raises(pe.ExamBlocked, match="EXAM_REFERENCE_DOES_NOT_PASS"):
        pe.exercise(raw, work, tmp_path / "bad", [], sys.executable)


@pytest.mark.skipif(shutil.which("age") is None or shutil.which("age-keygen") is None,
                    reason="age not installed")
def test_encrypt_roundtrip(tmp_path):
    import subprocess
    key = tmp_path / "key.txt"
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    pub = subprocess.run(["age-keygen", "-y", str(key)], check=True,
                         capture_output=True, text=True).stdout
    (tmp_path / "recipient.txt").write_text(pub)
    out = tmp_path / "x.age"
    pe.encrypt_roundtrip(b"{}\n", tmp_path / "recipient.txt", key, out)
    assert out.is_file()


def test_exam_preflight_rejects_missing_fail_codes_and_asserts():
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_NO_FAIL_CODES"):
        pe.lint_script("print('untraceable')\n")
    pe.lint_script('fail("EXAM_A")\n')
    with pytest.raises(pe.ExamBlocked, match="EXAM_LINT_ASSERT"):
        pe.lint_script('fail("EXAM_A")\nassert True\n')
    # Assertions nested in a function are still exam assertions.
    with pytest.raises(pe.ExamBlocked, match="EXAM_LINT_ASSERT"):
        pe.lint_script('def exam():\n    assert True\nfail("EXAM_A")\n')


def test_exam_timeout_uses_worker_validator_without_duplicate_limit():
    pe.lint_timeout(300)
    with pytest.raises(pe.ExamBlocked, match="EXAM_LINT_TIMEOUT"):
        pe.lint_timeout(901)
    with pytest.raises(pe.ExamBlocked, match="EXAM_LINT_TIMEOUT"):
        pe.lint_timeout(0)


def _scope_case(tmp_path, monkeypatch):
    storage = tmp_path / "pilot/runs"
    folder = storage / "req-9"
    folder.mkdir(parents=True)
    (folder / "lots.json").write_text(json.dumps({
        "lots": [{"id": "SOL-001", "write_paths": ["src/value.txt"]},
                 {"id": "SOL-002", "write_paths": ["src/other.txt"]}],
    }))
    (folder / "chain_plan.json").write_text(json.dumps({
        "bindings": [{"lot_id": "SOL-001", "task_name": "req9frontend1"}],
    }))
    monkeypatch.setattr(pe, "storage_path", lambda kind, root=None: storage)
    ref = tmp_path / "reference"
    ref.mkdir()
    mutants = tmp_path / "mutants"
    mutants.mkdir()
    case = mutants / "changed"
    case.mkdir()
    (ref / "src").mkdir()
    (case / "src").mkdir()
    (ref / "src/value.txt").write_text("reference")
    (case / "src/value.txt").write_text("mutant")
    return ref, case


def test_exam_reference_and_mutant_scope_checked_before_build(tmp_path, monkeypatch):
    ref, mutant = _scope_case(tmp_path, monkeypatch)
    pe.lint_overlay_scope(tmp_path, "req-9", "req9frontend1", ref, [mutant])
    (ref / "src/other.txt").write_text("outside lot")
    with pytest.raises(pe.ExamBlocked, match="EXAM_REFERENCE_OUT_OF_SCOPE"):
        pe.lint_overlay_scope(tmp_path, "req-9", "req9frontend1", ref, [mutant])
    (ref / "src/other.txt").unlink()
    (mutant / "src/other.txt").write_text("outside lot")
    with pytest.raises(pe.ExamBlocked, match="EXAM_REFERENCE_OUT_OF_SCOPE"):
        pe.lint_overlay_scope(tmp_path, "req-9", "req9frontend1", ref, [mutant])
    with pytest.raises(pe.ExamBlocked, match="EXAM_REFERENCE_OUT_OF_SCOPE"):
        pe.lint_overlay_scope(tmp_path, "req-9", "wrongtask", ref, [mutant])


def test_main_worker_loader_precedes_reference_and_mutant_compilation(
        tmp_path, monkeypatch, capsys):
    work = tmp_path / "scratch"
    work.mkdir()
    script = tmp_path / "check.py"
    script.write_text('fail("EXAM_A")\n')
    ref = tmp_path / "reference"
    ref.mkdir()
    mutants = tmp_path / "mutants"
    mutants.mkdir()
    trace = tmp_path / "trace.json"
    trace.write_text('{"EXAM_A": "env:build"}')
    calls = []
    def reject_at_loader(raw, root):
        calls.append("worker_load")
        raise pe.ExamBlocked("EXAM_WORKER_LOADER_REJECTED:fixture")
    from pilot.orchestrator.lifecycle_test_support import fake_api
    monkeypatch.setattr(pe, "lifecycle_api", fake_api({}))
    monkeypatch.setattr("pilot.orchestrator.request_lifecycle.request_for_task", lambda *a, **k: "req-9")
    monkeypatch.setattr(pe, "worker_load", reject_at_loader)
    monkeypatch.setattr(pe, "exercise",
                        lambda *args: pytest.fail("exercise must not run"))
    monkeypatch.setattr(sys, "argv", [
        "publish_exam.py", "--task", "req9frontend1", "--request", "req-9",
        "--script", str(script), "--family", "f", "--version", "v1",
        "--worktree", str(work), "--reference", str(ref),
        "--mutants", str(mutants), "--trace", str(trace),
        "--derived-from", "test",
    ])
    assert pe.main() == 1
    assert calls == ["worker_load"]
    assert "EXAM_WORKER_LOADER_REJECTED" in capsys.readouterr().out


def test_reference_must_pass_the_lots_visible_commands(tmp_path, monkeypatch):
    import subprocess as _sp
    work = tmp_path / "work"
    work.mkdir()
    _sp.run(["git", "init", "-q"], cwd=work, check=True)
    (work / "base.txt").write_text("base")
    _sp.run(["git", "add", "."], cwd=work, check=True)
    ref = tmp_path / "ref"
    (ref / "src").mkdir(parents=True)
    (ref / "src/ok.txt").write_text("ok")
    folder = tmp_path / "runs/req-1/templates"
    folder.mkdir(parents=True)
    check = ("import pathlib,sys; sys.exit(0 if pathlib.Path('src/ok.txt').exists() else 1)")
    folder.joinpath("t1.task.json").write_text(json.dumps({"task_spec": {"acceptance_commands": [
        {"name": "visible-ok", "argv": ["lf-python", "-c", check], "timeout_seconds": 30}]}}))
    monkeypatch.setattr(pe, "storage_path", lambda key, root: tmp_path / "runs")
    pe.visible_preflight(tmp_path, "req-1", "t1", work, ref, sys.executable)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(pe.ExamBlocked, match="EXAM_REFERENCE_FAILS_VISIBLE:visible-ok"):
        pe.visible_preflight(tmp_path, "req-1", "t1", work, empty, sys.executable)


def test_preflight_adds_the_standards_command_of_backend_lots(tmp_path, monkeypatch):
    folder = tmp_path / "req-1"
    folder.mkdir()
    (folder / "chain_plan.json").write_text(json.dumps({"bindings": [
        {"task_name": "t1", "lot_id": "L1"}, {"task_name": "t2", "lot_id": "L2"}]}))
    (folder / "lots.json").write_text(json.dumps({"lots": [
        {"id": "L1", "area": "BACKEND"}, {"id": "L2", "area": "FRONTEND"}]}))
    names = [c["name"] for c in pe.standards_commands(folder, "t1", [])]
    assert names == ["std-be-05-spotless-check"]
    assert pe.standards_commands(folder, "t2", []) == []
    assert pe.standards_commands(folder, "unknown", []) == []
    already = pe.standards_commands(folder, "t1", [])
    assert pe.standards_commands(folder, "t1", already) == []
