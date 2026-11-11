"""EX6 v2 PG11/12/13 contracts, isolated PostgreSQL and five local Git attacks."""
from __future__ import annotations
import json
import os
import sys
import unittest
from pathlib import Path

TOOLS=Path(__file__).resolve().parents[1]/"tools"
sys.path.insert(0,str(TOOLS))
import ex6_real_chain_v1 as chain
import ex6_pg12_pg13_v2 as local
from ex6_local_freeze_v1 import local_freeze_and_attacks,exact_patch_blobs

class EX6LocalV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chain.install()

    @classmethod
    def tearDownClass(cls):
        chain.uninstall()

    def test_only_real_ex6_blobs_are_reconstructed(self):
        from ex6_source_truth_v1 import source_truth,git_blob_sha
        real=source_truth()
        blobs=exact_patch_blobs()
        self.assertEqual(set(blobs),{h["path"] for h in real["hunks"]})
        for h in real["hunks"]:
            self.assertEqual(git_blob_sha(blobs[h["path"]]),h["git_blob_oid"])

    def test_pg11_v2_all_true_ex6_hunk_links_and_process(self):
        x=local.make_pg11_v2()
        self.assertEqual(x["c5"]["status"],"CANDIDATE_NOT_ADMITTED")
        self.assertEqual(len(x["traces"]),3)
        self.assertEqual(sum(len(t["links"]) for t in x["traces"]),4)
        self.assertEqual(x["rem_d4"]["visible_test_exit_code"],0)
        self.assertEqual(x["rem_d4"]["aosp_exit_code"],1)
        self.assertFalse(x["rem_d4"]["process_requirement_satisfied"])
        self.assertFalse(x["c5"]["production_authority"])

    def test_pg12_c1_to_c4_v2_exact_reference_and_false_authority(self):
        x=local.make_pg12_v2()
        for k in ("c1","c2","c3","c4"):
            self.assertEqual(x[k]["status"],"CANDIDATE_NOT_ADMITTED")
            self.assertFalse(x[k]["production_authority"])
        self.assertEqual(x["c1"]["candidate_commit_sha_reported"],local.N)
        self.assertEqual(x["c1"]["candidate_tree_sha_reported"],local.TREE)
        self.assertEqual(len(x["checks"]),13)
        self.assertTrue(all(t["observed_outcome"]=="NOT_RUN" for t in x["checks"]))

    def test_pg13_c1_c3_v2_and_exact_bridge(self):
        x=local.make_pg13_v2()
        for k in ("c1","c2","c3","bridge"):
            self.assertEqual(x[k]["status"],"CANDIDATE_NOT_ADMITTED")
            self.assertFalse(x[k]["production_authority"])
        self.assertEqual(len(x["c3"]["negative_scenarios"]),5)
        self.assertEqual(x["c1"]["candidate_commit_sha_reported"],local.N)
        self.assertFalse(x["bridge"]["freeze_enforced"])

    def test_pg14_v2_local_testing_receiver_accepts_shape_and_blocks_tamper(self):
        x=local.make_pg14_v2()
        self.assertEqual(x["c3"]["status"],"CANDIDATE_NOT_ADMITTED")
        self.assertEqual(x["verdict"]["verdict"],"ACCEPT")
        self.assertEqual(x["verdict"]["reason"],"LOCAL_FIXTURE_SHAPE_ACCEPTED_ONLY")
        self.assertEqual(x["tampered_verdict"]["verdict"],"BLOCK")
        self.assertFalse(x["verdict"]["production_authority"])
        self.assertFalse(x["verdict"]["testing_real_invoked"])
        self.assertFalse(x["c1"]["production_authority"])
        self.assertEqual(x["local_freeze"]["blocked_mutation_count"],5)

    def test_disposable_postgres_real_readback(self):
        if os.environ.get("PG12_DISPOSABLE_DB")!="YES":
            self.skipTest("Local disposable DB explicit opt-in only")
        from pg12_disposable_postgres_readback_v2 import persist_readback
        x=local.make_pg12_v2()
        receipt=persist_readback(x["c4"])
        self.assertEqual(receipt,x["c4"]["payload_candidate_sha256"])
        self.assertFalse(x["c4"]["persisted"])
        self.assertFalse(x["c4"]["production_authority"])

    def test_five_actual_immutable_git_mutation_attempts(self):
        x=local_freeze_and_attacks()
        self.assertEqual(x["source_commit"],local.N)
        self.assertEqual(x["blocked_mutation_count"],5)
        self.assertTrue(x["only_original_verified_ex6_blobs"])
        self.assertFalse(x["production_authority"])

    def test_no_ex5c_or_lote_c_contamination_in_v2_inputs(self):
        j=local.make_pg13_v2()
        text=json.dumps(j,sort_keys=True,default=str).lower()
        self.assertNotIn("ex5c",text)
        self.assertNotIn("lote-c",text)
        for key in ("c1","c2","c3","bridge"):
            self.assertNotIn("fixture://",json.dumps(j[key]))

if __name__=="__main__":
    unittest.main()
