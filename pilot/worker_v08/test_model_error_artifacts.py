#!/usr/bin/env python3
"""Free integration test: ORIGINAL Worker + fake MODEL_ERROR, no Anthropic API.

Creates an isolated disposable Git worktree and test-only oracle OUTSIDE it.
Checks both public artifact receipts, redaction, withheld patch and unknown
billing without claiming usage=0. No real hidden exercise-2 content involved.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"vendor/programming-agent/src"))
from programming_agent_runner.hashutil import source_snapshot_sha256
from programming_agent_runner.worker_spec import parse_worker_task
from programming_agent_runner.worker_oracle import load_hidden_oracle
from programming_agent_runner.verified_worker import run_verified_worker,validate_verified_worker_receipt
from programming_agent_runner.worker_receipt import validate_worker_receipt
from programming_agent_runner.model_client import ModelError
import programming_agent_runner.verified_worker as verified_module
from unittest.mock import patch
from receipt_diagnostics import (write_public_receipt,write_usage_unavailable,
                                 MISSING_USAGE_MESSAGE)

SECRET="sk-notreal-sentinel-THIS-MUST-NEVER-LEAK"
OUTPUT="MODEL_OUTPUT_TEXT_SENTINEL_MUST_NOT_LEAK"

class FakeTransportFailure:
    provider="anthropic"
    model="claude-sonnet-5-5"
    def generate(self,system_instruction,user_payload):
        raise ModelError("HTTP 404: provider error "+SECRET+" "+OUTPUT)

def git(repo,*args):
    return subprocess.run(["git","-C",str(repo),*args],capture_output=True,
                          check=True,text=True).stdout.strip()

class OriginalWorkerErrorArtifactTests(unittest.TestCase):
    def test_model_error_blocked_receipts_uploaded_safely(self):
        with tempfile.TemporaryDirectory(prefix="lf-original-worker-error-") as tmp:
            parent=Path(tmp)
            source=parent/"source"
            source.mkdir()
            (source/"a.py").write_text("x=1\n",encoding="utf-8")
            git(source,"init","-q")
            git(source,"config","user.email","pilot-test@example.invalid")
            git(source,"config","user.name","LF pilot test")
            git(source,"add","a.py")
            git(source,"commit","-qm","test fixture")
            head=git(source,"rev-parse","HEAD")
            fixture_cmd={"name":"visible","argv":["python3","-c","print('ok')"],
                         "timeout_seconds":30,"max_output_bytes":4096}
            task={"schema_version":1,"task_id":"LF-FAKE-MODEL-ERROR-TEST",
                  "objective":"Change a.py to use x=2.",
                  "base_head_sha":head,
                  "source_snapshot_sha256":source_snapshot_sha256(source),
                  "context_path_patterns":["a.py"],
                  "write_path_patterns":["a.py"],
                  "protected_path_patterns":["tests/**"],
                  "acceptance_commands":[fixture_cmd],
                  "max_attempts":1,"max_patch_bytes":10000,
                  "max_changed_files":1,"max_context_bytes":60000,
                  "allow_deletions":False}
            spec=parse_worker_task(task)
            oracle_path=parent/"private-oracle.json"
            raw=json.dumps({"schema_version":1,"family":"test_only",
                            "version":"v1","commands":[fixture_cmd]}).encode()
            oracle_path.write_bytes(raw)
            oracle=load_hidden_oracle(oracle_path,hashlib.sha256(raw).hexdigest())
            worker_records=[]
            real=verified_module.run_worker
            def trace(*args,**kwargs):
                result=real(*args,**kwargs)
                self.assertEqual(validate_worker_receipt(result.receipt,result.patch),[])
                worker_records.append(result.receipt)
                return result
            with patch.object(verified_module,"run_worker",side_effect=trace):
                verified=run_verified_worker(source,spec,FakeTransportFailure(),
                                             oracle,work_parent=parent)
            self.assertEqual(validate_verified_worker_receipt(verified.receipt,verified.patch),[])
            self.assertEqual(verified.receipt["status"],"BLOCKED")
            self.assertEqual(verified.patch,"")
            self.assertEqual(len(worker_records),1)
            visible=worker_records[0]
            self.assertEqual(visible["attempts"][0]["proposal_reason"],"MODEL_ERROR")
            self.assertEqual(visible["attempts"][0]["usage"],{})
            # Same artifact helpers used by production pilot runner.
            public=parent/"public"
            write_public_receipt(public,visible,"visible")
            write_public_receipt(public,verified.receipt,"verified","MODEL_ERROR")
            self.assertTrue(write_usage_unavailable(public,visible,verified.receipt))
            names={p.name for p in public.iterdir()}
            self.assertEqual(names,{"visible-worker-receipt.json",
                                    "verified-worker-receipt.json","cost.json"})
            visible_safe=json.loads((public/"visible-worker-receipt.json").read_text())
            verified_safe=json.loads((public/"verified-worker-receipt.json").read_text())
            cost=json.loads((public/"cost.json").read_text())
            self.assertIn("MODEL_ERROR",visible_safe["reason"])
            self.assertIn("MODEL_ERROR",verified_safe["reason"])
            self.assertEqual(visible_safe["attempts"][0]["proposal_reason"].split()[0],"MODEL_ERROR")
            self.assertEqual(cost["usage_status"],"UNAVAILABLE")
            self.assertEqual(cost["message"],MISSING_USAGE_MESSAGE)
            self.assertIsNone(cost["total_estimated_usd"])
            self.assertEqual(cost["billing_status"],"UNKNOWN_NOT_ZERO")
            self.assertFalse(verified_safe["patch_delivered"])
            exported="\n".join(p.read_text(encoding="utf-8") for p in public.iterdir())
            for private_text in (SECRET,OUTPUT,"holdout.oracle.json","secret_key"):
                self.assertNotIn(private_text,exported)
            self.assertEqual(git(source,"status","--porcelain"),"")

if __name__=="__main__":
    unittest.main(verbosity=2)
