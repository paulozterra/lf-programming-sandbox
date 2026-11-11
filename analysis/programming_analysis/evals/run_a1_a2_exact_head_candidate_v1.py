"""Run the five narrow A1/A2 candidate suites against one exact, clean Git HEAD.

Source-only harness. Requires an externally isolated, unprivileged runner.
Neither this script nor a PASS certifies producer/judge independence, CURRENT
business evidence, host authorization, or A3 admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SUITES = (
    ("A1_REGISTERED_SKILL", "skills/programming_analysis/steps/a1/evals",
     "test_governed_step_homology_v1.py", 20),
    ("A1_JUDGE_POLICY_GAP", "skills/programming_analysis/steps/a1/evals",
     "test_judge_policy_gap_readback_v1.py", 14),
    ("A2_LF_SCOPE", "skills/programming_analysis/steps/a2/evals",
     "test_business_semantic_scope_l1_l2_20261108.py", 21),
    ("A2_GOLDEN_SEMANTIC", "skills/programming_analysis/steps/a2/evals",
     "test_semantic_golden_preview_integration_v1.py", 9),
    ("A2P_RESEARCH_POLICY", "skills/programming_analysis/steps/a2/evals",
     "test_a2_p_research_policy_boundary_v1.py", 10),
)
SHA = re.compile(r"^[a-f0-9]{40}$")


def git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True,
                       check=False, timeout=15)
    if p.returncode:
        raise ValueError("GIT_READBACK_FAILED:" + " ".join(args))
    return p.stdout.strip()


def preflight(root: Path, expected: str, output: Path) -> dict:
    if not SHA.fullmatch(expected):
        raise ValueError("EXPECTED_HEAD_SHA_INVALID")
    if not (root / ".git").exists():
        raise ValueError("EXACT_GIT_CHECKOUT_REQUIRED")
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("GIT_TOPLEVEL_MISMATCH")
    actual = git(root, "rev-parse", "HEAD")
    if actual != expected:
        raise ValueError("EXACT_HEAD_MISMATCH:" + actual)
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("DIRTY_WORKTREE_REJECTED")
    if output == root or root in output.parents:
        raise ValueError("RECEIPT_DIR_MUST_BE_OUTSIDE_REPOSITORY")
    blobs = {}
    for _, folder, filename, _ in SUITES:
        relative = folder + "/" + filename
        f = (root / relative).resolve()
        if root not in f.parents or not f.is_file():
            raise ValueError("REQUIRED_SUITE_MISSING:" + relative)
        b = f.read_bytes()
        local_blob = hashlib.sha1(b"blob " + str(len(b)).encode()
                                  + b"\x00" + b).hexdigest()
        tracked = git(root, "ls-tree", "HEAD", "--", relative)
        if not tracked or len(tracked.split()) < 3 or tracked.split()[2] != local_blob:
            raise ValueError("SOURCE_BLOB_DRIFT:" + relative)
        blobs[relative] = local_blob
    return {"source_commit": actual, "test_file_git_blobs": blobs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.repo_root.resolve(), args.receipt_dir.resolve()
    receipt = {"schema_version": "ANALYSIS_A1_A2_EXACT_HEAD_TEST_REPLAY_V1",
               "source_commit_expected": args.expected_head,
               "status": "BLOCKED", "blocking_codes": [],
               "source_attested": False, "independent_judge_verified": False,
               "a3_allowed": False, "runtime_qualified": False, "suites": []}
    try:
        receipt.update(preflight(root, args.expected_head, output))
        import jsonschema  # noqa: F401; dependency is required by existing validators
    except (ValueError, OSError, subprocess.SubprocessError, ImportError) as exc:
        receipt["blocking_codes"] = [str(exc).split(":")[0][:100]]
        print(json.dumps(receipt, sort_keys=True))
        return 2
    output.mkdir(parents=True, exist_ok=True)
    for label, folder, filename, expected_count in SUITES:
        cmd = [sys.executable, "-I", "-B", "-m", "unittest", "discover",
               "-s", folder, "-p", filename, "-v"]
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                                  check=False, timeout=120, env={
                                      "PATH": os.environ.get("PATH", ""),
                                      "HOME": os.environ.get("HOME", "/tmp"),
                                      "PYTHONDONTWRITEBYTECODE": "1",
                                      "PYTHONNOUSERSITE": "1",
                                  })
            log = proc.stdout + "\n" + proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            log = "TIMEOUT:" + str(exc)
            exit_code = 124
        log_path = output / (label.lower() + ".log")
        log_path.write_text(log, encoding="utf-8")
        count_match = re.search(r"Ran (\d+) tests? in ", log)
        observed = int(count_match.group(1)) if count_match else None
        good = exit_code == 0 and observed == expected_count and bool(
            re.search(r"(?m)^OK\s*$", log))
        receipt["suites"].append({
            "name": label, "test_pattern": filename,
            "expected_count": expected_count, "observed_count": observed,
            "exit_code": exit_code, "passed": good,
            "output_sha256": hashlib.sha256(log.encode("utf-8")).hexdigest(),
            "log_path": str(log_path),
        })
    all_pass = all(x["passed"] for x in receipt["suites"])
    receipt["status"] = ("LOCAL_TEST_REPLAY_PASS_UNATTESTED" if all_pass
                         else "LOCAL_TEST_REPLAY_FAIL_OR_INCOMPLETE")
    receipt["blocking_codes"] = [] if all_pass else ["SPECIALIZED_TESTS_NOT_ALL_PASS"]
    path = output / "receipt.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"],
                      "source_commit": receipt["source_commit"],
                      "suites": receipt["suites"],
                      "receipt_path": str(path),
                      "a3_allowed": False}, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
