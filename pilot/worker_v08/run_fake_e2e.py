#!/usr/bin/env python3
"""No-key/no-model-network Worker @298307e real run_verified_worker integration pilot.

Hidden tests are supplied as an owner-held file OUTSIDE the repo; never in task
context or committed. Quality/readback manifests are materialized in /tmp and
validated by the original Worker parsers, not represented as a CLI PASS.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PIN="298307e2f9cac72abfde2b181f3554b0e28bad24"
ADAPTER_PIN="a0ec3385e322b51793e6f06c7d8d580d83cd15d6"
EXPECTED_HOLDOUT_SHA="979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821"
SCRIPT=Path(__file__).resolve()
REPO=SCRIPT.parents[2].resolve()
MANIFEST=SCRIPT.with_name("manifest.json")
def die(msg):
    raise RuntimeError(msg)
def canonical_bytes(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()
def sha_json(x):
    return sha_bytes(canonical_bytes(x))
def git(*args):
    return subprocess.run(["git","-C",str(REPO),*args],check=True,
                          capture_output=True,text=True).stdout.strip()
def require_pinned(worker_checkout:Path):
    if not (worker_checkout/"src/programming_agent_runner/worker_spec.py").is_file():
        die("WORKER_CHECKOUT_MISSING")
    got=subprocess.run(["git","-C",str(worker_checkout),"rev-parse","HEAD"],
                       check=True,capture_output=True,text=True).stdout.strip()
    if got!=PIN:die("WORKER_COMMIT_MISMATCH")
    sys.path.insert(0,str(worker_checkout/"src"))
def command(name,argv):
    return {"name":name,"argv":argv,"timeout_seconds":60,"max_output_bytes":12000}
def quality_plan(task):
    """Explicitly scoped candidate QA plan; no fabricated PASS or hidden evidence."""
    risk=[]
    dims=("concurrency","atomicity","idempotency","retries","partial_failures",
          "external_side_effects","security","persistence")
    for dim in dims:
        if dim=="security":
            risk.append({"dimension":dim,"classification":"APPLIES",
                         "justification":"Reject malformed branch validation inputs in the out-of-repo holdout.",
                         "coverage":[{"kind":"hidden_adversarial_test","ref":"owner-holdout:branch-invalid"}]})
        else:
            risk.append({"dimension":dim,"classification":"N/A",
                         "justification":("The current function is a pure regex branch-name validator; "
                                          +dim+" does not involve a stateful external operation."),
                         "coverage":[]})
    pre=[
        command("parse_compile",["python3","-m","py_compile","standards/tools/checks.py"]),
        command("lint_static",["python3","-c","import ast,pathlib;ast.parse(pathlib.Path('standards/tools/checks.py').read_text())"]),
        command("setup_import",["python3","-c","import sys;sys.path.insert(0,'standards/tools');import checks"]),
        command("reachability",["python3","-c","import sys;sys.path.insert(0,'standards/tools');import checks;assert checks.check_branch('lf/prog-a/a') == []"])
    ]
    return {"schema_version":1,"task_id":task["task_id"],"base_head_sha":task["base_head_sha"],
            "risk_profile":risk,"fixture_preflight_commands":pre,
            "semantic_paths":["standards/tools/checks.py"]}
def readback_manifest(task):
    """There is no row to read back for a pure local regex predicate."""
    return {"schema_version":2,"task_id":task["task_id"],"checks":[],
            "not_applicable_reason":"Pure local branch-name predicate; no external data row or database was mutated."}
def make_diff(path,old,new):
    before=old.splitlines(keepends=True)
    after=new.splitlines(keepends=True)
    lines=list(difflib.unified_diff(before,after,fromfile="a/"+path,
                                   tofile="b/"+path,n=3,lineterm="\n"))
    if not lines:die("PILOT_NO_PATCH")
    return "diff --git a/"+path+" b/"+path+"\n"+"".join(lines)
class FakeModel:
    provider="fake"
    model="fake-code-model"
    def __init__(self,proposal,response_id):
        self.proposal=proposal
        self.response_id=response_id
        self.calls=0
        self.payloads=[]
    def generate(self,system_instruction,user_payload):
        from programming_agent_runner.openai_responses import ModelResponse
        self.calls+=1
        self.payloads.append(user_payload)
        if self.calls>1:die("FAKE_MODEL_MORE_THAN_ONE_ATTEMPT")
        return ModelResponse(response_id=self.response_id,requested_model=self.model,
               resolved_model="fake-code-model-001",
               output_text=json.dumps(self.proposal,sort_keys=True),
               usage={"input_tokens":10,"output_tokens":10,"total_tokens":20})
def load_cost_adapter(checkout:Path):
    source=checkout.resolve(strict=True)
    got=subprocess.run(["git","-C",str(source),"rev-parse","HEAD"],
                       check=True,capture_output=True,text=True).stdout.strip()
    if got!=ADAPTER_PIN:die("COST_ADAPTER_COMMIT_MISMATCH")
    module=source/"sandbox/lf_contract_gate_test/programming_agent_four_stage/worker_pilot_adapter_exp"
    if not (module/"worker_cost_report_v1.py").is_file():
        die("COST_ADAPTER_REAL_MODULE_MISSING")
    sys.path.insert(0,str(module))
    from worker_cost_report_v1 import price_receipt
    return price_receipt
def fake_cost(visible_receipt,price_receipt):
    """Call the ACTUAL LF #3676 cost adapter against sealed visible Worker receipt."""
    before=canonical_bytes(visible_receipt)
    report=price_receipt(visible_receipt)
    if canonical_bytes(visible_receipt)!=before:die("COST_ADAPTER_CHANGED_SEALED_RECEIPT")
    if (report.get("model_provider")!="fake" or report.get("real_api_usage") is not False
        or report.get("total_estimated_usd")!="0" or
        report.get("price_table_version")!="FAKE_MODEL_NO_BILLING_V1"):
        die("COST_ADAPTER_FAKE_ZERO_POLICY_FAILED")
    return report
