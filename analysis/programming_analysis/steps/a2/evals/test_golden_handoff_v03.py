"""Validate the existing v0.3 proposed A2 Golden handoff, without real authority."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]

def load(rel,name):
    spec=importlib.util.spec_from_file_location(name,ROOT / rel)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

fixture_mod=load('evals/test_golden_dimensions_v1.py','golden_fixture_v1')
v03=load('adapters/golden_handoff_v03.py','golden_v03')
CATALOG=ROOT/'catalog/A2_GOLDEN_CATALOGO_DIMENSIONAL_v0_2.json'
SCHEMA=ROOT/'schemas/A2_GOLDEN_CONTRATO_SALIDA_PROPUESTA_v0_3.schema.json'

def make():
    return fixture_mod.fixture()

def run(*args):
    if not args:args=make()
    return v03.prepare_golden_v03(*args,catalog_path=CATALOG,schema_path=SCHEMA)

class GoldenV03(unittest.TestCase):
    def test_schema_exact_and_59_elements(self):
        r=run();self.assertEqual(r['schema_version'],'A2_GOLDEN_HANDOFF_PROPOSAL_V0_3')
        self.assertFalse(list(Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(r)))
        self.assertEqual(len(r['dimension_results']),12)
        self.assertEqual(sum(len(x['elements']) for x in r['dimension_results']),59)
        self.assertEqual(len(r['a3_resolution_plan']['source_resolution_requests']),26)
    def test_no_data_loss_source_and_input_hash(self):
        a,b,s=make();r=run(a,b,s)
        self.assertEqual(r['source_binding']['a1_output_sha256'],v03._digest(a))
        self.assertEqual(r['source_binding']['signal_bundle_sha256'],v03._digest(s))
        self.assertEqual(r['canonical_classification'],b['classification'])
    def test_exact_catalog_and_policy_binding(self):
        r=run();self.assertEqual(r['source_binding']['catalog_sha256'],hashlib.sha256(CATALOG.read_bytes()).hexdigest())
        self.assertEqual(r['source_binding']['a2_policy_blob_sha1'],'0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051')
    def test_26_conditional_and_33_fixed(self):
        r=run();items=[e for d in r['dimension_results'] for e in d['elements']]
        self.assertEqual(sum(x['applicability']=='REQUIRED' for x in items),33)
        self.assertEqual(sum(x['applicability']!='REQUIRED' for x in items),26)
        self.assertEqual(sum(x['applicability']=='NOT_APPLICABLE' for x in items),0)
        self.assertTrue(all(x['fulfilment']=='PENDING_EVIDENCE' for x in items))
    def test_a3_needs_have_exact_references(self):
        r=run();items=[e for d in r['dimension_results'] for e in d['elements']]
        reqs={x['need_id'] for x in r['a3_resolution_plan']['source_resolution_requests']}
        self.assertTrue(all(set(e['a3_need_refs']).issubset(reqs) for e in items))
        self.assertEqual(len(reqs),26)
    def test_26_activation_cases_validate_against_proposed_schema(self):
        for eid,mutate in fixture_mod.POSITIVES.items():
            with self.subTest(eid=eid):
                a,b,s=make();mutate(a,b,s['depth_signals'])
                if eid=='D02-E02':
                    s['target_granularity']='CONTROL';s['nested_parent_ref']='MODULE-1';b['classification']['target_granularity']='CONTROL'
                b['classification']['signals_sha256']=fixture_mod._digest(s)
                r=run(a,b,s)
                self.assertEqual(r.get('schema_version'),'A2_GOLDEN_HANDOFF_PROPOSAL_V0_3')
                items=[e for d in r['dimension_results'] for e in d['elements']]
                self.assertEqual(next(e for e in items if e['element_id']==eid)['applicability'],'CONDITIONAL_REQUIRED')
    def test_no_external_authority_or_judge(self):
        r=run();self.assertEqual(r['contract_status'],'DESIGN_CANDIDATE_NOT_ADMITTED')
        self.assertEqual(r['a3_resolution_plan']['consumer_state'],'PENDING_NATIVE_REVIEW')
        self.assertFalse(any(r['producer_assertions'][key] for key in ('source_attested','independent_judge_verified','effects_executed','operationally_integrated')))
        self.assertIsNone(r['producer_assertions']['next_step'])
    def test_no_forged_semantic_receipt_element(self):
        r=run();e=next(e for d in r['dimension_results'] for e in d['elements'] if e['element_id']=='D12-E05')
        self.assertIsNone(e['finding']);self.assertEqual(e['gap_codes'],[])
        self.assertEqual(e['a3_need_refs'],[]);self.assertEqual(e['fulfilment'],'PENDING_EVIDENCE')
    def test_preserve_need_more_evidence(self):
        a,b,s=make();b['status']='NEED_MORE_EVIDENCE';r=run(a,b,s)
        self.assertEqual(r['processing_state'],'NEED_MORE_EVIDENCE')
        self.assertTrue(r['a3_resolution_plan']['source_resolution_requests'])
    def test_missing_schema_blocks(self):
        a,b,s=make();r=v03.prepare_golden_v03(a,b,s,catalog_path=CATALOG,schema_path=ROOT/'schemas/absent.json')
        self.assertEqual(r['blocking_codes'],['GOLDEN_V03_SCHEMA_SOURCE_UNAVAILABLE_OR_DRIFTED'])
    def test_schema_drift_blocks(self):
        tmp=Path(tempfile.gettempdir())/'altered_a2_golden_schema.json'
        tmp.write_bytes(SCHEMA.read_bytes()+b' ')
        a,b,s=make();r=v03.prepare_golden_v03(a,b,s,catalog_path=CATALOG,schema_path=tmp)
        self.assertEqual(r['blocking_codes'],['GOLDEN_V03_SCHEMA_SOURCE_UNAVAILABLE_OR_DRIFTED'])
    def test_a1_business_drift_blocks(self):
        a,b,s=make();a['business']='SALY';r=run(a,b,s)
        self.assertEqual(r['blocking_codes'],['GOLDEN_BUSINESS_CONFLICT'])
    def test_model_claim_of_judge_blocks(self):
        a,b,s=make();b['independent_judge_verified']=True;r=run(a,b,s)
        self.assertEqual(r['blocking_codes'],['GOLDEN_FORGED_OPERATIONAL_AUTHORITY'])
    def test_no_mutation(self):
        inputs=make();b=copy.deepcopy(inputs);run(*inputs);self.assertEqual(inputs,b)
    def test_bad_canonical_classification_no_output(self):
        a,b,s=make();del b['classification']['nested_parent_ref'];r=run(a,b,s)
        self.assertEqual(r['blocking_codes'],['GOLDEN_V03_OUTPUT_SCHEMA_NOT_MET'])

if __name__=='__main__':unittest.main(verbosity=2)
