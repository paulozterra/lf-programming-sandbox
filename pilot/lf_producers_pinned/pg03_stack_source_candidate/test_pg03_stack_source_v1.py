"""PG-03_C1 offline exact-object readback; synthetic git repository only."""
import subprocess
import tempfile
from pathlib import Path
from pg03_stack_source_v1 import resolve_stack, StackSourceBlocked

with tempfile.TemporaryDirectory() as td:
    p=Path(td)
    def git(*args):
        return subprocess.check_output(["git","-C",td,*args],stderr=subprocess.DEVNULL,text=True).strip()
    git("init","-q")
    git("config","user.email","qualifier@example.invalid")
    git("config","user.name","Qualification Fixture")
    (p/"pom.xml").write_text("<project><modelVersion>4.0.0</modelVersion></project>")
    git("add","pom.xml")
    git("commit","-qm","fixture")
    sha=git("rev-parse","HEAD")
    out=resolve_stack(p,"fixture/repository",sha,["pom.xml"])
    assert out["status"]=="CANDIDATE_NOT_ADMITTED"
    assert out["sources"][0]["path"]=="pom.xml" and len(out["sources"][0]["sha256"])==64
    assert out["stack_profile_verified"] is False
    # Working tree mutation cannot alter exact-commit evidence.
    (p/"pom.xml").write_text("tampered")
    assert resolve_stack(p,"fixture/repository",sha,["pom.xml"])==out
    def blocked(commit,paths,reason):
        try: resolve_stack(p,"fixture/repository",commit,paths)
        except StackSourceBlocked as exc: assert str(exc)==reason,(str(exc),reason)
        else: raise AssertionError(reason)
    blocked("b"*40,["pom.xml"],"EXACT_GIT_OBJECT_UNAVAILABLE")
    blocked(sha,["../secret"],"UNSUPPORTED_STACK_SOURCE_PATH")
    blocked(sha,["pom.xml","pom.xml"],"SOURCE_MANIFEST_INVALID")
    blocked(sha,["package.json"],"EXACT_GIT_OBJECT_UNAVAILABLE")
    blocked("bad",["pom.xml"],"TARGET_COMMIT_INVALID")
print("PG03_C1_EXACT_GIT_SOURCE_PASS pinned=1 tamper=1 negatives=5 authority=0")
