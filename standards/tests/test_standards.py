"""Pruebas de los checks del catálogo: cada check falla con su caso negativo (PG-00·C7)."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import checks
import render_llm
import validate_catalog

FIXTURES = ROOT / "tests" / "fixtures"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))

    def test_catalog_is_valid(self):
        self.assertEqual(validate_catalog.validate(self.catalog), [])

    def test_duplicate_id_is_rejected(self):
        bad = copy.deepcopy(self.catalog)
        bad["rules"].append(copy.deepcopy(bad["rules"][0]))
        self.assertTrue(any("duplicado" in e for e in validate_catalog.validate(bad)))

    def test_shadow_without_command_is_rejected(self):
        bad = copy.deepcopy(self.catalog)
        rule = next(r for r in bad["rules"] if r["enforcement"]["state"] == "shadow")
        del rule["enforcement"]["command"]
        self.assertTrue(any("necesita 'command'" in e for e in validate_catalog.validate(bad)))

    def test_llm_catalog_is_up_to_date(self):
        expected = render_llm.render(self.catalog)
        self.assertEqual((ROOT / "CATALOGO.md").read_text(encoding="utf-8"), expected)


class CheckTests(unittest.TestCase):
    def test_filenames_negative(self):
        self.assertTrue(checks.check_filenames([str(FIXTURES / "frontend-bad")]))

    def test_filenames_positive(self):
        self.assertEqual(checks.check_filenames([str(FIXTURES / "frontend-good")]), [])

    def test_suppressions_negative(self):
        self.assertTrue(checks.check_suppressions([str(FIXTURES / "suppressions" / "bad.ts")]))

    def test_suppressions_positive(self):
        self.assertEqual(checks.check_suppressions([str(FIXTURES / "suppressions" / "good.ts")]), [])

    def test_branch_negative(self):
        self.assertTrue(checks.check_branch("feature/descuentos"))

    def test_branch_positive(self):
        self.assertEqual(checks.check_branch("lf/prog-sandbox/pg00-reglamento-v0-1"), [])


if __name__ == "__main__":
    unittest.main()
