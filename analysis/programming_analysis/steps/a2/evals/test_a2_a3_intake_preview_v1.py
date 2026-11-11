"""Source-only integration tests for the A2→A3 transport envelope."""
import unittest,copy,importlib.util
from pathlib import Path
from test_golden_handoff_v03 import run
from test_a2 import a1input, low, RUN_A1, RUN as RUN_A2
A2_BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('a2_a3_intake_preview',A2_BASE/'adapters/a2_a3_intake_preview_v1.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
prepare_preview=module.prepare_preview
def fixture():
  # Use real A1/A2 validators, not the historic A1_SOURCE_CANDIDATE_V1 fixture.
  a=RUN_A1.run(a1input())
  s=low()
  b=RUN_A2.run(a,s)
  return a,b,s,run(a,b,s)
class IntakePreview(unittest.TestCase):
 def test_real_a1_a2_validator_chain(self):
  a,b,s,g=fixture()
  self.assertEqual(a['schema_version'],'A1_INTERNAL_STEP_CANDIDATE_RESULT_V1')
  self.assertEqual(a['status'],'VALID_OUTPUT')
  self.assertEqual(b['schema_version'],'A2_INTERNAL_STEP_CANDIDATE_RESULT_V1')
  self.assertEqual(b['status'],'CANDIDATE_UNATTESTED')
  self.assertEqual(g['canonical_classification'],b['classification'])
  self.assertEqual(prepare_preview(a,b,s,g)['status'],'PREVIEW_PREPARED_NOT_DISPATCHABLE')
 def test_obsolete_a1_schema_refused(self):
  a,b,s,g=fixture()
  a['schema_version']='A1_SOURCE_CANDIDATE_V1'
  self.assertEqual(prepare_preview(a,b,s,g)['blocking_codes'],['A2_A3_A1_NOT_ELIGIBLE'])
 def reject(self, mutate, code):
  x=fixture();mutate(*x);r=prepare_preview(*x)
  self.assertEqual(r['status'],'BLOCKED',r);self.assertEqual(r['blocking_codes'],[code]);self.assertFalse(r['a3_allowed'])
 def test_positive_prepared_not_dispatched(self):
  a,b,s,g=fixture();r=prepare_preview(a,b,s,g)
  self.assertEqual(r['status'],'PREVIEW_PREPARED_NOT_DISPATCHABLE')
  self.assertEqual(set(r['a3_input_preview']),{'REQUEST_CONTEXT_V1','ANALYSIS_CHANGE_CLASSIFICATION_V1'})
  self.assertEqual(r['business'],'LF');self.assertEqual(len(r['a3_resolution_plan_preview']['source_resolution_requests']),26)
  self.assertFalse(r['a3_allowed']);self.assertIsNone(r['next_step']);self.assertFalse(r['source_authenticated'])
 def test_no_mutation(self):
  x=fixture();original=copy.deepcopy(x);prepare_preview(*x);self.assertEqual(x,original)
 def test_business_drift(self):self.reject(lambda a,b,s,g:b.update(business='SALY'),'A2_A3_BUSINESS_CROSS_SCOPE')
 def test_signal_drift(self):self.reject(lambda a,b,s,g:s['depth_signals'].update(materiality_level='HIGH'),'A2_A3_SIGNALS_DIGEST_MISMATCH')
 def test_missing_nine_signals(self):self.reject(lambda a,b,s,g:s['depth_signals'].pop('materiality_level'),'A2_A3_NINE_SIGNALS_REQUIRED')
 def test_missing_a1(self):self.reject(lambda a,b,s,g:a.update(status='BLOCKED'),'A2_A3_A1_NOT_ELIGIBLE')
 def test_forged_a2_authority(self):self.reject(lambda a,b,s,g:b.update(independent_judge_verified=True),'A2_A3_A2_FALSE_AUTHORITY')
 def test_changed_target(self):self.reject(lambda a,b,s,g:b['classification'].update(target_ref='OTHER'),'A2_A3_TARGET_NOT_IN_A1')
 def test_golden_class_conflict(self):self.reject(lambda a,b,s,g:g['canonical_classification'].update(depth_level='L3'),'A2_A3_GOLDEN_CLASSIFICATION_CONFLICT')
 def test_a1_source_drift(self):self.reject(lambda a,b,s,g:a['payload']['objective'].update(problem_statement='Altered'),'A2_A3_SOURCE_BINDING_DRIFT')
 def test_a3_source_sha_drift(self):self.reject(lambda a,b,s,g:g['source_binding'].update(a3_contract_blob_sha1='0'*40),'A2_A3_SOURCE_BINDING_DRIFT')
 def test_false_golden_judge(self):self.reject(lambda a,b,s,g:g['producer_assertions'].update(independent_judge_verified=True),'A2_A3_GOLDEN_FALSE_AUTHORITY')
 def test_missed_element(self):self.reject(lambda a,b,s,g:g['dimension_results'][0]['elements'].pop(),'A2_A3_ELEMENTS_MISSING_OR_DUPLICATED')
 def test_false_satisfied(self):self.reject(lambda a,b,s,g:g['dimension_results'][0]['elements'][0].update(fulfilment='SATISFIED'),'A2_A3_ELEMENT_FALSE_COMPLETION')
 def test_false_signal_attestation(self):self.reject(lambda a,b,s,g:g['signal_evidence_map'][0].update(attestation_state='VERIFIED'),'A2_A3_SIGNAL_LINEAGE_FALSE_AUTHORITY')
 def test_one_signal_not_lineaged(self):self.reject(lambda a,b,s,g:g['signal_evidence_map'].pop(),'A2_A3_SIGNAL_LINEAGE_INCOMPLETE')
 def test_false_consumer_ready(self):self.reject(lambda a,b,s,g:g['a3_resolution_plan'].update(consumer_state='READY'),'A2_A3_RESOLUTION_PLAN_INVALID')
 def test_missing_research_need(self):self.reject(lambda a,b,s,g:g['a3_resolution_plan']['source_resolution_requests'].pop(),'A2_A3_RESEARCH_REQUEST_COVERAGE_MISSING')
 def test_corrupt_research_need_id(self):self.reject(lambda a,b,s,g:g['a3_resolution_plan']['source_resolution_requests'][0].update(need_id='OTHER'),'A2_A3_RESEARCH_REQUEST_ID_MISMATCH')
 def test_no_question(self):self.reject(lambda a,b,s,g:g['a3_resolution_plan']['source_resolution_requests'][0].update(material_question=' '),'A2_A3_RESEARCH_REQUEST_NOT_EVIDENCED')
 def test_no_target_authority(self):self.reject(lambda a,b,s,g:g['a3_resolution_plan']['target_resolution_requests'][0].update(expected_evidence='NOT_REQUIRED'),'A2_A3_TARGET_AUTHORITY_QUERY_MISSING')
 def test_no_business(self):self.reject(lambda a,b,s,g:a.update(business=None),'A2_A3_A1_BUSINESS_INVALID')
if __name__=='__main__':unittest.main(verbosity=2)
