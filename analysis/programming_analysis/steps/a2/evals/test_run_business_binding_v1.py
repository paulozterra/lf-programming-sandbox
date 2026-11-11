"""Synthetic reconciliation tests; rows are NOT live authority receipts."""
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("run_binding", ROOT / "adapters/run_business_binding_v1.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
reconcile = mod.reconcile

H1 = 'a'*64
H2 = 'b'*64
H3 = 'c'*64
H4 = 'd'*64
H5 = 'e'*64


def bundle():
    parent = {
        'execution_id':'PROFILE-SIM-01','operation_code':'EJECUCION_PERFIL_LF',
        'status':'IN_PROGRESS','target_code':'PROFILE-SIM','request_sha256':H1,
        'manifest':{'business':'LF','router_profile_handoff':{
            'business':'LF','profile_code':'PROFILE-SIM','request_sha256':H1,
            'router_authorization_receipt':{
                'schema_version':'LF_ROUTER_PROFILE_AUTHORIZATION_RECEIPT_V1',
                'router':'ACT-0001','operation_code':'EJECUCION_PERFIL_LF',
                'action_code':'PROFILE_EXECUTION','asset_type':'PERFIL',
                'profile_execution_allowed':True,'business':'LF','profile_code':'PROFILE-SIM',
                'request_sha256':H1,'fingerprint_sha256':H2,
                'gate2_semantic_receipt_sha256':H3,
                'operation_revision_sha256':H4,'router_source_md5':'a'*32
            }}}
    }
    invocation = {
        'skill_run_id':'RUN-SIM-01','skill_code':'PROGRAMMING_ANALYSIS_LF',
        'parent_execution_id':'PROFILE-SIM-01','profile_code':'PROFILE-SIM',
        'status':'COMPLETED','child_execution_id':'SKILL-SIM-01',
        'input_sha256':H2,'evidence_ref':'SKILLRUN:RUN-SIM-01:'+H5
    }
    child = {'execution_id':'SKILL-SIM-01','operation_code':'EJECUCION_SKILL_LF',
             'target_code':'PROGRAMMING_ANALYSIS_LF','created_by_execution_id':'PROFILE-SIM-01',
             'request_sha256':H1,'status':'IN_PROGRESS',
             'manifest':{'profile_handoff':{'source_execution_id':'PROFILE-SIM-01',
                                            'skill_run_id':'RUN-SIM-01'}}}
    return parent,invocation,child

class SourceOnlyBinding(unittest.TestCase):
    def check(self,fn,reason):
        p,i,c=bundle(); fn(p,i,c)
        r=reconcile(p,i,c,'PROFILE-SIM-01')
        self.assertEqual(r['status'],'BLOCKED')
        self.assertEqual(r['blocking_codes'],[reason])
        self.assertFalse(r['a3_allowed'])
        self.assertFalse(r['readback_authenticated'])

    def test_01_consistency_does_not_authorize(self):
        p,i,c=bundle();p['trusted']=True;i['native_judge_passed']=True
        r=reconcile(p,i,c,'PROFILE-SIM-01')
        self.assertEqual(r['status'],'CANDIDATE_CONSISTENT')
        self.assertEqual(r['business'],'LF')
        self.assertFalse(r['a3_allowed'])
        self.assertFalse(r['readback_authenticated'])

    def test_02_missing_rows(self):
        p,i,c=bundle()
        self.assertEqual(reconcile(p,None,c,p['execution_id'])['blocking_codes'],['RUN_READBACK_ROWS_REQUIRED'])

    def test_03_wrong_actor(self):
        p,i,c=bundle()
        self.assertEqual(reconcile(p,i,c,'OTHER')['blocking_codes'],['RUN_PARENT_ACTOR_BINDING_MISMATCH'])

    def test_04_parent_stale(self):self.check(lambda p,i,c:p.update(status='COMPLETED'),'RUN_PARENT_NOT_ACTIVE_PROFILE')
    def test_05_missing_root_business(self):self.check(lambda p,i,c:p['manifest'].pop('business'),'RUN_BUSINESS_ROOT_MISSING')
    def test_06_cross_business_root(self):self.check(lambda p,i,c:p['manifest'].update(business='SALY'),'RUN_ROUTER_HANDOFF_SCOPE_MISMATCH')
    def test_07_handoff_missing(self):self.check(lambda p,i,c:p['manifest'].pop('router_profile_handoff'),'RUN_ROUTER_HANDOFF_MISSING')
    def test_08_handoff_business_mismatch(self):self.check(lambda p,i,c:p['manifest']['router_profile_handoff'].update(business='SALY'),'RUN_ROUTER_HANDOFF_SCOPE_MISMATCH')
    def test_09_request_mismatch(self):self.check(lambda p,i,c:p['manifest']['router_profile_handoff'].update(request_sha256=H2),'RUN_REQUEST_IDENTITY_MISMATCH')
    def test_10_missing_receipt(self):self.check(lambda p,i,c:p['manifest']['router_profile_handoff'].pop('router_authorization_receipt'),'RUN_ROUTER_RECEIPT_MISSING')
    def test_11_bad_router_receipt(self):self.check(lambda p,i,c:p['manifest']['router_profile_handoff']['router_authorization_receipt'].update(router='OTHER'),'RUN_ROUTER_RECEIPT_INVALID')
    def test_12_receipt_business_saly(self):self.check(lambda p,i,c:p['manifest']['router_profile_handoff']['router_authorization_receipt'].update(business='SALY'),'RUN_ROUTER_RECEIPT_SCOPE_MISMATCH')
    def test_13_receipt_bad_digest(self):self.check(lambda p,i,c:p['manifest']['router_profile_handoff']['router_authorization_receipt'].update(fingerprint_sha256='nope'),'RUN_ROUTER_RECEIPT_DIGEST_INVALID')
    def test_14_wrong_skill(self):self.check(lambda p,i,c:i.update(skill_code='OTHER'),'RUN_SKILL_INVOCATION_MISMATCH')
    def test_15_wrong_parent_in_invocation(self):self.check(lambda p,i,c:i.update(parent_execution_id='OTHER'),'RUN_SKILL_INVOCATION_MISMATCH')
    def test_16_missing_child_id(self):self.check(lambda p,i,c:i.update(child_execution_id=None),'RUN_SKILL_INVOCATION_EVIDENCE_INVALID')
    def test_17_forged_evidence_ref(self):self.check(lambda p,i,c:i.update(evidence_ref='SKILLRUN:FORGED:'+H5),'RUN_SKILL_INVOCATION_EVIDENCE_INVALID')
    def test_18_wrong_child_code(self):self.check(lambda p,i,c:c.update(target_code='ANOTHER_SKILL'),'RUN_SKILL_CHILD_IDENTITY_MISMATCH')
    def test_19_wrong_child_parent(self):self.check(lambda p,i,c:c.update(created_by_execution_id='OTHER'),'RUN_SKILL_CHILD_IDENTITY_MISMATCH')
    def test_20_wrong_child_request(self):self.check(lambda p,i,c:c.update(request_sha256=H2),'RUN_SKILL_CHILD_IDENTITY_MISMATCH')
    def test_21_child_link_cross_run(self):self.check(lambda p,i,c:c['manifest']['profile_handoff'].update(skill_run_id='OTHER'),'RUN_SKILL_CHILD_HANDOFF_MISMATCH')
    def test_22_no_child_run(self):
        p,i,c=bundle();self.assertEqual(reconcile(p,i,None,p['execution_id'])['status'],'BLOCKED')
    def test_read_only_sql_invocation_does_not_count_as_governed_run(self):
        p,i,c=bundle()
        i["child_execution_id"] = None
        r=reconcile(p,i,None,p["execution_id"])
        self.assertEqual(r["blocking_codes"],["RUN_GOVERNED_CHILD_ABSENT_READ_ONLY_INVOKER"])
        self.assertFalse(r["readback_authenticated"])
        self.assertFalse(r["a3_allowed"])

    def test_unrelated_legacy_skill_run_is_not_admissible(self):
        p,i,c=bundle()
        c["target_code"] = "ACT-0057"
        r=reconcile(p,i,c,p["execution_id"])
        self.assertEqual(r["blocking_codes"],["RUN_SKILL_CHILD_IDENTITY_MISMATCH"])

    def test_23_immutable_inputs(self):
        p,i,c=bundle(); originals=copy.deepcopy((p,i,c));reconcile(p,i,c,p['execution_id']);self.assertEqual((p,i,c),originals)
    def test_24_host_scoping_cannot_be_self_attested(self):
        p,i,c=bundle();p['readback_authenticated']=True;c['judge_pass']=True
        r=reconcile(p,i,c,p['execution_id'])
        self.assertFalse(r['readback_authenticated'])
        self.assertFalse(r['operationally_integrated'])
    def test_25_missing_child_profile_handoff(self):
        self.check(lambda p,i,c:c['manifest'].pop('profile_handoff'),'RUN_SKILL_CHILD_HANDOFF_MISMATCH')


class BridgeWiringCandidate(unittest.TestCase):
    """Bridge wiring checks with A1/A2 and A3 mocked; no native authority."""
    def invoke(self, run_readback=None, expected_business=None, a1business='LF'):
        from types import SimpleNamespace
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location(
            'a1_a2_bridge', ROOT / 'adapters/a1_a2_candidate_bridge_v1.py')
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        a1 = {'business':a1business,'schema_version':'A1_INTERNAL_STEP_CANDIDATE_RESULT_V1',
              'status':'VALID_OUTPUT','skill_code':'PROGRAMMING_ANALYSIS_LF',
              'payload':{'schema_version':'REQUEST_CONTEXT_V1', 'target_hints':['T-001'],
                         'source_refs':['user://test'], 'provided_facts':[],
                         'objective':{'problem_statement':'Test','desired_outcome':'Test'},
                         'constraints':[]}}
        a2 = {'business':a1business,'schema_version':'A2_INTERNAL_STEP_CANDIDATE_RESULT_V1',
              'status':'CANDIDATE_UNATTESTED','skill_code':'PROGRAMMING_ANALYSIS_LF',
              'classification':{'schema_version':'ANALYSIS_CHANGE_CLASSIFICATION_V1','target_ref':'T-001'}}
        def loader(path, name):
            if path == 'steps/a1/validators/run.py':
                return SimpleNamespace(run=lambda _: a1)
            if path == 'steps/a2/validators/run.py':
                return SimpleNamespace(run=lambda _a,_s: a2)
            if path == 'adapters/run_business_binding_v1.py':
                return mod
            if path == 'adapters/a2_a3_business_handoff_v1.py':
                return SimpleNamespace(prepare_candidate=lambda _a,_b,expected:
                    {'status':'BLOCKED' if not expected or expected != a1business else 'CANDIDATE',
                     'business':expected, 'a3_allowed':False})
            raise AssertionError('UNEXPECTED_STEP_INJECTION')
        with patch.object(bridge, '_load', side_effect=loader):
            result = bridge.prepare_candidate({}, {}, expected_business=expected_business,
                                              run_readback=run_readback,
                                              actor_parent_execution_id='PROFILE-SIM-01')
        return result

    def test_26_caller_business_alone_not_authority(self):
        result = self.invoke(expected_business='LF')
        self.assertEqual(result['run_business_binding_candidate']['status'],'BLOCKED')
        self.assertEqual(result['a3_handoff_candidate']['status'],'BLOCKED')

    def test_27_consistent_run_binding_yields_only_a3_candidate(self):
        parent, invocation, child = bundle()
        result = self.invoke({'parent_run':parent,'skill_invocation':invocation,'child_run':child})
        self.assertEqual(result['run_business_binding_candidate']['status'],'CANDIDATE_CONSISTENT')
        self.assertEqual(result['a3_handoff_candidate']['business'],'LF')
        self.assertFalse(result['runtime_qualified'])
        self.assertIsNone(result['next_step'])
        self.assertFalse(result['a3_handoff_candidate']['a3_allowed'])

    def test_28_caller_business_veto_does_not_override_run(self):
        parent, invocation, child = bundle()
        result = self.invoke({'parent_run':parent,'skill_invocation':invocation,'child_run':child},
                             expected_business='SALY')
        self.assertEqual(result['run_business_binding_candidate']['business'],'LF')
        self.assertEqual(result['a3_handoff_candidate']['status'],'BLOCKED')

    def test_29_a1_business_conflict_still_blocks_handoff(self):
        parent, invocation, child = bundle()
        result = self.invoke({'parent_run':parent,'skill_invocation':invocation,'child_run':child},
                             a1business='SALY')
        # Real A2->A3 guard rejects the conflict. The mock reflects its public contract.
        self.assertEqual(result['a3_handoff_candidate']['status'],'BLOCKED')
        self.assertFalse(result['a3_handoff_candidate']['a3_allowed'])

    def test_30_malformed_run_readback_fails_closed(self):
        result = self.invoke(run_readback={'parent_run':'not-a-row'},expected_business='LF')
        self.assertEqual(result['run_business_binding_candidate']['status'],'BLOCKED')
        self.assertIsNone(result['a3_handoff_candidate']['business'])

if __name__=='__main__':unittest.main()
