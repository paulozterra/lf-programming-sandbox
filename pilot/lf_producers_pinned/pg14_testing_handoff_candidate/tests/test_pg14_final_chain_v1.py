"""PG14 real PG13 C3 -> C1-C3, local Testing receiver positive and negatives."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
             "pg06_preflight_candidate","pg07_worker_candidate","pg08_build_candidate",
             "pg09_iteration_candidate","pg10_conflict_candidate","pg11_integrity_candidate",
             "pg12_identity_candidate","pg13_freeze_candidate","pg14_testing_handoff_candidate"):
    for part in ("tools","tests"):
        p=ROOT/name/part
        if p.is_dir():sys.path.insert(0,str(p))
from test_pg13_freeze_chain_v1 import build as real_pg13
from pg14_c1_testing_execution_contract_candidate_v1 import prepare_pg14_c1,Blocked as C1Blocked
from pg14_c2_testing_payload_candidate_v1 import prepare_pg14_c2,Blocked as C2Blocked
from pg14_c3_testing_admission_readback_request_candidate_v1 import prepare_pg14_c3,Blocked as C3Blocked
from pg14_pg13_freeze_bridge_v1 import bridge_pg13_to_pg14,PG14BridgeBlocked
from pg14_local_testing_receiver_v1 import simulate_testing_receiver

CONTRACT_PATH=ROOT/"wave1_boundary_contracts"/"testing_admission_contract_v1.json"
def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

def make_chain():
    prev=real_pg13() # actual producer PG13 C3 chain and PG12 C4
    identity=prev["pg12"]["c1"]
    frozen=prev["c3"]["source_pg12_c1_sha256"]
    analysis={"package_ref":"fixture://analysis/package/not-ready",
        "package_sha256":"d"*64,"source_currentness_ref":"fixture://analysis/currentness",
        "ready_verified":False}
    c1=prepare_pg14_c1(pg13_c3=prev["c3"],admission_contract=contract(),
        analysis_package_ref=analysis["package_ref"],
        analysis_package_sha256=analysis["package_sha256"],
        source_currentness_ref=analysis["source_currentness_ref"],
        frozen_candidate_ref="fixture://frozen/candidate",
        frozen_candidate_sha256=frozen)
    commitment=identity["candidate_commit_sha_reported"]
    bridge=bridge_pg13_to_pg14(
        pg12_c1=identity,pg13_bridge=prev["bridge"],
        pg13_c1=prev["c1"],pg13_c2=prev["c2"],pg13_c3=prev["c3"],
        pg14_c1=c1,
        freeze_tag_ref="refs/tags/frozen/"+commitment,
        freeze_tag_oid="e"*40,analysis_package_observation=analysis)
    obligations=[{"obligation_ref":"B2B-RULE-TEST-001",
         "spec_ref":"fixture://analysis/spec","test_case_ref":"fixture://case/B2B",
         "expected_oracle_ref":"fixture://blind/oracle/restricted"}]
    copytexts=[{"text_ref":"fixture://copy/pending/001",
        "source_ref":"fixture://copy/source","status":"PENDING_COPY"}]
    c2args={"pg14_c1":c1,"catalog_version_ref":"fixture://catalog/v1",
        "spec_test_obligations":obligations,
        "blind_test_contract_ref":"fn_submit_blind_test_contract",
        "pending_copy_texts":copytexts}
    c2=prepare_pg14_c2(**c2args)
    c3=prepare_pg14_c3(pg14_c2=c2,
        testing_admission_endpoint_ref="fixture://testing/local-only",
        readback_contract_ref="fixture://readback/contract",
        request_key_ref="fixture://testing/request/1")
    verdict=simulate_testing_receiver(
        pg14_bridge=bridge,pg14_c1=c1,pg14_c2=c2,pg14_c3=c3,
        request_payload=c3["admission_request"])
    return locals()

class PG14ChainTests(unittest.TestCase):
    def test_positive_actual_pg13_c3_to_testing_candidate(self):
        x=make_chain()
        self.assertEqual(x["c1"]["source_pg13_c3_sha256"],x["prev"]["c3"]["candidate_sha256"])
        self.assertEqual(x["bridge"]["source_pg14_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c2"]["source_pg14_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg14_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["bridge"]["frozen_commit_sha"],x["prev"]["pg12"]["c1"]["candidate_commit_sha_reported"])
        self.assertEqual(x["verdict"]["verdict"],"ACCEPT")
        self.assertFalse(x["verdict"]["testing_real_invoked"])
        self.assertFalse(x["bridge"]["analysis_ready_verified"])
        self.assertFalse(x["c3"]["testing_request_sent"])
        self.assertFalse(x["c3"]["handoff_allowed"])
    def test_c1_missing_frozen_digest_blocked(self):
        x=make_chain()
        with self.assertRaises(C1Blocked):
            prepare_pg14_c1(pg13_c3=x["prev"]["c3"],admission_contract=contract(),
                analysis_package_ref=x["analysis"]["package_ref"],
                analysis_package_sha256=x["analysis"]["package_sha256"],
                source_currentness_ref=x["analysis"]["source_currentness_ref"],
                frozen_candidate_ref="fixture://frozen",frozen_candidate_sha256=None)
    def test_c1_missing_analysis_digest_blocked(self):
        x=make_chain()
        with self.assertRaises(C1Blocked):
            prepare_pg14_c1(pg13_c3=x["prev"]["c3"],admission_contract=contract(),
                analysis_package_ref=x["analysis"]["package_ref"],
                analysis_package_sha256=None,
                source_currentness_ref=x["analysis"]["source_currentness_ref"],
                frozen_candidate_ref="fixture://frozen",
                frozen_candidate_sha256=x["prev"]["c3"]["source_pg12_c1_sha256"])
    def test_c1_mismatched_frozen_digest_blocked(self):
        x=make_chain()
        with self.assertRaisesRegex(C1Blocked,"C1_FROZEN_IDENTITY_DRIFT"):
            prepare_pg14_c1(pg13_c3=x["prev"]["c3"],admission_contract=contract(),
                analysis_package_ref=x["analysis"]["package_ref"],
                analysis_package_sha256=x["analysis"]["package_sha256"],
                source_currentness_ref=x["analysis"]["source_currentness_ref"],
                frozen_candidate_ref="fixture://frozen",frozen_candidate_sha256="a"*64)
    def test_c1_execution_contract_drift_blocked(self):
        x=make_chain();c=contract()
        c["modes"]["EXECUTION"]["requires"]=["analysis_package_ref"]
        with self.assertRaisesRegex(C1Blocked,"MODE_EXECUTION_CONTRACT_DRIFT"):
            prepare_pg14_c1(pg13_c3=x["prev"]["c3"],admission_contract=c,
                analysis_package_ref=x["analysis"]["package_ref"],
                analysis_package_sha256=x["analysis"]["package_sha256"],
                source_currentness_ref=x["analysis"]["source_currentness_ref"],
                frozen_candidate_ref="fixture://frozen",
                frozen_candidate_sha256=x["prev"]["c3"]["source_pg12_c1_sha256"])
    def test_bridge_mismatched_annotated_tag_blocked(self):
        x=make_chain()
        with self.assertRaisesRegex(PG14BridgeBlocked,"FROZEN_TAG_DRIFT"):
            bridge_pg13_to_pg14(pg12_c1=x["prev"]["pg12"]["c1"],
                pg13_bridge=x["prev"]["bridge"],pg13_c1=x["prev"]["c1"],
                pg13_c2=x["prev"]["c2"],pg13_c3=x["prev"]["c3"],
                pg14_c1=x["c1"],freeze_tag_ref="refs/tags/frozen/"+"f"*40,
                freeze_tag_oid="e"*40,analysis_package_observation=x["analysis"])
    def test_bridge_wrong_analysis_sha_even_if_c1_unmodified_blocked(self):
        x=make_chain();ob=copy.deepcopy(x["analysis"])
        ob["package_sha256"]="f"*64
        with self.assertRaisesRegex(PG14BridgeBlocked,"ANALYSIS_PACKAGE_DRIFT"):
            bridge_pg13_to_pg14(pg12_c1=x["prev"]["pg12"]["c1"],
                pg13_bridge=x["prev"]["bridge"],pg13_c1=x["prev"]["c1"],
                pg13_c2=x["prev"]["c2"],pg13_c3=x["prev"]["c3"],
                pg14_c1=x["c1"],freeze_tag_ref=x["bridge"]["freeze_tag_ref_reported"],
                freeze_tag_oid=x["bridge"]["freeze_tag_oid_reported"],
                analysis_package_observation=ob)
    def test_c2_missing_b2b_obligation_blocked(self):
        x=make_chain();bad=copy.deepcopy(x["c2args"])
        bad["spec_test_obligations"][0]["obligation_ref"]="OTHER"
        with self.assertRaisesRegex(C2Blocked,"B2B_RULE_TEST_001_REQUIRED"):
            prepare_pg14_c2(**bad)
    def test_c2_wrong_blind_test_contract_blocked(self):
        x=make_chain();bad=copy.deepcopy(x["c2args"])
        bad["blind_test_contract_ref"]="unapproved-contract"
        with self.assertRaises(C2Blocked):prepare_pg14_c2(**bad)
    def test_c2_missing_catalog_blocked(self):
        x=make_chain();bad=copy.deepcopy(x["c2args"])
        bad["catalog_version_ref"]=""
        with self.assertRaises(C2Blocked):prepare_pg14_c2(**bad)
    def test_c2_empty_copy_list_is_blocked_by_receiver(self):
        x=make_chain();bad=copy.deepcopy(x["c2args"])
        bad["pending_copy_texts"]=[]
        c2=prepare_pg14_c2(**bad)
        c3=prepare_pg14_c3(pg14_c2=c2,
            testing_admission_endpoint_ref="fixture://testing/local-only",
            readback_contract_ref="fixture://readback/contract",
            request_key_ref="fixture://testing/request/1")
        r=simulate_testing_receiver(pg14_bridge=x["bridge"],pg14_c1=x["c1"],
            pg14_c2=c2,pg14_c3=c3,request_payload=c3["admission_request"])
        self.assertEqual(r["verdict"],"BLOCK")
    def test_c3_tampered_request_local_block(self):
        x=make_chain();bad=copy.deepcopy(x["c3"]["admission_request"])
        bad["frozen_candidate_sha256_reported"]="f"*64
        r=simulate_testing_receiver(pg14_bridge=x["bridge"],pg14_c1=x["c1"],
            pg14_c2=x["c2"],pg14_c3=x["c3"],request_payload=bad)
        self.assertEqual(r["verdict"],"BLOCK")
        self.assertFalse(r["testing_real_invoked"])
    def test_c3_no_real_testing_authority(self):
        x=make_chain()
        for name in ("c1","c2","c3","bridge"):
            self.assertFalse(x[name]["production_authority"])
            self.assertFalse(x[name]["handoff_allowed"])
        self.assertFalse(x["c3"]["testing_readback_executed"])
if __name__=="__main__":unittest.main()
