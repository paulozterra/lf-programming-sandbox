"""A2 Golden source-only dynamic 12/59 candidate, independent negative cases."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import importlib.util
ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("a2_golden_dimensions", ROOT / "adapters/golden_dimensions_v1.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build_golden, load_catalog, COND_IDS, _digest = module.build_golden, module.load_catalog, module.COND_IDS, module._digest

CATALOG=ROOT / "catalog/A2_GOLDEN_CATALOGO_DIMENSIONAL_v0_2.json"


def fixture():
    a1={"schema_version":"A1_SOURCE_CANDIDATE_V1", "business":"LF",
        "status":"VALID_OUTPUT","interpretation_state":"PRESTRUCTURED_UNATTESTED",
        "semantic_review_required":False,
        "payload":{"objective":{"problem_statement":"Revisar ingreso B2B LF","desired_outcome":"Definir requisitos"},
                   "target_hints":["B2B-AUTH-001"],"source_refs":["user://case-1"],
                   "provided_facts":[],"ambiguities":[]}}
    bundle={"schema_version":"ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1","business":"LF",
        "target_ref":"B2B-AUTH-001","change_type":"REVIEW","target_granularity":"SCREEN",
        "nested_parent_ref":None,"evidence_refs":["user://case-1"],
        "depth_signals":{
            "materiality_level":"LOW","scope_bounded":"TRUE","authority_state":"SUFFICIENT",
            "reversibility_state":"DEMONSTRATED","currentness_decision":"CURRENT",
            "material_contradiction":False,"known_cross_scope_impact":False,
            "unresolved_material_signal_count":0,"required_specialist_count":0}}
    a2={"schema_version":"A2_INTERNAL_STEP_CANDIDATE_RESULT_V1","business":"LF",
        "status":"CANDIDATE_UNATTESTED", "source_attested":False,
        "independent_judge_verified":False,"next_step":None,
        "classification":{"schema_version":"ANALYSIS_CHANGE_CLASSIFICATION_V1",
          "change_type":"REVIEW","target_ref":"B2B-AUTH-001","target_granularity":"SCREEN",
          "depth_level":"L1","nested_parent_ref":None,"depth_reason_predicates":["materiality_level=LOW"],"evidence_refs":["user://case-1"],"specialist_resolution":"NOT_REQUESTED","signals_sha256":_digest(bundle)}}
    return a1,a2,bundle


def run(*args):
    if not args:args=fixture()
    return build_golden(*args,catalog_path=CATALOG)


def setfact(a1,code):
    a1['payload']['provided_facts'].append({'fact_code':code,'value':'TRUE','source_ref':'user://case-1'})

# Each of the 26 has a witness of positive activation. Source-only, not CURRENT.
POSITIVES={
 "D01-E04":lambda a,b,s:a['payload']['ambiguities'].append('Scope material'),
 "D02-E02":lambda a,b,s:None,
 "D02-E04":lambda a,b,s:a['payload']['target_hints'].append('SECOND-TARGET'),
 "D02-E05":lambda a,b,s:s.update(known_cross_scope_impact='UNKNOWN'),
 "D03-E03":lambda a,b,s:s.update(materiality_level='HIGH'),
 "D03-E05":lambda a,b,s:s.update(materiality_level='UNKNOWN'),
 "D04-E03":lambda a,b,s:s.update(materiality_level='MEDIUM'),
 "D04-E04":lambda a,b,s:s.update(material_contradiction=True),
 "D04-E05":lambda a,b,s:setfact(a,'RISK_REGISTER_EMPTY'),
 "D05-E03":lambda a,b,s:s.update(authority_state='INSUFFICIENT'),
 "D05-E04":lambda a,b,s:setfact(a,'AUTHORITY_CONFLICT'),
 "D06-E04":lambda a,b,s:s.update(currentness_decision='UNKNOWN_FAIL_CLOSED'),
 "D06-E05":lambda a,b,s:setfact(a,'SOURCE_CONFLICT'),
 "D07-E03":lambda a,b,s:setfact(a,'SOURCE_REVISION'),
 "D07-E04":lambda a,b,s:s.update(currentness_decision='STALE_AFFECTED'),
 "D08-E02":lambda a,b,s:s.update(reversibility_state='DEMONSTRATED'),
 "D08-E03":lambda a,b,s:s.update(reversibility_state='UNKNOWN'),
 "D09-E02":lambda a,b,s:setfact(a,'KNOWN_DEPENDENCY'),
 "D09-E03":lambda a,b,s:s.update(required_specialist_count=2),
 "D09-E04":lambda a,b,s:s.update(required_specialist_count=2),
 "D09-E05":lambda a,b,s:s.update(required_specialist_count=2),
 "D10-E05":lambda a,b,s:s.update(materiality_level='UNKNOWN'),
 "D11-E02":lambda a,b,s:s.update(unresolved_material_signal_count=1),
 "D11-E03":lambda a,b,s:None,
 "D11-E04":lambda a,b,s:setfact(a,'ABSENCE_CLAIM'),
 "D12-E03":lambda a,b,s:None,
}

class GoldenDimensions(unittest.TestCase):
    def test_catalog_exact(self):
        c=load_catalog(CATALOG)
        self.assertEqual(len(c['dimensions']),12)
        self.assertEqual(len(c['elements']),59)
        self.assertEqual({e['id'] for e in c['elements'] if e['applicability_category']=='CONDITIONAL'},set(COND_IDS))
    def test_all_ids_and_two_axes(self):
        r=run()
        self.assertEqual(r['status'],'CANDIDATE_UNATTESTED')
        self.assertEqual(len(r['dimensions']),12)
        self.assertEqual(len(r['elements']),59)
        self.assertEqual(r['coverage']['always_required'],33)
        self.assertEqual(r['coverage']['conditional_required']+r['coverage']['conditional_unresolved'],26)
        self.assertEqual(r['coverage']['not_applicable'],0)
        self.assertEqual(r['coverage']['satisfied'],0)
        self.assertTrue(all(e['fulfilment']=='PENDING_EVIDENCE' for e in r['elements']))
        self.assertEqual({e['element_id'] for e in r['elements']},
                         {x['element_id'] for d in r['dimensions'] for x in d['elements']})
        self.assertFalse(r['a3_allowed']);self.assertIsNone(r['next_step'])
    def test_26_positive_witnesses_source_only(self):
        self.assertEqual(set(POSITIVES),set(COND_IDS))
        for eid,tweak in POSITIVES.items():
            with self.subTest(eid=eid):
                a,b,s=fixture();tweak(a,b,s['depth_signals'])
                if eid=="D02-E02":
                    s["target_granularity"]="CONTROL"
                    s["nested_parent_ref"]="MODULE-1"
                    b["classification"]["target_granularity"]="CONTROL"
                b['classification']['signals_sha256']=_digest(s)
                r=run(a,b,s)
                self.assertEqual(r['status'],'CANDIDATE_UNATTESTED')
                item=next(x for x in r['elements'] if x['element_id']==eid)
                self.assertEqual(item['applicability'],'CONDITIONAL_REQUIRED')
                self.assertEqual(item['fulfilment'],'PENDING_EVIDENCE')
                self.assertFalse(r['a3_allowed'])
    def test_true_consequence_never_false_na(self):
        a,b,s=fixture();s['depth_signals']['known_cross_scope_impact']='UNKNOWN'
        b['classification']['signals_sha256']=_digest(s)
        r=run(a,b,s)
        for eid in ('D02-E05','D04-E03','D04-E04','D09-E02'):
            self.assertEqual(next(x for x in r['elements'] if x['element_id']==eid)['applicability'],'CONDITIONAL_REQUIRED')
    def test_missing_false_proof_unresolved_not_na(self):
        r=run()
        for eid in ('D01-E04','D04-E05','D05-E04','D06-E05','D07-E03','D11-E04'):
            item=next(x for x in r['elements'] if x['element_id']==eid)
            self.assertEqual(item['applicability'],'UNRESOLVED_TRIGGER')
            self.assertEqual(item['fulfilment'],'PENDING_EVIDENCE')
    def test_33_always_required(self):
        r=run();self.assertEqual(sum(x['applicability']=='REQUIRED' for x in r['elements']),33)
    def test_no_fake_semantic_receipt(self):
        r=run();e=next(x for x in r['elements'] if x['element_id']=='D12-E05')
        self.assertIsNone(e['value']);self.assertFalse(r['independent_judge_verified'])
    def test_facts_cannot_be_unreferenced(self):
        a,b,s=fixture();a['payload']['provided_facts'].append({'fact_code':'AUTHORITY_CONFLICT','value':'TRUE','source_ref':'forged://elsewhere'})
        r=run(a,b,s);e=next(x for x in r['elements'] if x['element_id']=='D05-E04')
        self.assertEqual(e['applicability'],'UNRESOLVED_TRIGGER')
    def test_negative_facts_do_not_prove_na(self):
        a,b,s=fixture();a['payload']['provided_facts'].append({'fact_code':'AUTHORITY_CONFLICT','value':'FALSE','source_ref':'user://case-1'})
        r=run(a,b,s);self.assertEqual(next(x for x in r['elements'] if x['element_id']=='D05-E04')['applicability'],'UNRESOLVED_TRIGGER')
    def test_untrusted_declared_values_not_satisfied(self):
        r=run();e=next(x for x in r['elements'] if x['element_id']=='D03-E01')
        self.assertEqual(e['value'],'LOW');self.assertEqual(e['fulfilment'],'PENDING_EVIDENCE')
    def test_target_mutation_blocked(self):
        a,b,s=fixture();b['classification']['target_ref']='OTHER'
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_TARGET_CONFLICT'])
    def test_cross_business_blocked(self):
        a,b,s=fixture();s['business']='SALY'
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_BUSINESS_CONFLICT'])
    def test_a2_result_business_conflict(self):
        a,b,s=fixture();b['business']='SALY'
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_BUSINESS_CONFLICT'])
    def test_input_digest_mutation(self):
        a,b,s=fixture();s['depth_signals']['materiality_level']='HIGH'
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_INPUT_DIGEST_MISMATCH'])
    def test_untyped_signal_missing(self):
        a,b,s=fixture();del s['depth_signals']['materiality_level']
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_CANONICAL_FIELDS_MISSING'])
    def test_semantic_a1_not_admitted(self):
        a,b,s=fixture();a['semantic_review_required']=True
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_A1_SEMANTIC_GATE_NOT_RESOLVED'])
    def test_blocked_a2_cannot_be_golden(self):
        a,b,s=fixture();b['status']='BLOCKED'
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_CANONICAL_A2_NOT_QUALIFIED'])
    def test_claim_judge_not_accepted(self):
        a,b,s=fixture();b['independent_judge_verified']=True
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_FORGED_OPERATIONAL_AUTHORITY'])
    def test_claim_current_not_accepted(self):
        a,b,s=fixture();b['source_attested']=True
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_FORGED_OPERATIONAL_AUTHORITY'])
    def test_claim_next_step_not_accepted(self):
        a,b,s=fixture();b['next_step']='A3'
        self.assertEqual(run(a,b,s)['blocking_codes'],['GOLDEN_FORGED_OPERATIONAL_AUTHORITY'])
    def test_unknown_not_l1_claim(self):
        a,b,s=fixture();s['depth_signals']['materiality_level']='UNKNOWN'
        b['classification']['signals_sha256']=_digest(s)
        r=run(a,b,s)
        self.assertFalse(r['a3_allowed']);self.assertEqual(r['coverage']['not_applicable'],0)
    def test_no_mutate_inputs(self):
        inp=fixture();before=copy.deepcopy(inp)
        run(*inp);self.assertEqual(inp,before)
    def test_cross_catalog_drift(self):
        import tempfile
        p=Path(tempfile.gettempdir()) / "tampered_a2_golden_catalog.json"
        data=CATALOG.read_bytes().replace(b'"DESIGN_ONLY_NOT_IMPLEMENTED"',b'"READY"')
        p.write_bytes(data)
        self.assertEqual(build_golden(*fixture(),catalog_path=p)['blocking_codes'],['GOLDEN_CATALOG_SOURCE_UNAVAILABLE_OR_DRIFTED'])
    def test_missing_catalog(self):
        self.assertEqual(build_golden(*fixture(),catalog_path=ROOT / "catalog/absent.json")['status'],'BLOCKED')
    def test_all_lineage_unverified(self):
        r=run();self.assertEqual(len(r['signal_lineage']),9)
        self.assertTrue(all(not x['producer_verified'] and not x['currentness_verified'] for x in r['signal_lineage']))
    def test_a3_requests_dir_and_stop(self):
        r=run();self.assertTrue(r['a3_requests'])
        self.assertTrue(all(x['stop_condition']=='CURRENT_SERVER_READBACK_OR_TYPED_BLOCKER' for x in r['a3_requests']))
        self.assertTrue(all(x['source_refs'] for x in r['a3_requests']))

if __name__=='__main__':unittest.main(verbosity=2)
