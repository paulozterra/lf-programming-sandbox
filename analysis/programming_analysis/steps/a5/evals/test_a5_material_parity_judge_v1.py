"""A5 mechanical judge: pass unmodified projection; fail tampering/omissions."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import unittest

ROOT=Path(__file__).resolve().parents[1]

def load(name,rel):
    p=ROOT/rel
    spec=importlib.util.spec_from_file_location(name,p)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

a5=load("a5_judge_fixture_consumer","validators/run.py")
judge=load("a5_material_parity_judge","judges/material_parity_v1.py")
fixture=load("a5_material_example","evals/test_a5_material_decisions_v1.py")


class MaterialJudgeTests(unittest.TestCase):
    def test_exact_full_source_material_passes(self):
        data=fixture.full_input();sidecar=fixture.sidecar()
        out=a5.run(data,sidecar)
        verdict=judge.judge(data,out,sidecar)
        self.assertEqual(verdict["verdict"],"PASS",verdict["violations"])
        self.assertFalse(verdict["independent_semantic_review"])

    def test_deleting_one_item_fails(self):
        data=fixture.full_input()
        result=a5.run(data,fixture.sidecar())
        result["decision_items"].pop()
        verdict=judge.judge(data,result,fixture.sidecar())
        self.assertEqual(verdict["verdict"],"FAIL")
        self.assertIn("MATERIAL_ITEM_COUNT_NOT_PARITY",verdict["violations"])

    def test_mutating_rule_content_fails(self):
        data=fixture.full_input()
        result=a5.run(data,fixture.sidecar())
        row=next(x for x in result["decision_items"] if x["decision_item_id"]=="A3:policy_scope_clear_rule_candidates:0")
        row["source_payload"]["description"]="invented material"
        verdict=judge.judge(data,result,fixture.sidecar())
        self.assertIn("LOSSY_MATERIAL_PAYLOAD:A3:policy_scope_clear_rule_candidates:0",
                      verdict["violations"])

    def test_promoting_pending_rule_to_owner_fails(self):
        data=fixture.full_input()
        result=a5.run(data,fixture.sidecar())
        row=next(x for x in result["decision_items"] if x["decision_item_id"]=="A3:excluded_rule_items:0")
        row["owner_decision_required"]=True
        verdict=judge.judge(data,result,fixture.sidecar())
        self.assertEqual(verdict["verdict"],"FAIL")
        self.assertIn("FALSE_OWNER_DECISION:A3:excluded_rule_items:0",
                      verdict["violations"])

    def test_false_a6_admission_fails(self):
        data=fixture.full_input()
        result=a5.run(data,fixture.sidecar())
        result["a6_allowed"]=True
        verdict=judge.judge(data,result,fixture.sidecar())
        self.assertIn("FALSE_RUNTIME_ADMISSION",verdict["violations"])

    def test_hidden_missing_source_collections_fails(self):
        data=fixture.full_input()
        del data["TARGETED_EVIDENCE_SET_V1"]["policy_link_items"]
        result=a5.run(data,fixture.sidecar())
        result["material_ledger"]["missing_collections"]=[]
        verdict=judge.judge(data,result,fixture.sidecar())
        self.assertIn("MISSING_COLLECTIONS_HIDDEN",verdict["violations"])

    def test_mutated_decision_fingerprint_fails(self):
        data=fixture.full_input()
        result=a5.run(data,fixture.sidecar())
        result["decision_context"]["material_question"]="forged question"
        result["decisions"][0]["material_question"]="forged question"
        verdict=judge.judge(data,result,fixture.sidecar())
        self.assertIn("DECISION_FINGERPRINT_DRIFT",verdict["violations"])

if __name__=="__main__":
    unittest.main()
