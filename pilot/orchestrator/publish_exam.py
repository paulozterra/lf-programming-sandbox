#!/usr/bin/env python3
"""T31: the only way the independent examiner prepares a hidden exam.

Runs, in the examiner's private workspace and before anything is published,
the same checks the trusted Worker applies, then writes ciphertext and
metadata that are consistent by construction:

1. build the oracle from a check script, split into Worker-sized argv chunks;
2. load it with the vendored Worker loader (load_hidden_oracle and
   assert_hidden_oracle_external);
3. run it, in a clean copy of git-tracked files (as the Worker does), against
   the reference overlay (must PASS) and each mutant overlay (each must FAIL);
4. encrypt to the repository recipient, decrypt back and compare bytes;
5. write metadata whose holdout_sha256 is the plaintext SHA the Worker checks.

Any failure stops before writing to the repository. Plaintext never enters
the repository; only ciphertext and metadata do.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
CHUNK_BYTES = 4000          # Worker limit is 4096 bytes per argument.
MAX_ARGS = 64               # Worker limit on argv length.
EXEC_PREFIX = ["lf-python", "-c", "import sys;exec(''.join(sys.argv[1:]))"]


class ExamBlocked(RuntimeError):
    pass


def chunks(script: str) -> list[str]:
    out, cur = [], ""
    for ch in script:
        if len((cur + ch).encode("utf-8")) > CHUNK_BYTES:
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    if "".join(out) != script or len(out) + len(EXEC_PREFIX) > MAX_ARGS:
        raise ExamBlocked("EXAM_SCRIPT_TOO_LARGE")
    return out


def build_oracle(script: str, *, name: str, family: str, version: str,
                 timeout: int, max_output: int) -> bytes:
    oracle = {"commands": [{"argv": [*EXEC_PREFIX, *chunks(script)],
                            "max_output_bytes": max_output, "name": name,
                            "timeout_seconds": timeout}],
              "family": family, "schema_version": 1, "version": version}
    return (json.dumps(oracle, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def worker_load(raw: bytes, root: Path) -> None:
    from programming_agent_runner.worker_oracle import (
        assert_hidden_oracle_external, load_hidden_oracle)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "holdout.oracle.json"
        path.write_bytes(raw)
        try:
            oracle = load_hidden_oracle(path, hashlib.sha256(raw).hexdigest())
            assert_hidden_oracle_external(root, oracle)
        except Exception as exc:  # report the Worker's own code
            raise ExamBlocked("EXAM_WORKER_LOADER_REJECTED:" + str(exc).split(":")[0]) from None


def overlay(base: Path, files: Path, dest: Path) -> None:
    """dest = copy of base worktree with files/<repo path> laid over it."""
    for src in sorted(p for p in files.rglob("*") if p.is_file()):
        rel = src.relative_to(files)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)


def run_oracle(raw: bytes, workdir: Path, python: str) -> bool:
    for cmd in json.loads(raw)["commands"]:
        argv = list(cmd["argv"])
        if argv[0] == "lf-python":
            argv[0] = python
        try:
            result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True,
                                    timeout=cmd["timeout_seconds"])
        except subprocess.TimeoutExpired:
            return False
        if result.returncode != 0:
            return False
    return True


def clean_copy(worktree: Path, dest: Path) -> Path:
    """T31.1: like the Worker, run the oracle on git-tracked files only
    (no node_modules, build caches or other local state)."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=worktree, check=True,
                            capture_output=True).stdout.split(b"\0")
    for raw in listed:
        if not raw:
            continue
        rel = raw.decode("utf-8")
        src = worktree / rel
        if src.is_symlink() or not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    return dest


def worker_order_copy(candidate: Path, dest: Path) -> Path:
    """Copy every file of `candidate` in sorted relative-path order, like
    worker_workspace.copy_candidate_for_commands."""
    files = sorted(p.relative_to(candidate).as_posix() for p in candidate.rglob("*")
                   if p.is_file() and not p.is_symlink())
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / rel, target)
    return dest


