"""CHG-0008: ADR-014 modifies existing IaC rules without duplicating them."""
import json
import unittest
from pathlib import Path

class CHG0008IaCTest(unittest.TestCase):
    def test_iac_tightening_and_separate_governance(self):
        root=Path(__file__).resolve().parents[1]
        catalog=json.loads((root/"catalog.json").read_text(encoding="utf8"))
        chg=json.loads((root/"changes"/"CHG-0008.json").read_text(encoding="utf8"))
        self.assertEqual(catalog["catalog_version"],"0.8.0")
        self.assertEqual(chg["change_class"],"TIGHTENING")
        self.assertEqual(chg["evidence"]["review"],"PENDING_INDEPENDENT_SEMANTIC_REVIEW")
        rules={r["id"]:r for r in catalog["rules"]}
        self.assertEqual(len(rules),86)
        self.assertNotIn("STD-IAC-08",rules)
        for rule_id in ("STD-IAC-01","STD-IAC-05","STD-IAC-06"):
            rule=rules[rule_id]
            self.assertEqual(rule["severity"],"BLOCK")
            self.assertEqual(rule["status"],"APROBADO")
            self.assertIn("ADR-PROG-STD-014",rule["rule"])
            self.assertEqual(rule["enforcement"]["state"],"planned")
            self.assertTrue(rule["examples"]["good"])
            self.assertTrue(rule["examples"]["bad"])
        self.assertIn("Fase 4",rules["STD-IAC-01"]["rule"])
        self.assertIn("Floci",rules["STD-IAC-05"]["rule"])
        self.assertIn("prohibido aplicar recursos en la nube",rules["STD-IAC-06"]["rule"])
        for slug in ("spring-boot","nextjs","postgres-flyway"):
            skill=json.loads((root/"skills"/slug/"skill.json").read_text(encoding="utf8"))
            self.assertEqual(skill["catalog_compat"],"0.8")
