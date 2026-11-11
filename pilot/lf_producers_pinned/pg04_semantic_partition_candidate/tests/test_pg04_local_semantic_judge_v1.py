"""Local model response checks are structural; they do NOT prove semantic correctness."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pg04_local_semantic_judge_v1 import build_review_bundle,prompt_for,validate_response,CRITERIA
from pg_programming_offline_lab_v1 import _strategy,PACKET
from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome

def sample():
    p=json.loads(PACKET.read_text(encoding="utf-8"))
    part=partition_by_semantic_outcome(strategy=_strategy(p),
        partition_contract=p["partition_contract"],obligations=p["obligations"],
        outcome_registry=p["outcome_registry"])
    bundle=build_review_bundle(p,part)
    rows=[{"criterion":name,"result":"PASS","evidence_paths":["/partition/solutions/0"],
           "rationale":"Coherent synthetic sample; no external source attestation"} for name in CRITERIA]
    response={"schema_version":"PG04_LOCAL_JUDGE_RESPONSE_V1",
              "bundle_sha256":bundle["bundle_sha256"],
              "verdict":"PASS","criteria":rows,"blocking_findings":[]}
    return p,part,bundle,response

class Tests(unittest.TestCase):
    def test_prompt_and_freeze_are_deterministic(self):
        a=sample()[2]
        self.assertEqual(a,sample()[2])
        self.assertIn("BUNDLE INMUTABLE",prompt_for(a))

    def test_shape_pass_never_grants_authority(self):
        _,_,b,r=sample()
        output=validate_response(r,b)
        self.assertEqual(output["review_output_shape"],"PASS")
        self.assertEqual(output["model_reported_verdict"],"PASS")
        for flag in ("semantic_correctness_independently_verified","provider_attested",
                     "independence_attested","official_judge_executed",
                     "production_authority","checkpoint_closure_allowed"):
            self.assertIs(output[flag],False)

    def test_wrong_frozen_digest_rejected(self):
        _,_,b,r=sample()
        r["bundle_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_BUNDLE_BINDING_INVALID"):
            validate_response(r,b)

    def test_missing_criterion_rejected(self):
        _,_,b,r=sample()
        r["criteria"].pop()
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_CRITERIA_INCOMPLETE"):
            validate_response(r,b)

    def test_duplicate_criterion_rejected(self):
        _,_,b,r=sample()
        r["criteria"][1]["criterion"]=r["criteria"][0]["criterion"]
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_CRITERION_INVALID"):
            validate_response(r,b)

    def test_fake_json_pointer_rejected(self):
        _,_,b,r=sample()
        r["criteria"][0]["evidence_paths"]=["/not/a/real/source"]
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_EVIDENCE_INVALID"):
            validate_response(r,b)

    def test_fake_pass_when_one_criterion_fails_rejected(self):
        _,_,b,r=sample()
        r["criteria"][0]["result"]="FAIL"
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_VERDICT_CONTRADICTORY"):
            validate_response(r,b)

    def test_inconclusive_supported_without_authority(self):
        _,_,b,r=sample()
        r["criteria"][0]["result"]="INCONCLUSIVE"
        r["verdict"]="INCONCLUSIVE"
        out=validate_response(r,b)
        self.assertEqual(out["model_reported_verdict"],"INCONCLUSIVE")
        self.assertFalse(out["checkpoint_closure_allowed"])

    def test_refuse_non_synthetic_payload(self):
        p,part,_,_=sample()
        p["simulation_only"]=False
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_SYNTHETIC_PACKET_ONLY"):
            build_review_bundle(p,part)

    def test_partition_digest_tamper(self):
        p,part,_,_=sample()
        part["solutions"][0]["business_outcome"]="changed after freeze"
        with self.assertRaisesRegex(ValueError,"LOCAL_JUDGE_PARTITION_DIGEST_DRIFT"):
            build_review_bundle(p,part)

if __name__=="__main__":
    unittest.main()
