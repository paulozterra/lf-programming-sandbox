"""Synthetic exact-commit Maven and Node parsing, candidate only."""
import json
import subprocess
import tempfile
from pathlib import Path
from pg03_stack_source_v1 import resolve_stack_semantics, StackSourceBlocked

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    def git(*args):
        return subprocess.check_output(["git","-C",tmp,*args],text=True,stderr=subprocess.DEVNULL).strip()
    git("init","-q")
    git("config","user.email","tester@example.invalid")
    git("config","user.name","Test")
    (root/"pom.xml").write_text('<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion></project>')
    (root/"package.json").write_text(json.dumps({"name":"fixture","dependencies":{"angular":"^20.0.0"}}))
    git("add","pom.xml","package.json")
    git("commit","-qm","valid")
    good=git("rev-parse","HEAD")
    out=resolve_stack_semantics(root,"example/stack",good,["pom.xml","package.json"])
    assert len(out["parsed_profiles"])==2
    assert out["stack_profile_verified"] is False and out["authority"] is False
    assert next(x for x in out["parsed_profiles"] if x["ecosystem"]=="NODE")["declared_dependencies"]["dependencies"]["angular"]=="^20.0.0"
    (root/"pom.xml").write_text("<project>changed</project>")
    assert resolve_stack_semantics(root,"example/stack",good,["pom.xml","package.json"])==out
    git("add","pom.xml")
    git("commit","-qm","invalid-maven")
    invalid_maven=git("rev-parse","HEAD")
    try: resolve_stack_semantics(root,"example/stack",invalid_maven,["pom.xml"])
    except StackSourceBlocked as e: assert str(e)=="MAVEN_MODEL_INVALID"
    else: raise AssertionError("invalid model accepted")
    (root/"package.json").write_text('{"name":"fixture","dependencies":{"x":false}}')
    git("add","package.json")
    git("commit","-qm","invalid-node")
    invalid_node=git("rev-parse","HEAD")
    try: resolve_stack_semantics(root,"example/stack",invalid_node,["package.json"])
    except StackSourceBlocked as e: assert str(e)=="NODE_DEPENDENCIES_INVALID"
    else: raise AssertionError("invalid deps accepted")
    try: resolve_stack_semantics(root,"example/stack",good,["yarn.lock"])
    except StackSourceBlocked as e: assert str(e)=="EXACT_GIT_OBJECT_UNAVAILABLE"
    else: raise AssertionError("missing lockfile accepted")
print("PG03_C1_STACK_SEMANTICS_PASS parsed=2 pinned_tamper=1 negatives=3 authority=0")
