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
    IntegrationBlocked, extract_exact_zip, extract_exact_zip_bundle, verify_run, allowed_paths,
    validate_patch_against_repo, chg_payload, existing_integration_branch,
    command,
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


def test_resume_existing_identical_branch_tree(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    repo.mkdir()
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "offline@example.invalid")
    git(repo, "config", "user.name", "CP35")
    (repo / "file.txt").write_text("base\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "base")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    branch = "lf/native-integration/p4data-run-42"
    git(repo, "switch", "-c", branch)
    (repo / "file.txt").write_text("verified patch\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "native patch first attempt")
    prior_sha = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    git(repo, "push", "origin", branch)
    # Replay with the same tree and a different commit identity.
    git(repo, "switch", "main")
    git(repo, "switch", "-c", "retry")
    (repo / "file.txt").write_text("verified patch\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "native patch replay")
    assert git(repo, "rev-parse", "HEAD") != prior_sha
    assert git(repo, "rev-parse", "HEAD^{tree}") == tree
    assert existing_integration_branch(repo, branch, tree) == prior_sha


def test_resume_existing_different_branch_blocks(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    repo.mkdir()
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "offline@example.invalid")
    git(repo, "config", "user.name", "CP35")
    (repo / "file.txt").write_text("base\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "base")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    branch = "lf/native-integration/p4data-run-42"
    git(repo, "switch", "-c", branch)
    (repo / "file.txt").write_text("untrusted remote tree\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "different")
    git(repo, "push", "origin", branch)
    expected = git(repo, "rev-parse", "main^{tree}")
    with pytest.raises(IntegrationBlocked, match="CP35_BRANCH_EXISTS_DIFFERENT"):
        existing_integration_branch(repo, branch, expected)


def test_command_failure_stderr_is_bounded_and_redacts_tokens(monkeypatch):
    import os
    secret = "ghs_" + "x" * 40
    monkeypatch.setenv("GH_TOKEN", secret)
    completed = subprocess.CompletedProcess(
        ["gh"], 1, b"", ("gh: " + secret + " permission denied " + "Z" * 4000).encode())
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)
    with pytest.raises(IntegrationBlocked) as error:
        command(["gh", "pr", "create"])
    reason = str(error.value)
    assert "CP35_COMMAND_FAILED:gh:stderr=" in reason
    assert secret not in reason
    assert "[REDACTED]" in reason
    assert len(reason) <= 1260
    with pytest.raises(IntegrationBlocked) as git_error:
        command(["git", "push"])
    assert "CP35_COMMAND_FAILED:git:stderr=" in str(git_error.value)

def test_confirm_class_empty_detected_classes_accepts_editorial(tmp_path):
    from unittest.mock import patch as mocked
    from native_verified_integration import confirm_class_after_commit
    chg = tmp_path / "standards/changes/CHG-9999.json"
    chg.parent.mkdir(parents=True)
    chg.write_text(json.dumps({"change_class": "ADDITIVE"}))
    output = json.dumps({"findings": [{"reason_code": "CHANGE_CLASS_MISMATCH"}],
                         "detected_class": []}).encode()
    results = [subprocess.CompletedProcess(["python3"], 1, output, b""),
               subprocess.CompletedProcess(["python3"], 0, b"{}", b"")]
    with (mocked("native_verified_integration.subprocess.run", side_effect=results) as run,
          mocked("native_verified_integration.command", return_value=b"") as command):
        confirm_class_after_commit(tmp_path, chg)
    assert json.loads(chg.read_text())["change_class"] == "EDITORIAL"
    assert run.call_count == 2
    assert command.call_count == 3


def test_confirm_class_rejects_ambiguous_detected_classes(tmp_path):
    from unittest.mock import patch as mocked
    from native_verified_integration import confirm_class_after_commit
    chg = tmp_path / "standards/changes/CHG-9999.json"
    chg.parent.mkdir(parents=True)
    chg.write_text(json.dumps({"change_class": "ADDITIVE"}))
    output = json.dumps({"findings": [{"reason_code": "CHANGE_CLASS_MISMATCH"}],
                         "detected_class": ["ADDITIVE", "EDITORIAL"]}).encode()
    with mocked("native_verified_integration.subprocess.run",
                return_value=subprocess.CompletedProcess(["python3"], 1, output, b"")):
        with pytest.raises(IntegrationBlocked, match="CP35_C9_CHECK_FAILED"):
            confirm_class_after_commit(tmp_path, chg)
