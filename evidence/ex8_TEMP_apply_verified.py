#!/usr/bin/env python3
"""ONE-SHOT EX8 verified patch integration, external helper only; never merge this script."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import os

REPO = Path.cwd()
BASE = "7614876639dba757d25e91d5fea606a5387c36e9"
PROPOSAL_COMMIT = "131fafba675917fb6efa445c0ae353f50186207f"
PROPOSAL_BLOB = "f40d0216aab99ed14f0850784b5974b34757901e"
PACK = "c409f35069345a8b686cfaf99082fe8b953ec6ac023b006fb0af4da26f36c92f"
PROPOSAL_SHA = "f1dc9d8c49fa58e93763563e9f34dd6fede1159ba3e5b9dc0e9ae3bfae9ceb97"
PREFIX="apps/time-service/src/main/java/lf/sandbox/time/reminder/"
FILES=sorted([PREFIX+x for x in ("ReminderRepository.java","InMemoryReminderRepository.java","ReminderController.java")])
TARGET_BRANCH="lf/ex8-verified-chg0035"

def run(*cmd, cwd=None, input=None, capture=False):
    p=subprocess.run(cmd, cwd=cwd or REPO,input=input,text=True,
                     capture_output=capture)
    if p.returncode:
        print("FAILED",cmd,"returncode",p.returncode, "stdout",p.stdout[-2400:] if p.stdout else "",
              "stderr",p.stderr[-2400:] if p.stderr else "",flush=True)
        raise SystemExit(p.returncode)
    return p.stdout if capture else ""

run("git","fetch","origin","main","lf/native-proposal/ex8")
assert run("git","rev-parse","origin/main",capture=True).strip()==BASE, "MAIN_DRIFT"
assert run("git","rev-parse","origin/lf/native-proposal/ex8",capture=True).strip()==PROPOSAL_COMMIT, "PROPOSAL_COMMIT_DRIFT"
raw=run("git","show","origin/lf/native-proposal/ex8:pilot/native_proposals/ex8.json",capture=True)
assert run("git","hash-object","--stdin",input=raw,capture=True).strip()==PROPOSAL_BLOB, "PROPOSAL_BLOB_DRIFT"
env=json.loads(raw)
assert env["task_pack_sha256"]==PACK and env["proposal_sha256"]==PROPOSAL_SHA
assert sorted(env["proposal"]["changed_paths"])==FILES
patch=env["proposal"]["patch"]
assert patch.count("diff --git ")==3
assert all("diff --git a/"+p+" b/"+p in patch for p in FILES)
with tempfile.TemporaryDirectory(prefix="ex8_verified_") as d:
    root=Path(d)/"source"
    run("git","worktree","add","--detach",str(root),BASE)
    assert run("git","rev-parse","HEAD",cwd=root,capture=True).strip()==BASE
    pp=Path(d)/"verified.patch"
    pp.write_text(patch,encoding="utf-8")
    run("git","apply","--check",str(pp),cwd=root)
    run("git","apply",str(pp),cwd=root)
    modified=sorted(run("git","diff","--name-only",cwd=root,capture=True).splitlines())
    assert modified==FILES, "SCOPE_DRIFT"
    assert run("git","diff","--no-ext-diff","--",*FILES,cwd=root,capture=True)==patch, "PATCH_BYTES_DRIFT"
    assert not run("git","diff","--check",cwd=root,capture=True), "PATCH_WHITESPACE"
    # Both the original verified patch and the inserted source blobs must match.
    expected={"InMemoryReminderRepository.java":"9659720",
              "ReminderController.java":"b8305a9","ReminderRepository.java":"2efbdc9"}
    for path in FILES:
        blob=run("git","hash-object",path,cwd=root,capture=True).strip()
        assert blob.startswith(expected[Path(path).name]), ("TARGET_BLOB_MISMATCH",path,blob)
        print("EX8_VERIFIED_JAVA_BLOB",Path(path).name,blob,flush=True)
    print("EX8_EXACT_VERIFIED_PATCH_APPLIED_ON_MAIN_PASS",flush=True)

    # THE NO-EDIT GATE. Do not run spotless:apply or alter any Java.
    run("mvn","-B","-q","-f","apps/time-service/pom.xml","spotless:check",cwd=root)
    print("EX8_STD_BE_05_SPOTLESS_CHECK_PASS_BEFORE_ANY_BRANCH_COMMIT",flush=True)

    run("mvn","-B","-q","-f","apps/time-service/pom.xml","package",cwd=root)
    print("EX8_MVN_PACKAGE_EXISTING_TESTS_PASS",flush=True)
    run("python3","apps/time-service/visible-tests/ex8/run_visible.py",cwd=root)
    print("EX8_VISIBLE_TEST_PASS",flush=True)
    assert sorted(run("git","diff","--name-only",cwd=root,capture=True).splitlines())==FILES

    chg={
      "schema_version":"LF_STANDARD_CHANGE_V1","change_id":"CHG-0035",
      "title":"EX8: incorporar los tres Java exactos del parche nativo verificado, Lote F",
      "change_class":"EDITORIAL",
      "trigger":{"kind":"OWNER","reference":"Paulo 2026-11-10: EX8 run 42901867465 PASS intento 1, incorporar parche 131fafb sin propuesta JSON"},
      "reason":"Integrar exactamente los tres Java del parche EX8 validado por worker-native run 42901867465, intento 1, sobre del commit 131fafba675917fb6efa445c0ae353f50186207f. El patch coincide byte a byte con propuesta SHA-256 f1dc9d8c49fa58e93763563e9f34dd6fede1159ba3e5b9dc0e9ae3bfae9ceb97 y los nuevos blobs git; no se reformatea, ni se publica pilot/native_proposals/ex8.json. Preserva REM-A..E, implementa REM-F1..F4, formato Palantir STD-BE-05 verificado con Spotless.",
      "artifacts":[],
      "affected":{"rule_ids":["STD-BE-05"],"term_ids":[],"paths":FILES+["standards/CAMBIOS.md","standards/changes/CHG-0035.json"]},
      "existing_code_impact":{"mode":"NEW_OR_MODIFIED_ONLY","baseline_ref":"standards/baseline/","expected_direction":"NON_INCREASING"},
      "security_pin_invalidation":{"invalidates":False,"affected_artifacts":[]},
      "requested_by":"agent:gpt","approved_by":"paulozterra",
      "evidence":{"pr_url":""},
      "decision_ref":"EX8 Worker native CI run 42901867465 verified PASS attempt 1. Proposal commit 131fafba675917fb6efa445c0ae353f50186207f, proposal_sha256 "+PROPOSAL_SHA+", task_pack_sha256 "+PACK+". Native verified patch artifact 13802777995. Preflight against main "+BASE+": exact git patch and three target blobs, mvn spotless:check PASS without apply, mvn package PASS and EX8 visible PASS. No new source files, protected tests or proposal JSON in PR. CANDIDATE_SANDBOX_ONLY."
    }
    path=root/"standards/changes/CHG-0035.json"
    assert not path.exists()
    path.write_text(json.dumps(chg,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    run("python3","standards/tools/changes.py","render",cwd=root)
    run("python3","standards/tools/changes.py","render","--check",cwd=root)
    run("python3","standards/tools/changes.py","check","--base","origin/main",cwd=root)
    tracked=sorted(run("git","status","--short",cwd=root,capture=True).splitlines())
    expected_final=sorted(FILES+["standards/CAMBIOS.md","standards/changes/CHG-0035.json"])
    run("git","add","--",*expected_final,cwd=root)
    staged=sorted(run("git","diff","--cached","--name-only",cwd=root,capture=True).splitlines())
    assert staged==expected_final, ("FINAL_SCOPE_DRIFT",staged)
    assert not run("git","diff","--cached","--check",cwd=root,capture=True)
    run("git","config","user.name","github-actions[bot]",cwd=root)
    run("git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com",cwd=root)
    run("git","commit","-m","CHG-0035: integrate exact EX8 native verified patch (3 Java)",cwd=root)
    sha=run("git","rev-parse","HEAD",cwd=root,capture=True).strip()
    assert run("git","rev-parse","HEAD^",cwd=root,capture=True).strip()==BASE
    print("EX8_CANDIDATE_COMMIT_SHA="+sha,flush=True)
    run("git","push","origin","HEAD:refs/heads/"+TARGET_BRANCH,cwd=root)
    print("EX8_CANDIDATE_BRANCH_PUSH_PASS",flush=True)
