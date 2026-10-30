"""PG-00 C6/C9 regressions: exact catalog pin and fail-closed change classification."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

STD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STD / "tools"))
import skills
import changes


class C6PinIntegrityTests(unittest.TestCase):
    def test_declared_catalog_version_must_match_content_even_with_valid_digest(self):
        raw = (STD / "catalog.json").read_bytes()
        actual_version = json.loads(raw)["catalog_version"]
        pin = {"catalog_sha256": hashlib.sha256(raw).hexdigest(),
               "catalog_version": actual_version}
        _, receipt = skills.assemble(pin, ["spring-boot"], ["STD-BE"])
        self.assertEqual(receipt["catalog_sha256"], pin["catalog_sha256"])
        altered = dict(pin, catalog_version=actual_version.rsplit(".", 1)[0] + ".999")
        with self.assertRaisesRegex(ValueError, "BLOCK_SKILL_CATALOG_PIN_MISMATCH"):
            skills.assemble(altered, ["spring-boot"], ["STD-BE"])
        with self.assertRaisesRegex(ValueError, "BLOCK_SKILL_CATALOG_PIN_MISMATCH"):
            skills.assemble(dict(pin, catalog_version="0.6.1"),
                            ["spring-boot"], ["STD-BE"])


class C9ClassificationRegressions(unittest.TestCase):
    def test_skill_compatibility_tightening_is_not_additive(self):
        old = {"skill_version": "0.2.0", "catalog_compat": "0.6",
               "glossary_compat": "0.4", "domains": ["STD-BE"],
               "exclude_rule_ids": []}
        new = copy.deepcopy(old)
        new.update(skill_version="0.3.0", catalog_compat="0.7")
        diff = changes.walk(changes.normalized(old), changes.normalized(new))
        category, warnings, errors = changes.classify_skill_fields(
            [d for d in diff if d[0] != "/skill_version"],
            "standards/skills/spring-boot/skill.json")
        self.assertEqual((category, warnings, errors), ("TIGHTENING", [], []))

    def test_mixed_skill_domain_removal_and_addition_fails_closed(self):
        category, _, errors = changes.classify_skill_fields(
            [("/domains", ["STD-BE", "STD-SEC"], ["STD-BE", "STD-API"])],
            "standards/skills/spring-boot/skill.json")
        self.assertIn("MIXED_CHANGE_REQUIRES_SPLIT", errors)
        self.assertEqual(category, "SECURITY")

    def test_undeclared_skill_field_rejected(self):
        _, _, errors = changes.classify_skill_fields(
            [("/unexpected_switch", False, True)],
            "standards/skills/spring-boot/skill.json")
        self.assertIn("UNCLASSIFIED_FIELD_CHANGE", errors)


if __name__ == "__main__":
    unittest.main()