def exercise(raw: bytes, worktree: Path, reference: Path, mutants: list[Path],
             python: str) -> dict:
    results = {}
    for label, files in [("reference", reference)] + [(m.name, m) for m in mutants]:
        with tempfile.TemporaryDirectory(prefix="lf-exam-case-") as tmp:
            # T39: same order as the Worker: base + change in a candidate, then
            # the commands workspace copied path by path in sorted order (so
            # e.g. a tracked build output gets a newer mtime than the sources).
            candidate = clean_copy(worktree, Path(tmp) / "candidate")
            overlay(candidate, files, candidate)
            case = worker_order_copy(candidate, Path(tmp) / "commands")
            results[label] = run_oracle(raw, case, python)
    if not results.get("reference"):
        raise ExamBlocked("EXAM_REFERENCE_DOES_NOT_PASS")
    survivors = sorted(k for k, ok in results.items() if k != "reference" and ok)
    if survivors:
        raise ExamBlocked("EXAM_MUTANTS_SURVIVE:" + ",".join(survivors))
    if not mutants:
        raise ExamBlocked("EXAM_WITHOUT_MUTANTS")
    return results


def encrypt_roundtrip(raw: bytes, recipient: Path, identity: Path, out: Path) -> None:
    subprocess.run(["age", "-R", str(recipient), "-o", str(out)], input=raw, check=True)
    back = subprocess.run(["age", "-d", "-i", str(identity), str(out)],
                          capture_output=True, check=True).stdout
    if back != raw:
        out.unlink(missing_ok=True)
        raise ExamBlocked("EXAM_ENCRYPTION_ROUNDTRIP_MISMATCH")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--request", required=True)
    p.add_argument("--script", type=Path, required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--name", default="holdout")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--max-output", type=int, default=8000)
    p.add_argument("--worktree", type=Path, required=True,
                   help="scratch checkout of current main used to run the exam")
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--mutants", type=Path, required=True,
                   help="directory with one overlay directory per mutant")
    p.add_argument("--identity", type=Path, required=True)
    p.add_argument("--derived-from", required=True)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--project-ref", default="lf_java")
    a = p.parse_args()
    try:
        if not TASK.fullmatch(a.task):
            raise ExamBlocked("EXAM_TASK_INVALID")
        if a.worktree.resolve() == ROOT.resolve():
            raise ExamBlocked("EXAM_WORKTREE_MUST_BE_SCRATCH")
        raw = build_oracle(a.script.read_text("utf-8"), name=a.name, family=a.family,
                           version=a.version, timeout=a.timeout, max_output=a.max_output)
        worker_load(raw, ROOT)
        mutants = sorted(d for d in a.mutants.iterdir() if d.is_dir())
        results = exercise(raw, a.worktree, a.reference, mutants, a.python)
        cipher = ROOT / "pilot/holdouts" / f"{a.task}.oracle.json.age"
        if cipher.exists():
            raise ExamBlocked("EXAM_ALREADY_PUBLISHED_USE_NEW_VERSION_PR")
        encrypt_roundtrip(raw, ROOT / "pilot/holdouts/recipient.txt", a.identity, cipher)
        meta = ROOT / "pilot/runs" / a.request / "claude_meta" / f"{a.task}.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({
            "holdout_ref": f"pilot/holdouts/{a.task}.oracle.json.age",
            "holdout_sha256": hashlib.sha256(raw).hexdigest(),
            "project_ref": a.project_ref, "written_by": "claude",
            "derived_from": a.derived_from}, indent=2, ensure_ascii=False) + "\n", "utf-8")
    except ExamBlocked as exc:
        print(str(exc))
        return 1
    print(json.dumps({"status": "EXAM_READY_TO_PUBLISH", "task": a.task,
                      "mutants_killed": len(results) - 1,
                      "holdout_sha256": hashlib.sha256(raw).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
