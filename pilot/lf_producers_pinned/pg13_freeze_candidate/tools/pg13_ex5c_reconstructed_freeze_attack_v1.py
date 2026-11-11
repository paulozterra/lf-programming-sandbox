"""EX5C REAL-SANDBOX local Git freeze; NO productive Git writes.

Imports the existing PG13 immutable-ref attack helper. Rebuilds the *actual*
18 Git blobs from the fixed EX5C bundle; produces the exact subtree OID, then
creates an isolated local commit over that subtree (not the LF or sandbox
original root commit). Attempts five mutation operations against bare refs.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "pg07_worker_candidate/tools"))
from pg07_real_worker_evidence_adapter_v1 import (
    load_real_bundle, decode, SUBTREE, RealEvidenceBlocked
)
from pg13_disposable_git_mutation_test_v1 import (
    HOOK, git, require, read_ref, reject_and_preserve
)

FIXTURE = ROOT / "pg07_worker_candidate/fixtures/lf-evidence-bundle-v1.json"
FIXED_SHA = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"


def local_freeze_and_attacks() -> dict:
    data = load_real_bundle(FIXTURE, FIXED_SHA)
    assert data["production_authority"] is False
    with tempfile.TemporaryDirectory(prefix="lf_ex5c_exact_freeze_") as tmp:
        root = Path(tmp)
        work = root / "checkout"
        bare = root / "remote.git"
        require(git("init", "--bare", str(bare), cwd=root), "initialize bare")
        require(git("init", str(work), cwd=root), "initialize disposable work")
        require(git("remote", "add", "origin", str(bare), cwd=work), "add local remote")

        for entry in data["files"]:
            relative = entry["path"].removeprefix("apps/time-service/")
            # Path/scope + OID already independently validated by load_real_bundle.
            assert relative != entry["path"] and not relative.startswith("/") and ".." not in Path(relative).parts
            dest = work / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(decode(entry["content_base64"]))
        require(git("add", ".", cwd=work), "add reconstructed blobs")
        rebuilt = require(git("write-tree", cwd=work), "write exact subtree")
        if rebuilt != SUBTREE:
            raise AssertionError("PG13_EX5C_REAL_SUBTREE_MISMATCH")

        def commit_tree(tree: str, label: str, parent: str | None = None) -> str:
            args = ["-c", "user.name=LF local only", "-c", "user.email=lf@example.invalid",
                    "commit-tree", tree]
            if parent:
                args += ["-p", parent]
            args += ["-m", label]
            return require(git(*args, cwd=work), "make "+label)

        frozen = commit_tree(rebuilt, "EX5C exact real subtree — local candidate")
        branch_ref = "refs/heads/frozen"
        require(git("branch", "frozen", frozen, cwd=work), "branch frozen")
        require(git("push", "origin", "frozen:"+branch_ref, cwd=work), "push initial frozen")
        tag_ref = "refs/tags/frozen/" + rebuilt
        require(git("-c", "user.name=LF local only", "-c", "user.email=lf@example.invalid",
                    "tag", "-a", "frozen/" + rebuilt,
                    "-m", "EX5C reconstructed subtree OID " + rebuilt, frozen,
                    cwd=work), "tag exact subtree")
        require(git("push", "origin", tag_ref, cwd=work), "push original freeze tag")
        tag_oid = read_ref(root, bare, tag_ref)
        if read_ref(root, bare, branch_ref) != frozen:
            raise AssertionError("PG13_EX5C_FROZEN_LOCAL_COMMIT_MISMATCH")

        hook = bare / "hooks/pre-receive"
        hook.write_text(HOOK, encoding="utf-8")
        hook.chmod(0o755)
        require(git("checkout", "frozen", cwd=work), "checkout frozen")
        (work / "mutation-probe.txt").write_text("forward\n", encoding="utf-8")
        require(git("add", "mutation-probe.txt", cwd=work), "stage forward")
        forward_tree = require(git("write-tree", cwd=work), "tree forward")
        forward = commit_tree(forward_tree, "normal forward", frozen)
        divergent = commit_tree(forward_tree, "divergent")

        changes = {
            "FORCE_PUSH": lambda: git("push", "--force", "origin",
                                      divergent + ":" + branch_ref, cwd=work),
            "NORMAL_FAST_FORWARD": lambda: git("push", "origin",
                                                forward + ":" + branch_ref, cwd=work),
            "DELETE": lambda: git("push", "origin", ":" + branch_ref, cwd=work),
            "RECREATE_DIFFERENT_SHA": lambda: git(
                "push", "origin", forward + ":refs/tags/frozen/" + forward, cwd=work),
            "DELETE_ANNOTATED_TAG": lambda: git(
                "push", "origin", ":" + tag_ref, cwd=work)
        }
        for label, operation in changes.items():
            reject_and_preserve(label, operation, root, bare,
                                branch_ref, frozen, tag_ref, tag_oid)
        print("PG13_EX5C_REAL_BLOB_TREE_REBUILD_PASS")
        print("PG13_EX5C_REBUILT_SUBTREE_SHA=" + rebuilt)
        print("PG13_EX5C_ORIGINAL_ROOT_COMMIT_RECONSTRUCTED=FALSE")
        print("PG13_EX5C_PRODUCTION_AUTHORITY=FALSE")
        return {"subtree_oid": rebuilt, "local_frozen_commit": frozen,
                "local_tag_oid": tag_oid, "blocked_mutation_count": len(changes),
                "production_authority": False}


if __name__ == "__main__":
    local_freeze_and_attacks()
