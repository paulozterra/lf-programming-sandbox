"""A3 development checks: policy typing and partial inherited-rule scope.
No governed run, external read, or runtime/approval assertion.
"""
from __future__ import annotations
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

a3 = load("a3_development_consumer", "validators/run.py")
policy = load("a3_development_policy", "adapters/policy_readback_v1.py")
SCREEN = "B2B-AUTH-001"
REF = "supabase://lf_ops.pantallas/" + SCREEN
EFF = "supabase://programacion.fn_input_effective_rule_links_v1/51/INPUT_GOVERNANCE"

def inputs():
    context = {
        "schema_version": "REQUEST_CONTEXT_V1", "no_solution_inferred": True,
        "objective": {"problem_statement": "Implementar B2B-AUTH-001"},
        "constraints": ["Pendientes no bloquean alcance vigente"],
        "source_refs": ["user://request"], "target_hints": [SCREEN],
    }
    classification = {
        "schema_version": "ANALYSIS_CHANGE_CLASSIFICATION_V1",
        "target_ref": SCREEN, "target_granularity": "SCREEN",
    }
    return {"REQUEST_CONTEXT_V1": context,
            "ANALYSIS_CHANGE_CLASSIFICATION_V1": classification}

def policy_readback():
    table="lf_ops.politicas_seguridad"
    return {
        "schema_version":"LF_SCREEN_POLICIES_READBACK_V1",
        "source_function":"lf_ops.fn_screen_contract_v1",
        "business":"LF","target_ref":SCREEN,"source_ref":REF,
        "source_attested":False,
        "policy_objects":[{"table":table,"primary_key":"security_policy_id",
            "policy_id":1,"policy_code":"SEC-RLS","status":"VIGENTE",
            "parameters":{"enabled":True},
            "source_ref":"supabase://"+table+"/1","read_origin":"LF_SCREEN_CONTRACT",
            "read_source_ref":REF}],
        "supplemental_policy_source_refs":[],
    }

def sources():
    def row(code,pid,status,origin,config):
        return {"code":code,"status":status,"pending_decision":False,
            "source_ref":"supabase://lf_ops.reglas/"+str(pid),
            "binding_source":origin,"config":config}
    linked=[
        {"code":"RULE-A","status":"VIGENTE","pending_decision":False,
         "title":"Can login","source_ref":"supabase://lf_ops.reglas/1",
         "association_ref":"supabase://lf_ops.reglas_pantallas/1"},
        {"code":"RULE-B","status":"CANDIDATO","pending_decision":False,
         "title":"Future rule","source_ref":"supabase://lf_ops.reglas/2",
         "association_ref":"supabase://lf_ops.reglas_pantallas/2"},
    ]
    rules=[
        row("RULE-A",1,"VIGENTE","LEGACY_EXPLICIT",{}),
        row("RULE-B",2,"CANDIDATO","LEGACY_EXPLICIT",{}),
        row("RULE-C",3,"VIGENTE","DERIVED_GLOBAL",{}),
        row("RULE-D",4,"CANDIDATO","DERIVED_GLOBAL",{}),
    ]
    return {
        "schema_version":"LF_SCREEN_SOURCE_READBACK_V1",
        "business":"LF","source_function":"lf_ops.fn_screen_contract_v1",
        "target_ref":SCREEN,"screen_ref":REF,"screen_status":"CANDIDATO",
        "contract_version":"v1.2", "linked_rules":linked,
        "policy_links":[],
        "effective_rule_readback":{
            "screen_id":51,"source_function":"programacion.fn_input_effective_rule_links_v1",
            "business":"LF","target_ref":SCREEN,"consumer":"INPUT_GOVERNANCE",
            "source_ref":EFF,"source_attested":False,"rules":rules},
        "policy_resolution_readback":policy_readback(),
    }

