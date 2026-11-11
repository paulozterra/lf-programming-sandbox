"""Offline negatives for v2 gate. No fake v2 fixture, no fabricated PASS.

Once sandbox's *real* v2 artifact exists, pin its external SHA in a separate
integration fixture/test and feed the returned observations to the original
PG06 C4 and PG08 C2 producers. Until then, missing v2 -> BLOCK.
"""
from __future__ import annotations
import hashlib
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pg08_ex5c_v2_format_lint_adapter_v1 import (
    V2EvidenceBlocked,load_v2,stable_violation,
    V1_SHA,GJF_SHA,BASE,HEAD,V2_FIXTURE_PATH,V2_FIXTURE_SHA256,
    run_real_pg06_c4_pg08_c2,to_pg06_c4_baseline,to_pg08_c2_candidate
)


V1_FIXTURE = (Path(__file__).resolve().parents[1] /
              "fixtures/lf-evidence-bundle-v1.json")
V1_FIXED = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"


class EX5CV2RealProducerTests(unittest.TestCase):
    def setUp(self):
        from pg07_real_worker_evidence_adapter_v1 import load_real_bundle
        self.v1 = load_real_bundle(V1_FIXTURE, V1_FIXED)
        self.v2 = load_v2(V2_FIXTURE_PATH, V2_FIXTURE_SHA256)

    def test_real_v2_two_git_snapshots_pinned_and_no_authority(self):
        self.assertEqual([s["commit"] for s in self.v2["snapshots"]], [BASE, HEAD])
        self.assertEqual([len(x["formatter"]["findings"]) for x in self.v2["snapshots"]],
                         [24, 29])
        self.assertEqual([x["formatter"]["execution"]["exit_code"] for x in self.v2["snapshots"]],
                         [1, 1])
        self.assertEqual([x["javac"]["execution"]["exit_code"] for x in self.v2["snapshots"]],
                         [0, 0])
        self.assertEqual([len(x["javac"]["findings"]) for x in self.v2["snapshots"]],
                         [0, 0])
        self.assertFalse(self.v2["production_authority"])

    def test_real_pg06_c4_and_pg08_c2_original_producers_report_new_blockers(self):
        real = run_real_pg06_c4_pg08_c2(v1=self.v1, v2=self.v2)
        self.assertEqual(real["pg06_c4"]["solutions"][0]["diagnostic_status"],
                         "REPORTED_BASELINE_FAILURE")
        self.assertEqual(real["pg08_c2"]["solutions"][0]["reported_diagnostic"],
                         "REPORTED_NEW_BLOCKERS")
        self.assertGreater(len(real["pg08_c2"]["solutions"][0]["reported_new_blockers"]), 0)
        self.assertFalse(real["pg06_c4"]["production_authority"])
        self.assertFalse(real["pg08_c2"]["production_authority"])
        self.assertFalse(real["pg08_c2"]["pg08_c2_pass"])
        self.assertEqual(real["pg08_c2"]["source_pg06_c4_sha256"],
                         real["pg06_c4"]["candidate_sha256"])
        print("EX5C_PG06_C4_REAL_BASELINE_SOURCE_ONLY_PASS")
        print("EX5C_PG08_C2_REAL_NEW_FORMAT_BLOCKERS=BLOCK")
        print("EX5C_PG08_C2_AUTHORITY_FALSE")

    def test_real_format_exit_one_cannot_be_declared_pass(self):
        rows = to_pg08_c2_candidate(self.v2)
        self.assertEqual(rows[0]["checks"][0]["kind"], "FORMAT")
        self.assertEqual(rows[0]["checks"][0]["result"], "FAIL")
        self.assertEqual(rows[0]["checks"][0]["exit_code"], 1)
        self.assertEqual(rows[0]["checks"][1]["result"], "PASS")

    def test_one_changed_stdout_byte_blocks_before_original_producer(self):
        changed = copy.deepcopy(self.v2)
        changed["snapshots"][1]["formatter"]["execution"]["stdout"]["sha256"] = "f" * 64
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v2.json"
            raw = (json.dumps(changed, sort_keys=True) + "\n").encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(V2EvidenceBlocked, "FORMAT_STDOUT_DIGEST_BLOCK"):
                load_v2(p, hashlib.sha256(raw).hexdigest())

    def test_one_changed_git_blob_blocks_even_with_rehashed_package(self):
        changed = copy.deepcopy(self.v2)
        changed["snapshots"][1]["files"][0]["content_base64"] = "YQ=="
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v2.json"
            raw = (json.dumps(changed, sort_keys=True) + "\n").encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(V2EvidenceBlocked, "JAVA_BLOB_DIGEST_BLOCK"):
                load_v2(p, hashlib.sha256(raw).hexdigest())

    def test_altered_authority_blocks_even_with_rehashed_package(self):
        changed = copy.deepcopy(self.v2)
        changed["snapshots"][0]["authority_authenticated"] = True
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v2.json"
            raw = (json.dumps(changed, sort_keys=True) + "\n").encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(V2EvidenceBlocked, "NESTED_AUTHORITY_INJECTION_BLOCK"):
                load_v2(p, hashlib.sha256(raw).hexdigest())


class EX5CV2OfflineGateTests(unittest.TestCase):
    def test_missing_v2_bundle_blocks_without_synthetic_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"lf-evidence-bundle-v2.json"
            with self.assertRaisesRegex(V2EvidenceBlocked,"FIXTURE_SHA_OR_PATH_NOT_PINNED_BLOCK"):
                load_v2(p,"0"*64)

    def test_unpinned_v2_bundle_always_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"v2.json"
            p.write_text('{"source":"synthetic"}')
            with self.assertRaisesRegex(V2EvidenceBlocked,"FIXTURE_SHA_OR_PATH_NOT_PINNED_BLOCK"):
                load_v2(p,"")

    def test_replacement_rehashed_against_wrong_pin_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"v2.json"
            p.write_bytes(b'{"schema_version":"FAKE"}')
            with self.assertRaisesRegex(V2EvidenceBlocked,"FIXTURE_SHA_CHANGED_BLOCK"):
                load_v2(p,"f"*64)

    def test_rehashed_authority_injection_is_blocked_at_v2(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"v2.json"
            doc={"schema_version":"LF_EX5C_REAL_EVIDENCE_BUNDLE_V2",
                 "evidence_kind":"REAL_SANDBOX_UNAUTHENTICATED",
                 "base_commit":BASE,"candidate_commit":HEAD,
                 "v1_bundle_sha256":V1_SHA,
                 "diff_sha256":"bfba0329bcac92dbde06a1319a16acd535acd718f224df6121dae3c70fe307c6",
                 "formatter_version":"1.30.0",
                 "formatter_sha256":GJF_SHA,
                 "production_authority":True,
                 "tool_execution_verified":False,
                 "receipt_authenticated":False,
                 "worker_invoked":False,
                 "snapshots":[]}
            raw=(json.dumps(doc)+"\n").encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(V2EvidenceBlocked,"AUTHORITY_BLOCK"):
                load_v2(p,hashlib.sha256(raw).hexdigest())

    def test_violation_id_is_stable_across_base_candidate(self):
        x=stable_violation("GOOGLE_JAVA_FORMAT","apps/time-service/src/main/java/A.java",10,"z")
        self.assertEqual(x,stable_violation("GOOGLE_JAVA_FORMAT",
                                           "apps/time-service/src/main/java/A.java",10,"z"))
        self.assertNotEqual(x,stable_violation("GOOGLE_JAVA_FORMAT",
                                              "apps/time-service/src/main/java/A.java",11,"z"))

if __name__=="__main__":
    unittest.main()
