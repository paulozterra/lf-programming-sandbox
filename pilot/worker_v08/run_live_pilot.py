#!/usr/bin/env python3
"""Manual-only, pinned Worker v0.8 pilot. Not a scheduler or an authority grant.

prepare: offline preflight and original manifest validation (NO API KEY).
execute: call ORIGINAL Worker CLI in-process, capturing its ORIGINAL visible
         Worker receipt for real usage, without modifying Worker files.
cost:    use pinned LF #3676 price_receipt; fail closed above USD 0.10.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch

PIN_WORKER="298307e2f9cac72abfde2b181f3554b0e28bad24"
PIN_ADAPTER="5c981dfc77f8ffee1aa3cd66ab08a3b4d0051e2e"
PIN_HOLDOUT="979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821"
CEILING=Decimal("0.10")
LIMITS={"max_attempts":1,"max_context_bytes":60000,
        "max_patch_bytes":20000,"max_changed_files":3}
SCRIPT=Path(__file__).resolve()
MANIFEST=SCRIPT.with_name("manifest.json")

def fail(code):
    raise RuntimeError(code)

def sh256(b):
    return hashlib.sha256(b).hexdigest()

def put(path,value):
    if path.exists():
        fail("PILOT_OUTPUT_ALREADY_EXISTS:"+path.name)
    path.write_bytes(json.dumps(value,sort_keys=True,indent=2,
                               ensure_ascii=False,allow_nan=False).encode("utf-8")+b"\n")
    path.chmod(0o600)

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def head(repo):
    return subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
                          check=True,capture_output=True,text=True).stdout.strip()

def check_source(args):
    source=args.repo.resolve(strict=True)
    worker=args.worker.resolve(strict=True)
    adapter=args.adapter.resolve(strict=True)
    if head(worker)!=PIN_WORKER or head(adapter)!=PIN_ADAPTER:
        fail("PINNED_DEPENDENCY_HEAD_DRIFT")
    if source!=SCRIPT.parents[2]:
        fail("PILOT_REPOSITORY_PATH_MISMATCH")
    if subprocess.run(["git","-C",str(source),"status","--porcelain"],
                      check=True,capture_output=True,text=True).stdout.strip():
        fail("PILOT_SOURCE_REPOSITORY_DIRTY")
    private=args.private.resolve()
    if private==source or private.is_relative_to(source):
        fail("PILOT_PRIVATE_DIR_INSIDE_SOURCE")
    if private==worker or private.is_relative_to(worker):
        fail("PILOT_PRIVATE_DIR_INSIDE_WORKER")
    if private==adapter or private.is_relative_to(adapter):
        fail("PILOT_PRIVATE_DIR_INSIDE_ADAPTER")
    if not private.is_dir():
        fail("PILOT_PRIVATE_DIR_MISSING")
    if head(source)!=os.environ.get("GITHUB_SHA",head(source)):
        fail("PILOT_SOURCE_CHECKOUT_SHA_MISMATCH")
    return source,worker,adapter,private

def imports(worker,adapter):
    sys.path.insert(0,str(worker/"src"))
    sys.path.insert(0,str(adapter/"sandbox/lf_contract_gate_test/programming_agent_four_stage/worker_pilot_adapter_exp"))
    from pg07_to_worker_v1_adapter import check_limits,build_worker_command,sha
    from worker_cost_report_v1 import price_receipt
    return check_limits,build_worker_command,sha,price_receipt

def prepare(args):
    source,worker,adapter,private=check_source(args)
    declaration=read(MANIFEST)
    if (declaration.get("worker_commit")!=PIN_WORKER or
        declaration.get("cost_adapter_source_commit")!=PIN_ADAPTER or
        declaration.get("external_holdout_sha256")!=PIN_HOLDOUT or
        declaration.get("source_repo")!="paulozterra/lf-programming-sandbox"):
        fail("PILOT_DECLARATION_DRIFT")
    if (declaration.get("target_file")!="standards/tools/checks.py" or
        declaration.get("limits")!={**LIMITS,"max_output_tokens":8000,"allow_deletions":False}):
        fail("PILOT_TARGET_OR_LIMITS_DRIFT")
    if os.environ.get("PILOT_PROVIDER")!="anthropic" or os.environ.get("PILOT_MODEL")!="claude-haiku-5-5":
        fail("PILOT_PROVIDER_MODEL_FORBIDDEN")
    if os.environ.get("PILOT_MAX_ATTEMPTS")!="1":
        fail("PILOT_ATTEMPTS_FORBIDDEN")
    oracle_path=private/"holdout.oracle.json"
    if not oracle_path.is_file() or sh256(oracle_path.read_bytes())!=PIN_HOLDOUT:
        fail("HIDDEN_HOLDOUT_SHA_MISMATCH")
    if oracle_path.resolve().is_relative_to(source):
        fail("HIDDEN_HOLDOUT_INSIDE_SOURCE")
    # Hardened CLI @298307e requires a real owner baseline at this path.
    # DO NOT fabricate baseline or spend tokens if it is absent.
    baseline=source/"quality/programming_quality/baseline_v1.json"
    if not baseline.is_file():
        fail("HARDENED_WORKER_QUALITY_BASELINE_MISSING_NO_MODEL_CALL")
    if declaration["old_line"] not in (source/declaration["target_file"]).read_text(encoding="utf-8"):
        fail("PILOT_SOURCE_TARGET_DRIFT")
    check_limits,build_command,sha,_=imports(worker,adapter)
    from programming_agent_runner.worker_spec import parse_worker_task
    from programming_agent_runner.hashutil import source_snapshot_sha256
    from programming_agent_runner.programming_quality_hardening_v7_runtime import (
        load_quality_plan,load_readback_manifest)
    from programming_agent_runner.worker_oracle import load_hidden_oracle,assert_hidden_oracle_external
    # Reuse offline free pilot's declared quality/readback policy.
    from run_fake_e2e import quality_plan,readback_manifest
    task={"schema_version":1,"task_id":"LF-WORKER-PILOT-REAL-001",
          "objective":declaration["objective"],
          "base_head_sha":head(source),
          "source_snapshot_sha256":source_snapshot_sha256(source),
          "context_path_patterns":[declaration["target_file"]],
          "write_path_patterns":[declaration["target_file"]],
          "protected_path_patterns":["standards/tests/**"],
          "acceptance_commands":[declaration["visible_acceptance_command"]],
          "max_attempts":1,"max_context_bytes":60000,"max_patch_bytes":20000,
          "max_changed_files":3,"allow_deletions":False}
    check_limits(task)
    spec=parse_worker_task(task)
    quality=quality_plan(task)
    readback=readback_manifest(task)
    put(private/"task.v1.json",task)
    put(private/"quality-plan.json",quality)
    put(private/"readback-manifest.json",readback)
    outer={"schema_version":"LF_WORKER_PILOT_UNADMITTED_ENVELOPE_V1",
           "task_id":task["task_id"],"task_sha256":sha(task),
           "source_manifest_sha256":sh256(MANIFEST.read_bytes()),
           "pg07_admitted":False,"production_authority":False}
    put(private/"extra.envelope.json",outer)
    qpath=private/"quality-plan.json"
    rpath=private/"readback-manifest.json"
    hpath=private/"holdout.oracle.json"
    qual=load_quality_plan(qpath,sh256(qpath.read_bytes()))
    rb=load_readback_manifest(rpath,sh256(rpath.read_bytes()))
    oracle=load_hidden_oracle(hpath,PIN_HOLDOUT)
    assert_hidden_oracle_external(source,oracle)
    if qual.task_id!=spec.task_id or qual.base_head_sha!=spec.base_head_sha:
        fail("QUALITY_TASK_DRIFT")
    if rb.task_id!=spec.task_id:
        fail("READBACK_TASK_DRIFT")
    # Original adapter is used for a second hard-limit check and exact CLI argv.
    argv=build_command(repo_path=source,output_dir=private,worker_checkout=worker,
                       model="claude-haiku-5-5",provider="anthropic")
    if argv[argv.index("--max-output-tokens")+1]!="8000":
        fail("OUTPUT_TOKEN_CAP_MISSING")
    put(private/"cli-argv.json",argv)
    print("PILOT_PREPARED_PINNED_LIMITED_NO_MODEL")

def execute(args):
    source,worker,adapter,private=check_source(args)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        fail("ANTHROPIC_API_KEY_MISSING")
    check_limits,build_command,sha,_=imports(worker,adapter)
    from programming_agent_runner import worker_cli
    from programming_agent_runner import verified_worker
    from programming_agent_runner.worker_receipt import validate_worker_receipt
    from programming_agent_runner.worker_spec import parse_worker_task
    task=read(private/"task.v1.json")
    check_limits(task)
    parse_worker_task(task)
    command=build_command(repo_path=source,output_dir=private,worker_checkout=worker,
                          model="claude-haiku-5-5",provider="anthropic")
    if read(private/"cli-argv.json")!=command:
        fail("CLI_ARGUMENTS_CHANGED_SINCE_PREFLIGHT")
    seen=[]
    original=verified_worker.run_worker
    def capture_visible(*a,**kw):
        result=original(*a,**kw)  # Actual original Worker; no code replacement.
        if validate_worker_receipt(result.receipt,result.patch):
            fail("ORIGINAL_VISIBLE_RECEIPT_INVALID")
        seen.append(result.receipt)
        return result
    saved=sys.argv
    try:
        # Run REAL worker_cli.main, not a fake CLI. Intercept only its
        # underlying original run_worker result so usage is verifiable.
        sys.argv=["programming-agent-worker"]+command[1:]
        with patch.object(verified_worker,"run_worker",side_effect=capture_visible):
            exit_code=worker_cli.main()
    finally:
        sys.argv=saved
    if seen:
        put(private/"visible-worker-receipt.json",seen[0])
    receipt_path=private/"verified-worker-receipt.json"
    if not receipt_path.is_file():
        fail("HARDENED_WORKER_RECEIPT_MISSING")
    receipt=read(receipt_path)
    if receipt.get("status")!="PASS" or exit_code!=0:
        fail("HARDENED_WORKER_NOT_PASS")
    if len(seen)!=1 or seen[0].get("status")!="PASS":
        fail("VISIBLE_WORKER_USAGE_RECEIPT_NOT_AVAILABLE")
    patch_path=private/"worker.patch"
    patch_data=patch_path.read_bytes()
    if not patch_data or len(patch_data)>LIMITS["max_patch_bytes"]:
        fail("PATCH_MISSING_OR_OVERSIZED")
    if (receipt.get("patch_delivered") is not True or
        receipt.get("patch_sha256")!=sh256(patch_data)):
        fail("HARDENED_WORKER_PATCH_DIGEST_DRIFT")
    print("PILOT_REAL_WORKER_PASS_COST_GATE_PENDING")

def cost(args):
    source,worker,adapter,private=check_source(args)
    _,_,_,price_receipt=imports(worker,adapter)
    visible_path=private/"visible-worker-receipt.json"
    overall_path=private/"verified-worker-receipt.json"
    if not visible_path.is_file() or not overall_path.is_file():
        fail("REAL_VISIBLE_USAGE_NOT_AVAILABLE")
    visible=read(visible_path)
    hardened=read(overall_path)
    if (visible.get("model_provider")!="anthropic" or
        hardened.get("model_provider")!="anthropic" or
        visible.get("task_id")!=hardened.get("task_id")):
        fail("WORKER_RECEIPTS_NOT_BOUND")
    # Failed patches can still spend tokens: always account for actual usage.
    result=price_receipt(visible)
    if result.get("model_provider")!="anthropic" or result.get("real_api_usage") is not True:
        fail("PRICE_PROVIDER_OR_USAGE_INVALID")
    if len(result.get("attempts",[]))!=1:
        fail("ATTEMPT_COUNT_NOT_ONE")
    try: amount=Decimal(result["total_estimated_usd"])
    except (InvalidOperation,KeyError,ValueError):fail("COST_NUMBER_INVALID")
    if not amount.is_finite() or amount<0 or amount>CEILING:
        fail("PILOT_COST_OVER_USD_0_10")
    artifact=private/"public"
    if artifact.exists():fail("PUBLIC_ARTIFACT_ALREADY_EXISTS")
    artifact.mkdir(mode=0o700)
    for filename in ("verified-worker-receipt.json","visible-worker-receipt.json"):
        shutil.copyfile(private/filename,artifact/filename)
    put(artifact/"cost.json",result)
    patch=private/"worker.patch"
    if hardened.get("status")=="PASS":
        if not patch.is_file() or not patch.stat().st_size:
            fail("PASS_WITHOUT_PATCH")
        shutil.copyfile(patch,artifact/"worker.patch")
        (artifact/"worker.patch").chmod(0o600)
    (artifact/"pilot-summary.log").write_text(
        "PILOT_WORKER_STATUS="+str(hardened.get("status"))+
        "; Anthropic model pinned; attempts=1; cost_usd="
        +str(amount)+"; oracle content excluded; stage7_admitted=false\n",
        encoding="utf-8")
    print("PILOT_COST_GATE_PASS_USD_"+str(amount)+
          "_WORKER_STATUS_"+str(hardened.get("status")))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=["prepare","execute","cost"])
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--worker",type=Path,required=True)
    p.add_argument("--adapter",type=Path,required=True)
    p.add_argument("--private",type=Path,required=True)
    a=p.parse_args()
    {"prepare":prepare,"execute":execute,"cost":cost}[a.phase](a)
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("PILOT_BLOCKED:"+str(exc),file=sys.stderr)
        raise SystemExit(1)
