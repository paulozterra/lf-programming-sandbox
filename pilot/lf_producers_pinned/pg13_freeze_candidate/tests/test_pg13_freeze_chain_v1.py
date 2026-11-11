"""PG-13 real PG12 producer chain + exact freeze and rebuild negative tests."""
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
             "pg06_preflight_candidate","pg07_worker_candidate",
             "pg08_build_candidate","pg09_iteration_candidate",
             "pg10_conflict_candidate","pg11_integrity_candidate",
             "pg12_identity_candidate","pg13_freeze_candidate"):
    for sub in ("tests","tools"):
        folder=ROOT/name/sub
        if folder.is_dir():sys.path.insert(0,str(folder))
from test_pg12_identity_chain_v1 import inputs as pg12_inputs
from pg13_c1_freeze_intent_candidate_v1 import prepare_pg13_c1,Blocked as C1Blocked
from pg13_c2_rebuild_comparison_candidate_v1 import prepare_pg13_c2,Blocked as C2Blocked
from pg13_c3_mutation_block_candidate_v1 import prepare_pg13_c3,Blocked as C3Blocked,SCENARIOS
from pg13_pg12_exact_freeze_bridge_v1 import bridge_pg12_c4_to_pg13_c1,PG13BridgeBlocked

def build():
    pg12=pg12_inputs()  # actual PG12 C1-C4 producers
    c1=prepare_pg13_c1(pg12_c4=pg12["c4"],
         candidate_commit_sha=pg12["c1"]["candidate_commit_sha_reported"],
         candidate_tree_sha=pg12["c1"]["candidate_tree_sha_reported"],
         freeze_policy_ref="fixture://freeze/policy",
         freeze_request_ref="fixture://freeze/request")
    bridge=bridge_pg12_c4_to_pg13_c1(
        pg12_c1=pg12["c1"],pg12_c4=pg12["c4"],pg13_c1=c1)
    rebuild=[{"artifact_ref":"fixture://build/candidate",
        "baseline_digest_sha256":"a"*64,"rebuild_digest_sha256":"a"*64,
        "difference_ref":None}]
    c2=prepare_pg13_c2(pg13_c1=c1,rebuild_observations=rebuild,
        build_recipe_ref="fixture://build/recipe",environment_lock_ref="fixture://environment/lock")
    scenarios=[{"scenario_code":code,"attempt_ref":"fixture://mutation/"+code,
        "expected_verdict":"BLOCK","evidence_ref":"fixture://evidence/"+code}
        for code in sorted(SCENARIOS)]
    c3=prepare_pg13_c3(pg13_c2=c2,mutation_scenarios=scenarios,
         policy_ref="fixture://freeze/policy")
    return locals()

