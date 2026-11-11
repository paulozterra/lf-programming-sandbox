import json
from pathlib import Path
import unittest
P=Path(__file__).resolve().parents[1]
REPO=P.parents[1]
M=json.loads((P/'contracts/analysis_skill_manifest_v1.json').read_text(encoding='utf-8'))
class AnalysisStagePackage(unittest.TestCase):
 def test_single_skill(self):
  self.assertEqual(M['skill_code'],'PROGRAMMING_ANALYSIS_LF')
  self.assertEqual(M['external_invocations'],1)
  self.assertFalse(M['standalone_a1_registration_allowed'])
 def test_15_steps(self):
  self.assertEqual([x['step_id'] for x in M['steps']],[f'A{i}' for i in range(1,16)])
 def test_internal_a1(self):
  self.assertTrue((P/'steps/a1/STEP.md').is_file())
  self.assertFalse((P/'steps/a1/SKILL.md').exists())
  self.assertFalse((REPO/'skills/programming_analysis_a1/SKILL.md').exists())
  self.assertEqual(M['steps'][0]['module_entrypoint'],'steps/a1/validators/run.py:run')
 def test_canonical_sources(self):
  for s in M['steps']:
   with self.subTest(step=s['step_id']):self.assertTrue((REPO/s['source_contract']).is_file(),s['source_contract'])
 def test_non_operational(self):
  self.assertEqual(M['status'],'REGISTERED_CANDIDATE_RUNTIME_DISABLED')
  self.assertTrue(all(not s['operationally_verified'] for s in M['steps']))
  self.assertFalse(M['real_model_receipts'])
  self.assertFalse(M['independent_judge_receipts'])
 def test_no_parallel_engine(self):
  self.assertTrue(M['no_router_to_skill_direct'])
  self.assertTrue(M['no_internal_parallel_runner'])
 def test_procedure_parity(self):
  src=json.loads((REPO/M['procedure_source']).read_text(encoding='utf-8'))
  self.assertEqual([s['source_contract'] for s in M['steps'][:9]],[s['source_contract'] for s in src['steps']])
 def test_a3_candidate_consumer_and_remaining_steps_not_fake_executors(self):
  a3=M['steps'][2]
  self.assertEqual(a3['module_entrypoint'],'steps/a3/validators/run.py:run')
  self.assertTrue((P/'steps/a3/validators/run.py').is_file())
  self.assertEqual(a3['implementation_state'],'LOCAL_SOURCE_READBACK_CONSUMER_CANDIDATE_UNQUALIFIED')
  self.assertFalse(a3['operationally_verified'])
  self.assertFalse(a3['source_attested'])
  self.assertFalse(a3['next_step_allowed'])
  self.assertTrue(all(s['module_entrypoint'] is None for s in M['steps'][3:]))
 def test_a2_internal_candidate_not_operational(self):
  self.assertEqual(M['steps'][1]['module_entrypoint'],'steps/a2/validators/run.py:run')
  self.assertEqual(M['steps'][1]['implementation_state'],'LOCAL_TYPED_POLICY_PROJECTION_CANDIDATE_UNQUALIFIED')
  self.assertFalse(M['steps'][1]['operationally_verified'])
  self.assertFalse(M['steps'][1]['source_attested'])
  self.assertFalse(M['steps'][1]['next_step_allowed'])
 def test_asset_registered_but_runtime_disabled(self):
  self.assertEqual(M['asset_registration']['asset_id'],414)
  self.assertFalse(M['asset_registration']['runtime_binding_enabled'])
 def test_A10_A15_requirements_not_falsely_empty(self):
  for s in M['steps'][9:]:
   with self.subTest(step=s['step_id']):
    self.assertIsNone(s['requires'])
    self.assertEqual(s['input_required_state'],'NOT_RECONCILED_FROM_CANONICAL_VALIDATION_SOURCE')
    self.assertTrue(s['no_input_inference_allowed'])
 def test_exactly_one_skill_file(self):
  self.assertEqual([x.relative_to(P).as_posix() for x in P.rglob('SKILL.md')],['SKILL.md'])
 def test_a1_step_envelope_identifies_parent(self):
  schema=json.loads((P/'steps/a1/schemas/output.schema.json').read_text(encoding='utf-8'))
  self.assertEqual(schema['properties']['skill_code']['const'],M['skill_code'])
  self.assertEqual(schema['properties']['schema_version']['const'],'A1_INTERNAL_STEP_CANDIDATE_RESULT_V1')
  self.assertEqual(schema['properties']['step_code']['const'],'A1')
 def test_operation_steps_are_not_analysis_steps(self):
  self.assertEqual(M['operation_code'],'EJECUCION_SKILL_LF')
  self.assertEqual(M['internal_step_count'],15)
  self.assertNotEqual(M['internal_step_count'],9)
if __name__=='__main__':unittest.main()
