"""Offline, source-only behavioral tests; no real judge, A3 or inventory."""
import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / 'adapters'
spec = importlib.util.spec_from_file_location('a2_unresolved', HERE / 'unresolved_research_preview_v1.py')
impl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impl)


def make(case='02'):
    if case == '02':
        raw = 'Necesito una vista para que las empresas entren al portal'
        op, target, cap, mention = 'IMPLEMENT', 'SCREEN', 'ENTERPRISE_PORTAL_ACCESS', 'vista para que las empresas entren al portal'
        constraint = []
        code = 'PORTAL_ENTRY_MODE_UNRESOLVED'
        statement = 'La solicitud no determina si la entrada requiere autenticación o si consiste en navegación/acceso al portal.'
        spans = [('OPERATION', 'Necesito'), ('ARTIFACT', 'vista'),
                 ('CAPABILITY', 'entren al portal'), ('ACTOR_SCOPE', 'empresas')]
    else:
        raw = 'No crees otra pantalla; usa la existente'
        op, target, cap, mention = 'REUSE', 'SCREEN', 'UNKNOWN', 'pantalla'
        constraint = ['No crees otra pantalla']
        code = 'FUNCTIONAL_CAPABILITY_UNSPECIFIED'
        statement = 'La funcionalidad de la pantalla existente no está especificada.'
        spans = [('OPERATION', 'usa la existente'), ('ARTIFACT', 'pantalla'),
                 ('ASSUMPTION', 'existente'), ('NEGATION', 'No crees otra pantalla')]
    intent = {
        'operation': {'kind': op},
        'desired_outcome': 'Reutilizar existente' if case=='04' else 'Acceso portal',
        'explicit_constraints': [{'text': x} for x in constraint],
        'target': {'artifact_kind': target, 'canonical_capability': cap,
                   'raw_mentions': [mention]},
        'evidence_spans': [{'dimension': kind, 'quote': quote,
                            'start': raw.index(quote), 'end': raw.index(quote)+len(quote)}
                           for kind, quote in spans],
        'material_ambiguities': [{'code': code, 'statement': statement, 'materiality': 'MATERIAL'}],
        'dimensions_to_investigate': ['EXISTING_ARTIFACT_INVENTORY', code],
    }
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return {
        'schema_version': 'A1_INTERNAL_STEP_CANDIDATE_RESULT_V1',
        'skill_code': 'PROGRAMMING_ANALYSIS_LF', 'step_code': 'A1',
        'status': 'REQUIRES_DECISION', 'business': 'LF',
        'next_capability': None, 'external_authority_verified': False,
        'operationally_integrated': False, 'effects_executed': False,
        'semantic_review_identity_verified': False,
        'interpretation_state': 'SEMANTIC_CANDIDATE_UNATTESTED',
        'semantic_reviewer_ref': 'fixture://not-an-independent-review',
        'original_request_sha256': digest,
        'semantic_candidate_sha256': impl._hash(intent),
        'intent_analysis': intent,
        'payload': {
            'objective': {'problem_statement': raw, 'desired_outcome': 'Reutilizar existente' if case=='04' else 'Acceso portal'},
            'source_refs': ['user://a1-raw-'+digest[:20]],
            'target_hints': [mention],
            'constraints': constraint,
            'ambiguities': [{'code': code, 'statement': statement,
                             'materiality': 'MATERIAL', 'resolution_state': 'OPEN'}],
        },
    }


