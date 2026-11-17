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
