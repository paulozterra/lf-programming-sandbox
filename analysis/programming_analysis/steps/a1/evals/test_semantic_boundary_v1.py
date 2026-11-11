"""Synthetic consumer stand-ins: not a real model call or independent judge receipt."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "a1_semantic_boundary", ROOT / "semantic/semantic_boundary_v1.py"
)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def original():
    return json.loads((ROOT / "fixtures/semantic_original_context_v1.json").read_text(encoding="utf-8"))


def proposal(packet):
    out = json.loads((ROOT / "fixtures/semantic_model_candidate_fixture_v1.json").read_text(encoding="utf-8"))
    out["original_request_sha256"] = packet["original_request_sha256"]
    return out


def fixture():
    context = original()
    packet = M.prepare(context)
    model = proposal(packet)
    return context, packet, model


def review(candidate):
    return {
        "candidate_sha256": candidate["candidate_sha256"],
        "original_request_sha256": candidate["original_request_sha256"],
        "status": "PASS",
        "covered_action_ids": [r["id"] for r in candidate["observed_actions"]],
        "independently_observed_actions": [
            {"literal_span": r["literal_span"], "normalized_action": r["normalized_action"]}
            for r in candidate["observed_actions"]
        ],
        "unsupported_claims": [],
        "omitted_actions": [],
        "scope_expansions": [],
        "review_ref": "fixture://untrusted-judge-stand-in",
    }


class SemanticBoundaryTests(unittest.TestCase):
    def assert_block(self, packet, model, code):
        result = M.evaluate_model_candidate(packet, model)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertIn(code, result["blocking_codes"])
        self.assertFalse(result["semantic_verified"])
        self.assertIsNone(result["next_capability"])

    def test_01_prepare_preserves_literal_and_context(self):
        context=original();preserved=copy.deepcopy(context)
        packet=M.prepare(context)
        self.assertEqual(context,preserved)
        self.assertEqual(packet["business"],"LF")
        self.assertEqual(packet["original_request"],context["original_request"])
        self.assertEqual(packet["provided_facts"],context["provided_facts"])

    def test_02_model_standin_dual_actions_and_received_code(self):
        context,packet,model=fixture()
        r=M.evaluate_model_candidate(packet,model)
        self.assertEqual(r["status"],"REQUIRES_INDEPENDENT_SEMANTIC_REVIEW",r)
        self.assertEqual(len(r["observed_actions"]),2)
        self.assertEqual(r["a1_result"]["status"],"REQUIRES_SEMANTIC_REVIEW")
        self.assertIn("B2B-AUTH-001",r["a1_result"]["normalized_prompt"])
        self.assertIn("Inicio de sesión B2B",r["a1_result"]["normalized_prompt"])
        self.assertIsNone(r["next_capability"])
        self.assertFalse(r["operationally_verified"])

    def test_03_no_business_inference(self):
        x=original();x["business"]="SALY"
        self.assertEqual(M.prepare(x)["blocking_codes"],["BUSINESS_BINDING_NOT_QUALIFIED"])

    def test_04_no_original_source_ref(self):
        x=original();x["source_refs"]=[]
        self.assertEqual(M.prepare(x)["blocking_codes"],["PROVIDED_FACTS_PROVENANCE_INVALID"])

    def test_05_model_literal_hash_mismatch(self):
        _,p,m=fixture();m["original_request_sha256"]="0"*64
        self.assert_block(p,m,"MODEL_LITERAL_BINDING_MISMATCH")

    def test_06_model_drops_received_code(self):
        _,p,m=fixture();m["target_hints"]=[]
        self.assert_block(p,m,"RECEIVED_CONTEXT_DROPPED_TARGET_HINTS")

    def test_07_model_invents_code(self):
        _,p,m=fixture();m["target_hints"].append("B2B-AUTH-999")
        self.assert_block(p,m,"TARGET_IDENTIFIER_INVENTED")

    def test_08_model_invents_source(self):
        _,p,m=fixture();m["source_refs"].append("saly://cuentas/1")
        self.assert_block(p,m,"SOURCE_REF_INVENTED")

    def test_09_model_drops_given_fact(self):
        _,p,m=fixture();m["provided_facts"]=[]
        self.assert_block(p,m,"RECEIVED_FACTS_DROPPED")

    def test_10_model_invents_fact(self):
        _,p,m=fixture();m["provided_facts"].append({"fact_code":"APPROVED","value":True,"source_ref":m["source_refs"][0]})
        self.assert_block(p,m,"UNATTESTED_FACT_INVENTED")

    def test_11_model_drops_governance_constraint(self):
        _,p,m=fixture();m["constraints"]=[]
        self.assert_block(p,m,"RECEIVED_CONTEXT_DROPPED_CONSTRAINTS")

    def test_12_model_action_span_fabricated(self):
        _,p,m=fixture();m["observed_actions"][1]["literal_span"]="aplicar SQL"
        self.assert_block(p,m,"MODEL_ACTION_SPAN_NOT_GROUNDED")

    def test_13_model_no_actions(self):
        _,p,m=fixture();m["observed_actions"]=[]
        self.assert_block(p,m,"MODEL_ACTION_EVIDENCE_MISSING")

    def test_14_model_schema_extra_authority_field(self):
        _,p,m=fixture();m["authorization"]="APPROVED"
        self.assert_block(p,m,"MODEL_CANDIDATE_CONTRACT_INVALID")

    def test_15_judge_standin_is_not_independence_proof(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m)
        result=M.validate_review(c,review(c))
        self.assertEqual(result["status"],"REVIEW_STRUCTURAL_PASS_ONLY")
        self.assertFalse(result["independence_verified"])
        self.assertFalse(result["operationally_verified"])
        self.assertIsNone(result["next_capability"])

    def test_16_judge_fails_on_missing_action_coverage(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["covered_action_ids"]=["ACT-EVALUATE"]
        result=M.validate_review(c,r)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("REVIEW_ACTION_COVERAGE_MISMATCH",result["blocking_codes"])

    def test_17_judge_fails_on_unsupported_claim(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["unsupported_claims"]=["Code claimed CURRENT without authority"]
        self.assertIn("REVIEW_HAS_MATERIAL_FINDINGS",M.validate_review(c,r)["blocking_codes"])

    def test_18_judge_fails_on_omitted_implementation_action(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["omitted_actions"]=["implementar"]
        self.assertIn("REVIEW_HAS_MATERIAL_FINDINGS",M.validate_review(c,r)["blocking_codes"])

    def test_19_judge_fails_on_scope_expansion(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["scope_expansions"]=["deploy production"]
        self.assertIn("REVIEW_HAS_MATERIAL_FINDINGS",M.validate_review(c,r)["blocking_codes"])

    def test_20_judge_cannot_swap_candidate(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["candidate_sha256"]="0"*64
        self.assertIn("REVIEW_CANDIDATE_SHA_MISMATCH",M.validate_review(c,r)["blocking_codes"])

    def test_21_judge_cannot_swap_literal(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["original_request_sha256"]="0"*64
        self.assertIn("REVIEW_LITERAL_SHA_MISMATCH",M.validate_review(c,r)["blocking_codes"])

    def test_22_judge_fail_verdict_cannot_approve(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["status"]="FAIL"
        self.assertIn("REVIEW_VERDICT_NOT_PASS",M.validate_review(c,r)["blocking_codes"])

    def test_23_missing_judge_receipt_blocks(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m)
        self.assertIn("REVIEW_CONTRACT_INVALID",M.validate_review(c,None)["blocking_codes"])

    def test_24_no_model_output_blocks(self):
        _,p,_=fixture()
        self.assert_block(p,None,"MODEL_CANDIDATE_NOT_OBJECT")

    def test_25_no_trusted_context_blocks(self):
        result=M.evaluate_model_candidate({},proposal(M.prepare(original())))
        self.assertEqual(result["status"],"BLOCKED")

    def test_26_original_missing_blocks(self):
        x=original();x["original_request"]=""
        self.assertIn("ORIGINAL_LITERAL_MISSING",M.prepare(x)["blocking_codes"])

    def test_27_forged_issuer_claim_not_permitted(self):
        _,p,m=fixture();m["model_call_ref"]="fake://self"
        self.assert_block(p,m,"MODEL_CANDIDATE_CONTRACT_INVALID")


    def test_28_judge_independent_finds_extra_literal_action(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["independently_observed_actions"].append(
            {"literal_span":"reglas","normalized_action":"comprobar reglas"}
        )
        v=M.validate_review(c,r)
        self.assertEqual(v["status"],"BLOCKED")
        self.assertIn("INDEPENDENT_ACTION_RECONCILIATION_MISMATCH",v["blocking_codes"])

    def test_29_judge_independent_missing_implementation_action(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["independently_observed_actions"] = r["independently_observed_actions"][:1]
        v=M.validate_review(c,r)
        self.assertIn("INDEPENDENT_ACTION_RECONCILIATION_MISMATCH",v["blocking_codes"])

    def test_30_model_task_tamper_rejected(self):
        _,p,m=fixture();p["original_request"] += " Alterado"
        self.assert_block(p,m,"PREPARED_LITERAL_HASH_INVALID")

    def test_31_independent_action_fake_span_rejected(self):
        _,p,m=fixture();c=M.evaluate_model_candidate(p,m);r=review(c)
        r["independently_observed_actions"][0]["literal_span"]="desplegar a producción"
        v=M.validate_review(c,r)
        self.assertIn("INDEPENDENT_ACTION_EVIDENCE_INVALID",v["blocking_codes"])


    def test_32_missing_target_preserves_need_more_evidence(self):
        _,p,m=fixture()
        p["target_hints"]=[]
        m["target_hints"]=[]
        r=M.evaluate_model_candidate(p,m)
        self.assertEqual(r["status"],"NEED_MORE_EVIDENCE")
        self.assertIsNone(r["next_capability"])
        self.assertFalse(r["operationally_verified"])

    def test_33_material_ambiguity_preserves_decision(self):
        _,p,m=fixture()
        m["ambiguities"]=[{
            "code":"A1-SCOPE-OPEN",
            "statement":"El alcance de la implementación no está definido",
            "materiality":"MATERIAL",
            "resolution_state":"OPEN",
        }]
        r=M.evaluate_model_candidate(p,m)
        self.assertEqual(r["status"],"REQUIRES_DECISION")
        self.assertFalse(r["semantic_verified"])
        self.assertIsNone(r["next_capability"])


    def test_34_unhashable_model_intent_fails_closed(self):
        _,p,m=fixture()
        m["declared_intent_kind"]=["EVOLVE"]
        self.assert_block(p,m,"MODEL_INTENT_INVALID")


if __name__ == "__main__":
    unittest.main(verbosity=2)
