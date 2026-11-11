"""Mechanical judge negatives for consolidated A5 Front/Back rule profiles."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,rel):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
a5=load("a5_rule_judge_consumer","validators/run.py")
fixture=load("a5_rule_judge_fixture","evals/test_a5_material_decisions_v1.py")
layers=load("a5_rule_judge_binding","evals/test_a5_rule_layer_consolidation_v1.py")
judge=load("a5_rule_layer_parity_judge","judges/rule_layer_parity_v1.py")


def pair():
    source=fixture.full_input()
    sidecar=fixture.sidecar()
    return source,sidecar,a5.run(source,sidecar)


class A5RuleLayerJudgeTests(unittest.TestCase):
    def test_original_four_rule_cards_pass(self):
        a,b,c=pair()
        r=judge.judge(a,c,b)
        self.assertEqual(r["verdict"],"PASS",r["violations"])
        self.assertEqual(r["rules_checked"],4)
        self.assertFalse(r["independent_semantic_review"])

    def test_shared_candidate_provenance_passes_without_attestation(self):
        a,b,c=pair()
        b["rule_layer_bindings"]=[
            layers.layer_bind(layer="FRONTEND",responsibility="Mostrar estado del login."),
            layers.layer_bind(layer="BACKEND",responsibility="Validar el acceso en servidor."),
        ]
        c=a5.run(a,b)
        r=judge.judge(a,c,b)
        self.assertEqual(r["verdict"],"PASS",r["violations"])
        self.assertFalse(r["source_attested"])

    def test_deleted_rule_is_detected(self):
        a,b,c=pair()
        c["rule_profiles"]["rules"].pop()
        r=judge.judge(a,c,b)
        self.assertIn("RULE_CARDINALITY_OR_IDENTITY_LOSS",r["violations"])

    def test_fake_shared_layer_without_source_is_detected(self):
        a,b,c=pair()
        p=c["rule_profiles"]["rules"][0]
        p["layer_classification"]="SHARED_CANDIDATE"
        r=judge.judge(a,c,b)
        self.assertIn("FALSE_FRONT_BACK_CLASSIFICATION:"+p["rule_code"],r["violations"])

    def test_falsified_source_rule_data_is_detected(self):
        a,b,c=pair()
        p=c["rule_profiles"]["rules"][0]
        p["rule_source_row"]["title"]="Invented"
        r=judge.judge(a,c,b)
        self.assertIn("RULE_SOURCE_ROW_LOSS:"+p["rule_code"],r["violations"])

    def test_layer_responsibility_mutation_is_detected(self):
        a,b,c=pair()
        b["rule_layer_bindings"]=[layers.layer_bind()]
        c=a5.run(a,b)
        p=next(x for x in c["rule_profiles"]["rules"] if x["rule_code"]=="AUTH-CRED-01")
        p["layers"]["FRONTEND"]["responsibility"]="Atribución inventada"
        r=judge.judge(a,c,b)
        self.assertIn("LAYER_RESPONSIBILITY_MUTATED:AUTH-CRED-01:FRONTEND",r["violations"])

    def test_missing_identity_remains_visible_for_old_excluded_fixture(self):
        old=load("a5_legacy_fixture","evals/test_a5_decision_adr_v1.py")
        data=old.inputs()
        sidecar=old.packet()
        out=a5.run(data,sidecar)
        r=judge.judge(data,out,sidecar)
        self.assertEqual(r["verdict"],"PASS",r["violations"])
        self.assertEqual(len(out["rule_profiles"]["unresolved_rule_identities"]),1)


if __name__=="__main__":
    unittest.main()