def link_pg07_candidate(verified_receipt,cost_record,source_path=None):
    """Exact verified evidence; PG07 admission remains FALSE absent real PG07 package."""
    original={"schema_version":"PG07_WORKER_PILOT_RECEIPT_LINK_CANDIDATE_V1",
              "status":"CANDIDATE_NOT_ADMITTED",
              "task_id":verified_receipt["task_id"],
              "task_sha256":verified_receipt["task_sha256"],
              "verified_worker_receipt_sha256":verified_receipt["receipt_sha256"],
              "verified_worker_status":verified_receipt["status"],
              "verified_worker_patch_sha256":verified_receipt["patch_sha256"],
              "cost_record_sha256":sha_json(cost_record),
              "pg07_source_binding":"NOT_PROVIDED",
              "pg07_receipt_guard_executed":False,
              "pg07_admitted":False,
              "production_authority":False,"dispatch_allowed":False}
    if source_path is not None:die("PG07_FULL_SOURCE_BINDING_NOT_IMPLEMENTED")
    return {**original,"candidate_sha256":sha_json(original)}
def store(folder,name,doc):
    p=folder/name
    raw=json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False).encode()+b"\n"
    p.write_bytes(raw);p.chmod(0o600)
    return sha_bytes(raw)
def run(args):
    if not args.holdout.is_file() or not args.holdout.is_absolute():
        die("OWNER_HOLDOUT_EXTERNAL_REQUIRED")
    if args.holdout.resolve().is_relative_to(REPO):
        die("HIDDEN_HOLDOUT_IN_REPO")
    if sha_bytes(args.holdout.read_bytes())!=EXPECTED_HOLDOUT_SHA:
        die("HIDDEN_HOLDOUT_SHA_MISMATCH")
    if git("status","--porcelain"):die("SOURCE_WORKTREE_NOT_CLEAN")
    if not REPO.joinpath("standards/tools/checks.py").is_file() or not REPO.joinpath("standards/tests/test_standards.py").is_file():
        die("EXISTING_FUNCTION_OR_VISIBLE_TEST_MISSING")
    require_pinned(args.worker_checkout.resolve())
    cost_adapter=load_cost_adapter(args.adapter_checkout)
    from programming_agent_runner.hashutil import source_snapshot_sha256
    from programming_agent_runner.worker_spec import parse_worker_task
    from programming_agent_runner.worker_receipt import validate_worker_receipt
    from programming_agent_runner.worker_oracle import load_hidden_oracle,assert_hidden_oracle_external
    from programming_agent_runner.programming_quality import load_quality_plan
    from programming_agent_runner.programming_quality_hardening_v2 import load_readback_manifest
    from programming_agent_runner.verified_worker import (
        run_verified_worker,validate_verified_worker_receipt)
    import programming_agent_runner.verified_worker as vw
    task_decl=json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (task_decl["worker_commit"]!=PIN or
        task_decl["cost_adapter_source_commit"]!=ADAPTER_PIN or
        task_decl["external_holdout_sha256"]!=EXPECTED_HOLDOUT_SHA):
        die("PILOT_DECLARATION_DRIFT")
    target=task_decl["target_file"]
    original=REPO.joinpath(target).read_text(encoding="utf-8")
    if original.count(task_decl["old_line"])!=1:die("TARGET_SOURCE_DRIFT")
    task={"schema_version":1,"task_id":"LF-WORKER-FAKE-PILOT-001",
          "objective":task_decl["objective"],
          "base_head_sha":git("rev-parse","HEAD"),
          "source_snapshot_sha256":source_snapshot_sha256(REPO),
          "context_path_patterns":[target],"write_path_patterns":[target],
          "protected_path_patterns":["standards/tests/**"],
          "acceptance_commands":[task_decl["visible_acceptance_command"]],
          "max_attempts":1,"max_patch_bytes":20000,
          "max_changed_files":3,"max_context_bytes":60000,"allow_deletions":False}
    spec=parse_worker_task(task)
    good=task_decl["good_line"];bad=task_decl["bad_line"]
    if good==bad or task_decl["old_line"] in (good,bad):die("PILOT_PATCH_EXPECTATIONS_INVALID")
    def proposal(replacement):
        diff=make_diff(target,original,original.replace(task_decl["old_line"],replacement))
        return {"schema_version":1,"summary":"Pilot branch guard adjustment.",
                "patch":diff,"changed_paths":[target]}
    with tempfile.TemporaryDirectory(prefix="lf-worker-free-") as td:
        private=Path(td)
        if private.resolve().is_relative_to(REPO):die("EXTERNAL_TEMP_INSIDE_REPOSITORY")
        quality=quality_plan(task);readback=readback_manifest(task)
        qhash=store(private,"quality-plan.json",quality)
        rhash=store(private,"readback-manifest.json",readback)
        q=load_quality_plan(private/"quality-plan.json",qhash)
        rb=load_readback_manifest(private/"readback-manifest.json",rhash)
        if q.task_id!=spec.task_id or rb.task_id!=spec.task_id:die("MANIFEST_TASK_ID_DRIFT")
        oracle=load_hidden_oracle(args.holdout,EXPECTED_HOLDOUT_SHA)
        assert_hidden_oracle_external(REPO,oracle)
        report=[]
        original_run_worker=vw.run_worker
        for label,expect,replacement in (("correct","PASS",good),("incorrect","FAIL",bad)):
            seen=[]
            def traced_worker(*worker_args,**worker_kwargs):
                val=original_run_worker(*worker_args,**worker_kwargs)
                seen.append(val)
                return val
            fake=FakeModel(proposal(replacement),"fake-pilot-"+label)
            with patch.object(vw,"run_worker",side_effect=traced_worker):
                outcome=run_verified_worker(REPO,spec,fake,oracle,work_parent=private)
            if not seen:die("VISIBLE_WORKER_NEVER_EXECUTED")
            visible=seen[0]
            if validate_worker_receipt(visible.receipt,visible.patch):
                die("ORIGINAL_VISIBLE_WORKER_RECEIPT_INVALID")
            if validate_verified_worker_receipt(outcome.receipt,outcome.patch):
                die("ORIGINAL_VERIFIED_WORKER_RECEIPT_INVALID")
            if outcome.receipt["status"]!=expect:die("UNEXPECTED_VERIFIED_STATUS:"+label+":"+outcome.receipt["status"])
            if label=="correct" and (not outcome.patch or outcome.receipt["hidden_oracle"]["status"]!="PASS"):
                die("CORRECT_PATCH_NOT_VERIFIED")
            if label=="incorrect" and (outcome.patch or outcome.receipt["patch_delivered"] is not False):
                die("BAD_PATCH_DELIVERED")
            if fake.calls!=1:die("FAKE_MODEL_CALL_COUNT_INVALID")
            if any("holdout" in str(k).lower() or "oracle" in str(k).lower()
                   for k in fake.payloads[0].get("workspace",{})):
                die("HIDDEN_ORACLE_LEAKED_TO_FAKE_BUILDER")
            cost=fake_cost(visible.receipt,cost_adapter)
            link=link_pg07_candidate(outcome.receipt,cost)
            report.append({"case":label,"expected_status":expect,
                           "status":outcome.receipt["status"],
                           "verified_receipt_sha256":outcome.receipt["receipt_sha256"],
                           "visible_receipt_sha256":visible.receipt["receipt_sha256"],
                           "hidden_oracle_status":outcome.receipt["hidden_oracle"]["status"],
                           "patch_delivered":outcome.receipt["patch_delivered"],
                           "cost_total_usd":cost["total_estimated_usd"],
                           "pg07_admitted":link["pg07_admitted"]})
            store(private,label+"-visible-receipt.json",visible.receipt)
            store(private,label+"-verified-receipt.json",outcome.receipt)
            store(private,label+"-cost.json",cost)
            store(private,label+"-pg07-link-candidate.json",link)
            (private/(label+"-patch.diff")).write_text(outcome.patch,encoding="utf-8")
            print("PASS FAKE_E2E",label,expect,"hidden",outcome.receipt["hidden_oracle"]["status"],
                  "USD",cost["total_estimated_usd"])
        if git("status","--porcelain"):die("SOURCE_CHANGED_BY_WORKER")
        if args.output:
            if args.output.exists():die("OUTPUT_DIRECTORY_ALREADY_EXISTS")
            args.output.mkdir(parents=False,mode=0o700)
            for file in private.iterdir():
                if file.name not in ("holdout.oracle.json",):
                    dest=args.output/file.name
                    dest.write_bytes(file.read_bytes());dest.chmod(0o600)
        print(json.dumps({"status":"FREE_FAKE_E2E_PASS","worker_commit":PIN,
            "source_head":task["base_head_sha"],"task_sha256":spec.sha256,
            "cost_adapter_commit":ADAPTER_PIN,
            "holdout_sha256":EXPECTED_HOLDOUT_SHA,
            "quality_plan_file_sha256":qhash,"readback_manifest_file_sha256":rhash,
            "cases":report,"workflow_authorized":False},sort_keys=True))
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--worker-checkout",type=Path,required=True)
    parser.add_argument("--adapter-checkout",type=Path,required=True)
    parser.add_argument("--holdout",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    run(args)
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("FAIL",type(exc).__name__,str(exc),file=sys.stderr)
        raise SystemExit(1)
