"""Lossless A5 item coverage and false human decision adversarial tests.

Synthetic scoped LF sample. NO production authority, real currentness or real
LLM semantic judge receipt is asserted by this test.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("a5_material_candidate",ROOT/"validators/run.py")
a5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a5)

TARGET="B2B-AUTH-001"
SCREEN="supabase://lf_ops.pantallas/B2B-AUTH-001"
RULE1="supabase://lf_ops.reglas/101"
RULE2="supabase://lf_ops.reglas/102"


def full_input():
    return {
        "REQUEST_CONTEXT_V1":{
            "schema_version":"REQUEST_CONTEXT_V1","target_hints":["Inicio de sesión B2B"],
            "objective":{"problem_statement":"Implementar pantalla Inicio de sesión B2B"},
            "constraints":["Solo reglas vigentes y vinculaciones aprobadas"]
        },
        "ANALYSIS_CHANGE_CLASSIFICATION_V1":{
            "schema_version":"ANALYSIS_CHANGE_CLASSIFICATION_V1",
            "target_ref":"Inicio de sesión B2B","change_type":"CREATE"},
        "TARGETED_EVIDENCE_SET_V1":{
            "schema_version":"TARGETED_EVIDENCE_SET_V1","business":"LF",
            "status":"SOURCE_READBACK_PROCESSED_UNATTESTED","target_ref":TARGET,
            "declared_target_hint":"Inicio de sesión B2B",
            "source_refs":[SCREEN,RULE1,RULE2],
            "currentness_refs":[],
            "policy_scope_clear_rule_candidates":[
                {"rule_code":"AUTH-CRED-01","rule_status":"VIGENTE",
                 "pending_decision":False,"source_ref":RULE1,
                 "title":"Validación de credenciales",
                 "description":"Aplicar autenticación según política vigente de acceso.",
                 "policy_dependency_disposition":"NO_KNOWN_POLICY_DEPENDENCY_BLOCKER"},
                {"rule_code":"AUTH-ERR-02","rule_status":"VIGENTE",
                 "pending_decision":False,"source_ref":RULE2,
                 "title":"Mensajes de error",
                 "description":"Mostrar estado de autenticación sin divulgar credenciales.",
                 "policy_dependency_disposition":"NO_KNOWN_POLICY_DEPENDENCY_BLOCKER"}
            ],
            "policy_deferred_rule_items":[
                {"rule_code":"AUTH-SESS-03","rule_status":"VIGENTE","pending_decision":False,
                 "source_ref":"supabase://lf_ops.reglas/103",
                 "title":"Configuración de sesión","policy_dependency_disposition":"DEFER_UNAPPROVED_OR_UNRESOLVED_POLICY"}],
            "excluded_rule_items":[
                {"rule_code":"AUTH-PENDING-04","rule_status":"CANDIDATO",
                 "pending_decision":True,"source_ref":"supabase://lf_ops.reglas/104",
                 "title":"Cambio propuesto no aprobado"}],
            "evidence_items":[
                {"rule_code":"AUTH-CRED-01","rule_status":"VIGENTE","pending_decision":False,"source_ref":RULE1},
                {"rule_code":"AUTH-ERR-02","rule_status":"VIGENTE","pending_decision":False,"source_ref":RULE2}],
            "policy_link_items":[
                {"source_ref":"supabase://lf_ops.pantallas_politicas/201","status":"VIGENTE","policy_code":"POL-AUTH-01"}],
            "policy_resolution":{
                "counts":{"policy_objects":1,"policy_objects_vigente":1},
                "approved_policy_objects":[{"policy_id":201,"status":"VIGENTE",
                    "source_ref":"supabase://lf_ops.politicas/201",
                    "config":{"attempt_limit":5}}],
                "pending_policy_objects":[{"policy_id":202,"status":"CANDIDATO"}]
            },
            "material_contract_readback":{
                "status":"MATERIAL_CONTRACT_PROJECTED_UNATTESTED",
                "source_ref":SCREEN,"source_function":"lf_ops.fn_screen_contract_v1",
                "contract_sections":{
                    "fields":[{"name":"email","status":"VIGENTE","label":"Correo electrónico"}],
                    "errors":[{"code":"INVALID_LOGIN","status":"CANDIDATO"}],
                    "visual":{"status":"VIGENTE","tokens":{"button":"#00A32A"}},
                    "context":{},"metadata":{},"profiles":[],"analytics":[],"evidence":[]},
                "status_items":[
                    {"source_ref":SCREEN+"#contract/fields/0","pointer":"fields/0","source_status":"VIGENTE"},
                    {"source_ref":SCREEN+"#contract/errors/0","pointer":"errors/0","source_status":"CANDIDATO"}]
            },
            "scope_alerts":["PENDING_RULES_EXCLUDED"],
            "unresolved_material_gaps":[],
        },
        "SHARED_CHANGE_IMPACT_ANALYSIS":{
            "schema_version":"SHARED_CHANGE_IMPACT_ANALYSIS",
            "business":"LF","status":"PLANNED_BUILD_IMPACT_UNATTESTED",
            "target_ref":TARGET,"target_change_action":"CREATE",
            "analysis_mode":"PLANNED_BUILD","target_code_destination":None,
            "evidence_refs":[SCREEN,RULE1,RULE2],
            "direct_impacts":[
                {"affected_ref":RULE1,"requirement_code":"AUTH-CRED-01",
                 "change_action":"CREATE","definition_action":"REUSE",
                 "impact_class":"PLANNED_NEW_IMPLEMENTATION_OBLIGATION",
                 "source_status":"VIGENTE",
                 "source_payload_hint":"Keep rule definition unchanged"},
                {"affected_ref":SCREEN+"#contract/fields/0",
                 "change_action":"CREATE","definition_action":"REUSE",
                 "impact_class":"PLANNED_MATERIAL_DEFINITION",
                 "source_status":"VIGENTE"}
            ],
            "indirect_impacts":[{"affected_ref":"dbfunc://existing_auth","impact_class":"POTENTIAL_GRAPH_RELATION_NOT_BEHAVIOR_PROOF",
                 "change_action":"UNKNOWN","description":"Potential dependency only"}],
            "consumers":[{"source_ref":"dbfunc://session_consumer",
                "target_ref":"dbfunc://existing_auth","relation_type":"CALLS"}],
            "dependency_paths":[{"source_ref":"dbfunc://existing_auth",
                "target_ref":"dbtable://session","relation_type":"READS"}],
            "excluded_pending_obligations":[{"affected_ref":SCREEN+"#contract/errors/0",
                "source_status":"CANDIDATO","change_action":"UNKNOWN"}],
            "unresolved_material_impacts":[
                {"code":"A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED",
                 "target_ref":TARGET,"source_id":"S3_INV_OBJECT",
                 "detail":"Existing dependency currentness unconfirmed"},
                {"code":"A4_TARGET_RUNTIME_CURRENTNESS_NOT_ATTESTED",
                 "target_ref":TARGET,"source_id":"S1_A3"}
            ],
        },
    }


FLAGS=[
"canonical_authority_or_owner_changes",
"transversal_capability_created_extended_or_retired",
"cross_stage_or_multi_consumer_contract_changes",
"canonical_state_authority_or_lifecycle_changes",
"material_migration_cutover_or_long_lived_compatibility_changes",
"security_or_privacy_boundary_changes",
"runtime_or_production_topology_changes",
]


def sidecar():
    return {
        "schema_version":"A5_GOVERNED_DECISION_READBACK_V1",
        "business":"LF","target_ref":TARGET,"source_attested":False,
        "adr_trigger_review":{"flags":{x:False for x in FLAGS},
            "evidence_ref":SCREEN,"source_attested":False},
    }


class A5ItemTests(unittest.TestCase):
    def test_lossless_every_a3_a4_row_and_exact_payload(self):
        original=full_input();before=deepcopy(original)
        out=a5.run(original,sidecar())
        self.assertEqual(original,before)
        self.assertEqual(out["status"],"UNRESOLVED")
        ledger=out["material_ledger"]
        self.assertEqual(ledger["coverage"]["omitted_material_item_count"],0)
        self.assertTrue(ledger["coverage"]["complete_for_provided_collections"])
        self.assertEqual(ledger["coverage"]["input_item_count"],17)
        self.assertEqual(len(out["decision_items"]),17)
        self.assertEqual(len({i["decision_item_id"] for i in out["decision_items"]}),17)
        self.assertEqual(out["material_coverage"]["output_item_count"],17)
        for item in out["decision_items"]:
            stage=original["TARGETED_EVIDENCE_SET_V1"] if item["source_stage"]=="A3" else original["SHARED_CHANGE_IMPACT_ANALYSIS"]
            path=item["source_path"]
            if path.startswith("material_contract_readback.status_items["):
                actual=stage["material_contract_readback"]["status_items"][int(path.split("[")[1][:-1])]
            else:
                section,num=path[:-1].split("[")
                actual=stage[section][int(num)]
            self.assertEqual(item["source_payload"],actual)
        self.assertEqual(ledger["source_detail"]["a3_policy_resolution"],
                         original["TARGETED_EVIDENCE_SET_V1"]["policy_resolution"])
        self.assertEqual(ledger["source_detail"]["a3_material_contract"],
                         original["TARGETED_EVIDENCE_SET_V1"]["material_contract_readback"])

    def test_approved_rules_keep_original_title_description(self):
        out=a5.run(full_input(),sidecar())
        row=next(x for x in out["decision_items"] if x["subject_code"]=="AUTH-CRED-01"
                 and x["kind"]=="APPROVED_RULE")
        self.assertEqual(row["title"],"Validación de credenciales")
        self.assertIn("política vigente",row["description"])
        self.assertEqual(row["decision_classification"],
                         "NO_NEW_DECISION_REQUIRED_SOURCE_CANDIDATE")
        self.assertIsNone(row["material_question"])
        self.assertFalse(row["owner_decision_required"])

    def test_pending_rules_and_definitions_do_not_require_owner(self):
        out=a5.run(full_input(),sidecar())
        for row in out["decision_items"]:
            if row["kind"] in ("POLICY_DEFERRED_RULE","EXCLUDED_RULE","EXCLUDED_OBLIGATION"):
                self.assertEqual(row["decision_classification"],"EXCLUDED_FROM_APPROVED_SCOPE")
                self.assertFalse(row["owner_decision_required"])
        self.assertEqual(out["pending_owner_decisions"],[])
        self.assertFalse(out["a6_allowed"])

    def test_gap_preserves_specific_error_and_next_action(self):
        out=a5.run(full_input(),sidecar())
        gap=next(x for x in out["decision_items"]
                 if x["subject_code"]=="A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED")
        self.assertEqual(gap["decision_classification"],"TARGETED_EVIDENCE_REQUIRED")
        self.assertEqual(gap["next_action"],"TARGETED_SOURCE_READBACK_ONLY")
        self.assertFalse(gap["owner_decision_required"])
        self.assertEqual(gap["source_payload"]["detail"],
                         "Existing dependency currentness unconfirmed")

    def test_incomplete_source_collection_visible_not_implicitly_empty(self):
        data=full_input()
        del data["TARGETED_EVIDENCE_SET_V1"]["policy_link_items"]
        out=a5.run(data,sidecar())
        self.assertIn("A3.policy_link_items",out["material_coverage"]["missing_source_collections"])
        self.assertFalse(out["material_coverage"]["complete_for_provided_collections"])
        self.assertIn("A5_MATERIAL_SOURCE_COLLECTIONS_NOT_SUPPLIED",
                      out["unresolved_material_questions"])
        self.assertFalse(out["a6_allowed"])

    def test_malformed_row_fails_closed(self):
        data=full_input()
        data["SHARED_CHANGE_IMPACT_ANALYSIS"]["direct_impacts"][0]=None
        out=a5.run(data,sidecar())
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A5_MATERIAL_ROW_INVALID:A4.direct_impacts",out["blocking_codes"])

    def test_currentness_and_a6_never_self_attested(self):
        out=a5.run(full_input(),sidecar())
        self.assertFalse(out["source_attested"])
        self.assertFalse(out["independent_judge_verified"])
        self.assertFalse(out["a6_allowed"])
        self.assertTrue(out["candidate_independent_scope_available"])
        self.assertEqual(out["scope_disposition"],
                         "NO_NEW_OWNER_DECISION_DEMONSTRATED_SOURCE_CANDIDATE")

    def test_owner_question_needs_explicit_source_item_and_authority(self):
        p=sidecar()
        p["material_decisions"]=[{
            "source_item_id":"A4:direct_impacts:0",
            "material_question":"¿Se autoriza ampliar el alcance de esta regla a otro consumidor?",
            "owner_role":"OWNER_HUMAN","evidence_ref":SCREEN,
            "source_attested":False}]
        out=a5.run(full_input(),p)
        self.assertEqual(out["status"],"REQUIRES_DECISION")
        self.assertEqual(len(out["pending_owner_decisions"]),1)
        self.assertIsNone(out["pending_owner_decisions"][0]["selected_option_ref"])
        self.assertFalse(out["a6_allowed"])
        self.assertEqual(out["decision_context"],out["decisions"][0])

    def test_forged_owner_question_and_missing_evidence_blocked(self):
        p=sidecar()
        p["material_decisions"]=[{
            "source_item_id":"A4:direct_impacts:999",
            "material_question":"¿Se autoriza ampliar el alcance de esta regla a otro consumidor?",
            "owner_role":"OWNER_HUMAN","evidence_ref":SCREEN,
            "source_attested":False}]
        self.assertIn("A5_OWNER_DECISION_MISSING_MATERIAL_BINDING",
                      a5.run(full_input(),p)["blocking_codes"])
        p["material_decisions"][0]["source_item_id"]="A4:direct_impacts:0"
        p["material_decisions"][0]["evidence_ref"]="made-up://no_source"
        self.assertEqual(a5.run(full_input(),p)["status"],"BLOCKED")

    def test_evidence_gap_must_not_auto_be_owner_question(self):
        p=sidecar()
        p["material_decisions"]=[{
            "source_item_id":"A4:unresolved_material_impacts:0",
            "material_question":"¿Se aprueba el hecho de que falta evidencia técnica?",
            "owner_role":"OWNER_HUMAN","evidence_ref":SCREEN,
            "source_attested":False}]
        out=a5.run(full_input(),p)
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A5_MISSING_EVIDENCE_NOT_OWNER_DECISION",out["blocking_codes"])

    def test_cannot_escalate_excluded_pending_rule(self):
        p=sidecar()
        p["material_decisions"]=[{
            "source_item_id":"A3:excluded_rule_items:0",
            "material_question":"¿Se permite promover la regla pendiente sin nueva aprobación?",
            "owner_role":"OWNER_HUMAN","evidence_ref":SCREEN,
            "source_attested":False}]
        out=a5.run(full_input(),p)
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A5_EXCLUDED_RULE_CANNOT_TRIGGER_OWNER_DECISION",
                      out["blocking_codes"])

    def test_new_adr_trigger_without_question_does_not_invent_owner_question(self):
        p=sidecar()
        p["adr_trigger_review"]["flags"]["cross_stage_or_multi_consumer_contract_changes"]=True
        p["adr_search"]={
            "state":"NO_CURRENT_ADR","source_function":"transversal.decision_log",
            "target_ref":TARGET,"source_attested":False,"evidence_ref":SCREEN
        }
        out=a5.run(full_input(),p)
        self.assertEqual(out["status"],"REQUIRES_DECISION")
        self.assertEqual(len(out["architecture_decision_items"]),1)
        item=out["architecture_decision_items"][0]
        self.assertIsNone(item["material_question"])
        self.assertTrue(item["semantic_review_needed"])
        self.assertTrue(item["decision_required"])
        self.assertFalse(out["a6_allowed"])

    def test_new_adr_trigger_with_source_bound_material_question(self):
        p=sidecar()
        flag="cross_stage_or_multi_consumer_contract_changes"
        p["adr_trigger_review"]["flags"][flag]=True
        p["adr_search"]={
            "state":"NO_CURRENT_ADR","source_function":"transversal.decision_log",
            "target_ref":TARGET,"source_attested":False,"evidence_ref":SCREEN
        }
        p["adr_trigger_review"]["material_detail"]={
            flag:{"material_question":"¿Se aprueba modificar el contrato compartido entre consumidores?",
                  "evidence_ref":SCREEN}
        }
        out=a5.run(full_input(),p)
        self.assertEqual(out["architecture_decision_items"][0]["status"],
                         "REQUIRES_OWNER_DECISION_CANDIDATE")
        self.assertFalse(out["architecture_decision_items"][0]["semantic_review_needed"])
        self.assertFalse(out["a6_allowed"])
        p["adr_trigger_review"]["material_detail"][flag]["evidence_ref"]="unknown://not-bound"
        self.assertIn("A5_ADR_QUESTION_NOT_SOURCE_BOUND",
                      a5.run(full_input(),p)["blocking_codes"])

    def test_repeatable_and_changes_hash_when_material_evidence_changes(self):
        a=a5.run(full_input(),sidecar())
        b=a5.run(full_input(),sidecar())
        self.assertEqual(a["material_ledger"]["ledger_fingerprint_sha256"],
                         b["material_ledger"]["ledger_fingerprint_sha256"])
        c=full_input()
        c["TARGETED_EVIDENCE_SET_V1"]["material_contract_readback"]["contract_sections"]["visual"]["tokens"]["button"]="#FFFFFF"
        changed=a5.run(c,sidecar())
        self.assertNotEqual(a["material_ledger"]["ledger_fingerprint_sha256"],
                            changed["material_ledger"]["ledger_fingerprint_sha256"])


if __name__ == "__main__":
    unittest.main()
