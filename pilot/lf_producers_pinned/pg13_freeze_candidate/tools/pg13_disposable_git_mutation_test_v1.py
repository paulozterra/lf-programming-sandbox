"""Real immutable-ref attack suite, only in an auto-cleaned temporary Git repo.

A pre-receive hook rejects all future creates, updates and deletes on
refs/heads/frozen and refs/tags/frozen/*. A freeze is established before
installing the hook. No productive Git repository is touched.
"""
import subprocess
import tempfile
from pathlib import Path

HOOK = """#!/bin/sh
while read old new ref; do
  case "$ref" in
    refs/heads/frozen|refs/tags/frozen/*)
      echo "LF_FROZEN_REF_IMMUTABLE: $ref" >&2
      exit 1
      ;;
  esac
done
exit 0
"""

def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, text=True,
                          capture_output=True, timeout=20)

def require(proc, label):
    if proc.returncode != 0:
        raise AssertionError(f"{label}: {proc.stderr.strip()}")
    return proc.stdout.strip()

def commit(work, text, label):
    (work / "feature.txt").write_text(text, encoding="utf-8")
    require(git("add", "feature.txt", cwd=work), "add "+label)
    require(git("-c", "user.name=LF Test", "-c", "user.email=lf@example.invalid",
                "commit", "-m", label, cwd=work), "commit "+label)
    return require(git("rev-parse", "HEAD", cwd=work), "head "+label)

def read_ref(root, bare, ref):
    return require(git("--git-dir", str(bare), "rev-parse", "--verify", ref,
                       cwd=root), "read ref")

def reject_and_preserve(label, operation, root, bare, branch_ref, frozen_sha, tag_ref, tag_oid):
    proc = operation()
    if proc.returncode == 0:
        raise AssertionError(label+"_UNEXPECTEDLY_ACCEPTED")
    if "LF_FROZEN_REF_IMMUTABLE" not in proc.stderr:
        raise AssertionError(label+"_NOT_REJECTED_BY_FREEZE_HOOK: "+proc.stderr)
    if read_ref(root, bare, branch_ref) != frozen_sha:
        raise AssertionError(label+"_FROZEN_BRANCH_CHANGED")
    if read_ref(root, bare, tag_ref) != tag_oid:
        raise AssertionError(label+"_FROZEN_TAG_CHANGED")
    print("PG13_C3_"+label+"_BLOCK=PASS")
    print("PG13_C3_"+label+"_COMMAND_EXIT_NONZERO=TRUE")
    print("PG13_C3_"+label+"_REFS_UNCHANGED=TRUE")

def main():
    with tempfile.TemporaryDirectory(prefix="lf_pg13_frozen_git_") as temporary:
        root=Path(temporary)
        bare=root/"remote.git"
        work=root/"work"
        branch_ref="refs/heads/frozen"
        require(git("init", "--bare", str(bare), cwd=root), "init bare")
        require(git("--git-dir", str(bare), "config", "receive.denyNonFastForwards",
                    "true", cwd=root), "deny non-FF")
        require(git("--git-dir", str(bare), "config", "receive.denyDeletes",
                    "true", cwd=root), "deny deletes")
        require(git("init", "-b", "frozen", str(work), cwd=root), "init work")
        require(git("remote", "add", "origin", str(bare), cwd=work), "remote")
        base_sha=commit(work, "base\n", "base")
        require(git("push", "-u", "origin", "frozen", cwd=work), "push base")
        frozen_sha=commit(work, "frozen\n", "freeze original")
        require(git("push", "origin", "frozen", cwd=work), "push frozen")
        tag_ref="refs/tags/frozen/"+frozen_sha
        require(git("-c", "user.name=LF Test", "-c", "user.email=lf@example.invalid",
                    "tag", "-a", "frozen/"+frozen_sha, "-m", "Immutable freeze record",
                    frozen_sha, cwd=work), "tag frozen")
        require(git("push", "origin", tag_ref, cwd=work), "push frozen tag")
        tag_oid=read_ref(root, bare, tag_ref)
        if read_ref(root, bare, branch_ref)!=frozen_sha:
            raise AssertionError("FREEZE_INITIAL_SHA_MISMATCH")
        # Install immutability protection after the initial frozen refs exist.
        hook_path=bare/"hooks"/"pre-receive"
        hook_path.write_text(HOOK, encoding="utf-8")
        hook_path.chmod(0o755)
        # 1. Force push a divergent commit.
        require(git("reset", "--hard", base_sha, cwd=work), "reset base")
        divergent_sha=commit(work, "divergent\n", "divergent mutation")
        if divergent_sha==frozen_sha:raise AssertionError("DIVERGENT_SHA_EQUAL_FROZEN")
        reject_and_preserve("FORCE_PUSH",
            lambda:git("push", "--force", "origin", "HEAD:"+branch_ref, cwd=work),
            root, bare, branch_ref, frozen_sha, tag_ref, tag_oid)
        # 2. Normal fast-forward, previously accepted without the hook.
        require(git("reset", "--hard", frozen_sha, cwd=work), "restore frozen")
        forward_sha=commit(work, "legitimate-looking appended commit\n", "forward mutation")
        if forward_sha==frozen_sha:raise AssertionError("FORWARD_SHA_EQUAL_FROZEN")
        reject_and_preserve("NORMAL_FAST_FORWARD",
            lambda:git("push", "origin", "HEAD:"+branch_ref, cwd=work),
            root, bare, branch_ref, frozen_sha, tag_ref, tag_oid)
        # 3. Delete frozen branch.
        reject_and_preserve("DELETE",
            lambda:git("push", "origin", ":"+branch_ref, cwd=work),
            root, bare, branch_ref, frozen_sha, tag_ref, tag_oid)
        # 4. Create an alternate ref under the frozen namespace, different SHA.
        # Deleting/re-creating the original ref is impossible because deletion blocks.
        replacement_ref="refs/tags/frozen/"+forward_sha
        if git("--git-dir", str(bare), "show-ref", "--verify", "--quiet",
               replacement_ref, cwd=root).returncode==0:
            raise AssertionError("REPLACEMENT_REF_ALREADY_EXISTS")
        reject_and_preserve("RECREATE_DIFFERENT_SHA",
            lambda:git("push", "origin", forward_sha+":"+replacement_ref, cwd=work),
            root, bare, branch_ref, frozen_sha, tag_ref, tag_oid)
        if git("--git-dir", str(bare), "show-ref", "--verify", "--quiet",
               replacement_ref, cwd=root).returncode==0:
            raise AssertionError("REPLACEMENT_REF_CREATED")
        # Extra: annotated freeze tag cannot be deleted either.
        reject_and_preserve("DELETE_ANNOTATED_TAG",
            lambda:git("push", "origin", ":"+tag_ref, cwd=work),
            root, bare, branch_ref, frozen_sha, tag_ref, tag_oid)
        print("PG13_C3_FROZEN_COMMIT_SHA="+frozen_sha)
        print("PG13_C3_FROZEN_TAG_OBJECT_SHA="+tag_oid)
        print("PG13_C3_RECEIVE_DENY_DELETES=TRUE")
        print("PG13_C3_PRE_RECEIVE_IMMUTABILITY_HOOK=TRUE")
        print("PG13_C3_PRODUCTION_FREEZE_VERIFIED=FALSE")

if __name__=="__main__":
    main()
