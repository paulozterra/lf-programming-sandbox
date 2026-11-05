#!/usr/bin/env python3
"""Offline task-specific holdout and scope admission. No API key or model.

Never substitute another task's hash, never manufacture a missing holdout digest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CATALOG=Path(__file__).with_name("tasks.json")
SPEC="standards/tools/MIGRATIONS_SPEC.md"
SHA=re.compile(r"^[0-9a-f]{64}$")
TASKS=("exercise-1","exercise-2")
EX1_SHA="979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821"
EX2_SHA="44f75fa89fa6974cdcecc43bb2c2669d73eb4bf45fbebb3ec0f2308fce3551ee"
SPEC_SHA="b699c77f46df4c1be31865d3568ee5c1f2673f6b0cfbe1745bba60d7b068251c"

class TaskBlocked(ValueError):
    pass

def block(code):
    raise TaskBlocked(code)

def select(task_name:str,*,require_holdout:bool=True)->dict:
    if task_name not in TASKS:
        block("PILOT_TASK_NOT_ALLOWED")
    data=json.loads(CATALOG.read_text(encoding="utf-8"))
    if (data.get("schema_version")!="LF_WORKER_PILOT_TASK_CATALOG_V1"
        or data.get("allowed_tasks")!=list(TASKS)
        or set(data.get("tasks",{}))!=set(TASKS)):
        block("PILOT_TASK_CATALOG_INVALID")
    task=data["tasks"][task_name]
    expected_keys={"task_id","objective","context_path_patterns","write_path_patterns",
                   "protected_path_patterns","acceptance_commands","holdout_sha256",
                   "spec_path","spec_sha256","source_precondition"}
    if not isinstance(task,dict) or set(task)!=expected_keys:
        block("PILOT_TASK_FIELDS_INVALID")
    if task["task_id"]!="LF-WORKER-PILOT-REAL-"+("001" if task_name=="exercise-1" else "002"):
        block("PILOT_TASK_ID_INVALID")
    if not isinstance(task["objective"],str) or not task["objective"].strip():
        block("PILOT_OBJECTIVE_MISSING")
    if task["protected_path_patterns"]!=["standards/tests/**"]:
        block("PILOT_PROTECTED_SCOPE_DRIFT")
    if task_name=="exercise-1":
        if (task["write_path_patterns"]!=["standards/tools/checks.py"]
            or task["context_path_patterns"]!=["standards/tools/checks.py"]
            or task["spec_path"] is not None or task["spec_sha256"] is not None
            or task["holdout_sha256"]!=EX1_SHA):
            block("PILOT_EXERCISE1_SCOPE_DRIFT")
    else:
        if (task["write_path_patterns"]!=["standards/tools/migrations.py","standards/tools/checks.py"]
            or task["context_path_patterns"]!=[
                SPEC,"standards/tools/checks.py","standards/tests/test_migrations.py"]
            or task["spec_path"]!=SPEC or task["spec_sha256"]!=SPEC_SHA
            or ("NORMATIVE SPEC SHA256="+SPEC_SHA) not in task["objective"]):
            block("PILOT_EXERCISE2_SCOPE_DRIFT")
        if task["holdout_sha256"]!=EX2_SHA or task["holdout_sha256"]==EX1_SHA:
            block("PILOT_EXERCISE2_HOLDOUT_SHA_DRIFT")
        p=ROOT/SPEC
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=SPEC_SHA:
            block("PILOT_MIGRATIONS_SPEC_SHA_DRIFT")
    checks=task["acceptance_commands"]
    if not isinstance(checks,list) or len(checks)!=1 or not isinstance(checks[0],dict):
        block("PILOT_ACCEPTANCE_INVALID")
    if (checks[0].get("argv",[])[:3]!=["python3","-m","unittest"]
        or not isinstance(checks[0].get("timeout_seconds"),int)
        or not isinstance(checks[0].get("max_output_bytes"),int)):
        block("PILOT_ACCEPTANCE_INVALID")
    pre=task["source_precondition"]
    if not isinstance(pre,dict) or pre.get("path") not in task["write_path_patterns"]:
        block("PILOT_SOURCE_PRECONDITION_INVALID")
    if task_name=="exercise-2" and pre!={"kind":"NEW_FILE_ABSENT","path":"standards/tools/migrations.py"}:
        block("PILOT_SOURCE_PRECONDITION_INVALID")
    digest=task["holdout_sha256"]
    if require_holdout and (not isinstance(digest,str) or not SHA.fullmatch(digest)):
        block("PILOT_HOLDOUT_SHA_UNREGISTERED:"+task_name)
    if digest is not None and (not isinstance(digest,str) or not SHA.fullmatch(digest)):
        block("PILOT_HOLDOUT_SHA_INVALID")
    return task

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--task",required=True,choices=TASKS)
    p.add_argument("--github-output",type=Path)
    a=p.parse_args()
    try:
        task=select(a.task,require_holdout=True)
    except TaskBlocked as e:
        print("BLOCK "+str(e))
        raise SystemExit(1)
    if a.github_output:
        with a.github_output.open("a",encoding="utf-8") as f:
            f.write("sha256="+task["holdout_sha256"]+"\n")
    print("PILOT_TASK_SHA_REGISTERED task="+a.task)
if __name__=="__main__":
    main()