class DevelopmentScope(unittest.TestCase):
    def test_pending_direct_and_inherited_do_not_block_source_scoping(self):
        out = a3.run(inputs(), sources())
        self.assertEqual(out["status"],"SOURCE_READBACK_PROCESSED_UNATTESTED")
        self.assertEqual(out["counts"]["effective_rules_total"],4)
        self.assertEqual(out["counts"]["effective_rules_vigente_no_pending"],2)
        self.assertEqual(out["counts"]["effective_rules_excluded"],2)
        self.assertEqual(out["counts"]["inherited_derived_global_excluded"],1)
        self.assertEqual(
            {r["rule_code"] for r in out["policy_scope_clear_rule_candidates"]},
            {"RULE-A","RULE-C"})
        self.assertEqual(
            {r["rule_code"] for r in out["excluded_rule_items"]},
            {"RULE-B","RULE-D"})
        self.assertFalse(out["a4_allowed"])
        self.assertFalse(out["source_attested"])

    def test_unapproved_policy_binding_defers_only_dependent_rule(self):
        base=sources()
        base["effective_rule_readback"]["rules"][0]["config"]={"security_policy_id":1}
        base["policy_links"]=[{
            "source_ref":"supabase://lf_ops.pantallas_politicas/1",
            "reference_role":"rls_security_policy_id",
            "policy_target_ref":"supabase://lf_ops.politicas_seguridad/1",
            "status":"CANDIDATO","policy_kind":"seguridad"}]
        out=a3.run(inputs(),base)
        self.assertEqual([r["rule_code"] for r in out["policy_deferred_rule_items"]],["RULE-A"])
        self.assertEqual([r["rule_code"] for r in out["policy_scope_clear_rule_candidates"]],["RULE-C"])
        self.assertFalse(out["a4_allowed"])

    def test_untyped_policy_numeric_id_does_not_grant(self):
        read=policy_readback()
        effective={"rules":[{"code":"R","status":"VIGENTE",
                    "pending_decision":False,"config":{"trusted_device_policy_id":1}}]}
        out=policy.project(effective,[],read,target_ref=SCREEN,screen_ref=REF)
        dep=out["rule_policy_dependencies"][0]
        self.assertEqual(dep["status"],"POLICY_REFERENCE_TYPE_UNBOUND_OBJECT_OBSERVED")
        self.assertIsNone(dep["policy_target_ref"])
        self.assertFalse(dep["eligible_for_implementation"])
        self.assertFalse(dep["untyped_id_observation"]["relation_attested"])

    def test_full_material_contract_preserves_statuses_without_promoting(self):
        src=sources()
        src["contract_sections"]={
            "fields":[{"field_code":"LOGIN_EMAIL","status":"CANDIDATO","required":True}],
            "errors":[{"error_code":"BAD_CREDENTIALS","status":"CANDIDATO"}],
            "visual":{"colors":[{"token_name":"green_action","status":"VIGENTE"}],
                      "variants":[{"variant_code":"MOBILE","status":"CANDIDATO_VISUAL"}]},
            "context":{"module_code":"B2B_AUTENTICACION"},
            "metadata":{"screen_code":SCREEN},
            "profiles":[],"analytics":[],"evidence":[],
        }
        frozen=copy.deepcopy(src)
        out=a3.run(inputs(),src)
        self.assertEqual(src,frozen)
        material=out["material_contract_readback"]
        self.assertEqual(material["counts"]["sections"],8)
        self.assertEqual(material["counts"]["status_items"],4)
        self.assertEqual(material["counts"]["vigente_source_candidates"],1)
        self.assertEqual(material["counts"]["pending_or_other_status"],3)
        self.assertEqual(out["counts"]["material_sections_total"],8)
        self.assertTrue(all(not item["implementation_approved"]
                            for item in material["status_items"]))
        self.assertFalse(out["a4_allowed"])

    def test_incomplete_material_is_blocked_not_assumed(self):
        src=sources();src["contract_sections"]={"fields":[]}
        out=a3.run(inputs(),src)
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A3_MATERIAL_CONTRACT_SECTIONS_INCOMPLETE",out["blocking_codes"])

    def test_exact_source_and_business_fail_closed(self):
        inputs_copy=inputs(); wrong=sources(); wrong["business"]="SALY"
        self.assertEqual(a3.run(inputs_copy,wrong)["status"],"BLOCKED")
        self.assertEqual(a3.run(inputs_copy,sources(),business="SALY")["status"],"BLOCKED")
        self.assertFalse(a3.run(inputs_copy,sources())["runtime_qualified"])

if __name__ == "__main__":
    unittest.main()
