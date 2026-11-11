import unittest
try:
    from .pg03_exception_routing_v1 import classify_exceptions, ExceptionRoutingBlocked
except ImportError:
    from pg03_exception_routing_v1 import classify_exceptions, ExceptionRoutingBlocked

S={"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,"handoff_allowed":False,"scope_ids":["S1"]}
def check(kind="EVIDENCE_GAP", **changes):
    e={"id":"E1","kind":kind,"source_ref":"analysis:E1","scope_id":"S1"}
    e.update(changes)
    return classify_exceptions(strategy=S,exceptions=[e])
class Tests(unittest.TestCase):
    def test_empty_never_approves(self):
        x=classify_exceptions(strategy=S,exceptions=[])
        self.assertFalse(x["waiver_authorized"])
        self.assertFalse(x["handoff_allowed"])
    def test_evidence_is_not_owner_decision(self):
        self.assertEqual(check()["exceptions"][0]["route"],"TARGETED_ANALYSIS_EVIDENCE")
    def test_owner_requires_currentness_lookup(self):
        self.assertEqual(check("OWNER_DECISION")["exceptions"][0]["route"],"CHECK_EXISTING_CURRENT_DECISION_FIRST")
    def test_technical_strategy_stays_in_pg03(self):
        self.assertEqual(check("TECHNICAL_STRATEGY")["exceptions"][0]["route"],"PG03_TECHNICAL_RESOLUTION")
    def test_waiver_is_not_issued(self):
        x=check("POLICY_DEVIATION")
        self.assertFalse(x["waiver_authorized"])
        self.assertEqual(x["status"],"BLOCKED")
    def test_unverified_approval_rejected(self):
        for field in ("approved","waiver_granted"):
            with self.subTest(field=field), self.assertRaises(ExceptionRoutingBlocked):
                check(**{field:True})
    def test_unknown_scope_rejected(self):
        with self.assertRaises(ExceptionRoutingBlocked):check(scope_id="OTHER")
    def test_missing_source_rejected(self):
        with self.assertRaises(ExceptionRoutingBlocked):check(source_ref="")
    def test_unknown_type_rejected(self):
        with self.assertRaises(ExceptionRoutingBlocked):check("UNKNOWN")
    def test_duplicate_rejected(self):
        e={"id":"E1","kind":"EVIDENCE_GAP","source_ref":"analysis:E1","scope_id":"S1"}
        with self.assertRaises(ExceptionRoutingBlocked):
            classify_exceptions(strategy=S,exceptions=[e,e])
    def test_authority_escalation_rejected(self):
        with self.assertRaises(ExceptionRoutingBlocked):
            classify_exceptions(strategy=dict(S,production_authority=True),exceptions=[])
if __name__=="__main__":unittest.main()
