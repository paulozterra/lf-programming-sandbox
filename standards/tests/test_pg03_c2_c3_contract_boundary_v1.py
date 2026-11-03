"""PG-03 C2→C3: prove exact-source candidate receipt is NOT an authenticated handoff.

Uses existing skills.select_and_assemble. Does not implement a second
skill selector, strategist, adapter, or provider. A safe barrier test:
upstream run/stack identity must come from authentic PG-02/C1, not this receipt.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

STD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STD / "tools"))
import skills


class C2C3ContractBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (STD / "catalog.json").read_bytes()
        cls.pin = {
            "catalog_sha256": hashlib.sha256(raw).hexdigest(),
            "catalog_version": json.loads(raw)["catalog_version"],
        }

    def test_original_selector_returns_candidate_not_authenticated_stack(self):
        content, receipt = skills.select_and_assemble(
            evidence={"spring_boot": True, "next": True},
            active=["STD-BE", "STD-API"],
            pin=self.pin,
        )
        self.assertTrue(content)
        self.assertEqual(receipt["selection_status"], "CANDIDATE_NOT_ADMITTED")
        self.assertIs(receipt["production_authority"], False)
        self.assertIs(receipt["pg02_source_verified"], False)
        self.assertEqual([x["skill"] for x in receipt["skills"]], ["spring-boot"])
        # These are separately owned by PG-02 / C1 / selector-run attestation.
        # Do not synthesize them from the local skill selection receipt.
        for key in ("run_id", "stack_commit", "selector_commit",
                    "commit_sha", "sources", "authority", "status"):
            self.assertNotIn(key, receipt, key)
        # C3 requires a C1 stack evidence object, not C2 Skills receipt.
        self.assertNotEqual(receipt.get("status"), "CANDIDATE_NOT_ADMITTED")
        self.assertIsNot(receipt.get("authority"), False)

    def test_existing_c2_binding_requires_fields_missing_in_raw_receipt(self):
        _, receipt = skills.select_and_assemble(
            evidence={"spring_boot": True},
            active=["STD-BE", "STD-API"],
            pin=self.pin,
        )
        # Canonical C2 source-binding (#3519) has a DISTINCT selection envelope.
        required = {
            "status", "run_id", "stack_commit", "catalog_sha256",
            "selector_repo", "selector_path", "selector_commit",
            "active_domains", "skills",
        }
        self.assertEqual(
            required - receipt.keys(),
            {"status", "run_id", "stack_commit", "selector_repo",
             "selector_path", "selector_commit", "active_domains"},
        )
        for skill in receipt["skills"]:
            self.assertNotIn("skill_version", skill)
        self.assertEqual(receipt["catalog_sha256"], self.pin["catalog_sha256"])

    def test_deterministic_candidate_receipt_not_upgradeable_by_replay(self):
        args = dict(evidence={"spring_boot": True},
                    active=["STD-BE", "STD-API"], pin=self.pin)
        _, first = skills.select_and_assemble(**args)
        _, second = skills.select_and_assemble(**args)
        self.assertEqual(first, second)
        self.assertIs(first["production_authority"], False)
        self.assertIs(second["production_authority"], False)

    def test_shared_stack_ambiguity_blocks_before_strategy(self):
        with self.assertRaisesRegex(skills.StackDecisionError, "STACK_AMBIGUOUS"):
            skills.select_and_assemble(
                evidence={"spring_boot": True, "next": True},
                active=["STD-API"], pin=self.pin,
            )


if __name__ == "__main__":
    unittest.main()
