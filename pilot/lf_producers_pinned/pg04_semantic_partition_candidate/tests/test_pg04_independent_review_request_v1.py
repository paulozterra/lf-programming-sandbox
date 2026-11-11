"""PG04 C7 preflight regression tests: shape != independent authorization."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pg04_independent_review_request_v1 import prepare_partition_review_request, ReviewRequestBlocked
from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome
from test_pg04_semantic_partition_candidate_v1 import args

def baseline():
    partition=partition_by_semantic_outcome(**args())
    sources={k:{"ref":"fixture://"+k,"sha256":"a"*64} for k in
             ("a9_package","pg03_strategy","pg04_partition_contract","outcome_registry","typed_obligations")}
    sources["pg03_strategy"]["sha256"]=partition["strategy_sha256"]
    sources["source_head_sha"]="b"*40
    return {"partition":partition,"sources":sources,"producer_execution_id":"producer-fixture"}

class ReviewPreflightTests(unittest.TestCase):
    def reject(self,code,mutate):
        p=baseline();mutate(p)
        with self.assertRaisesRegex(ReviewRequestBlocked,"^"+code+"$"):
            prepare_partition_review_request(**p)
    def test_positive_untrusted(self):
        p=prepare_partition_review_request(**baseline())
        self.assertEqual(p["subject_type"],"PG04_SOLUTION_PARTITION_CANDIDATE")
        self.assertEqual(p["solution_ids"],["SOL-001","SOL-002"])
        self.assertEqual(len(p["required_assertions"]),8)
        self.assertEqual(p["status"],"CANDIDATE_NOT_ADMITTED")
        self.assertIsNone(p["reviewer_execution_id"])
        for x in ("review_execution_allowed","production_authority","handoff_allowed",
                  "semantic_judge_executed","source_readback_verified",
                  "ledger_receipt_verified","reviewer_independence_attested"):
            self.assertIs(p[x],False)
    def test_unicode_partition_subject_digest(self):
        p=baseline()
        p["partition"]["solutions"][0]["business_outcome"]="Confirmación de pago"
        p["partition"]["candidate_sha256"]=hashlib.sha256(json.dumps(
            {k:v for k,v in p["partition"].items() if k!="candidate_sha256"},
            sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
        packet=prepare_partition_review_request(**p)
        self.assertEqual(packet["subject_sha256"],hashlib.sha256(json.dumps(
            p["partition"],sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest())
        self.assertFalse(packet["review_execution_allowed"])
    def test_generic_assurance_receipt_is_explicitly_missing(self):
        p=prepare_partition_review_request(**baseline())
        self.assertIsNone(p["subject_receipt_id"])
        self.assertEqual(p["subject_ref"],"PG04_SOLUTION_PARTITION_CANDIDATE/"+p["candidate_sha256"])
        self.assertEqual(p["first_runtime_blocker"],"PG04_VERIFIED_SUBJECT_RECEIPT_MISSING")
        self.assertIn("EVIDENCE_LEDGER_VERIFIED_SUBJECT_RECEIPT",p["required_runtime_binding"])
        self.assertFalse(p["review_execution_allowed"])
    def test_determinism(self):
        self.assertEqual(prepare_partition_review_request(**baseline()),prepare_partition_review_request(**baseline()))
    def test_deepcopy_manifest(self):
        p=baseline();out=prepare_partition_review_request(**p)
        original=copy.deepcopy(out["source_manifest"])
        p["sources"]["a9_package"]["ref"]="tampered"
        self.assertEqual(original,out["source_manifest"])
    def test_partition_mutation(self):
        self.reject("PARTITION_DIGEST_DRIFT",lambda p:p["partition"]["solutions"][0].update(business_outcome="FORGED"))
    def test_partition_digest_missing(self):
        self.reject("PARTITION_DIGEST_INVALID",lambda p:p["partition"].pop("candidate_sha256"))
    def test_partition_authority_escalation(self):
        self.reject("PARTITION_NOT_UNTRUSTED_CANDIDATE",lambda p:p["partition"].update(handoff_allowed=True))
    def test_judge_flag_forged(self):
        self.reject("PARTITION_NOT_UNTRUSTED_CANDIDATE",lambda p:p["partition"].update(semantic_judge_executed=True))
    def test_source_authenticity_claim(self):
        self.reject("PARTITION_NOT_UNTRUSTED_CANDIDATE",lambda p:p["partition"].update(source_authenticity="VERIFIED"))
    def test_source_manifest_missing(self):
        self.reject("REVIEW_SOURCE_MANIFEST_INCOMPLETE",lambda p:p["sources"].pop("a9_package"))
    def test_source_manifest_extra(self):
        self.reject("REVIEW_SOURCE_MANIFEST_INCOMPLETE",lambda p:p["sources"].update(extra="f"))
    def test_source_digest_invalid(self):
        self.reject("REVIEW_SOURCE_BINDING_INVALID",lambda p:p["sources"]["typed_obligations"].update(sha256="wrong"))
    def test_source_head_invalid(self):
        self.reject("REVIEW_SOURCE_HEAD_INVALID",lambda p:p["sources"].update(source_head_sha="main"))
    def test_source_strategy_sha_drift(self):
        self.reject("REVIEW_STRATEGY_SOURCE_DRIFT",lambda p:p["sources"]["pg03_strategy"].update(sha256="f"*64))
    def test_producer_missing(self):
        self.reject("PRODUCER_ID_MISSING",lambda p:p.update(producer_execution_id=""))
    def test_solution_strategy_ref_drift(self):
        p=baseline()
        p["partition"]["solutions"][0]["strategy_ref"]="f"*64
        p["partition"]["candidate_sha256"]=hashlib.sha256(json.dumps(
            {k:v for k,v in p["partition"].items() if k!="candidate_sha256"},
            sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        self.reject("PARTITION_SOLUTION_BINDING_DRIFT",lambda d:d.update(p))
if __name__=="__main__":
    unittest.main()
