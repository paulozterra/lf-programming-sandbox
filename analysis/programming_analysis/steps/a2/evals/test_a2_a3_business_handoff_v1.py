"""Business-scoped A2->A3 handoff synthetic tests; NEVER native judge receipts."""
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("handoff", ROOT/"adapters/a2_a3_business_handoff_v1.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
prepare_candidate = mod.prepare_candidate

def inputs():
    a1 = {"schema_version":"A1_INTERNAL_STEP_CANDIDATE_RESULT_V1",
          "skill_code":"PROGRAMMING_ANALYSIS_LF","status":"VALID_OUTPUT","business":"LF",
          "payload":{"schema_version":"REQUEST_CONTEXT_V1","target_hints":["B2B-AUTH-001"],
                     "source_refs":["user://origin"],"provided_facts":[],
                     "objective":{"problem_statement":"Revisar login B2B","desired_outcome":"Identificar brechas"},
                     "constraints":["READ_ONLY"]}}
    a2 = {"schema_version":"A2_INTERNAL_STEP_CANDIDATE_RESULT_V1",
          "skill_code":"PROGRAMMING_ANALYSIS_LF","business":"LF","status":"CANDIDATE_UNATTESTED",
          "classification":{"schema_version":"ANALYSIS_CHANGE_CLASSIFICATION_V1",
                            "target_ref":"B2B-AUTH-001","depth_level":"L2"}}
    return a1,a2

class BusinessHandoff(unittest.TestCase):
    def test_positive_candidate_only(self):
        a1,a2=inputs(); r=prepare_candidate(a1,a2,"LF")
        self.assertEqual(r["business"],"LF")
        self.assertEqual(set(r["a3_inputs"]),{"REQUEST_CONTEXT_V1","ANALYSIS_CHANGE_CLASSIFICATION_V1"})
        self.assertEqual(r["research_brief"]["product"]["state"],"UNKNOWN")
        self.assertFalse(r["a3_allowed"])
        self.assertFalse(r["judge_verified"])
        self.assertIsNone(r["next_step"])

    def test_lf_to_saly_blocks(self):
        a1,a2=inputs(); a2["business"]="SALY"
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["CROSS_BUSINESS_HANDOFF_FORBIDDEN"])

    def test_missing_business_a1_blocks(self):
        a1,a2=inputs(); a1["business"]=None
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["BUSINESS_SCOPE_UNRESOLVED"])

    def test_missing_business_a2_blocks(self):
        a1,a2=inputs(); del a2["business"]
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["CROSS_BUSINESS_HANDOFF_FORBIDDEN"])

    def test_wrong_authority_business_blocks(self):
        a1,a2=inputs()
        self.assertEqual(prepare_candidate(a1,a2,"SALY")["blocking_codes"],["CROSS_BUSINESS_HANDOFF_FORBIDDEN"])

    def test_conflicting_business_fact_blocks(self):
        a1,a2=inputs();a1["payload"]["provided_facts"]=[{"fact_code":"BUSINESS_CODE","value":"SALY","source_ref":"user://origin"}]
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["BUSINESS_IDENTITY_FACT_CONFLICT"])

    def test_target_not_in_a1_blocks(self):
        a1,a2=inputs();a2["classification"]["target_ref"]="SALY-OTHER"
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["A3_TARGET_NOT_BOUND_TO_A1"])

    def test_product_module_only_when_supplied(self):
        a1,a2=inputs();a1["payload"]["provided_facts"]=[
            {"fact_code":"PRODUCT_NAME","value":"B2B","source_ref":"user://origin"},
            {"fact_code":"MODULE_NAME","value":"Login","source_ref":"user://origin"}]
        r=prepare_candidate(a1,a2,"LF")
        self.assertEqual(r["research_brief"]["product"]["state"],"DECLARED_UNATTESTED")
        self.assertEqual(r["research_brief"]["module"]["value"],"Login")

    def test_product_unbound_source_blocks(self):
        a1,a2=inputs();a1["payload"]["provided_facts"]=[
            {"fact_code":"PRODUCT_NAME","value":"Inventado","source_ref":"other://missing"}]
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["SPECIFICATION_SOURCE_INVALID"])

    def test_duplicate_module_blocks(self):
        a1,a2=inputs();a1["payload"]["provided_facts"]=[
            {"fact_code":"MODULE_NAME","value":"Login","source_ref":"user://origin"},
            {"fact_code":"MODULE_NAME","value":"Otra","source_ref":"user://origin"}]
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["IDENTITY_FACT_CONFLICT_OR_DUPLICATE"])

    def test_malformed_source_reference_fail_closed(self):
        a1,a2=inputs();a1["payload"]["source_refs"]=[{"unhashable":"injection"}]
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["A3_SOURCE_REFS_MISSING"])

    def test_schema_rejects_claimed_a3_activation(self):
        from jsonschema import Draft202012Validator
        import json
        a1,a2=inputs();r=prepare_candidate(a1,a2,"LF")
        r["a3_allowed"]=True
        schema=json.loads((ROOT/"adapters/a2_a3_business_handoff_v1.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(Draft202012Validator(schema).is_valid(r))

    def test_name_and_code_both_legitimate(self):
        a1,a2=inputs();a1["payload"]["provided_facts"]=[
            {"fact_code":"MODULE_NAME","value":"Login","source_ref":"user://origin"},
            {"fact_code":"MODULE_CODE","value":"AUTH-001","source_ref":"user://origin"}]
        r=prepare_candidate(a1,a2,"LF")
        self.assertEqual(r["research_brief"]["module"]["value"],"Login")
        self.assertEqual(len(r["research_brief"]["declared_facts"]),2)

    def test_inputs_immutable_and_no_forged_pass(self):
        a1,a2=inputs();aa,bb=copy.deepcopy(a1),copy.deepcopy(a2)
        a2["independent_judge_verified"]=True
        r=prepare_candidate(a1,a2,"LF")
        self.assertFalse(r["judge_verified"]);self.assertFalse(r["a3_allowed"])
        self.assertEqual(a1,aa)
        r["a3_inputs"]["REQUEST_CONTEXT_V1"]["target_hints"].append("TAMPER")
        self.assertEqual(a1,aa)

    def test_no_handoff_after_failed_a2(self):
        a1,a2=inputs();a2["status"]="BLOCKED"
        self.assertEqual(prepare_candidate(a1,a2,"LF")["blocking_codes"],["A2_HANDOFF_INVALID"])

    def test_related_business_no_scope_rewrite(self):
        a1,a2=inputs();a1["payload"]["provided_facts"]=[
            {"fact_code":"RELATED_BUSINESS","value":"SALY","source_ref":"user://origin"}]
        r=prepare_candidate(a1,a2,"LF")
        self.assertEqual(r["business"],"LF")
        self.assertFalse(r["a3_allowed"])
