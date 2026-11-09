"""Offline, no-network EX6 provenance, policy, SHA and tampering checks."""
import base64
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import build_bundle_v1 as g
import verify_bundle_v1 as v

def sha(x):
    return hashlib.sha256(x).hexdigest()

def command(argv):
    return {"argv":argv,"exit_code":0,"duration_ms":1,
            "stdout":{"sha256":sha(b""),"bytes":0,"base64":""},
            "stderr":{"sha256":sha(b""),"bytes":0,"base64":""}}

def sample():
    def snap(label, commit):
        java=["apps/time-service/src/main/java/lf/sandbox/time/TimeController.java"]
        cmds={"build":command(["mvn","package"]),
              "format_aosp":command(["java","-jar","pinned.jar","--aosp",
                                      "--dry-run","--set-exit-if-changed",*java]),
              "classpath_resolution":command(["mvn","dependency:build-classpath"]),
              "javac_lint":command(["javac","-Xlint:all",*java])}
        if label=="candidate":
            cmds["visible_ex6"]=command(["python3",g.EX6_VISIBLE])
        return {"label":label,"commit":commit,"java_paths":java,
                "java_file_count":len(java),"commands":cmds}
    return {"schema_version":"LF_EX6_BUILD_LINT_AOSP_EVIDENCE_V1",
         "base_commit":g.BASE,"candidate_commit":g.CANDIDATE,
         "formatter_version":g.GJF_VERSION,"formatter_sha256":g.GJF_SHA256,
         "formatter_flags":["--aosp","--dry-run","--set-exit-if-changed"],
         "write_paths":list(g.ADDED),
         "production_authority":False,"receipt_authenticated":False,
         "holdout_accessed":False,"worker_invoked":False,"api_calls":0,
         "snapshots":[snap("baseline",g.BASE),snap("candidate",g.CANDIDATE)]}

def raw(d):
    return (json.dumps(d,sort_keys=True,separators=(",",":"))+"\n").encode()

class TestEX6Bundle(unittest.TestCase):
    def test_pinned_snapshots_and_formatter(self):
        self.assertEqual(len(g.BASE),40)
        self.assertEqual(len(g.CANDIDATE),40)
        self.assertEqual(g.GJF_VERSION,"1.30.0")
        self.assertEqual(len(g.GJF_SHA256),64)
        self.assertEqual(len(g.ADDED),3)
        self.assertEqual(set(g.ADDED),set(g.ADDED))
        self.assertEqual(v.verify(raw(sample()),sha(raw(sample())))["api_calls"],0)

    def test_modified_bytes_rejected_against_sha(self):
        obj=sample()
        encoded=raw(obj)
        obj["snapshots"][0]["label"]="not-base"
        with self.assertRaisesRegex(ValueError,"DIGEST_MISMATCH"):
            v.verify(raw(obj),sha(encoded))

    def test_substituted_provenance_rejected_even_if_rehashed(self):
        obj=sample()
        obj["candidate_commit"]="f"*40
        with self.assertRaisesRegex(ValueError,"SOURCE_DRIFT"):
            v.verify(raw(obj),sha(raw(obj)))

    def test_stream_tamper_detected_even_if_bundle_rehashed(self):
        obj=sample()
        obj["snapshots"][0]["commands"]["build"]["stdout"]["base64"]=base64.b64encode(b"forged").decode()
        with self.assertRaisesRegex(ValueError,"STREAM_DIGEST_MISMATCH"):
            v.verify(raw(obj),sha(raw(obj)))

    def test_authority_escalation_rejected(self):
        obj=sample()
        obj["production_authority"]=True
        with self.assertRaisesRegex(ValueError,"AUTHORITY_DRIFT"):
            v.verify(raw(obj),sha(raw(obj)))

    def test_missing_aosp_flag_rejected(self):
        obj=sample()
        obj["snapshots"][0]["commands"]["format_aosp"]["argv"].remove("--aosp")
        with self.assertRaisesRegex(ValueError,"AOSP_NOT_SET"):
            v.verify(raw(obj),sha(raw(obj)))

    def test_missing_candidate_visible_check_rejected(self):
        obj=sample()
        del obj["snapshots"][1]["commands"]["visible_ex6"]
        with self.assertRaisesRegex(ValueError,"COMMAND_COVERAGE"):
            v.verify(raw(obj),sha(raw(obj)))

    def test_nonzero_formatter_is_evidence_not_failure_or_pass(self):
        obj=sample()
        obj["snapshots"][0]["commands"]["format_aosp"]["exit_code"]=1
        out=v.verify(raw(obj),sha(raw(obj)))
        self.assertEqual(out["snapshots"][0]["commands"]["format_aosp"]["exit_code"],1)

    def test_dispatch_is_manual_and_secretless(self):
        y=(HERE.parents[1]/".github/workflows/ex6-build-lint-evidence.yml").read_text()
        self.assertIn("  workflow_dispatch:",y)
        for forbidden in ("pull_request:","pull_request_target:","schedule:","secrets.",
                          "ANTHROPIC_API_KEY","PILOT_HOLDOUT","gh pr create","gh workflow run"):
            self.assertNotIn(forbidden,y)
        self.assertIn("  contents: read",y)
        self.assertIn("ref: "+g.BASE,y)
        self.assertIn("ref: "+g.CANDIDATE,y)
        self.assertIn("sha256sum --check",y)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",y)

if __name__=="__main__":
    unittest.main()