class PendingResearchTests(unittest.TestCase):
    def test_02_access_does_not_infer_auth(self):
        r = impl.prepare(make('02'))
        self.assertEqual(r['status'], 'RESEARCH_PLAN_ONLY')
        self.assertEqual(r['research_plan']['functional_capability_hint'], 'ENTERPRISE_PORTAL_ACCESS')
        self.assertEqual(r['research_plan']['unresolved_ambiguities'][0]['code'], 'PORTAL_ENTRY_MODE_UNRESOLVED')
        self.assertEqual(r['research_plan']['source_research_tasks'][0]['priority_order'], list(impl.RESOLUTION_ORDER))
        self.assertFalse(r['a3_dispatch_allowed'])
        self.assertIsNone(r['a2_classification'])

    def test_04_reuse_and_negation_preserved(self):
        r = impl.prepare(make('04'))
        self.assertEqual(r['status'], 'RESEARCH_PLAN_ONLY')
        self.assertEqual(r['research_plan']['operation_hint'], 'REUSE')
        self.assertEqual(r['research_plan']['constraints'], ['No crees otra pantalla'])
        self.assertEqual(r['research_plan']['functional_capability_hint'], 'UNKNOWN')
        self.assertFalse(r['a2_depth_classified'])
        self.assertFalse(r['source_authenticated'])

    def test_no_mutation(self):
        x = make('04'); original = copy.deepcopy(x)
        impl.prepare(x)
        self.assertEqual(x, original)

    def test_no_semantic_judge_identity_claim(self):
        r=impl.prepare(make('02'))
        self.assertFalse(r['independent_judge_attested'])
        self.assertFalse(r['runtime_integrated'])
        self.assertIsNone(r['a3_canonical_inputs'])

    def test_status_valid_output_is_not_decision_preview(self):
        x = make('02'); x['status'] = 'VALID_OUTPUT'
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_A1_DECISION_REQUIRED'])

    def test_semantic_candidate_hash_tamper(self):
        x = make('02'); x['intent_analysis']['target']['canonical_capability']='AUTH_FLOW'
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_A1_DIGEST_MISMATCH'])

    def test_raw_request_hash_tamper(self):
        x = make('04'); x['original_request_sha256'] = '0' * 64
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_A1_DIGEST_MISMATCH'])

    def test_constraint_negation_removed(self):
        x = make('04'); x['intent_analysis']['evidence_spans'] = [s for s in x['intent_analysis']['evidence_spans'] if s['dimension']!='NEGATION']
        x['semantic_candidate_sha256']=impl._hash(x['intent_analysis'])
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_CONSTRAINT_SPAN_MISSING'])

    def test_mismatch_declared_ambiguity(self):
        x = make('02'); x['payload']['ambiguities'][0]['code'] = 'NEW_NOT_DECLARED'
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_MATERIAL_AMBIGUITY_DRIFT'])

    def test_closed_ambiguity_cannot_generate_preview(self):
        x = make('04'); x['payload']['ambiguities'][0]['resolution_state'] = 'RESOLVED_FROM_SOURCE'
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_MATERIAL_AMBIGUITY_DRIFT'])

    def test_false_authority_refused(self):
        x=make('02'); x['external_authority_verified'] = True
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_A1_FALSE_AUTHORITY'])

    def test_target_drift_refused(self):
        x=make('02'); x['payload']['target_hints'] = ['NOT_IN_RAW']
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_SOURCE_OR_CONSTRAINT_DRIFT'])

    def test_semantic_span_index_drift_refused(self):
        x=make('02'); x['intent_analysis']['evidence_spans'][0]['end'] -= 1
        x['semantic_candidate_sha256']=impl._hash(x['intent_analysis'])
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_SEMANTIC_EVIDENCE_DRIFT'])

    def test_missing_source_refs_refused(self):
        x=make('04'); x['payload']['source_refs'] = []
        self.assertEqual(impl.prepare(x)['blocking_codes'], ['A2_RESEARCH_SOURCE_OR_CONSTRAINT_DRIFT'])

    def test_material_negation_cannot_disappear_from_payload(self):
        x=make('04')
        x['payload']['constraints'] = []
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_EXPLICIT_CONSTRAINT_DRIFT'])

    def test_extra_payload_constraint_cannot_be_injected(self):
        x=make('04')
        x['payload']['constraints'] = ['No crees otra pantalla', 'usa la existente']
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_EXPLICIT_CONSTRAINT_DRIFT'])

    def test_desired_outcome_cannot_change_without_intent_hash(self):
        x=make('02')
        x['payload']['objective']['desired_outcome'] = 'Crear credenciales B2B'
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_DESIRED_OUTCOME_DRIFT'])

    def test_missing_semantic_outcome_is_not_assumed(self):
        x=make('02')
        del x['intent_analysis']['desired_outcome']
        x['semantic_candidate_sha256'] = impl._hash(x['intent_analysis'])
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_DESIRED_OUTCOME_DRIFT'])

    def test_untyped_raw_mentions_fail_closed(self):
        x=make('04')
        x['intent_analysis']['target']['raw_mentions']=None
        x['semantic_candidate_sha256']=impl._hash(x['intent_analysis'])
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_SOURCE_OR_CONSTRAINT_DRIFT'])

    def test_extra_target_hint_not_in_A1_intent_rejected(self):
        x=make('02')
        x['payload']['target_hints'].append('INVENTED_SCREEN')
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_SOURCE_OR_CONSTRAINT_DRIFT'])

    def test_malformed_declared_ambiguity_fail_closed_no_exception(self):
        x=make('02')
        x['intent_analysis']['material_ambiguities'][0]['code']=['NOT_A_CODE']
        x['semantic_candidate_sha256']=impl._hash(x['intent_analysis'])
        self.assertEqual(impl.prepare(x)['blocking_codes'],
                         ['A2_RESEARCH_AMBIGUITY_INVALID'])

    def test_02_work_order_specific_to_portal_ambiguity(self):
        order=impl.prepare(make('02'))['research_plan']['actionable_research_order']
        self.assertEqual(order['status'], 'SOURCE_RESEARCH_INSTRUCTIONS_ONLY')
        self.assertEqual(order['requested_operation'], 'IMPLEMENT')
        questions=[x['question'] for x in order['tasks']]
        self.assertTrue(any('autenticación' in q for q in questions))
        self.assertTrue(any('PORTAL_ENTRY_MODE' in q for q in questions))
        self.assertFalse(order['a3_dispatch_allowed'])
        self.assertFalse(order['implementation_allowed'])
        self.assertFalse(order['source_refs_are_current_verified'])

    def test_04_work_order_requires_reuse_and_no_new_screen(self):
        order=impl.prepare(make('04'))['research_plan']['actionable_research_order']
        self.assertEqual(order['requested_operation'], 'REUSE')
        contra=[x for x in order['tasks'] if x['id'].startswith('A3-CONSTRAINT-')]
        self.assertEqual(len(contra), 1)
        self.assertEqual(contra[0]['literal_constraint'], 'No crees otra pantalla')
        self.assertIn('infrinja', contra[0]['verify'][1])
        self.assertEqual(order['decision_if_no_delta'],
                         'NO_CHANGE_CANDIDATE: no modificar; verificar por evidencia antes de cerrar')

    def test_work_orders_differ_by_user_intent_not_generic_boilerplate(self):
        a=impl.prepare(make('02'))['research_plan']['actionable_research_order']
        b=impl.prepare(make('04'))['research_plan']['actionable_research_order']
        self.assertNotEqual(a['tasks'],b['tasks'])
        self.assertNotEqual(a['target_hint_unverified'], b['target_hint_unverified'])
        self.assertNotEqual(a['requested_operation'], b['requested_operation'])
        self.assertNotEqual(
            [t.get('ambiguity_code') for t in a['tasks'] if 'ambiguity_code' in t],
            [t.get('ambiguity_code') for t in b['tasks'] if 'ambiguity_code' in t]
        )

    def test_work_order_requires_verifiable_source_and_delta(self):
        order=impl.prepare(make('04'))['research_plan']['actionable_research_order']
        self.assertEqual(order['source_resolution_order'],list(impl.RESOLUTION_ORDER))
        ids=[t['id'] for t in order['tasks']]
        self.assertEqual(ids[:4], [
            'A3-01-IDENTITY','A3-02-BASELINE','A3-03-DELTA','A3-04-IMPACT'
        ])
        self.assertTrue(any('versión/hash' in x for x in order['tasks'][0]['evidence_required']))
        self.assertTrue(any('explicit_delta' in x for x in order['tasks'][2]['evidence_required']))
        self.assertEqual(len(order['acceptance_after_research']),5)

    def test_no_change_is_a_candidate_not_approved_change(self):
        r=impl.prepare(make('02'))
        order=r['research_plan']['actionable_research_order']
        self.assertIn('NO_CHANGE_CANDIDATE',order['decision_if_no_delta'])
        self.assertEqual(r['status'],'RESEARCH_PLAN_ONLY')
        self.assertIsNone(r['a2_classification'])
        self.assertIsNone(r['a3_canonical_inputs'])
        self.assertFalse(r['a3_dispatch_allowed'])

    def test_no_user_refs_promoted_to_verified_currentness(self):
        order=impl.prepare(make('04'))['research_plan']['actionable_research_order']
        self.assertFalse(order['source_refs_are_current_verified'])
        self.assertEqual(order['decision_if_evidence_missing'],
                         'NEED_MORE_EVIDENCE; no clasificar como READY')
        self.assertFalse(order['implementation_allowed'])
        self.assertTrue(all(t['evidence_required'] for t in order['tasks']))

    def test_cannot_escalate_owner_question_automatically(self):
        r=impl.prepare(make('04'))
        self.assertEqual(r['research_plan']['source_research_tasks'][0]['owner_decision'],
                         'ONLY_IF_MATERIAL_UNRESOLVED_AFTER_SOURCE_REVIEW')
        self.assertIsNone(r['next_step'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
