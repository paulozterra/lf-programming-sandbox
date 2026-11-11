"""Synthetic transition tests ONLY; simulated receipts NEVER evidence of live native judge."""
import copy
import hashlib
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "guards"))
from native_review_cycle_v1 import evaluate_cycle, make_profile_terminal_report, _sha

def h(value):return hashlib.sha256(value.encode()).hexdigest()

def finding(fid='F01', retryable=True):
    return {'finding_id':fid,'dimension_id':'D03','element_id':'D03-E02','criterion_id':'SEMANTIC_DEPTH',
        'failure_code':'INSUFFICIENT_JUSTIFICATION','severity':'P1','expected':'Fundamentar los riesgos materiales',
        'observed':'No se explican los efectos y su posible alcance','evidence_state':'NOT_PROVEN','evidence_refs':[],
        'repair_instruction':'Comparar riesgo con señales A1 y política actual e identificar brechas para A3', 'retryable':retryable}

def attempt(n,det='PASS',judge='PASS',ids=None,resolutions=None):
    out={'attempt_number':n,'candidate_ref':f'fixture://a2/candidate/{n}',
       'candidate_sha256':h(f'a2 candidate {n}'),
       'deterministic':{'result':det,'validator_ref':f'fixture://validator/{n}','feedback':([finding('D'+str(n))] if det=='FAIL' else [])},
       'native_review':{'mode':'EXISTING_NATIVE_ROUTE','result':judge,
          'receipt_ref':f'fixture://native/judge/{n}' if judge in ('PASS','FAIL') else None,
          'review_sha256':h(f'native review {n}') if judge in ('PASS','FAIL') else None,
          'feedback':[finding(fid) for fid in (ids or [])] if judge=='FAIL' else []},
       'previous_defect_resolution':resolutions or []}
    return out

def packet(attempts,ticket='fixture://ticket/1'):
    return {'schema_version':'A2_GOLDEN_REVIEW_CYCLE_PROPOSAL_V0_7',
            'execution_id':'EXEC-SYNTHETIC-A2-001', 'ticket_ref':ticket,
            'a1_input_sha256':h('fixture a1 input'),
            'a2_contract_ref':'A2_GOLDEN_CONTRATO_SALIDA_PROPUESTA_v0_3.schema.json',
            'a2_policy_blob_sha1':'0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051',
            'rubric_sha256':h('fixture rubric'), 'max_submissions':3, 'submissions':attempts}

def receipts(p):
    return {x['attempt_number']:{'execution_id':p['execution_id'],'candidate_sha256':x['candidate_sha256'],
       'review_sha256':x['native_review']['review_sha256'],'receipt_ref':x['native_review']['receipt_ref'],
       'verdict':x['native_review']['result'],'feedback_sha256':_sha(x['native_review']['feedback']),'source_verified':True}
       for x in p['submissions'] if x['native_review']['result'] in ('PASS','FAIL')}

def deterministic_receipts(p):
    return {x['attempt_number']:{'execution_id':p['execution_id'], 'candidate_sha256':x['candidate_sha256'],
      'validator_ref':x['deterministic']['validator_ref'],'result':x['deterministic']['result'],
      'feedback_sha256':_sha(x['deterministic']['feedback']), 'source_verified':True}
      for x in p['submissions']}

def gate(p):
    x=p['submissions'][-1]
    return {'execution_id':p['execution_id'],'a1_input_sha256':p['a1_input_sha256'],
      'candidate_sha256':x['candidate_sha256'], 'judge_review_sha256':x['native_review']['review_sha256'],
      'validator_ref':x['deterministic']['validator_ref'],
      'a2_stage_source_attested':True,'readback_verified':True,'source_verified':True}

def decide(p, verified=True, closure=None, handoff=True):
    return evaluate_cycle(p,verified_native_receipts=receipts(p) if verified else None,
       verified_ticket_closure=closure,verified_deterministic_receipts=deterministic_receipts(p),
       verified_handoff_gate=gate(p) if handoff else None)

def resolved(fid):return {'finding_id':fid,'status':'RESOLVED','evidence_refs':[f'fixture://correction/{fid}']}

