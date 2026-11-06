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
TASKS=("exercise-1","exercise-2","exercise-3","ex4a","ex4b","ex5c")
EX1_SHA="979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821"
EX2_SHA="44f75fa89fa6974cdcecc43bb2c2669d73eb4bf45fbebb3ec0f2308fce3551ee"
SPEC_SHA="b699c77f46df4c1be31865d3568ee5c1f2673f6b0cfbe1745bba60d7b068251c"
EX3_SPEC="apps/time-service/TIME_SERVICE_SPEC.md"
EX3_SPEC_SHA="70cb7e3f2678ff70e2de54cfbea2d7d305e54d6308c2155c3728907183e8ee26"
EX4_SPEC="apps/time-service/REMINDERS_SPEC.md"
EX4_SPEC_SHA="dbcb41edebc7f1a195b01c9242d08f0c33e5d280aab4dff39e50d88220a4184b"
EX4_SHA={"ex4a":"cd0e9d7fc73aa92280b162e8c0f3f79d98cd7046b5626737666df97080f2af54",
         "ex4b":"8df8ec9858e8dd0078e955b285bac110becc781b55280b17edd9b811d44a900c"}
EX5_SHA="2bf9c94f0c6db7bd660af7096b61cdb63715f0933ac24985c8d7e5b973d930a8"
EX5_SPEC_SHA="45f06d002dd7152f88bc9a3332eb3f3b6c10a2c8773e2cb7b0beeadf61810d00"
REMINDER="apps/time-service/src/main/java/lf/sandbox/time/reminder/"

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
    expected_keys={"task_id","objective","write_path_patterns",
                   "protected_path_patterns","acceptance_commands","holdout_sha256",
                   "spec_path","spec_sha256","source_precondition"}
    if task_name!="ex5c":
        expected_keys.add("context_path_patterns")
    else:
        expected_keys.add("spec_paths")
    if not isinstance(task,dict) or set(task)!=expected_keys:
        block("PILOT_TASK_FIELDS_INVALID")
    if task["task_id"]!="LF-WORKER-PILOT-REAL-"+{"exercise-1":"001","exercise-2":"002","exercise-3":"003","ex4a":"004A","ex4b":"004B","ex5c":"005C"}[task_name]:
        block("PILOT_TASK_ID_INVALID")
    if not isinstance(task["objective"],str) or not task["objective"].strip():
        block("PILOT_OBJECTIVE_MISSING")
    if task_name in EX4_SHA:
        protected=["apps/time-service/src/test/**","apps/time-service/pom.xml",
                   "apps/time-service/src/main/java/lf/sandbox/time/*.java"]
        if task_name=="ex4b":
            protected += [REMINDER+file for file in ("Reminder.java","ReminderRepository.java",
                                                    "InMemoryReminderRepository.java")]
    elif task_name=="ex5c":
        protected=["apps/time-service/src/test/**","apps/time-service/pom.xml",
                   REMINDER+"Reminder.java",
                   "apps/time-service/src/main/java/lf/sandbox/time/*.java"]
    else:
        protected=["apps/time-service/src/test/**"] if task_name=="exercise-3" else ["standards/tests/**"]
    if task["protected_path_patterns"]!=protected:
        block("PILOT_PROTECTED_SCOPE_DRIFT")
    if task_name=="exercise-1":
        if (task["write_path_patterns"]!=["standards/tools/checks.py"]
            or task["context_path_patterns"]!=["standards/tools/checks.py"]
            or task["spec_path"] is not None or task["spec_sha256"] is not None
            or task["holdout_sha256"]!=EX1_SHA):
            block("PILOT_EXERCISE1_SCOPE_DRIFT")
    elif task_name=="exercise-2":
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
    elif task_name=="exercise-3":  # disjoint scope, specification pinned before API use.
        if (task["write_path_patterns"]!=[
                "apps/time-service/pom.xml","apps/time-service/src/main/**"]
            or task["context_path_patterns"]!=[
                EX3_SPEC,"apps/time-service/src/test/**","backend/pom.xml"]
            or task["spec_path"]!=EX3_SPEC or task["spec_sha256"]!=EX3_SPEC_SHA
            or ("NORMATIVE SPEC SHA256="+EX3_SPEC_SHA) not in task["objective"]):
            block("PILOT_EXERCISE3_SCOPE_DRIFT")
        if (task["source_precondition"]!={
                "kind":"NEW_FILE_ABSENT","path":"apps/time-service/pom.xml"}):
            block("PILOT_EXERCISE3_PRECONDITION_INVALID")
        source=ROOT/EX3_SPEC
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=EX3_SPEC_SHA:
            block("PILOT_TIME_SERVICE_SPEC_SHA_DRIFT")
        # No fabricated digest: fail closed during real workflow admission.
        if task["holdout_sha256"] in (EX1_SHA,EX2_SHA):
            block("PILOT_EXERCISE3_HOLDOUT_REUSED")
    elif task_name in EX4_SHA:  # previous tasks retain their original spec A/B pin
        a=task_name=="ex4a"
        writes=([REMINDER+name for name in ("Reminder.java","ReminderRepository.java",
                                             "InMemoryReminderRepository.java")] if a
                else [REMINDER+"ReminderController.java"])
        context=([EX4_SPEC,"apps/time-service/pom.xml",
                  "apps/time-service/src/main/java/lf/sandbox/time/TimeServiceApplication.java",
                  "apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderRepositoryVisibleTest.java"] if a
                 else [EX4_SPEC,"apps/time-service/pom.xml"]+
                      [REMINDER+name for name in ("Reminder.java","ReminderRepository.java",
                                                  "InMemoryReminderRepository.java")]+
                      ["apps/time-service/src/main/java/lf/sandbox/time/TimeController.java",
                       "apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderControllerVisibleTest.java"])
        if (task["write_path_patterns"]!=writes or task["context_path_patterns"]!=context
            or task["spec_path"]!=EX4_SPEC or task["spec_sha256"]!=EX4_SPEC_SHA
            or task["holdout_sha256"]!=EX4_SHA[task_name]
            or task["source_precondition"]!={"kind":"NEW_FILE_ABSENT","path":writes[0]}):
            block("PILOT_EX4_SCOPE_OR_SHA_DRIFT")
        spec=ROOT/EX4_SPEC
        if not spec.is_file() or hashlib.sha256(spec.read_bytes().split(b"## Lote C ",1)[0]).hexdigest()!=EX4_SPEC_SHA:
            block("PILOT_EX4_SPEC_SHA_DRIFT")
    else:  # ex5c: no hand-written context_path_patterns
        writes=[REMINDER+n for n in ("ReminderRepository.java","InMemoryReminderRepository.java","ReminderController.java")]
        if (task["write_path_patterns"]!=writes or task["spec_paths"]!=[EX4_SPEC]
            or task["spec_path"]!=EX4_SPEC or task["spec_sha256"]!=EX5_SPEC_SHA
            or task["holdout_sha256"]!=EX5_SHA
            or task["source_precondition"]!={"kind":"EXISTING_FILE_PRESENT","path":writes[0]}):
            block("PILOT_EX5_SCOPE_OR_SHA_DRIFT")
        spec=ROOT/EX4_SPEC
        if not spec.is_file() or hashlib.sha256(spec.read_bytes()).hexdigest()!=EX5_SPEC_SHA:
            block("PILOT_EX5_SPEC_SHA_DRIFT")
        if any(not (ROOT / name).is_file() or (ROOT / name).is_symlink() for name in writes):
            block("PILOT_EX5_WRITE_TARGET_MISSING")
    checks=task["acceptance_commands"]
    if not isinstance(checks,list) or len(checks)!=1 or not isinstance(checks[0],dict):
        block("PILOT_ACCEPTANCE_INVALID")
    if task_name in EX4_SHA:
        if checks[0]!={
            "name":"reminder-repository-visible" if task_name=="ex4a" else "reminder-full-visible",
            "argv":(["mvn","-B","-q","-f","apps/time-service/pom.xml",
                     "-Dtest=ReminderRepositoryVisibleTest","test"] if task_name=="ex4a" else
                    ["mvn","-B","-q","-f","apps/time-service/pom.xml","test"]),
            "timeout_seconds":600,"max_output_bytes":32000}:
            block("PILOT_ACCEPTANCE_INVALID")
    elif task_name=="ex5c":
        if checks[0]!={"name":"reminder-delete-search-full-visible",
                       "argv":["mvn","-B","-q","-f","apps/time-service/pom.xml","test"],
                       "timeout_seconds":600,"max_output_bytes":32000}:
            block("PILOT_ACCEPTANCE_INVALID")
    elif task_name=="exercise-3":
        if checks[0]!={"name":"time-service-maven-verify",
                       "argv":["mvn","-B","-q","-f","apps/time-service/pom.xml","verify"],
                       "timeout_seconds":600,"max_output_bytes":32000}:
            block("PILOT_ACCEPTANCE_INVALID")
    elif (checks[0].get("argv",[])[:3]!=["python3","-m","unittest"]
          or not isinstance(checks[0].get("timeout_seconds"),int)
          or not isinstance(checks[0].get("max_output_bytes"),int)):
        block("PILOT_ACCEPTANCE_INVALID")
    pre=task["source_precondition"]
    if not isinstance(pre,dict) or pre.get("path") not in task["write_path_patterns"]:
        block("PILOT_SOURCE_PRECONDITION_INVALID")
    if task_name=="ex5c" and pre!={"kind":"EXISTING_FILE_PRESENT","path":REMINDER+"ReminderRepository.java"}:
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
