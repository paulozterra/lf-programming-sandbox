#!/usr/bin/env python3
"""Strict PG07 V2 -> WorkerTaskSpec V1 pilot adapter (NO MODEL, NO SECRETS).

Source authority: programming-agent @298307e2f9cac72abfde2b181f3554b0e28bad24
(see worker_spec.py and worker_cli.py). All manifests are owner-provided and
copied only to a private directory outside the repository. No fake oracle/QA.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Any

WORKER_COMMIT="298307e2f9cac72abfde2b181f3554b0e28bad24"
TASK_FIELDS=frozenset({
 "schema_version","task_id","objective","base_head_sha","source_snapshot_sha256",
 "context_path_patterns","write_path_patterns","protected_path_patterns","acceptance_commands",
 "max_attempts","max_patch_bytes","max_changed_files","max_context_bytes","allow_deletions"})
PG07_REQUIRED=frozenset({
 "schema_version","task_id","objective","expected_change","human_story","functional_contract",
 "scope","cases","dependency_resolution","dependency_task_ids","required_tests","required_evidence",
 "blocked_if","base_head_sha","source_snapshot_sha256","context_path_patterns",
 "write_path_patterns","protected_path_patterns","files_expected","platform_refs",
 "interface_refs","acceptance_commands","max_attempts","max_patch_bytes","max_changed_files",
 "max_context_bytes","allow_deletions"})
LIMITS={"max_attempts":1,"max_context_bytes":60000,"max_patch_bytes":20000,
        "max_changed_files":3,"max_output_tokens":8000}
OBJ_MAX_BYTES=18000
_SHA40=re.compile(r"^[a-f0-9]{40}$")
_SHA64=re.compile(r"^[a-f0-9]{64}$")
_NAME=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FORBIDDEN_ARG_CHARS=set('|;&<>`$*?{}[]()') | {chr(10),chr(13),chr(92)}
class AdapterBlocked(ValueError):
    pass
def fail(code):raise AdapterBlocked(code)
def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
def sha(v):
    # Matches existing PG07 candidate digest (ensure_ascii=True), not file bytes.
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("utf-8")).hexdigest()
def sha_bytes(v):return hashlib.sha256(v).hexdigest()
def exact(x,fields,code):
    if not isinstance(x,dict) or set(x)!=set(fields):fail(code)
def safe_name(x):
    return isinstance(x,str) and bool(_NAME.fullmatch(x))
def check_limits(spec):
    for field,cap in LIMITS.items():
        if field=="max_output_tokens":continue
        x=spec.get(field)
        if type(x) is not int or x<1 or x>cap:fail("PILOT_LIMIT_MISSING_OR_EXCEEDED:"+field)
    if spec.get("allow_deletions") is not False:fail("PILOT_DELETIONS_FORBIDDEN")
def commands_from_declared(raw):
    """Never interpret shell; each user-declared command becomes an argv array."""
    if not isinstance(raw,list) or not raw or len(raw)>32:fail("ACCEPTANCE_MISSING")
    result=[]
    seen=set()
    for index,c in enumerate(raw):
        if isinstance(c,str):
            if not c.strip() or any(ch in c for ch in FORBIDDEN_ARG_CHARS):
                fail("ACCEPTANCE_SHELL_OR_AMBIGUOUS")
            try:argv=shlex.split(c,posix=True)
            except ValueError:fail("ACCEPTANCE_PARSE_INVALID")
            if not argv:fail("ACCEPTANCE_MISSING")
            # No commands are fabricated: owner must supply timeout/output limits
            # separately when PG07 has legacy string commands.
            fail("ACCEPTANCE_COMMAND_METADATA_MISSING")
        exact(c,{"name","argv","timeout_seconds","max_output_bytes"},"ACCEPTANCE_COMMAND_FORMAT_INVALID")
        if not safe_name(c["name"]) or c["name"] in seen:fail("ACCEPTANCE_COMMAND_NAME_INVALID")
        if not isinstance(c["argv"],list) or not 1<=len(c["argv"])<=64:fail("ACCEPTANCE_ARGV_INVALID")
        for item in c["argv"]:
            if (not isinstance(item,str) or not item or
                any(ch in item for ch in FORBIDDEN_ARG_CHARS) or
                len(item.encode("utf-8"))>4096):
                fail("ACCEPTANCE_SHELL_OR_AMBIGUOUS")
        if (type(c["timeout_seconds"]) is not int or not 1<=c["timeout_seconds"]<=900 or
            type(c["max_output_bytes"]) is not int or not 1024<=c["max_output_bytes"]<=2000000):
            fail("ACCEPTANCE_LIMIT_INVALID")
        seen.add(c["name"]);result.append(c.copy())
    return result
def bind_declared_commands(raw,owner_metadata):
    """Associate owner-provided execution metadata to an EXACT original string;
    no invented argv, timeout, or shell interpretation. Dictionary commands may
    be passed straight through. The metadata is also independently reviewed."""
    if isinstance(raw,list) and all(isinstance(x,dict) for x in raw):
        return commands_from_declared(raw)
    if not isinstance(raw,list) or not raw:fail("ACCEPTANCE_MISSING")
    if not isinstance(owner_metadata,list) or len(owner_metadata)!=len(raw):
        fail("ACCEPTANCE_COMMAND_METADATA_MISSING")
    out=[]
    for text,meta in zip(raw,owner_metadata):
        if not isinstance(text,str) or not text.strip() or any(ch in text for ch in FORBIDDEN_ARG_CHARS):
            fail("ACCEPTANCE_SHELL_OR_AMBIGUOUS")
        try:argv=shlex.split(text,posix=True)
        except ValueError:fail("ACCEPTANCE_PARSE_INVALID")
        if not argv:fail("ACCEPTANCE_MISSING")
        exact(meta,{"source_command","name","argv","timeout_seconds","max_output_bytes"},
              "ACCEPTANCE_METADATA_FIELDS_INVALID")
        if meta["source_command"]!=text or meta["argv"]!=argv:
            fail("ACCEPTANCE_OWNER_ARGV_NOT_EXACT")
        out.append({k:meta[k] for k in ("name","argv","timeout_seconds","max_output_bytes")})
    return commands_from_declared(out)
def _safe_paths(x):
    if not isinstance(x,list) or not x or not all(isinstance(p,str) for p in x) or len(set(x))!=len(x):
        fail("SCOPE_INVALID")
    for p in x:
        if (p.startswith("/") or "\\" in p or ".." in p.split("/") or
            ".git" in p.split("/") or not p.strip()):
            fail("SCOPE_INVALID")
    return x
def reject_hidden_oracle_fields(value):
    forbidden={"oracle_envelope","hidden_oracle_ref","hidden_oracle_sha256",
               "hidden_oracle_manifest","verifier_only_oracle","holdout_manifest"}
    if isinstance(value,dict):
        if any(key in forbidden for key in value):fail("ORACLE_FIELD_IN_PG07_TASK")
        for item in value.values():reject_hidden_oracle_fields(item)
    elif isinstance(value,list):
        for item in value:reject_hidden_oracle_fields(item)
def reject_oracle_context(paths):
    if not isinstance(paths,list) or not paths:fail("CONTEXT_SCOPE_MISSING")
    for path in paths:
        if not isinstance(path,str):fail("CONTEXT_SCOPE_INVALID")
        lower=path.lower().split("/")
        if any(any(token in segment for token in ("oracle","holdout","secret","credential",".env")) for segment in lower):
            fail("ORACLE_OR_SECRET_IN_CONTEXT")
def _role_stack(pg07):
    fc=pg07["functional_contract"]
    if not isinstance(fc,dict) or not isinstance(fc.get("role_and_stack"),dict):
        fail("ROLE_STACK_MISSING")
    rs=fc["role_and_stack"]
    if not isinstance(rs.get("profile_sha256"),str) or not _SHA64.fullmatch(rs["profile_sha256"]):
        fail("ROLE_SHA_MISSING")
    text=rs.get("profile_rules")
    if not isinstance(text,str) or sha_bytes(text.encode("utf-8"))!=rs["profile_sha256"]:
        fail("ROLE_SHA_DRIFT")
    skills=rs.get("skills")
    if not isinstance(skills,list) or not skills:fail("SKILL_SET_MISSING")
    if not isinstance(rs.get("skill_set_sha256"),str) or not _SHA64.fullmatch(rs["skill_set_sha256"]):
        fail("SKILL_SET_SHA_MISSING")
    identities=[];blocks=[];priority=[]
    for item in skills:
        if not isinstance(item,dict):fail("SKILL_INVALID")
        for k in ("skill_code","skill_version","skill_sha256","skill_rules","priority","expert_rules"):
            if k not in item:fail("SKILL_INCOMPLETE")
        if (type(item["priority"]) is not int or item["priority"]<=0 or
            not isinstance(item["skill_sha256"],str) or not _SHA64.fullmatch(item["skill_sha256"]) or
            not isinstance(item["skill_rules"],str) or
            sha_bytes(item["skill_rules"].encode("utf-8"))!=item["skill_sha256"]):
            fail("SKILL_SHA_OR_PRIORITY_INVALID")
        priority.append(item["priority"])
        identities.append({k:item[k] for k in ("skill_code","skill_version","skill_sha256","priority")})
        rules=item["expert_rules"]
        if not isinstance(rules,list) or len(rules)<3 or len({r.get("rule_id") for r in rules})<3:
            fail("SKILL_RULES_TOO_FEW")
        blocks.append((item,rules))
    if len(set(priority))!=len(priority) or priority!=sorted(priority):fail("SKILL_PRIORITY_CONFLICT")
    if sha(identities)!=rs["skill_set_sha256"]:fail("SKILL_SET_SHA_DRIFT")
    if rs.get("profile_code") is None:fail("PROFILE_CODE_MISSING")
    return rs,blocks
def objective_with_rules(pg07):
    rs,blocks=_role_stack(pg07)
    origin=pg07["objective"]
    if not isinstance(origin,str) or not origin.strip():fail("OBJECTIVE_MISSING")
    chunks=[origin,"[LF ROLE SOURCE]","profile_code="+str(rs["profile_code"]),
            "profile_sha256="+rs["profile_sha256"],
            "role_rules_begin",rs["profile_rules"],"role_rules_end"]
    for item,rules in blocks:
        chunks+=["[LF SKILL SOURCE]","skill_code="+str(item["skill_code"]),
                 "skill_version="+str(item["skill_version"]),
                 "skill_sha256="+item["skill_sha256"],
                 "skill_set_sha256="+rs["skill_set_sha256"]]
        for rule in rules:
            if (not isinstance(rule,dict) or set(rule)!={"rule_id","text","source_url"} or
                not all(isinstance(rule[k],str) and rule[k].strip() for k in rule) or
                not rule["source_url"].startswith("https://") or
                "**"+rule["rule_id"]+":** "+rule["text"] not in item["skill_rules"] or
                rule["source_url"] not in item["skill_rules"]):
                fail("SKILL_RULE_NOT_SOURCE_BOUND")
            chunks.append("RULE "+rule["rule_id"]+" | "+rule["text"]+" | SOURCE "+rule["source_url"])
    goal="\n".join(chunks)
    if len(goal.encode("utf-8"))>OBJ_MAX_BYTES:fail("OBJECTIVE_RULES_TOO_LARGE")
    if "oracle_envelope" in goal or "hidden_oracle" in goal or "holdout.oracle" in goal:
        fail("ORACLE_IN_OBJECTIVE")
    return goal
def validate_original_worker_paths(pg07,worker_checkout):
    """Do not repair/normalize: import EXACT Worker 298307e canonical path routines."""
    if worker_checkout is None:fail("WORKER_CHECKOUT_REQUIRED_FOR_PATH_VALIDATION")
    source=worker_checkout.resolve(strict=True)
    head=subprocess.run(["git","-C",str(source),"rev-parse","HEAD"],
                        capture_output=True,text=True,check=True).stdout.strip()
    if head!=WORKER_COMMIT:fail("WORKER_HEAD_NOT_PINNED")
    sys.path.insert(0,str(source/"src"))
    from programming_agent_runner.worker_spec import (
        canonical_relative_path, _validate_pattern, TaskSpecError)
    for field in ("context_path_patterns","write_path_patterns","protected_path_patterns"):
        items=pg07.get(field)
        if not isinstance(items,list) or not items:fail("ADAPTER_PATH_NOT_CANONICAL")
        for value in items:
            try:
                # Both original contracts; _validate_pattern itself calls canonical.
                if canonical_relative_path(value,field+"[]")!=value:
                    fail("ADAPTER_PATH_NOT_CANONICAL")
                if _validate_pattern(value,field+"[]")!=value:
                    fail("ADAPTER_PATH_NOT_CANONICAL")
            except TaskSpecError as exc:
                raise AdapterBlocked("ADAPTER_PATH_NOT_CANONICAL") from exc

def adapt(pg07,*,owner_commands=None,pg07_overlay=None,worker_checkout=None):
    """Output Worker V1 plus separate sealed envelope. Never grant dispatch."""
    if not isinstance(pg07,dict) or not PG07_REQUIRED.issubset(pg07):
        fail("PG07_TASK_INCOMPLETE")
    if pg07.get("schema_version")!=2:fail("PG07_SCHEMA_INVALID")
    check_limits(pg07)
    validate_original_worker_paths(pg07,worker_checkout)
    reject_hidden_oracle_fields(pg07)
    reject_oracle_context(pg07.get("context_path_patterns"))
    if pg07_overlay is None or not isinstance(pg07_overlay,dict):
        fail("PG07_SOURCE_OVERLAY_REQUIRED")
    if (pg07_overlay.get("production_authority") is not False or
        pg07_overlay.get("dispatch_allowed") is not False or
        pg07_overlay.get("worker_invoked") is not False or
        pg07_overlay.get("worker_task_overlay",{}).get("worker_spec_sha256")!=sha(pg07)):
        fail("PG07_OVERLAY_NOT_BOUND")
    write=_safe_paths(pg07["write_path_patterns"])
    if sorted(write)!=sorted(pg07_overlay["worker_task_overlay"].get("write_scope",[])):
        fail("WRITE_SCOPE_MISMATCH")
    if not isinstance(pg07["context_path_patterns"],list) or not isinstance(pg07["protected_path_patterns"],list):
        fail("PATHS_INVALID")
    if not pg07["protected_path_patterns"]:fail("PROTECTED_SCOPE_EMPTY")
    task={k:pg07[k] for k in TASK_FIELDS if k not in ("schema_version","objective","acceptance_commands")}
    task.update(schema_version=1,objective=objective_with_rules(pg07),
                acceptance_commands=bind_declared_commands(pg07["acceptance_commands"],owner_commands))
    exact(task,TASK_FIELDS,"WORKER_V1_FIELDS_INVALID")
    check_limits(task)
    if not _SHA40.fullmatch(task["base_head_sha"]) or not _SHA64.fullmatch(task["source_snapshot_sha256"]):
        fail("SOURCE_IDENTITY_INVALID")
    envelope={"schema_version":"LF_WORKER_V1_EXTRA_ENVELOPE_V1","task_id":task["task_id"],
              "task_sha256":sha(task),"pg07_sha256":sha(pg07),
              "pg07_extra":{k:pg07[k] for k in sorted(set(pg07)-TASK_FIELDS)},
              "pg07_worker_task_overlay":pg07_overlay["worker_task_overlay"],
              "production_authority":False}
    envelope["envelope_sha256"]=sha(envelope)
    return task,envelope

def _write_private(path:Path,document):
    data=canonical(document)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as handle:handle.write(data)
    except BaseException:
        path.unlink(missing_ok=True);raise
    return sha_bytes(data)
def load_real_worker_contract(worker_checkout:Path):
    """Imports ORIGINAL Worker implementation only if checkout matches exact HEAD."""
    source=worker_checkout.resolve(strict=True)
    result=subprocess.run(["git","-C",str(source),"rev-parse","HEAD"],
                          capture_output=True,text=True,check=True)
    if result.stdout.strip()!=WORKER_COMMIT:fail("WORKER_HEAD_NOT_PINNED")
    sys.path.insert(0,str(source/"src"))
    from programming_agent_runner.worker_spec import parse_worker_task
    from programming_agent_runner.programming_quality import load_quality_plan
    from programming_agent_runner.programming_quality_hardening_v2 import load_readback_manifest,readback_source_paths
    from programming_agent_runner.worker_oracle import load_hidden_oracle
    return parse_worker_task,load_quality_plan,load_readback_manifest,load_hidden_oracle,readback_source_paths

def materialize_external(*,repo_root:Path,outside_dir:Path,worker_checkout:Path,
                         task,envelope,owner_quality_plan,owner_readback_manifest,
                         owner_hidden_oracle):
    """Only owner-supplied manifests; validate each with ORIGINAL pinned loaders.
    No fabricated hidden checks, risk classifications or readback sources.
    """
    repository=repo_root.resolve(strict=True)
    output=outside_dir.resolve()
    if output==repository or output.is_relative_to(repository):fail("EXTERNAL_FILES_INSIDE_REPO")
    if output.exists():fail("OUTPUT_DIRECTORY_MUST_NOT_EXIST")
    for obj in (owner_quality_plan,owner_readback_manifest,owner_hidden_oracle):
        if not isinstance(obj,dict):fail("OWNER_MANIFEST_MISSING")
        if obj.get("task_id",task["task_id"])!=task["task_id"]:fail("MANIFEST_TASK_ID_MISMATCH")
    parse_worker_task,load_quality,load_readback,load_oracle,readback_source_paths=load_real_worker_contract(worker_checkout)
    parse_worker_task(task)
    if not isinstance(envelope,dict) or envelope.get("task_sha256")!=sha(task):
        fail("EXTRA_ENVELOPE_NOT_BOUND")
    output.mkdir(mode=0o700,parents=False)
    names=[("task.v1.json",task),("extra.envelope.json",envelope),
           ("quality-plan.json",owner_quality_plan),("readback-manifest.json",owner_readback_manifest),
           ("holdout.oracle.json",owner_hidden_oracle)]
    try:
        digests={name:_write_private(output/name,obj) for name,obj in names}
        quality=load_quality(output/"quality-plan.json",digests["quality-plan.json"])
        readback=load_readback(output/"readback-manifest.json",digests["readback-manifest.json"])
        oracle=load_oracle(output/"holdout.oracle.json",digests["holdout.oracle.json"])
        if quality.task_id!=task["task_id"] or quality.base_head_sha!=task["base_head_sha"]:
            fail("QUALITY_PLAN_NOT_PINNED_TO_TASK")
        if readback.task_id!=task["task_id"]:fail("READBACK_NOT_PINNED_TO_TASK")
        for source in readback_source_paths(readback):
            if not source.is_absolute() or source.resolve()==repository or source.resolve().is_relative_to(repository):
                fail("READBACK_SOURCE_INSIDE_REPOSITORY")
        if not oracle.commands:fail("ORACLE_COMMANDS_EMPTY")
        return {"directory":str(output),"sha256":digests}
    except BaseException:
        shutil.rmtree(output)
        raise

def build_worker_command(*,repo_path:Path,output_dir:Path,worker_checkout:Path,model="claude-haiku-5-5",provider="anthropic"):
    if provider!="anthropic" or model not in ("claude-haiku-5-5","claude-sonnet-5-5"):
        fail("PILOT_PROVIDER_OR_MODEL_FORBIDDEN")
    q=output_dir.resolve()
    if not (q/"task.v1.json").is_file():fail("PILOT_TASK_MISSING")
    task=json.loads((q/"task.v1.json").read_text(encoding="utf-8"))
    exact(task,TASK_FIELDS,"WORKER_V1_FIELDS_INVALID")
    if task.get("schema_version")!=1:fail("WORKER_V1_SCHEMA_INVALID")
    check_limits(task)
    parse_worker_task,_,_,_,_=load_real_worker_contract(worker_checkout)
    try:parse_worker_task(task)
    except Exception as exc:
        raise AdapterBlocked("WORKER_V1_CONTRACT_INVALID") from exc
    envelope_file=q/"extra.envelope.json"
    if not envelope_file.is_file():fail("EXTRA_ENVELOPE_MISSING")
    envelope=json.loads(envelope_file.read_text(encoding="utf-8"))
    if envelope.get("task_id")!=task["task_id"] or envelope.get("task_sha256")!=sha(task) or envelope.get("production_authority") is not False:
        fail("EXTRA_ENVELOPE_DRIFT")
    for name in ("task.v1.json","quality-plan.json","readback-manifest.json","holdout.oracle.json"):
        if not (q/name).is_file():fail("PILOT_EXTERNAL_INPUT_MISSING:"+name)
    if q==repo_path.resolve() or q.is_relative_to(repo_path.resolve()):fail("PILOT_OUTPUT_INSIDE_REPO")
    def digest(name):return sha_bytes((q/name).read_bytes())
    return ["programming-agent-worker","--provider",provider,"--model",model,
            "--repo-path",str(repo_path.resolve()),"--task-spec",str(q/"task.v1.json"),
            "--quality-plan",str(q/"quality-plan.json"),"--quality-plan-sha256",digest("quality-plan.json"),
            "--readback-manifest",str(q/"readback-manifest.json"),"--readback-manifest-sha256",digest("readback-manifest.json"),
            "--hidden-oracle-manifest",str(q/"holdout.oracle.json"),"--hidden-oracle-sha256",digest("holdout.oracle.json"),
            "--max-output-tokens","8000","--output",str(q/"verified-worker-receipt.json"),
            "--patch-output",str(q/"worker.patch")]