class CycleTests(unittest.TestCase):
    def case(self,attempts,expected,verified=True):
        p=packet(attempts)
        decision=decide(p,verified=verified)
        self.assertEqual(decision['status'],expected,decision)
        return p,decision

    def test_pass_first_try(self):
        p,r=self.case([attempt(1)],'A2_APPROVED')
        self.assertTrue(r['a3_invocation_allowed']); self.assertFalse(r['a3_invoked'])

    def test_fail_then_pass(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),attempt(2,resolutions=[resolved('F01')])]
        _,r=self.case(x,'A2_APPROVED');self.assertEqual(r['attempts_used'],2)

    def test_fail_fail_fail_exhausts_and_reports(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),
           attempt(2,judge='FAIL',ids=['F02'],resolutions=[resolved('F01')]),
           attempt(3,judge='FAIL',ids=['F03'],resolutions=[resolved('F02')])]
        p,r=self.case(x,'A2_EXHAUSTED');self.assertEqual(r['terminal_reason'],'A2_MAX_ATTEMPTS_EXCEEDED')
        self.assertFalse(r['a3_invocation_allowed']);self.assertTrue(r['profile_report_required'])
        report=make_profile_terminal_report(p,r)
        self.assertEqual(len(report['attempt_history']),3);self.assertFalse(report['a3_invoked'])
        self.assertEqual(report['ticket_closure'],'CLOSURE_NOT_VERIFIED')

    def test_third_try_pass_allowed(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),
           attempt(2,judge='FAIL',ids=['F02'],resolutions=[resolved('F01')]),
           attempt(3,resolutions=[resolved('F02')])]
        _,r=self.case(x,'A2_APPROVED');self.assertEqual(r['attempts_used'],3)

    def test_fail_first_returns_a2(self):
        _,r=self.case([attempt(1,judge='FAIL',ids=['F01'])],'A2_REPAIR_REQUIRED')
        self.assertEqual(r['next_action'],'REGENERATE_A2_WITH_HISTORY')

    def test_deterministic_fail_skips_judge(self):
        _,r=self.case([attempt(1,det='FAIL',judge='NOT_INVOKED')],'A2_REPAIR_REQUIRED')
        self.assertFalse(r['a3_invocation_allowed'])

    def test_judge_fail_without_explanation_blocked(self):
        _,r=self.case([attempt(1,judge='FAIL')],'A2_BLOCKED')
        self.assertEqual(r['terminal_reason'],'JUDGE_FAIL_WITHOUT_ACTIONABLE_FEEDBACK')

    def test_unverified_self_declared_pass_blocked(self):
        _,r=self.case([attempt(1)],'A2_BLOCKED',verified=False)
        self.assertEqual(r['terminal_reason'],'NATIVE_JUDGE_READBACK_UNVERIFIED')

    def test_wrong_receipt_hash_blocked(self):
        p=packet([attempt(1)]);rs=receipts(p);rs[1]['candidate_sha256']=h('other candidate')
        r=evaluate_cycle(p,verified_native_receipts=rs,verified_deterministic_receipts=deterministic_receipts(p),verified_handoff_gate=gate(p))
        self.assertEqual(r['terminal_reason'],'NATIVE_JUDGE_READBACK_UNVERIFIED')

    def test_fourth_attempt_blocked_by_schema(self):
        x=[attempt(i,judge='FAIL',ids=[f'F{i}']) for i in range(1,5)]
        _,r=self.case(x,'A2_BLOCKED');self.assertEqual(r['terminal_reason'],'REVIEW_CYCLE_SCHEMA_INVALID')

    def test_duplicate_candidate_hash_blocked(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),attempt(2,resolutions=[resolved('F01')])]
        x[1]['candidate_sha256']=x[0]['candidate_sha256']
        _,r=self.case(x,'A2_BLOCKED');self.assertEqual(r['terminal_reason'],'REPEATED_UNCHANGED_CANDIDATE')

    def test_missing_previous_defect_reconciliation_blocked(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),attempt(2)]
        _,r=self.case(x,'A2_BLOCKED');self.assertEqual(r['terminal_reason'],'PREVIOUS_FINDING_COVERAGE_INCOMPLETE')

    def test_false_resolution_when_finding_persists(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),attempt(2,judge='FAIL',ids=['F01'],resolutions=[resolved('F01')])]
        _,r=self.case(x,'A2_BLOCKED');self.assertEqual(r['terminal_reason'],'FALSE_RESOLUTION_OR_MISSING_EVIDENCE')

    def test_technical_judge_failure_no_retry_or_a3(self):
        _,r=self.case([attempt(1,judge='TECHNICAL_BLOCK')],'A2_BLOCKED')
        self.assertEqual(r['terminal_reason'],'NATIVE_JUDGE_TECHNICAL_BLOCK')

    def test_non_retryable_failure_blocks(self):
        x=[attempt(1,judge='FAIL',ids=['F01'])]
        x[0]['native_review']['feedback'][0]['retryable']=False
        _,r=self.case(x,'A2_BLOCKED');self.assertEqual(r['terminal_reason'],'NON_RETRYABLE_FINDING')

    def test_no_false_ticket_closure(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),
           attempt(2,judge='FAIL',ids=['F02'],resolutions=[resolved('F01')]),
           attempt(3,judge='FAIL',ids=['F03'],resolutions=[resolved('F02')])]
        p=packet(x)
        r=decide(p,closure={'receipt_ref':'fixture://close','ticket_ref':'wrong',
                                       'execution_id':p['execution_id'],'source_verified':True,'closed':True})
        self.assertEqual(r['ticket_closure'],'CLOSURE_NOT_VERIFIED')

    def test_verified_ticket_closure_fixture(self):
        x=[attempt(1,judge='FAIL',ids=['F01']),
           attempt(2,judge='FAIL',ids=['F02'],resolutions=[resolved('F01')]),
           attempt(3,judge='FAIL',ids=['F03'],resolutions=[resolved('F02')])]
        p=packet(x); external={'receipt_ref':'fixture://close','ticket_ref':p['ticket_ref'],
                               'execution_id':p['execution_id'],'source_verified':True,'closed':True}
        r=decide(p,closure=external)
        self.assertEqual(r['ticket_closure'],'TICKET_CLOSED_VERIFIED')
        self.assertEqual(r['execution_status_claim'],'UNVERIFIED_DESIGN_ONLY')

    def test_schema_refuses_unexpected_producer_judge_pass(self):
        p=packet([attempt(1)]);p['self_reported_judge_pass']=True
        r=decide(p);self.assertEqual(r['terminal_reason'],'REVIEW_CYCLE_SCHEMA_INVALID')

    def test_schema_refuses_invalid_failure_detail(self):
        x=[attempt(1,judge='FAIL',ids=['F01'])];x[0]['native_review']['feedback'][0]['repair_instruction']=''
        p=packet(x);r=decide(p)
        self.assertEqual(r['terminal_reason'],'REVIEW_CYCLE_SCHEMA_INVALID')

    def test_gate_unverified_never_invokes_a3(self):
        p=packet([attempt(1)])
        r=decide(p,handoff=False)
        self.assertEqual(r['status'],'A2_GATE_PENDING')
        self.assertFalse(r['a3_invocation_allowed'])

    def test_deterministic_receipt_missing_blocks(self):
        p=packet([attempt(1)])
        r=evaluate_cycle(p,verified_native_receipts=receipts(p),verified_handoff_gate=gate(p))
        self.assertEqual(r['terminal_reason'],'DETERMINISTIC_RECEIPT_UNVERIFIED')

    def test_tampered_native_feedback_blocked(self):
        p=packet([attempt(1,judge='FAIL',ids=['F01'])])
        rs=receipts(p)
        rs[1]['feedback_sha256']=h('different feedback')
        r=evaluate_cycle(p,verified_native_receipts=rs,verified_deterministic_receipts=deterministic_receipts(p))
        self.assertEqual(r['terminal_reason'],'NATIVE_JUDGE_READBACK_UNVERIFIED')

    def test_wrong_gate_source_binding_rejected(self):
        p=packet([attempt(1)])
        g=gate(p);g['a1_input_sha256']=h('wrong A1')
        r=evaluate_cycle(p,verified_native_receipts=receipts(p),verified_deterministic_receipts=deterministic_receipts(p),verified_handoff_gate=g)
        self.assertEqual(r['status'],'A2_GATE_PENDING')

if __name__=='__main__': unittest.main(verbosity=2)