"""Pinned npm lockfile contract: positive, drift and malformed negatives."""
import json
import subprocess
import tempfile
from pathlib import Path
from pg03_stack_source_v1 import resolve_stack_semantics, StackSourceBlocked

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    def git(*args):
        return subprocess.check_output(["git","-C",td,*args],text=True,stderr=subprocess.DEVNULL).strip()
    git("init","-q")
    git("config","user.email","tester@example.invalid")
    git("config","user.name","Test")
    manifest={"name":"fixture","dependencies":{"typescript":"^5.0.0"}}
    lock={"name":"fixture","lockfileVersion":3,"packages":{"":{"dependencies":{"typescript":"^5.0.0"}}}}
    (root/"package.json").write_text(json.dumps(manifest))
    (root/"package-lock.json").write_text(json.dumps(lock))
    def commit(label):
        git("add","package.json","package-lock.json")
        git("commit","-qm",label)
        return git("rev-parse","HEAD")
    ok_sha=commit("valid")
    files=["package.json","package-lock.json"]
    out=resolve_stack_semantics(root,"fixture/repo",ok_sha,files)
    assert [p["ecosystem"] for p in out["parsed_profiles"]]==["NODE_LOCK","NODE"]
    assert out["authority"] is False and out["stack_profile_verified"] is False
    (root/"package-lock.json").write_text(json.dumps({"name":"fixture","lockfileVersion":3,"packages":{"":{"dependencies":{"typescript":"^1.0.0"}}}}))
    assert resolve_stack_semantics(root,"fixture/repo",ok_sha,files)==out
    def reject(sha,reason):
        try: resolve_stack_semantics(root,"fixture/repo",sha,files)
        except StackSourceBlocked as e: assert str(e)==reason,(str(e),reason)
        else: raise AssertionError(reason)
    drift=commit("drift")
    reject(drift,"NODE_LOCK_DECLARATION_DRIFT")
    (root/"package-lock.json").write_text(json.dumps({"name":"fixture","lockfileVersion":3,"packages":{}}))
    bad=commit("missing root")
    reject(bad,"NODE_LOCK_INVALID")
    (root/"package-lock.json").write_text(json.dumps({"name":"fixture","lockfileVersion":"3","packages":{"":{}}}))
    bad_version=commit("invalid version")
    reject(bad_version,"NODE_LOCK_INVALID")
print("PG03_C1_NPM_LOCK_PASS pinned=1 tamper=1 drift=1 invalid=2 authority=0")
