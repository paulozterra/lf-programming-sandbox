"""T41: a registered file may change only through verified, Train-merged lineage."""
import hashlib
import subprocess
from pathlib import Path

import pytest

from pilot.orchestrator import reuse_assessment as ra

REL = "svc/Auth.java"
BRANCH = "lf/native-integration/req9backend2-run-123"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


def write(root, text, msg):
    (root / REL).parent.mkdir(parents=True, exist_ok=True)
    (root / REL).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    entry = write(tmp_path, "v1\n", "f5 integration")
    return tmp_path, entry


def row(entry):
    return {"merge_sha": entry, "files": [{"path": REL, "sha256": hashlib.sha256(b"v1\n").hexdigest()}]}


def train_merge(root, text, number=7):
    git(root, "checkout", "-q", "-b", "feat")
    write(root, text, "integration commit")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "feat", "-m", f"Merge PR #{number} via sandbox-train")
    git(root, "branch", "-q", "-D", "feat")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def test_unchanged_file_passes(repo):
    root, entry = repo
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert ra._verified_context(root, row(entry))[0]["path"] == REL


def test_train_merged_extension_is_accepted(repo):
    root, entry = repo
    train_merge(root, "v1\nv2\n")
    ctx = ra._verified_context(root, row(entry))
    assert ctx[0]["sha256"] == hashlib.sha256(b"v1\nv2\n").hexdigest()


def test_direct_commit_on_main_still_drifts(repo):
    root, entry = repo
    write(root, "hacked\n", "direct edit")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(ra.ReuseBlocked, match="REGISTRY_SHA_DRIFT"):
        ra._verified_context(root, row(entry))


def test_pending_integration_pr_only_with_its_branch(repo, monkeypatch):
    root, entry = repo
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "-b", BRANCH)
    write(root, "v1\nv2\n", "CP3.5 integration")
    monkeypatch.delenv("LF_PENDING_INTEGRATION_BRANCH", raising=False)
    with pytest.raises(ra.ReuseBlocked, match="REGISTRY_SHA_DRIFT"):
        ra._verified_context(root, row(entry))
    monkeypatch.setenv("LF_PENDING_INTEGRATION_BRANCH", "feat/anything")
    with pytest.raises(ra.ReuseBlocked, match="REGISTRY_SHA_DRIFT"):
        ra._verified_context(root, row(entry))
    monkeypatch.setenv("LF_PENDING_INTEGRATION_BRANCH", BRANCH)
    assert ra._verified_context(root, row(entry))


def test_train_merge_then_later_direct_edit_drifts(repo):
    root, entry = repo
    train_merge(root, "v1\nv2\n")
    write(root, "v1\nv2\nhack\n", "direct edit")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(ra.ReuseBlocked, match="REGISTRY_SHA_DRIFT"):
        ra._verified_context(root, row(entry))
