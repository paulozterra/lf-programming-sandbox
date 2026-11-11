"""A5 per-rule Front/Back/Shared classification. Synthetic LF data only.

Prohibits rule-name keyword inference, invented layers, automatic policy
promotion, and hidden duplicate or source identity drift.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

a5=module("a5_rule_consumer","validators/run.py")
fixture=module("a5_rule_fixture","evals/test_a5_material_decisions_v1.py")
RULE1=fixture.RULE1
RULE2=fixture.RULE2
TARGET=fixture.TARGET


def layer_bind(rule="AUTH-CRED-01",ref=RULE1,layer="FRONTEND",
               applies="APPLIES",responsibility="Aplicar la regla de acceso en la interfaz."):
    return {"rule_code":rule,"rule_source_ref":ref,"layer":layer,
            "applicability":applies,"responsibility":responsibility if applies=="APPLIES" else None,
            "evidence_ref":ref,"source_attested":False}


def run(data=None, sidecar=None):
    return a5.run(data or fixture.full_input(),sidecar if sidecar is not None else fixture.sidecar())


def profile(out,code):
    return next(x for x in out["rule_profiles"]["rules"] if x["rule_code"]==code)


class A5RuleLayerTests(unittest.TestCase):
    def test_one_rule_profile_per_unique_code_not_per_a3_a4_occurrence(self):
        data=fixture.full_input()
        before=deepcopy(data)
        out=run(data)
        self.assertNotEqual(out["status"],"BLOCKED")
        x=out["rule_profiles"]
        self.assertEqual(x["rule_count"],4)
        self.assertEqual(x["source_rule_occurrence_count"],4)
        self.assertEqual(len({r["rule_code"] for r in x["rules"]}),4)
        p=profile(out,"AUTH-CRED-01")
        self.assertEqual(p["rule_source_ref"],RULE1)
        self.assertEqual(p["title"],"Validación de credenciales")
        self.assertEqual(len(p["material_item_ids"]),3)
        self.assertEqual(len(p["implementation_impacts"]),1)
        self.assertEqual(p["implementation_impacts"][0]["action"],"CREATE")
        self.assertEqual(p["implementation_impacts"][0]["definition_action"],"REUSE")
        self.assertEqual(data,before)
        self.assertFalse(out["a6_allowed"])

    def test_without_canonical_layer_evidence_front_back_both_unknown(self):
        out=run()
        self.assertEqual(out["rule_profiles"]["rule_layer_evidence_missing_count"],4)
        for r in out["rule_profiles"]["rules"]:
            self.assertEqual(r["layer_classification"],"UNKNOWN")
            self.assertEqual(r["unresolved_layer_evidence"],["FRONTEND","BACKEND"])
            self.assertTrue(all(x["applicability"]=="UNKNOWN" for x in r["layers"].values()))
            self.assertFalse(r["independent_semantic_review"])

    def test_frontend_only_requires_explicit_backend_negative(self):
        sidecar=fixture.sidecar()
        sidecar["rule_layer_bindings"]=[layer_bind(),
            layer_bind(layer="BACKEND",applies="NOT_APPLICABLE")]
        out=run(sidecar=sidecar)
        p=profile(out,"AUTH-CRED-01")
        self.assertEqual(p["layer_classification"],"FRONTEND_ONLY_CANDIDATE")
        self.assertEqual(p["unresolved_layer_evidence"],[])
        self.assertFalse(p["source_attested"])
        self.assertEqual(p["layers"]["BACKEND"]["applicability"],"NOT_APPLICABLE")
        sidecar["rule_layer_bindings"].pop()
        q=profile(run(sidecar=sidecar),"AUTH-CRED-01")
        self.assertEqual(q["layer_classification"],"UNKNOWN")
        self.assertEqual(q["unresolved_layer_evidence"],["BACKEND"])

    def test_backend_only_requires_explicit_frontend_negative(self):
        sidecar=fixture.sidecar()
        sidecar["rule_layer_bindings"]=[
            layer_bind(layer="FRONTEND",applies="NOT_APPLICABLE"),
            layer_bind(layer="BACKEND",responsibility="Aplicar la regla en servidor.")
        ]
        p=profile(run(sidecar=sidecar),"AUTH-CRED-01")
        self.assertEqual(p["layer_classification"],"BACKEND_ONLY_CANDIDATE")
        self.assertEqual(p["layers"]["FRONTEND"]["responsibility"],None)

    def test_shared_requires_both_layers_with_individual_responsibility(self):
        sidecar=fixture.sidecar()
        sidecar["rule_layer_bindings"]=[
            layer_bind(layer="FRONTEND",responsibility="Mostrar estado del acceso."),
            layer_bind(layer="BACKEND",responsibility="Aplicar la validación de acceso."),
        ]
        p=profile(run(sidecar=sidecar),"AUTH-CRED-01")
        self.assertEqual(p["layer_classification"],"SHARED_CANDIDATE")
        self.assertNotEqual(p["layers"]["FRONTEND"]["responsibility"],
                            p["layers"]["BACKEND"]["responsibility"])
        self.assertFalse(p["layers"]["FRONTEND"]["source_attested"])
        self.assertFalse(p["layers"]["BACKEND"]["semantic_review_verified"])

    def test_no_applicable_layer_is_visible_not_automatically_implemented(self):
        sidecar=fixture.sidecar()
        sidecar["rule_layer_bindings"]=[
            layer_bind(layer="FRONTEND",applies="NOT_APPLICABLE"),
            layer_bind(layer="BACKEND",applies="NOT_APPLICABLE"),
        ]
        p=profile(run(sidecar=sidecar),"AUTH-CRED-01")
        self.assertEqual(p["layer_classification"],"NO_APPLICABLE_LAYER_CANDIDATE")
        self.assertEqual(p["layer_verification_state"],
                         "CANDIDATE_REQUIRES_SOURCE_ATTESTATION_AND_SEMANTIC_REVIEW")

    def test_repeated_effective_rule_with_source_drift_blocks(self):
        data=fixture.full_input()
        data["TARGETED_EVIDENCE_SET_V1"]["excluded_rule_items"].append({
            "rule_code":"AUTH-CRED-01","rule_status":"CANDIDATO",
            "pending_decision":True,"source_ref":"supabase://lf_ops.reglas/999"
        })
        out=run(data)
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A5_RULE_LAYER_DUPLICATE_OR_CONFLICTING_RULE",out["blocking_codes"])

    def test_approved_rule_must_remain_vigente_no_pending(self):
        data=fixture.full_input()
        data["TARGETED_EVIDENCE_SET_V1"]["policy_scope_clear_rule_candidates"][0]["pending_decision"]=True
        out=run(data)
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A5_RULE_LAYER_APPROVED_RULE_STATE_CONFLICT",out["blocking_codes"])

    def test_rule_specific_policy_dependencies_are_exact_and_full(self):
        data=fixture.full_input()
        policy=data["TARGETED_EVIDENCE_SET_V1"]["policy_resolution"]
        policy["rule_policy_dependencies"]=[
            {"rule_code":"AUTH-CRED-01","policy_target_ref":"supabase://lf_ops.politicas/201",
             "policy_code":"POL-AUTH-01","status":"APPROVED_POLICY_AND_BINDING",
             "eligible_for_implementation":True,"reference_role":"security_policy_id"},
            {"rule_code":"AUTH-ERR-02","policy_target_ref":"supabase://lf_ops.politicas/888",
             "status":"POLICY_TARGET_MISSING","eligible_for_implementation":False}
        ]
        out=run(data)
        a=profile(out,"AUTH-CRED-01")
        self.assertEqual(len(a["policy_dependencies"]),1)
        self.assertEqual(a["policy_objects"][0]["config"]["attempt_limit"],5)
        self.assertEqual(profile(out,"AUTH-ERR-02")["policy_objects"],[])
        self.assertEqual(len(profile(out,"AUTH-ERR-02")["policy_dependencies"]),1)
        self.assertFalse(out["source_attested"])

    def test_layer_evidence_cannot_be_for_unrelated_rule_or_fake_source(self):
        p=fixture.sidecar()
        p["rule_layer_bindings"]=[layer_bind(ref=RULE2)]
        self.assertIn("A5_RULE_LAYER_BINDING_UNTRUSTED_OR_CONFLICTING",
                      run(sidecar=p)["blocking_codes"])
        p["rule_layer_bindings"]=[layer_bind()]
        p["rule_layer_bindings"][0]["evidence_ref"]="supabase://lf_ops.reglas/999"
        self.assertIn("A5_RULE_LAYER_BINDING_UNTRUSTED_OR_CONFLICTING",
                      run(sidecar=p)["blocking_codes"])

    def test_duplicate_layer_assertions_fail_closed(self):
        p=fixture.sidecar()
        p["rule_layer_bindings"]=[layer_bind(),layer_bind()]
        self.assertEqual(run(sidecar=p)["status"],"BLOCKED")

    def test_layer_applicability_cannot_be_claimed_without_behavior(self):
        p=fixture.sidecar()
        p["rule_layer_bindings"]=[layer_bind(responsibility="")]
        self.assertIn("A5_RULE_LAYER_BEHAVIOR_EVIDENCE_REQUIRED",
                      run(sidecar=p)["blocking_codes"])
        p["rule_layer_bindings"]=[layer_bind(applies="NOT_APPLICABLE")]
        p["rule_layer_bindings"][0]["responsibility"]="Unexpected"
        self.assertIn("A5_RULE_LAYER_BEHAVIOR_EVIDENCE_REQUIRED",
                      run(sidecar=p)["blocking_codes"])

    def test_unknown_impact_or_missing_code_path_never_becomes_shared(self):
        data=fixture.full_input()
        data["SHARED_CHANGE_IMPACT_ANALYSIS"]["target_code_destination"]=None
        p=profile(run(data),"AUTH-CRED-01")
        self.assertEqual(p["layer_classification"],"UNKNOWN")
        self.assertIsNone(p["code_destination"])
        self.assertEqual(p["implementation_impacts"][0]["action"],"CREATE")

    def test_excluded_and_deferred_rules_never_promoted_by_layer_readback(self):
        p=fixture.sidecar()
        p["rule_layer_bindings"]=[layer_bind(
            rule="AUTH-PENDING-04",ref="supabase://lf_ops.reglas/104")]
        result=run(sidecar=p)
        self.assertEqual(result["status"],"BLOCKED")
        # Excluded source is not in A3 source_refs: not valid implementation
        # evidence. The excluded rule remains visible and not implementable.
        q=profile(run(),"AUTH-PENDING-04")
        self.assertEqual(q["implementation_scope"],"EXCLUDED_PENDING")
        self.assertFalse(q["scope_approved_source_candidate"])

    def test_fingerprint_is_deterministic_and_changes_with_bindings(self):
        a=run()
        b=run()
        self.assertEqual(a["rule_profiles"]["fingerprint_sha256"],
                         b["rule_profiles"]["fingerprint_sha256"])
        p=fixture.sidecar();p["rule_layer_bindings"]=[layer_bind()]
        c=run(sidecar=p)
        self.assertNotEqual(a["rule_profiles"]["fingerprint_sha256"],
                            c["rule_profiles"]["fingerprint_sha256"])


if __name__=="__main__":
    unittest.main()
