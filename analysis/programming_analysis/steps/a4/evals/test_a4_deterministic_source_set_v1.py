"""A4 deterministic source binding tests. Synthetic, not governed receipts."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("a4_source_projection", ROOT / "validators/run.py")
a4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a4)

TARGET = "B2B-AUTH-001"
SCREEN_REF = "supabase://lf_ops.pantallas/B2B-AUTH-001"
TECH_REF = "dbfunc://public.login_validate_credentials_v1(p_email text)"

def a3():
    return {
        "schema_version": "TARGETED_EVIDENCE_SET_V1",
        "status": "SOURCE_READBACK_PROCESSED_UNATTESTED",
        "business": "LF", "target_ref": TARGET,
        "declared_target_hint": "Login B2B",
        "source_refs": [SCREEN_REF],
        "unresolved_material_gaps": [],
        "as_is_baseline_or_new_implementation_evidence": {"source_attested": False},
    }

def a2():
    return {
        "schema_version": "ANALYSIS_CHANGE_CLASSIFICATION_V1",
        "target_ref": "Login B2B", "change_type": "MODIFY",
        "target_granularity": "SCREEN", "evidence_refs": [SCREEN_REF],
    }

def readback():
    return {
        "schema_version": "A4_EXISTING_IMPACT_CORE_READBACK_V1",
        "business": "LF", "target_ref": TARGET, "source_attested": False,
        "inventory_object": {
            "object_ref": TECH_REF, "object_type": "DB_FUNCTION",
            "active": True, "currentness": "CURRENT",
            "source_version": "candidate", "definition_sha256": None,
            "observed_main_sha": None
        },
        "identity_binding": {
            "target_ref": TARGET, "inventory_object_ref": TECH_REF,
            "source_ref": SCREEN_REF, "source_attested": False,
        },
        "impact_readback": {
            "source_function": "inventory.fn_impact_analysis_v1",
            "parameters": {
                "p_object_ref": TECH_REF, "p_max_depth": 3,
                "p_min_confidence": 0.8
            },
            "source_attested": False,
            "rows": [
                {"depth": 1, "affected_ref": "dbfunc://consumer_1",
                 "affected_type": "DB_FUNCTION", "via_relation": "CALLS",
                 "min_confidence": 0.91, "source_system": "INVENTORY"},
                {"depth": 2, "affected_ref": "dbfunc://consumer_2",
                 "affected_type": "DB_FUNCTION", "via_relation": "CALLS",
                 "min_confidence": 0.85, "source_system": "INVENTORY"},
            ]
        },
        "dependency_readback": {
            "source_function": "inventory.fn_dependencies_v1",
            "parameters": {
                "p_object_ref": TECH_REF, "p_direction": "BOTH",
                "p_max_depth": 2
            },
            "source_attested": False,
            "rows": [
                {"depth": 1, "direction": "IN",
                 "source_ref": "dbfunc://consumer_1",
                 "target_ref": TECH_REF, "relation_type": "CALLS",
                 "evidence_type": "INVENTORY", "confidence": 0.91},
                {"depth": 1, "direction": "OUT",
                 "source_ref": TECH_REF,
                 "target_ref": "dbtable://session", "relation_type": "READS",
                 "evidence_type": "INVENTORY", "confidence": 0.91},
            ]
        },
    }

class A4DeterministicSourceTests(unittest.TestCase):
    def test_exact_sources_project_direct_indirect_and_consumers(self):
        source=readback(); before=deepcopy(source)
        result=a4.run(a3(),a2(),source)
        self.assertEqual(result["status"],"PROJECTED_UNATTESTED")
        self.assertEqual(result["counts"],
                         {"direct":1,"indirect":1,"consumers":1,"dependency_paths":2})
        self.assertEqual(result["technical_root_ref"],TECH_REF)
        self.assertFalse(result["impact_verified"])
        self.assertFalse(result["a5_allowed"])
        self.assertEqual(source,before)

    def test_missing_target_mapping_never_means_no_impact(self):
        source=readback()
        source["inventory_object"]=None
        source["identity_binding"]=None
        r=a4.run(a3(),a2(),source)
        self.assertEqual(r["status"],"IMPACT_UNKNOWN")
        self.assertEqual(r["unresolved_material_impacts"][0]["source_id"],"S3_INV_OBJECT")

    def test_empty_graph_is_unknown_not_no_impact(self):
        source=readback()
        source["impact_readback"]["rows"]=[]
        source["dependency_readback"]["rows"]=[]
        r=a4.run(a3(),a2(),source)
        self.assertEqual(r["status"],"IMPACT_UNKNOWN")
        self.assertIn("A4_EMPTY_GRAPH_DOES_NOT_ESTABLISH_NO_IMPACT",
                      [x["code"] for x in r["unresolved_material_impacts"]])

    def test_other_inventory_object_binding_blocks(self):
        source=readback()
        source["identity_binding"]["inventory_object_ref"]="dbfunc://unrelated"
        r=a4.run(a3(),a2(),source)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertIn("A4_INVENTORY_TARGET_BINDING_MISSING_OR_DRIFTED",r["blocking_codes"])

    def test_source_function_and_params_not_flexible(self):
        source=readback()
        source["impact_readback"]["parameters"]["p_max_depth"]=6
        self.assertEqual(a4.run(a3(),a2(),source)["status"],"BLOCKED")
        source=readback()
        source["dependency_readback"]["source_function"]="invented.fn_impact_v2"
        self.assertEqual(a4.run(a3(),a2(),source)["status"],"BLOCKED")

    def test_currentness_gap_preserved(self):
        source=readback()
        source["inventory_object"]["currentness"]=None
        r=a4.run(a3(),a2(),source)
        self.assertEqual(r["status"],"IMPACT_UNKNOWN")
        self.assertIn("A4_INVENTORY_OBJECT_CURRENTNESS_NOT_VERIFIED",
                      [x["code"] for x in r["unresolved_material_impacts"]])

    def test_saly_and_target_mismatch_fail_closed(self):
        self.assertEqual(a4.run(a3(),a2(),readback(),business="SALY")["status"],"BLOCKED")
        bad=a2(); bad["target_ref"]="OTHER-TARGET"
        self.assertEqual(a4.run(a3(),bad,readback())["status"],"BLOCKED")

    def test_new_screen_build_without_code_path_or_inventory(self):
        evidence=a3()
        evidence["policy_scope_clear_rule_candidates"]=[
            {"rule_code":"RULE-A","source_ref":"supabase://lf_ops.reglas/1",
             "rule_status":"VIGENTE","pending_decision":False,
             "policy_dependency_disposition":"NO_KNOWN_POLICY_DEPENDENCY_BLOCKER"}
        ]
        evidence["material_contract_readback"]={
            "status":"MATERIAL_CONTRACT_PROJECTED_UNATTESTED",
            "status_items":[
                {"source_ref":SCREEN_REF+"#contract/visual/colors/0",
                 "source_status":"VIGENTE"},
                {"source_ref":SCREEN_REF+"#contract/fields/0",
                 "source_status":"CANDIDATO"},
            ]
        }
        classification=a2();classification["change_type"]="IMPLEMENT"
        before=deepcopy(evidence)
        result=a4.run(evidence,classification)
        self.assertEqual(result["status"],"PLANNED_BUILD_IMPACT_UNATTESTED")
        self.assertEqual(result["analysis_mode"],"PLANNED_BUILD")
        self.assertIsNone(result["target_code_destination"])
        self.assertIsNone(result["technical_root_ref"])
        self.assertEqual(result["counts"]["direct"],2)
        self.assertEqual(result["counts"]["excluded_pending"],1)
        self.assertEqual(result["target_code_state"],"NOT_ESTABLISHED_BY_SOURCE")
        self.assertTrue(result["implementation_scope_progress_possible"])
        self.assertFalse(result["no_impact_claimed"])
        self.assertFalse(result["a5_allowed"])
        self.assertEqual(evidence,before)

    def test_new_screen_with_no_technical_binding_still_projects_scope(self):
        evidence=a3()
        evidence["policy_scope_clear_rule_candidates"]=[
            {"rule_code":"RULE-A","source_ref":"supabase://lf_ops.reglas/1",
             "rule_status":"VIGENTE","pending_decision":False}
        ]
        classification=a2();classification["change_type"]="CREATE"
        sidecar=readback()
        sidecar["inventory_object"]=None
        sidecar["identity_binding"]=None
        result=a4.run(evidence,classification,sidecar)
        self.assertEqual(result["status"],"PLANNED_BUILD_IMPACT_UNATTESTED")
        self.assertEqual(result["counts"]["direct"],1)
        self.assertIsNone(result["target_code_destination"])

    def test_new_screen_without_source_rules_cannot_claim_ready(self):
        evidence=a3()
        evidence["policy_scope_clear_rule_candidates"]=[]
        classification=a2();classification["change_type"]="BUILD_NEW"
        result=a4.run(evidence,classification)
        self.assertFalse(result["implementation_scope_progress_possible"])
        self.assertFalse(result["a5_allowed"])
        self.assertIn("A4_APPROVED_SCOPE_HAS_NO_MATERIAL_OBLIGATIONS",
                      [x["code"] for x in result["unresolved_material_impacts"]])

    def test_new_screen_cannot_promote_candidate_rule(self):
        evidence=a3()
        evidence["policy_scope_clear_rule_candidates"]=[
            {"rule_code":"RULE-C","source_ref":"supabase://lf_ops.reglas/3",
             "rule_status":"CANDIDATO","pending_decision":False}
        ]
        classification=a2();classification["change_type"]="IMPLEMENT"
        result=a4.run(evidence,classification)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("A4_BUILD_RULE_SOURCE_STATUS_INVALID",result["blocking_codes"])

    def test_new_screen_does_not_ignore_forged_provider_readback(self):
        evidence=a3();evidence["policy_scope_clear_rule_candidates"]=[]
        classification=a2();classification["change_type"]="CREATE"
        sidecar=readback();sidecar["target_ref"]="OTHER"
        self.assertEqual(a4.run(evidence,classification,sidecar)["status"],"BLOCKED")

    def test_actions_are_classified_from_a2_explicit_intent(self):
        for operation, expected in [
            ("CREATE", "CREATE"), ("IMPLEMENT", "CREATE"),
            ("MODIFY", "MODIFY"), ("UPDATE", "MODIFY"),
            ("DELETE", "DELETE"), ("REMOVE", "DELETE"),
            ("REPLACE", "REPLACE"), ("REUSE", "REUSE"),
            ("NO_CHANGE", "NO_CHANGE"),
        ]:
            with self.subTest(operation=operation):
                classification=a2()
                classification["change_type"]=operation
                source=readback()
                result=a4.run(a3(),classification,source)
                self.assertEqual(result["target_change_action"],expected)
                self.assertEqual(result["requested_change_type"],operation)
                self.assertEqual(result["change_action_basis"],
                                 "A2_DECLARED_TARGET_INTENT_UNVERIFIED")
                self.assertFalse(result["a5_allowed"])

    def test_existing_graph_has_no_inferred_item_modifications_or_deletions(self):
        classification=a2();classification["change_type"]="DELETE"
        result=a4.run(a3(),classification,readback())
        self.assertEqual(result["target_change_action"],"DELETE")
        self.assertTrue(result["direct_impacts"])
        self.assertTrue(result["indirect_impacts"])
        self.assertTrue(all(x["change_action"]=="UNKNOWN"
                            for x in result["direct_impacts"]+result["indirect_impacts"]))
        self.assertTrue(all(x["change_action"]=="UNKNOWN"
                            for x in result["dependency_paths"]))
        self.assertTrue(result["no_write_performed"])

    def test_new_screen_is_created_but_existing_rule_definition_is_reused(self):
        evidence=a3()
        evidence["policy_scope_clear_rule_candidates"]=[
            {"rule_code":"LOGIN-RULE-01","source_ref":"supabase://lf_ops.reglas/1",
             "rule_status":"VIGENTE","pending_decision":False}
        ]
        evidence["material_contract_readback"]={
            "status":"MATERIAL_CONTRACT_PROJECTED_UNATTESTED",
            "status_items":[
                {"source_ref":SCREEN_REF+"#contract/visual/colors/0",
                 "source_status":"VIGENTE"},
                {"source_ref":SCREEN_REF+"#contract/fields/0",
                 "source_status":"CANDIDATO"},
            ]
        }
        classification=a2();classification["change_type"]="CREATE"
        result=a4.run(evidence,classification)
        self.assertEqual(result["target_change_action"],"CREATE")
        self.assertTrue(all(x["change_action"]=="CREATE"
                            for x in result["direct_impacts"]))
        self.assertTrue(all(x["definition_action"]=="REUSE"
                            for x in result["direct_impacts"]))
        self.assertEqual(result["excluded_pending_obligations"][0]["change_action"],
                         "UNKNOWN")
        self.assertIsNone(result["target_code_destination"])
        self.assertFalse(result["a5_allowed"])

    def test_unrecognized_operation_has_explicit_unknown_no_implicit_modify(self):
        classification=a2();classification["change_type"]="DO_SOMETHING_VAGUE"
        result=a4.run(a3(),classification,readback())
        self.assertEqual(result["status"],"NEED_MORE_EVIDENCE")
        self.assertEqual(result["target_change_action"],"UNKNOWN")
        self.assertEqual(result["direct_impacts"],[])
        self.assertFalse(result["a5_allowed"])

    def test_new_screen_with_related_existing_component_stays_create(self):
        evidence=a3()
        evidence["policy_scope_clear_rule_candidates"]=[
            {"rule_code":"LOGIN-RULE-01",
             "source_ref":"supabase://lf_ops.reglas/1",
             "rule_status":"VIGENTE","pending_decision":False}
        ]
        classification=a2()
        classification["change_type"]="CREATE"
        # This readback includes a related reusable component. It must not
        # become the code destination or turn CREATE into MODIFY.
        result=a4.run(evidence,classification,readback())
        self.assertEqual(result["analysis_mode"],"PLANNED_BUILD")
        self.assertEqual(result["target_change_action"],"CREATE")
        self.assertIsNone(result["target_code_destination"])
        self.assertIsNone(result["technical_root_ref"])
        self.assertEqual(result["direct_impacts"][0]["change_action"],"CREATE")
        self.assertEqual(result["direct_impacts"][0]["definition_action"],"REUSE")
        self.assertFalse(result["a5_allowed"])

    def test_missing_host_readback_no_fallback_search(self):
        r=a4.run(a3(),a2(),None)
        self.assertEqual(r["status"],"NEED_MORE_EVIDENCE")
        self.assertEqual(r["direct_impacts"],[])
        self.assertFalse(r["a5_allowed"])

if __name__ == "__main__":
    unittest.main()
