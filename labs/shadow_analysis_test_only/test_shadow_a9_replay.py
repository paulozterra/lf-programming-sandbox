import copy
import unittest
from shadow_a9_replay import inspect

def sample():
    return {"extensions":{"programming_context_snapshot":{
        "schema_version":"PROGRAMMING_CONTEXT_SNAPSHOT_V1",
        "scope_readiness":[{"scope_id":"S01","material_front_refs":["F01"]}],
        "material_front_coverage":{"fronts":[{"id":"F01","status":"REQUIRED","closure":"CLOSED"}]},
        "scope_front_matrix":[]}}}

class ShadowTests(unittest.TestCase):
    def test_source_unchanged_and_candidate_not_admitted(self):
        s=sample(); before=copy.deepcopy(s); r=inspect(s)
        self.assertEqual(s,before)
        self.assertEqual(len(r["suggested_matrix_rows"]),1)
        self.assertFalse(r["pg01_admitted"])
        self.assertFalse(r["handoff_allowed"])
    def test_missing_front_does_not_invent(self):
        s=sample();s["extensions"]["programming_context_snapshot"]["scope_readiness"][0]["material_front_refs"]=["F99"]
        r=inspect(s)
        self.assertEqual(r["suggested_matrix_rows"],[])
        self.assertIn("BROKEN_FRONT_REFERENCE",r["blockers"])
    def test_existing_matrix_is_not_duplicated(self):
        s=sample();s["extensions"]["programming_context_snapshot"]["scope_front_matrix"]=[{"scope_id":"S01","front_id":"F01"}]
        self.assertEqual(inspect(s)["suggested_matrix_rows"],[])
    def test_untyped_a6_stays_blocked(self):
        self.assertIn("A6_TYPED_IMPLEMENTABILITY_MISSING",inspect(sample())["blockers"])
    def test_without_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):inspect({})
if __name__=="__main__":unittest.main()
