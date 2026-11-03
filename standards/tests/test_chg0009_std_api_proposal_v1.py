"""CHG-0009 non-active proposal: parity with exact draft STD-API source.

This test intentionally does NOT approve levels, security, release or C9.
"""
import json
import unittest
from pathlib import Path

STD = Path(__file__).resolve().parents[1]
PROPOSAL = STD / "changes/proposals/CHG-0009.draft.json"
DOCUMENT = STD.parent / "docs/programming/CHG-0009_STD_API_LEVEL_SPLIT_PROPOSAL_20261103.md"
LEVELS = {
    "STD-API-01":"L2", "STD-API-02":"L2", "STD-API-03":"L2",
    "STD-API-04":"SPLIT", "STD-API-05":"SPLIT",
    "STD-API-06":"L1", "STD-API-07":"L2",
    "STD-API-08":"SPLIT", "STD-API-09":"L1",
}

class ProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(PROPOSAL.read_text(encoding="utf-8"))
        cls.cat = json.loads((STD / "catalog.json").read_text(encoding="utf-8"))
        cls.doc = DOCUMENT.read_text(encoding="utf-8")

    def test_proposal_matches_source_not_approval(self):
        self.assertEqual(self.d["status"], "DRAFT_FOR_INDEPENDENT_REVIEW")
        self.assertEqual(self.d["proposed_levels"], LEVELS)
        self.assertEqual(self.d["source"]["catalog_version"], self.cat["catalog_version"])
        self.assertEqual(self.cat["status"], "BORRADOR_EN_REPO_DE_CALIFICACION")
        self.assertEqual(self.d["precedence"], ["L1", "A", "B", "L2"])
        self.assertFalse(self.d["readiness"]["catalog_modified"])
        self.assertFalse(self.d["readiness"]["change_active"])
        self.assertFalse(self.d["readiness"]["owner_normative_go"])
        self.assertFalse(self.d["readiness"]["independent_security_review"])
        self.assertFalse(self.d["readiness"]["C3_release_verified"])
        self.assertFalse(self.d["readiness"]["PG03_C2_admitted"])
        self.assertFalse((STD / "changes/CHG-0009.json").exists())

    def test_all_nine_source_rules_preserved(self):
        rules=[r for r in self.cat["rules"] if r["domain"]=="STD-API"]
        self.assertEqual({r["id"] for r in rules}, set(LEVELS))
        self.assertTrue(all("level" not in r for r in rules))
        self.assertEqual(len(rules), 9)
        for rid in LEVELS:
            self.assertIn("| " + rid + " |", self.doc)

    def test_split_coverage_and_unresolved_ids(self):
        self.assertEqual({k for k,v in LEVELS.items() if v=="SPLIT"},
                         set(self.d["provisional_splits"]))
        for original,parts in self.d["provisional_splits"].items():
            self.assertEqual(parts,{"STD-API-04":["STD-API-10","STD-API-11"],"STD-API-05":["STD-API-12","STD-API-13"],"STD-API-08":["STD-API-14","STD-API-15"]}[original])
            self.assertTrue(all(__import__("re").fullmatch(r"STD-[A-Z]+-[0-9]{2}", x) for x in parts))
            self.assertTrue(set(parts).isdisjoint(LEVELS))
        self.assertEqual(self.d["readiness"]["canonical_new_ids"],"PROPOSED_NOT_APPROVED")
        self.assertEqual(self.d["readiness"]["reference_migration"],"PROPOSED_NOT_APPLIED")
        self.assertEqual(self.d["readiness"]["security_pin_invalidation_decision"],"SECURITY_REVIEW_AND_INVALIDATION_REQUIRED_IF_NORMATIVE_DIFF")
        self.assertEqual(self.d["change_class_proposed"],"SECURITY_REVIEW_REQUIRED")

    def test_security_carry_forward_is_explicit_and_inactive(self):
        security=self.d["proposed_security_carry_forward"]
        self.assertEqual(security["source_id"],"STD-API-04")
        self.assertIn("STD-API-10",security["non_waivable_ids"])
        self.assertIn("STD-API-10",security["security_change_class_ids"])
        self.assertTrue(security["policy_invariants_update_required"])
        self.assertTrue(security["changes_security_ids_update_required"])
        invariants=(STD/"tools/policy_invariants.py").read_text(encoding="utf8")
        checks=(STD/"tools/changes.py").read_text(encoding="utf8")
        self.assertIn('"STD-API-04"',invariants)
        self.assertIn('"STD-API-04"',checks)
        self.assertNotIn('"STD-API-10"',invariants)
        self.assertNotIn('"STD-API-10"',checks)
        self.assertFalse(self.d["readiness"]["owner_normative_go"])

    def test_obligation_trace_matrix(self):
        for part in self.d["proposed_split_levels"]:
            self.assertIn(part,self.doc)
        for required in ["REG_TEC_010","REG_API_005","Retry-After","X-Request-Id",
                         "X-Correlation-Id","numeric(18,2)","Idempotency-Key","D10"]:
            self.assertIn(required,self.doc)
        self.assertEqual(len(self.d["proposed_split_levels"]),6)
        self.assertEqual(self.d["proposed_reference_migration"],self.d["provisional_splits"])

if __name__ == "__main__":
    unittest.main()
