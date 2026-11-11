import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

RUN = load(ROOT / "validators/run.py", "a1_skill_run")
JUDGE = load(ROOT / "judges/semantic_guard.py", "a1_skill_judge")


def valid():
    return json.loads((ROOT / "fixtures/valid_lf.json").read_text(encoding="utf-8"))


class SkillA1Tests(unittest.TestCase):
    def test_01_valid_lf(self):
        r = RUN.run(valid())
        self.assertEqual(r["status"], "VALID_OUTPUT")
        self.assertEqual(r["payload"]["schema_version"], "REQUEST_CONTEXT_V1")
        self.assertEqual(r["next_capability"], "A2")
        self.assertFalse(r["operationally_integrated"])
        self.assertEqual(JUDGE.check(valid(), r), [])

    def test_02_no_profile_or_run_required(self):
        r = RUN.run(valid())
        self.assertNotIn("profile_code", r)
        self.assertNotIn("execution_id", r)
        self.assertNotIn("profile_code", r["payload"])

    def test_03_source_identity_preserved(self):
        x=valid();r=RUN.run(x)
        self.assertEqual(r["payload"]["provided_facts"], x["provided_facts"])
        self.assertFalse(r["external_authority_verified"])

    def test_04_material_open_question(self):
        x=valid();x["ambiguities"]=[{"code":"OPEN-1","statement":"Quién autoriza la regla","materiality":"MATERIAL","resolution_state":"OPEN"}]
        r=RUN.run(x)
        self.assertEqual(r["status"],"REQUIRES_DECISION")
        self.assertIsNone(r["next_capability"])

    def test_05_missing_target(self):
        x=valid();x["target_hints"]=[]
        r=RUN.run(x)
        self.assertEqual(r["status"],"NEED_MORE_EVIDENCE")
        self.assertIn("TARGET_HINT_MISSING",r["blocking_codes"])

    def test_06_lf_to_saly_fail_closed(self):
        x=valid();x["business"]="SALY"
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertTrue(any("BUSINESS_BINDING_NOT_QUALIFIED" in c for c in r["blocking_codes"]))

    def test_07_no_source_invention(self):
        x=valid();r=RUN.run(x)
        r["payload"]["source_refs"].append("forged://authority")
        self.assertIn("SOURCE_REF_INVENTED",JUDGE.check(x,r))

    def test_08_no_target_invention(self):
        x=valid();r=RUN.run(x)
        r["payload"]["target_hints"].append("OTHER")
        self.assertIn("TARGET_INVENTED",JUDGE.check(x,r))

    def test_09_objective_rewrite_rejected(self):
        x=valid();r=RUN.run(x)
        r["payload"]["objective"]["desired_outcome"]="Programar un backend"
        self.assertIn("OBJECTIVE_REWRITTEN",JUDGE.check(x,r))

    def test_10_fact_ref_not_declared(self):
        x=valid();x["provided_facts"][0]["source_ref"]="forged://ref"
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertIn("UNSUPPORTED_PROVIDED_FACT_REF",r["blocking_codes"])

    def test_11_immutable_source(self):
        x=valid();original=copy.deepcopy(x)
        RUN.run(x)
        self.assertEqual(x,original)

    def test_12_unknown_intent_stays_declared(self):
        r=RUN.run(valid())
        self.assertEqual(r["declared_intent_kind"],"UNKNOWN")
        self.assertNotIn("development_class",r)

    def test_13_invalid_fields_fail_closed(self):
        x=valid();x["unexpected"]="foo"
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")

    def test_14_prohibited_profile_injection(self):
        x=valid();x["profile_code"]="PERFIL-PROGRAMMING-ANALYSIS-LF"
        self.assertEqual(RUN.run(x)["status"],"BLOCKED")

    def test_15_false_runtime_claim(self):
        x=valid();r=RUN.run(x);r["effects_executed"]=True
        self.assertIn("FALSE_RUNTIME_OR_EFFECTS",JUDGE.check(x,r))

    def test_16_normalize_whitespace_and_deduplicate(self):
        x=valid();x["target_hints"]=[" B2B-AUTH-001 ","B2B-AUTH-001"]
        r=RUN.run(x)
        self.assertEqual(r["status"],"VALID_OUTPUT")
        self.assertEqual(r["payload"]["target_hints"],["B2B-AUTH-001"])

    def test_17_missing_essential_intent(self):
        x=valid();x["objective"]["desired_outcome"]="  "
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertIn("ESSENTIAL_OBJECTIVE_MISSING",r["blocking_codes"])

    def test_18_invalid_object(self):
        self.assertEqual(RUN.run(None)["status"],"BLOCKED")


    def test_19_literal_trace_and_semantic_review_required(self):
        from hashlib import sha256
        x=valid()
        x["original_request"]="Evalúa las reglas del login B2B e implementa lo que falta"
        x["input_mode"]="SEMANTIC_CANDIDATE"
        r=RUN.run(x)
        self.assertEqual(r["status"],"REQUIRES_SEMANTIC_REVIEW")
        self.assertEqual(r["original_request_sha256"],sha256(x["original_request"].encode("utf-8")).hexdigest())
        self.assertTrue(r["semantic_review_required"])
        self.assertEqual(r["interpretation_state"],"SEMANTIC_CANDIDATE_UNATTESTED")
        self.assertFalse(r["external_authority_verified"])
        self.assertIn("B2B-AUTH-001",r["normalized_prompt"])

    def test_20_semantic_candidate_without_literal_blocks(self):
        x=valid();x["input_mode"]="SEMANTIC_CANDIDATE"
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertTrue(any("ORIGINAL_LITERAL_REQUIRED" in c for c in r["blocking_codes"]))

    def test_21_explicit_saly_namespace_blocks_lf(self):
        x=valid();x["source_refs"].append("saly://clientes/1")
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertIn("CROSS_BUSINESS_SOURCE_REQUIRES_QUALIFIED_BINDING",r["blocking_codes"])

    def test_22_supabase_saly_namespace_blocks_lf(self):
        x=valid();x["source_refs"].append("supabase://saly.clientes/1")
        self.assertEqual(RUN.run(x)["status"],"BLOCKED")

    def test_23_name_and_code_received_reused_without_inventing(self):
        x=valid()
        x["provided_facts"].append({"fact_code":"SCREEN_NAME","value":"Inicio de sesión B2B","source_ref":x["source_refs"][0]})
        r=RUN.run(x)
        self.assertEqual(r["status"],"VALID_OUTPUT")
        self.assertIn("B2B-AUTH-001",r["normalized_prompt"])
        self.assertIn("Inicio de sesión B2B",r["normalized_prompt"])
        self.assertEqual(r["payload"]["provided_facts"],x["provided_facts"])
        self.assertEqual(JUDGE.check(x,r),[])

    def test_24_whitespace_in_source_ref_not_a_forgery(self):
        x=valid();x["source_refs"]=[" "+x["source_refs"][0]+" "]
        r=RUN.run(x)
        self.assertEqual(r["status"],"VALID_OUTPUT")
        self.assertEqual(r["payload"]["source_refs"],["user://analysis-a1-case-001"])
        self.assertEqual(JUDGE.check(x,r),[])

    def test_25_cross_namespace_casefold(self):
        x=valid();x["source_refs"].append("SALY://clientes/1")
        self.assertEqual(RUN.run(x)["status"],"BLOCKED")

    def test_26_malformed_source_array_fails_closed(self):
        x=valid();x["source_refs"]=[{"unexpected":"object"}]
        self.assertEqual(RUN.run(x)["status"],"BLOCKED")

    def test_27_guard_rejects_altered_original_sha(self):
        x=valid();x["original_request"]="Revisar login B2B"
        r=RUN.run(x)
        r["original_request_sha256"]="0"*64
        self.assertIn("ORIGINAL_REQUEST_PROVENANCE_MISMATCH",JUDGE.check(x,r))

    def test_28_guard_rejects_false_prompt(self):
        x=valid();r=RUN.run(x)
        r["normalized_prompt"]="Implementar otra cosa"
        self.assertIn("NORMALIZED_PROMPT_OBJECTIVE_MISMATCH",JUDGE.check(x,r))

    def test_29_guard_is_invoked_during_run(self):
        x=valid();fn=RUN._normalized_prompt
        try:
            RUN._normalized_prompt=lambda _: "Inventar otra solución"
            r=RUN.run(x)
            self.assertEqual(r["status"],"BLOCKED")
            self.assertIn("NORMALIZED_PROMPT_OBJECTIVE_MISMATCH",r["blocking_codes"])
        finally:
            RUN._normalized_prompt=fn

    def test_30_structured_no_raw_never_claims_semantic_attestation(self):
        r=RUN.run(valid())
        self.assertEqual(r["interpretation_state"],"PRESTRUCTURED_UNATTESTED")
        self.assertFalse(r["semantic_review_required"])
        self.assertIsNone(r["original_request_sha256"])

    def test_31_material_ambiguity_with_literal(self):
        x=valid();x["original_request"]="Evalúa el login y decide lo que falte"
        x["input_mode"]="SEMANTIC_CANDIDATE"
        x["ambiguities"]=[{"code":"OPEN-AUTH","statement":"Falta decidir alcance","materiality":"MATERIAL","resolution_state":"OPEN"}]
        r=RUN.run(x)
        self.assertEqual(r["status"],"REQUIRES_DECISION")
        self.assertIsNone(r["next_capability"])
        self.assertTrue(r["semantic_review_required"])

    def test_32_empty_literal_blocks(self):
        x=valid();x["original_request"]="   "
        r=RUN.run(x)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertTrue(any("ORIGINAL_LITERAL_EMPTY" in c for c in r["blocking_codes"]))

    def test_33_input_literal_is_not_rewritten(self):
        x=valid();x["original_request"]="Evalúa la talla de login e inmolementa lo que falta"
        original=copy.deepcopy(x)
        r=RUN.run(x)
        self.assertEqual(x,original)
        self.assertEqual(r["interpretation_state"],"SEMANTIC_CANDIDATE_UNATTESTED")
        self.assertFalse(r["external_authority_verified"])


    def test_34_unattested_semantic_candidate_no_automatic_handoff(self):
        x=valid();x["original_request"]="Evalúa el login B2B e implementa lo que falta"
        x["input_mode"]="SEMANTIC_CANDIDATE"
        r=RUN.run(x)
        self.assertEqual(r["status"],"REQUIRES_SEMANTIC_REVIEW")
        self.assertIsNone(r["next_capability"])
        self.assertTrue(r["semantic_review_required"])

    def test_35_semantic_candidate_reuses_screen_code_and_both_actions(self):
        x=json.loads((ROOT / "fixtures/semantic_candidate_lf.json").read_text(encoding="utf-8"))
        r=RUN.run(x)
        self.assertEqual(r["status"],"REQUIRES_SEMANTIC_REVIEW")
        self.assertIn("B2B-AUTH-001",r["normalized_prompt"])
        self.assertIn("Inicio de sesión B2B",r["normalized_prompt"])
        self.assertIn("Evaluar",r["normalized_prompt"])
        self.assertIn("implementar",r["normalized_prompt"])
        self.assertEqual(r["payload"]["target_hints"],["B2B-AUTH-001"])
        self.assertIsNone(r["next_capability"])
        self.assertFalse(r["external_authority_verified"])



if __name__ == "__main__":
    unittest.main(verbosity=2)
