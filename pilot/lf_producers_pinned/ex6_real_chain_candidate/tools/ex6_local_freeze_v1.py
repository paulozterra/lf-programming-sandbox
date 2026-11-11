"""Actual EX6 verified-patch blobs into disposable Git and 5 immutable-ref attacks.

Only local temporary Git repositories. Never pushes to GitHub or alters a
production branch. This is an enforcement experiment, not production freeze.
"""
from __future__ import annotations
import hashlib
import subprocess
import tempfile
import sys
from pathlib import Path

from ex6_source_truth_v1 import source_truth, _reader, EVIDENCE, git_blob_sha
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pg13_freeze_candidate" / "tools"))
from pg13_disposable_git_mutation_test_v1 import (
    HOOK, git, require, read_ref, reject_and_preserve
)
N="912c4ad9ea71f48edbd1ac58089441f9ed2c3449"

def exact_patch_blobs():
    truth=source_truth()
    patch=_reader.read_bundle(EVIDENCE)["worker.patch"].decode("utf-8")
    parts=["diff --git "+x for x in patch.split("diff --git ")[1:]]
    expected={x["path"]:x["git_blob_oid"] for x in truth["hunks"]}
    if len(parts)!=3:
        raise AssertionError("EX6_LOCAL_FREEZE_PATCH_COUNT_INVALID")
    out={}
    for part in parts:
        header=part.splitlines()[0].split()
        path=header[2].removeprefix("a/")
        if path not in expected or header[3]!="b/"+path:
            raise AssertionError("EX6_LOCAL_FREEZE_UNAUTHORIZED_HUNK")
        hunk_index=next((i for i,l in enumerate(part.splitlines(keepends=True))
                         if l.startswith("@@ ")),None)
        if hunk_index is None:
            raise AssertionError("EX6_LOCAL_FREEZE_HUNK_NOT_FOUND")
        lines=part.splitlines(keepends=True)[hunk_index+1:]
        if not lines or any(not l.startswith("+") for l in lines):
            raise AssertionError("EX6_LOCAL_FREEZE_HUNK_NOT_ADDED_ONLY")
        data="".join(x[1:] for x in lines).encode()
        if git_blob_sha(data)!=expected[path]:
            raise AssertionError("EX6_LOCAL_FREEZE_GIT_BLOB_DRIFT")
        out[path]=data
    if set(out)!=set(expected):
        raise AssertionError("EX6_LOCAL_FREEZE_PATH_SET_MISMATCH")
    return out

def local_freeze_and_attacks():
    blobs=exact_patch_blobs()
    with tempfile.TemporaryDirectory(prefix="lf_ex6_local_freeze_") as temp:
        root=Path(temp)
        bare=root/"remote.git"
        work=root/"checkout"
        require(git("init","--bare",str(bare),cwd=root),"bare local")
        require(git("init",str(work),cwd=root),"checkout local")
        require(git("remote","add","origin",str(bare),cwd=work),"local remote")
        for path,data in blobs.items():
            dest=work/path
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
            actual=require(git("hash-object",str(dest),cwd=work),"blob check")
            if actual != git_blob_sha(data):
                raise AssertionError("EX6_LOCAL_FREEZE_BYTES_NOT_IDENTICAL")
        require(git("add",".",cwd=work),"stage exact three real files")
        tree=require(git("write-tree",cwd=work),"tree exact")
        def local_commit(tree_oid,message,parent=None):
            args=["-c","user.name=LF local EX6","-c","user.email=ex6@example.invalid",
                  "commit-tree",tree_oid]
            if parent:
                args+=["-p",parent]
            return require(git(*args,"-m",message,cwd=work),"commit local")
        frozen=local_commit(tree,"EX6 three true Java blobs local-only")
        branch_ref="refs/heads/frozen"
        require(git("branch","frozen",frozen,cwd=work),"branch local")
        require(git("push","origin","frozen:"+branch_ref,cwd=work),"push initial local")
        tag_ref="refs/tags/frozen/"+N
        require(git("-c","user.name=LF local EX6","-c","user.email=ex6@example.invalid",
                    "tag","-a","frozen/"+N,"-m","EX6 original N local test",frozen,
                    cwd=work),"tag local")
        require(git("push","origin",tag_ref,cwd=work),"push tag local")
        tag_oid=read_ref(root,bare,tag_ref)
        if read_ref(root,bare,branch_ref)!=frozen:
            raise AssertionError("EX6_LOCAL_FREEZE_INITIAL_IDENTITY_DRIFT")
        hook=bare/"hooks"/"pre-receive"
        hook.write_text(HOOK,encoding="utf-8")
        hook.chmod(0o755)
        (work/"mutation-probe.txt").write_text("mutate\n")
        require(git("add","mutation-probe.txt",cwd=work),"add adversarial")
        new_tree=require(git("write-tree",cwd=work),"new tree")
        forward=local_commit(new_tree,"forward",frozen)
        divergent=local_commit(new_tree,"divergent")
        ops={
            "FORCE_PUSH":lambda:git("push","--force","origin",divergent+":"+branch_ref,cwd=work),
            "NORMAL_FAST_FORWARD":lambda:git("push","origin",forward+":"+branch_ref,cwd=work),
            "DELETE":lambda:git("push","origin",":"+branch_ref,cwd=work),
            "RECREATE_DIFFERENT_SHA":lambda:git("push","origin",forward+":refs/tags/frozen/"+forward,cwd=work),
            "DELETE_ANNOTATED_TAG":lambda:git("push","origin",":"+tag_ref,cwd=work),
        }
        for key,attack in ops.items():
            reject_and_preserve(key,attack,root,bare,branch_ref,frozen,tag_ref,tag_oid)
        print("PG13_EX6_GIT_LOCAL_BLOB_IDENTITY_PASS")
        print("PG13_EX6_FROZEN_MUTATION_ATTACKS_BLOCKED=5")
        print("PG13_EX6_PRODUCTION_FREEZE_VERIFIED=FALSE")
        return {"source_commit":N,"local_tree_oid":tree,
                "local_frozen_commit":frozen,"local_tag_oid":tag_oid,
                "blocked_mutation_count":5,
                "production_authority":False,
                "only_original_verified_ex6_blobs":True}
if __name__=="__main__":
    print(local_freeze_and_attacks())
