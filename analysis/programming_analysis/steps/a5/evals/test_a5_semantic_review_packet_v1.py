"""Contract-only semantic judge packet tests. No GPT verdict is generated."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def mod(name,relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
    return x
a5=mod("a5_semantic_input_consumer","validators/run.py")
example=mod("a5_semantic_example","evals/test_a5_material_decisions_v1.py")
packet_builder=mod("a5_semantic_packet","judges/semantic_review_packet_v1.py")


class A5SemanticPacketTests(unittest.TestCase):
    def test_source_sealed_every_item_in_batches(self):
        data=example.full_input();out=a5.run(data,example.sidecar())
        pkt=packet_builder.build(data,out,batch_size=5)
        self.assertEqual(pkt["total_items"],17)
        self.assertEqual([b["item_count"] for b in pkt["batches"]],[5,5,5,2])
        self.assertEqual(sum(b["item_count"] for b in pkt["batches"]),17)
        self.assertEqual(len({i for b in pkt["batches"] for i in b["item_ids"]}),17)
        self.assertFalse(pkt["independent_semantic_review"])
        self.assertFalse(pkt["reviewer_identity_attested"])
        self.assertIsNone(pkt["reviewer_verdict"])
        self.assertIsNone(pkt["case_specific_minimum_pending_decisions"])

    def test_reproducible_packets_and_evidence_change_invalidates_sha(self):
        data=example.full_input();out=a5.run(data,example.sidecar())
        a=packet_builder.build(data,out)
        b=packet_builder.build(deepcopy(data),deepcopy(out))
        self.assertEqual(a["packet_sha256"],b["packet_sha256"])
        changed=deepcopy(data)
        changed["TARGETED_EVIDENCE_SET_V1"]["policy_resolution"]["approved_policy_objects"][0]["config"]["attempt_limit"]=9
        updated=a5.run(changed,example.sidecar())
        c=packet_builder.build(changed,updated)
        self.assertNotEqual(a["packet_sha256"],c["packet_sha256"])

    def test_missing_item_and_invalid_batch_size_fail_closed(self):
        data=example.full_input();out=a5.run(data,example.sidecar())
        out["decision_items"].pop()
        with self.assertRaisesRegex(ValueError,"A5_SEMANTIC_MATERIAL_CARDINALITY_MISMATCH"):
            packet_builder.build(data,out)
        out=a5.run(data,example.sidecar())
        for value in (0,51,False):
            with self.assertRaisesRegex(ValueError,"A5_SEMANTIC_BATCH_SIZE_INVALID"):
                packet_builder.build(data,out,batch_size=value)

    def test_no_proof_of_independent_review_from_shape_only(self):
        data=example.full_input();out=a5.run(data,example.sidecar())
        packet=packet_builder.build(data,out)
        review={
            "schema_version":"A5_MATERIAL_SEMANTIC_REVIEW_V1",
            "packet_sha256":packet["packet_sha256"],
            "items":[{
                "item_id":x["decision_item_id"],
                "checks":[{
                    "check":check["check"],"verdict":"PASS",
                    "evidence_quotes":["synthetic untrusted assertion"]
                } for check in packet["checks"]]
            } for x in out["decision_items"]],
        }
        result=packet_builder.check_review_shape(packet,review)
        self.assertEqual(result["status"],"SHAPE_VALID_ONLY")
        self.assertFalse(result["independent_semantic_review"])
        review["packet_sha256"]="wrong"
        self.assertEqual(packet_builder.check_review_shape(packet,review)["status"],"BLOCKED")


if __name__=="__main__":
    unittest.main()
