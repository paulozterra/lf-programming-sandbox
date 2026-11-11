"""CP3.5 offline contract/adversarial tests; never download real native artifacts."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_verified_integration import (
    IntegrationBlocked, extract_exact_zip, verify_run, allowed_paths,
    validate_patch_against_repo, chg_payload,
)


def zipped(name, raw):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, raw)
    return output.getvalue()


def test_only_single_named_patch_and_no_zip_slip():
    raw = b"diff --git a/a b/a\n"
    assert extract_exact_zip(zipped("worker.patch", raw), "worker.patch", 1000) == raw
    for name in ("../worker.patch", "other.patch", "/worker.patch"):
        with pytest.raises(IntegrationBlocked, match="ARTIFACT_INVENTORY_INVALID"):
            extract_exact_zip(zipped(name, raw), "worker.patch", 1000)
    with pytest.raises(IntegrationBlocked, match="ARTIFACT_SIZE_INVALID"):
        extract_exact_zip(zipped("worker.patch", b"A" * 101), "worker.patch", 100)


def test_require_successful_trusted_native_run():
    run = {"id": 42, "conclusion": "success", "status": "completed",
           "run_attempt": 1, "event": "workflow_run", "head_branch": "main",
           "repository": {"full_name": "paulozterra/lf-programming-sandbox"},
           "path": ".github/workflows/worker-native.yml@refs/heads/main"}
    jobs = {"jobs": [{"name": "native", "conclusion": "success"}]}
    verify_run(run, jobs, 42)
    for key, bad in [("id", 43), ("conclusion", "failure"),
                     ("head_branch", "lf/native-proposal/fake"),
                     ("event", "pull_request"), ("run_attempt", 2),
                     ("path", ".github/workflows/untrusted.yml")]:
        with pytest.raises(IntegrationBlocked, match="NATIVE_RUN_UNTRUSTED"):
            verify_run({**run, key: bad}, jobs, 42)
    with pytest.raises(IntegrationBlocked, match="NATIVE_JOB_NOT_SUCCESS"):
        verify_run(run, {"jobs": [{"name": "native", "conclusion": "failure"}]}, 42)


def test_no_glob_vendor_or_forged_scope():
    base = {"task_spec": {"base_head_sha": "a" * 40,
                          "write_path_patterns": ["apps/time-service/src/main/java/x/Test.java"]}}
    assert allowed_paths(base) == ("a" * 40, {"apps/time-service/src/main/java/x/Test.java"})
    for bad in ["vendor/private.java", "pilot/holdouts/oracle.json.age",
                "apps/**", "../foo.java", ".github/workflows/push.yml",
                "frontend/src/app/../../passwd"]:
        with pytest.raises(IntegrationBlocked, match="TASK_SCOPE_UNSAFE"):
            allowed_paths({"task_spec": {**base["task_spec"],
                                         "write_path_patterns": [bad]}})


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def test_exact_patch_bytes_and_stale_base_rejected(tmp_path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "user.name", "CP35")
    target = tmp_path / "apps/time-service/src/main/java/x/Test.java"
    target.parent.mkdir(parents=True)
    target.write_text("class Test {}\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD")
    target.write_text("class Test { int n; }\n")
    patch = subprocess.check_output(["git", "-C", str(tmp_path), "diff"])
    git(tmp_path, "checkout", "--", ".")
    result = validate_patch_against_repo(tmp_path, patch, base,
                                         {"apps/time-service/src/main/java/x/Test.java"})
    assert result["apps/time-service/src/main/java/x/Test.java"] == hashlib.sha256(
        b"class Test { int n; }\n").hexdigest()
    git(tmp_path, "reset", "--hard", "HEAD")
    target.write_text("class Test { String s; }\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "other change")
    with pytest.raises(IntegrationBlocked, match="TASK_BASE_STALE"):
        validate_patch_against_repo(tmp_path, patch, base,
                                    {"apps/time-service/src/main/java/x/Test.java"})


def test_chg_declares_no_authority():
    chg = chg_payload(58, "candidate", 999, "c" * 64, ["db/migration/V001__test.sql"])
    assert chg["change_id"] == "CHG-0058"
    assert chg["approved_by"] == "paulozterra"
    assert chg["evidence"]["pr_url"] == ""
    assert chg["security_pin_invalidation"]["invalidates"] is False
