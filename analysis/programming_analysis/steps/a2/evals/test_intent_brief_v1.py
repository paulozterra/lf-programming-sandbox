"""Human-first A2 brief tests; all source-only and non-operational."""
from __future__ import annotations
import copy
import importlib.util
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('human_brief',BASE/'adapters/intent_brief_v1.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from test_golden_handoff_v03 import make,run
from test_a2_a3_intake_preview_v1 import prepare_preview


def fixture():
    a,b,s=make()
    return a,b,s,run(a,b,s)


class IntentBriefTests(unittest.TestCase):
    def test_01_human_primary_not_checklist(self):
        a,b,s,g=fixture();r=prepare_preview(a,b,s,g)
        self.assertEqual(r['status'],'PREVIEW_PREPARED_NOT_DISPATCHABLE')
        v=r['human_intent_brief']
        self.assertIn('El solicitante pidió',v['human_readable_document'])
        self.assertIn('Revisar ingreso B2B LF',v['human_readable_document'])
        self.assertIn('Definir requisitos',v['human_readable_document'])
        self.assertIn('criterio observable de éxito',v['human_readable_document'])
        self.assertEqual(v['golden_controls']['elements'],59)
        self.assertTrue(v['intent_review_required'])
    def test_02_ambiguities_empty_not_assumed_resolved(self):
        r=prepare_preview(*fixture())['human_intent_brief']
        self.assertTrue(r['ambiguities_absent_not_proven'])
        self.assertEqual(r['user_questions_candidates'],[])
        self.assertEqual(r['intent_quality_checks'][0]['status'],'PENDING_SEMANTIC_REVIEW_NOT_OWNER_QUESTION')
        self.assertFalse(r['owner_questions_sent'])
    def test_03_open_material_owner_question(self):
        a,b,s,g=fixture()
        a['payload']['ambiguities']=[{'code':'SCOPE','statement':'No sabemos si también incluye recuperación de acceso','materiality':'MATERIAL','resolution_state':'OPEN'}]
        v=mod.build_brief(a,b,s,g)
        self.assertEqual(len(v['user_questions_candidates']),1)
        self.assertIn('recuperación de acceso',v['user_questions_candidates'][0]['question'])
        self.assertEqual(v['recorded_open_ambiguities'][0]['status'],'DECLARED_OPEN_NOT_VERIFIED')
    def test_04_resolved_ambiguity_not_reopened_as_owner_question(self):
        a,b,s,g=fixture()
        a['payload']['ambiguities']=[{'code':'X','statement':'Ya resuelto desde fuente','materiality':'MATERIAL','resolution_state':'RESOLVED_FROM_SOURCE'}]
        v=mod.build_brief(a,b,s,g)
        self.assertEqual(len(v['user_questions_candidates']),0)
        self.assertEqual(v['recorded_open_ambiguities'],[])
        self.assertFalse(v['ambiguities_absent_not_proven'])
    def test_05_missing_constraints_are_not_none_exist(self):
        v=prepare_preview(*fixture())['human_intent_brief']
        self.assertEqual(v['constraints_status'],'NOT_PROVIDED_UNVERIFIED')
        self.assertIn('No se proporcionaron restricciones',v['human_readable_document'])
    def test_06_declared_constraints_transported_verbatim(self):
        a,b,s,g=fixture();a['payload']['constraints']=['No modificar las reglas vigentes sin aprobación']
        v=mod.build_brief(a,b,s,g)
        self.assertEqual(v['scope_constraints_declared'],a['payload']['constraints'])
        self.assertIn('No modificar las reglas vigentes',v['human_readable_document'])
        self.assertEqual(v['constraints_status'],'DECLARED_UNVERIFIED')
    def test_07_no_unproven_login_policy_as_fact(self):
        human=prepare_preview(*fixture())['human_intent_brief']['human_readable_document']
        for word in ('RATE-B2B-LOGIN','SESSION-B2B-DEFAULT','cinco intentos'):
            self.assertNotIn(word,human)
    def test_08_a3_questions_are_separate_from_owner_questions(self):
        v=prepare_preview(*fixture())['human_intent_brief']
        self.assertEqual(len(v['a3_investigation_tasks']),4)
        self.assertEqual(len(v['user_questions_candidates']),0)
        self.assertTrue(all(q['status']=='SUGGESTED_NOT_SENT_NEEDS_SEMANTIC_REVIEW' for q in v['user_questions_candidates']))
    def test_08b_ambiguity_escalation_is_research_first(self):
        a,b,s,g=fixture()
        a['payload']['ambiguities']=[{
            'code':'PORTAL_ENTRY_MODE_UNRESOLVED',
            'statement':'No sabemos si es navegación o autenticación',
            'materiality':'MATERIAL','resolution_state':'OPEN'
        }]
        result=mod.build_brief(a,b,s,g)
        self.assertEqual(len(result['user_questions_candidates']),1)
        self.assertEqual(result['user_questions_candidates'][0]['routing'],
            'A3_RESEARCH_FIRST_THEN_OWNER_IF_MATERIAL_UNRESOLVED')
        self.assertFalse(result['owner_questions_sent'])
        self.assertFalse(result['a3_allowed'])
        self.assertIn('definiciones',result['a3_investigation_tasks'][1]['request'])

    def test_08c_negative_constraint_remains_verbatim_without_owner_question(self):
        a,b,s,g=fixture()
        a['payload']['constraints']=['No crees otra pantalla; usa la existente']
        result=mod.build_brief(a,b,s,g)
        self.assertEqual(result['scope_constraints_declared'],a['payload']['constraints'])
        self.assertEqual(result['user_questions_candidates'],[])
        self.assertIn('No crees otra pantalla',result['human_readable_document'])
        self.assertTrue(result['intent_review_required'])

    def test_08d_owner_question_does_not_reopen_resolved_material(self):
        a,b,s,g=fixture()
        a['payload']['ambiguities']=[{
            'code':'ALREADY_RESOLVED',
            'statement':'Resuelta mediante definición vigente',
            'materiality':'MATERIAL','resolution_state':'RESOLVED_FROM_SOURCE'
        }]
        result=mod.build_brief(a,b,s,g)
        self.assertEqual(result['user_questions_candidates'],[])
        self.assertEqual(result['recorded_open_ambiguities'],[])
        self.assertFalse(result['a3_allowed'])

    def test_09_required_33_are_not_lost(self):
        v=prepare_preview(*fixture())['human_intent_brief']
        self.assertEqual(len(v['required_evidence_gaps']),33)
        self.assertEqual(len(set(v['required_evidence_gaps'])),33)
        self.assertEqual(v['required_evidence_gaps_status'],'33_MANDATORY_ITEMS_NEED_A3_EVIDENCE')
    def test_10_no_auto_run_and_no_judge(self):
        v=prepare_preview(*fixture())['human_intent_brief']
        self.assertFalse(v['source_attested']);self.assertFalse(v['independent_judge_verified'])
        self.assertFalse(v['run_verified']);self.assertFalse(v['a3_allowed'])
        self.assertIsNone(v['next_step'])
    def test_11_does_not_mutate_originals(self):
        x=fixture();prior=copy.deepcopy(x);prepare_preview(*x);self.assertEqual(x,prior)
    def test_12_empty_goal_blocked(self):
        a,b,s,g=fixture();a['payload']['objective']['desired_outcome']=' '
        self.assertEqual(mod.build_brief(a,b,s,g)['blocking_codes'],['INTENT_OBJECTIVE_INCOMPLETE'])
    def test_13_invalid_ambiguity_input_blocked(self):
        a,b,s,g=fixture();a['payload']['ambiguities']=['resolved']
        self.assertEqual(mod.build_brief(a,b,s,g)['blocking_codes'],['INTENT_AMBIGUITY_INPUT_INVALID'])
    def test_14_no_scope_mixing(self):
        a,b,s,g=fixture();a['business']='SALY'
        self.assertEqual(mod.build_brief(a,b,s,g)['blocking_codes'],['INTENT_BUSINESS_MISMATCH'])
    def test_15_target_must_appear_in_A1(self):
        a,b,s,g=fixture();b['classification']['target_ref']='OTHER'
        self.assertEqual(mod.build_brief(a,b,s,g)['blocking_codes'],['INTENT_TARGET_UNDECLARED'])
    def test_16_no_fake_golden_satisfied(self):
        a,b,s,g=fixture();g['dimension_results'][0]['elements'][0]['fulfilment']='SATISFIED'
        self.assertEqual(mod.build_brief(a,b,s,g)['blocking_codes'],['INTENT_ELEMENT_STATUS_DRIFT'])
    def test_17_explicit_source_binding(self):
        a,b,s,g=fixture();v=mod.build_brief(a,b,s,g)
        self.assertEqual(v['source_binding']['a1_result_sha256'],mod.digest(a))
        self.assertEqual(v['source_binding']['golden_handoff_sha256'],mod.digest(g))
    def test_18_no_source_is_blocked(self):
        a,b,s,g=fixture();a['payload']['source_refs']=[]
        self.assertEqual(mod.build_brief(a,b,s,g)['blocking_codes'],['INTENT_SOURCE_REFS_REQUIRED'])
    def test_19_brief_in_preview_digest(self):
        r=prepare_preview(*fixture())
        calc=mod.digest({'a3_input':r['a3_input_preview'],'research_plan':r['a3_resolution_plan_preview'], 'human_intent_brief':r['human_intent_brief']})
        self.assertEqual(r['preview_digest_sha256'],calc)
    def test_20_canonical_contract_not_replaced(self):
        r=prepare_preview(*fixture())
        self.assertEqual(set(r['a3_input_preview']),{'REQUEST_CONTEXT_V1','ANALYSIS_CHANGE_CLASSIFICATION_V1'})
        self.assertNotIn('human_intent_brief',r['a3_input_preview'])

if __name__=='__main__':unittest.main()
