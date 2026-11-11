"""Offline lab: switches affect diagnostic continuation, never core guards."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from pg_programming_offline_lab_v1 import run,GATES,PACKET
from pg04_semantic_partition_candidate_v1 import PartitionBlocked

def fixture():
    return json.loads(PACKET.read_text(encoding="utf-8"))

def stage(report,key):
    return next((x for x in report["stages"] if x["step"]==key),None)

class OfflineLabTests(unittest.TestCase):
    def test_strict_stops_at_a9(self):
        p=run(fixture())
        self.assertEqual(stage(p,"A9_CURRENTNESS")["status"],"BLOCKED")
        self.assertIsNone(stage(p,"PG04_C2"))
        self.assertFalse(p["pg01_admitted"])

    def test_diagnostic_without_switch_stops_at_a9(self):
        self.assertEqual(stage(run(fixture(),mode="diagnostic"),
                               "A9_CURRENTNESS")["status"],"BLOCKED")

    def test_strict_disallows_skips(self):
        with self.assertRaisesRegex(ValueError,"STRICT_MODE_CANNOT_SKIP_GATES"):
            run(fixture(),mode="strict",skip_gates=["A9_CURRENTNESS"])

    def test_unknown_gate_fails(self):
        with self.assertRaisesRegex(ValueError,"LAB_UNKNOWN_GATE"):
            run(fixture(),mode="diagnostic",skip_gates=["DISABLE_SECURITY"])

    def test_a9_skip_still_stops_at_pg03(self):
        r=run(fixture(),mode="diagnostic",skip_gates=["A9_CURRENTNESS"])
        self.assertEqual(stage(r,"A9_CURRENTNESS")["status"],"SKIPPED_FOR_DIAGNOSTICS")
        self.assertEqual(stage(r,"PG03_GOVERNED_RECEIPT")["status"],"BLOCKED")
        self.assertIsNone(stage(r,"PG04_C2"))

    def test_two_skips_reach_real_partition_and_dod(self):
        r=run(fixture(),mode="diagnostic",skip_gates=GATES[:2])
        self.assertEqual(stage(r,"PG04_C2")["status"],"VALIDATED_SYNTHETIC")
        self.assertIn("2 SOLUTIONs",stage(r,"PG04_C2")["detail"])
        self.assertEqual(stage(r,"PG04_C3_C4")["status"],"VALIDATED_SYNTHETIC")
        self.assertEqual(stage(r,"PG04_C5")["status"],"PLANNED_NOT_EXECUTED")
        self.assertEqual(stage(r,"PG04_SOURCE_AUTHENTICITY")["status"],"BLOCKED")
        self.assertFalse(r["receipts_verified"])

    def test_three_skips_prepare_review_without_receipt(self):
        r=run(fixture(),mode="diagnostic",skip_gates=GATES[:3])
        self.assertEqual(stage(r,"PG04_C7")["status"],"REQUEST_PREPARED_NOT_EXECUTED")
        self.assertIn("subject_receipt_id=null",stage(r,"PG04_C7")["detail"])
        self.assertEqual(stage(r,"PG04_INDEPENDENT_REVIEW")["status"],"BLOCKED")
        self.assertFalse(r["checkpoint_closure_allowed"])

    def test_all_skips_no_authority(self):
        r=run(fixture(),mode="diagnostic",skip_gates=GATES)
        self.assertEqual(stage(r,"END")["status"],"LAB_REACHED_END_NO_AUTHORITY")
        for name in ("governed_execution","production_authority","pg01_admitted",
                     "pg03_admitted","pg04_admitted","checkpoint_closure_allowed",
                     "receipts_verified"):
            self.assertIs(r[name],False)
        self.assertEqual(sum(row["status"]=="SKIPPED_FOR_DIAGNOSTICS"
                             for row in r["stages"]),4)

    def test_stable_report(self):
        self.assertEqual(run(fixture(),mode="diagnostic",skip_gates=GATES),
                         run(fixture(),mode="diagnostic",skip_gates=GATES))

    def test_fixture_cannot_claim_real_authority(self):
        p=fixture();p["simulation_only"]=False
        with self.assertRaisesRegex(ValueError,"LAB_REQUIRES_UNTRUSTED_SYNTHETIC_PACKET"):
            run(p,mode="diagnostic",skip_gates=GATES)

    def test_fixture_cannot_claim_authentic_sources(self):
        p=fixture();p["source_authenticity"]="VERIFIED"
        with self.assertRaisesRegex(ValueError,"LAB_REQUIRES_UNTRUSTED_SYNTHETIC_PACKET"):
            run(p,mode="diagnostic",skip_gates=GATES)

    def test_fixture_cannot_embed_fake_receipt(self):
        p=fixture();p["fake_a9"]["receipt_id"]="00000000-0000-0000-0000-000000000000"
        with self.assertRaisesRegex(ValueError,"LAB_REQUIRES_UNTRUSTED_SYNTHETIC_PACKET"):
            run(p,mode="diagnostic",skip_gates=GATES)

    def test_switch_cannot_disable_coverage_validation(self):
        p=fixture();p["obligations"][0]["requirement_ids"]=[]
        with self.assertRaisesRegex(PartitionBlocked,"COVERAGE_INCOMPLETE_OR_FOREIGN"):
            run(p,mode="diagnostic",skip_gates=GATES)

    def test_switch_cannot_disable_shared_contract_guard(self):
        p=fixture();p["obligations"][0]["shared_contracts"]=[{"definition":"forged"}]
        with self.assertRaisesRegex(PartitionBlocked,"INLINE_SHARED_CONTRACT_FORBIDDEN"):
            run(p,mode="diagnostic",skip_gates=GATES)

    def test_switch_cannot_disable_cycle_guard(self):
        p=fixture();p["obligations"][0]["depends_on"]=["UI"]
        with self.assertRaisesRegex(PartitionBlocked,"SOLUTION_DEPENDENCY_CYCLE"):
            run(p,mode="diagnostic",skip_gates=GATES)

if __name__=="__main__":
    unittest.main()
