#!/usr/bin/env python3
"""Rebuild only a sealed exercise-3 PASS patch, then publish executable JAR.

No model invocation, no oracle access, no response content in logs.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=Path(os.environ["RUNNER_TEMP"])/"lf-worker-pilot"

def gate(reason):
    raise SystemExit("EX3_JAR_BLOCKED:"+reason)

def main():
    task=os.environ.get("PILOT_TASK")
    if task not in ("exercise-3","ex4b"):
        gate("TASK_NOT_JAR_ELIGIBLE")
    expected_id=("LF-WORKER-PILOT-REAL-003" if task=="exercise-3"
                 else "LF-WORKER-PILOT-REAL-004B")
    verified=PRIVATE/"verified-worker-receipt.json"
    visible=PRIVATE/"visible-worker-receipt.json"
    cost=PRIVATE/"public/cost.json"
    patch=PRIVATE/"worker.patch"
    if not all(p.is_file() and not p.is_symlink() for p in (verified,visible,cost,patch)):
        gate("REQUIRED_PASS_EVIDENCE_MISSING")
    v=json.loads(verified.read_text(encoding="utf-8"))
    w=json.loads(visible.read_text(encoding="utf-8"))
    price=json.loads(cost.read_text(encoding="utf-8"))
    if (v.get("status")!="PASS" or w.get("status")!="PASS"
        or v.get("task_id")!=expected_id
        or w.get("task_id")!=v["task_id"] or not v.get("patch_delivered")
        or v.get("visible_receipt_sha256")!=w.get("receipt_sha256")
        or w.get("requested_model")!="claude-sonnet-5-5"):
        gate("RECEIPT_BINDING_OR_STATUS_INVALID")
    try:
        charged=Decimal(str(price["total_estimated_usd"]))
    except (KeyError,ValueError):
        gate("ACTUAL_PRICE_MISSING")
    if not charged.is_finite() or charged<0 or charged>Decimal("0.35"):
        gate("ACTUAL_COST_EXCEEDED")
    with tempfile.TemporaryDirectory(prefix="lf-ex3-jar-") as tmp:
        dest=Path(tmp)/"source"
        subprocess.run(["git","clone","--quiet","--local","--no-hardlinks",str(ROOT),str(dest)],
                       check=True,capture_output=True,timeout=120)
        head=subprocess.run(["git","-C",str(dest),"rev-parse","HEAD"],
                            capture_output=True,text=True,check=True).stdout.strip()
        if head!=v.get("base_head_sha"):
            gate("SOURCE_HEAD_MISMATCH")
        patch_bytes=patch.read_bytes()
        if len(patch_bytes)>40000 or not patch_bytes:
            gate("PATCH_SIZE_INVALID")
        for cmd in (["git","-C",str(dest),"apply","--check","-"],
                    ["git","-C",str(dest),"apply","-"]):
            result=subprocess.run(cmd,input=patch_bytes,capture_output=True,timeout=30)
            if result.returncode!=0:
                gate("PATCH_APPLY_INVALID")
        paths=subprocess.run(["git","-C",str(dest),"status","--porcelain","-z"],
                             capture_output=True,check=True).stdout.decode().split("\0")
        changed=[row[3:] for row in paths if row]
        allowed=lambda p: (p=="apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderController.java"
                           if task=="ex4b" else
                           p=="apps/time-service/pom.xml" or p.startswith("apps/time-service/src/main/"))
        if not changed or len(changed)>(1 if task=="ex4b" else 6) or any(
                not allowed(p) for p in changed):
            gate("PATCH_SCOPE_INVALID")
        result=subprocess.run(["mvn","-B","-q","-f","apps/time-service/pom.xml","verify"],
                              cwd=dest,capture_output=True,timeout=600)
        if result.returncode!=0:
            gate("MAVEN_VERIFY_FAILED")
        candidates=sorted((dest/"apps/time-service/target").glob("time-service-*.jar"))
        candidates=[p for p in candidates if not p.name.endswith((".original",".sources.jar",".javadoc.jar"))]
        if len(candidates)!=1:
            gate("EXECUTABLE_JAR_COUNT_INVALID")
        with zipfile.ZipFile(candidates[0]) as jar:
            if not any(x.startswith("BOOT-INF/classes/lf/sandbox/time/") for x in jar.namelist()):
                gate("EXECUTABLE_JAR_CONTENT_INVALID")
        public=PRIVATE/"public"
        public.mkdir(mode=0o700,exist_ok=True)
        output=public/"time-service.jar"
        if output.exists():
            gate("JAR_ALREADY_EXISTS")
        shutil.copyfile(candidates[0],output)
        output.chmod(0o600)
    print("EX3_VERIFIED_JAR_READY")

if __name__=="__main__":
    main()
