import unittest
from copy import deepcopy
try:
    from .pg03_handoff_boundary_v1 import prepare_pg04_handoff,HandoffBlocked
except ImportError:
    from pg03_handoff_boundary_v1 import prepare_pg04_handoff,HandoffBlocked

S={"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,"handoff_allowed":False,"candidate_sha256":"sha-test","requirement_ids":["R1","R2"],"acceptance_ids":["A1","A2"],"scope_ids":["S1"]}
C6={"status":"CANDIDATE_SUFFICIENT_NOT_ADMITTED","production_authority":False,"handoff_allowed":False,"gaps":[],"source_strategy_sha256":"sha-test"}
C7={"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,"handoff_allowed":False,"waiver_authorized":False,"exceptions":[]}
P={"schema_version":"PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1","partition_policy":{"canonical_spec_count":1,"partition_unit":"SOLUTION","minimum_rule":"SMALLEST_COHERENT_VALID_CHANGE"},"coverage":{"material_requirement_coverage_required_percent":100,"acceptance_obligation_coverage_required_percent":100}}
ROWS=[{"solution_id":"SOL1","scope_ids":["S1"],"strategy_ref":"pg03:strategy","requirement_ids":["R1"],"acceptance_ids":["A1"],"depends_on":[]},
{"solution_id":"SOL2","scope_ids":["S1"],"strategy_ref":"pg03:strategy","requirement_ids":["R2"],"acceptance_ids":["A2"],"depends_on":["SOL1"]}]

def check(**changes):
    args={"strategy":deepcopy(S),"sufficiency":deepcopy(C6),"exceptions_result":deepcopy(C7),"partition_contract":deepcopy(P),"solution_coverage":deepcopy(ROWS)}
    args.update(changes)
    return prepare_pg04_handoff(**args)

class HandoffTests(unittest.TestCase):
    def test_complete_candidate_stays_blocked_from_dispatch(self):
        result=check()
        self.assertEqual(result["status"],"CANDIDATE_NOT_ADMITTED")
        self.assertFalse(result["dispatch_allowed"])
        self.assertFalse(result["handoff_allowed"])
        self.assertEqual(result["requirement_owners"]["R2"],"SOL2")
    def test_deterministic(self):
        self.assertEqual(check()["candidate_sha256"],check()["candidate_sha256"])
    def test_missing_requirement(self):
        rows=deepcopy(ROWS);rows[1]["requirement_ids"]=["R1"]
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_duplicate_owner(self):
        rows=deepcopy(ROWS);rows[1]["requirement_ids"]=["R1"]
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_missing_acceptance(self):
        rows=deepcopy(ROWS);rows[1]["acceptance_ids"]=["A3"]
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_unclassified_scope(self):
        rows=deepcopy(ROWS);rows[0]["scope_ids"]=["UNKNOWN"]
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_unknown_dependency(self):
        rows=deepcopy(ROWS);rows[1]["depends_on"]=["MISSING"]
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_dependency_cycle(self):
        rows=deepcopy(ROWS);rows[0]["depends_on"]=["SOL2"]
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_missing_strategy_ref(self):
        rows=deepcopy(ROWS);rows[0]["strategy_ref"]=""
        with self.assertRaises(HandoffBlocked):check(solution_coverage=rows)
    def test_insufficient_c6(self):
        with self.assertRaises(HandoffBlocked):check(sufficiency=dict(C6,status="BLOCKED"))
    def test_c6_strategy_mismatch(self):
        with self.assertRaises(HandoffBlocked):check(sufficiency=dict(C6,source_strategy_sha256="other"))
    def test_open_exception(self):
        with self.assertRaises(HandoffBlocked):check(exceptions_result=dict(C7,status="BLOCKED",exceptions=[{"id":"E1"}]))
    def test_authority_escalation(self):
        with self.assertRaises(HandoffBlocked):check(strategy=dict(S,production_authority=True))
    def test_partition_drift(self):
        p=deepcopy(P);p["partition_policy"]["partition_unit"]="FILE"
        with self.assertRaises(HandoffBlocked):check(partition_contract=p)
    def test_fake_assurance_does_not_authorize(self):
        result=check(assurance_receipt={"status":"PASS","verified":True})
        self.assertFalse(result["handoff_allowed"])
        self.assertEqual(result["assurance_state"],"UNVERIFIED_EXTERNAL_AUTHORITY")
if __name__=="__main__":unittest.main()
