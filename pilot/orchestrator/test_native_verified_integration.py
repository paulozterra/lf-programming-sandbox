"""CP3.5 offline contract/adversarial tests; never download real native artifacts."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_verified_integration import (
    IntegrationBlocked, extract_exact_zip, extract_exact_zip_bundle, verify_run, allowed_paths,
    validate_patch_against_repo, chg_payload, command, existing_branch_sha,
    verify_existing_branch_tree, resume_prepared_branch,
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


def test_visible_cost_feedback_bundle_accepts_exact_three_members():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("status.json", "feedback.json", "cost.json"):
            archive.writestr(name, b'{"ok":true}')
    required = {n: 1000 for n in ("status.json", "feedback.json", "cost.json")}
    actual = extract_exact_zip_bundle(stream.getvalue(), required)
    assert set(actual) == set(required)
    assert all(value == b'{"ok":true}' for value in actual.values())


@pytest.mark.parametrize("extra", ["../evil.json", "receipt-extra.json", "status.json"])
def test_visible_cost_feedback_bundle_rejects_extra_duplicate_and_traversal(extra):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("status.json", "feedback.json", "cost.json"):
            archive.writestr(name, b'{"ok":true}')
        archive.writestr(extra, b"attack")
    required = {n: 1000 for n in ("status.json", "feedback.json", "cost.json")}
    with pytest.raises(IntegrationBlocked, match="ARTIFACT_INVENTORY_INVALID"):
        extract_exact_zip_bundle(stream.getvalue(), required)


def test_visible_cost_feedback_bundle_rejects_missing_and_oversized():
    required = {n: 10 for n in ("status.json", "feedback.json", "cost.json")}
    with pytest.raises(IntegrationBlocked, match="ARTIFACT_INVENTORY_INVALID"):
        extract_exact_zip_bundle(zipped("status.json", b'{}'), required)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in required:
            archive.writestr(name, b"x" * (11 if name == "feedback.json" else 2))
    with pytest.raises(IntegrationBlocked, match="ARTIFACT_SIZE_INVALID"):
        extract_exact_zip_bundle(stream.getvalue(), required)



def test_command_stderr_redacts_token_and_caps_length(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "github_pat_PRIVATE_TOKEN_SHOULD_NOT_LEAK")
    result = subprocess.CompletedProcess(
        args=["gh", "pr", "create"], returncode=1, stdout=b"",
        stderr=(b"permission denied github_pat_PRIVATE_TOKEN_SHOULD_NOT_LEAK "
                + b"X" * 4000))
    with patch("native_verified_integration.subprocess.run", return_value=result):
        with pytest.raises(IntegrationBlocked) as failure:
            command(["gh", "pr", "create"])
    assert "CP35_COMMAND_FAILED:gh:permission denied [REDACTED]" in str(failure.value)
    assert "PRIVATE_TOKEN" not in str(failure.value)
    assert len(str(failure.value)) < 850


def _resume_fixture(tmp_path):
    """A bare local remote, an old main, a newly advanced main, and one draft branch."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True,
                   capture_output=True)
    checkout = tmp_path / "repo"
    checkout.mkdir()
    git(checkout, "init", "-b", "main")
    git(checkout, "config", "user.email", "ci@example.invalid")
    git(checkout, "config", "user.name", "CP35")
    git(checkout, "remote", "add", "origin", str(bare))
    (checkout / "a.txt").write_text("base\\n")
    git(checkout, "add", ".")
    git(checkout, "commit", "-m", "original main")
    git(checkout, "push", "-u", "origin", "main")
    git(checkout, "switch", "-c", "lf/native-integration/example-run-42")
    (checkout / "a.txt").write_text("generated\\n")
    git(checkout, "add", ".")
    git(checkout, "commit", "-m", "generated patch")
    branch_sha = git(checkout, "rev-parse", "HEAD")
    expected_tree = git(checkout, "rev-parse", "HEAD^{tree}")
    git(checkout, "push", "-u", "origin", "lf/native-integration/example-run-42")
    git(checkout, "switch", "main")
    (checkout / "unrelated.txt").write_text("new CHG after old branch\\n")
    git(checkout, "add", ".")
    git(checkout, "commit", "-m", "new unrelated main change")
    return checkout, branch_sha, expected_tree


def test_resume_existing_branch_identical_tree(tmp_path):
    root, remote_sha, tree = _resume_fixture(tmp_path)
    actual = existing_branch_sha(root, "lf/native-integration/example-run-42")
    assert actual == remote_sha
    verify_existing_branch_tree(root, actual, tree)


def test_resume_existing_branch_different_tree_is_blocked(tmp_path):
    root, remote_sha, tree = _resume_fixture(tmp_path)
    actual = existing_branch_sha(root, "lf/native-integration/example-run-42")
    assert actual == remote_sha
    other = git(root, "rev-parse", "HEAD^{tree}")
    assert other != tree
    with pytest.raises(IntegrationBlocked, match="CP35_BRANCH_EXISTS_DIFFERENT"):
        verify_existing_branch_tree(root, actual, other)