class PG13Tests(unittest.TestCase):
    def test_real_pg12_c4_to_pg13_c1_c3(self):
        x=build()
        self.assertEqual(x["bridge"]["source_pg12_c4_sha256"],x["pg12"]["c4"]["candidate_sha256"])
        self.assertEqual(x["bridge"]["pg12_c4_payload_sha256"],x["pg12"]["c4"]["payload_candidate_sha256"])
        self.assertEqual(x["bridge"]["candidate_commit_sha"],x["pg12"]["c1"]["candidate_commit_sha_reported"])
        self.assertEqual(x["bridge"]["candidate_tree_sha"],x["pg12"]["c1"]["candidate_tree_sha_reported"])
        self.assertEqual(x["c2"]["source_pg13_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg13_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertTrue(x["c2"]["observations"][0]["digest_equal_reported"])
        self.assertFalse(x["c2"]["rebuild_performed_by_component"])
        for key in ("bridge","c1","c2","c3"):
            self.assertFalse(x[key]["production_authority"])
            self.assertFalse(x[key]["handoff_allowed"])
        self.assertEqual(x["c3"]["executed_negative_tests"],0)
    def test_c1_commit_drift_rejected(self):
        x=build();bad=copy.deepcopy(x["c1"])
        bad["candidate_commit_sha_reported"]="f"*40
        from pg13_pg12_exact_freeze_bridge_v1 import digest
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(PG13BridgeBlocked,"EXACT_COMMIT_TREE_DRIFT"):
            bridge_pg12_c4_to_pg13_c1(pg12_c1=x["pg12"]["c1"],
                pg12_c4=x["pg12"]["c4"],pg13_c1=bad)
    def test_c1_tree_drift_rejected(self):
        x=build();bad=copy.deepcopy(x["c1"])
        bad["candidate_tree_sha_reported"]="f"*40
        from pg13_pg12_exact_freeze_bridge_v1 import digest
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(PG13BridgeBlocked,"EXACT_COMMIT_TREE_DRIFT"):
            bridge_pg12_c4_to_pg13_c1(pg12_c1=x["pg12"]["c1"],
                pg12_c4=x["pg12"]["c4"],pg13_c1=bad)
    def test_c1_pg12_receipt_digest_drift_rejected(self):
        x=build();bad=copy.deepcopy(x["pg12"]["c4"])
        bad["payload_candidate_sha256"]="f"*64
        from pg13_pg12_exact_freeze_bridge_v1 import digest
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaises(PG13BridgeBlocked):
            bridge_pg12_c4_to_pg13_c1(pg12_c1=x["pg12"]["c1"],
                pg12_c4=bad,pg13_c1=x["c1"])
    def test_c1_rehashed_authority_injection_rejected(self):
        x=build();bad=copy.deepcopy(x["pg12"]["c4"])
        bad["production_authority"]=True
        from pg13_pg12_exact_freeze_bridge_v1 import digest
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(PG13BridgeBlocked,"AUTHORITY"):
            bridge_pg12_c4_to_pg13_c1(pg12_c1=x["pg12"]["c1"],
                pg12_c4=bad,pg13_c1=x["c1"])
    def test_c2_equal_digests_report_equal_no_runtime_pass(self):
        x=build()
        self.assertTrue(x["c2"]["observations"][0]["digest_equal_reported"])
        self.assertFalse(x["c2"]["rebuild_reproducibility_verified"])
    def test_c2_undocumented_digest_difference_rejected(self):
        x=build();bad=copy.deepcopy(x["rebuild"])
        bad[0]["rebuild_digest_sha256"]="b"*64
        with self.assertRaisesRegex(C2Blocked,"C2_DIFFERENCE_UNDOCUMENTED"):
            prepare_pg13_c2(pg13_c1=x["c1"],rebuild_observations=bad,
                build_recipe_ref="fixture://build/recipe",environment_lock_ref="fixture://environment/lock")
    def test_c2_documented_difference_does_not_claim_reproducible(self):
        x=build();bad=copy.deepcopy(x["rebuild"])
        bad[0]["rebuild_digest_sha256"]="b"*64
        bad[0]["difference_ref"]="fixture://known/nondeterminism"
        result=prepare_pg13_c2(pg13_c1=x["c1"],rebuild_observations=bad,
            build_recipe_ref="fixture://build/recipe",environment_lock_ref="fixture://environment/lock")
        self.assertFalse(result["observations"][0]["digest_equal_reported"])
        self.assertFalse(result["rebuild_reproducibility_verified"])
    def test_c2_equal_with_fictitious_difference_rejected(self):
        x=build();bad=copy.deepcopy(x["rebuild"])
        bad[0]["difference_ref"]="fixture://spurious"
        with self.assertRaisesRegex(C2Blocked,"C2_SPURIOUS_DIFFERENCE"):
            prepare_pg13_c2(pg13_c1=x["c1"],rebuild_observations=bad,
                build_recipe_ref="fixture://build/recipe",environment_lock_ref="fixture://environment/lock")
    def test_c3_missing_negative_scenario_rejected(self):
        x=build()
        with self.assertRaises(C3Blocked):
            prepare_pg13_c3(pg13_c2=x["c2"],mutation_scenarios=x["scenarios"][:-1],
                policy_ref="fixture://freeze/policy")
    def test_c3_falsified_pass_verdict_rejected(self):
        x=build();bad=copy.deepcopy(x["scenarios"])
        bad[0]["expected_verdict"]="PASS"
        with self.assertRaises(C3Blocked):
            prepare_pg13_c3(pg13_c2=x["c2"],mutation_scenarios=bad,
                policy_ref="fixture://freeze/policy")
if __name__=="__main__":unittest.main()
