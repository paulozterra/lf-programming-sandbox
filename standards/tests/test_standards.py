"""Pruebas de los checks del catálogo: cada check falla con su caso negativo (PG-00·C7)."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import checks
import glossary
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


GLOSSARY_FIXTURES = FIXTURES / "glossary"


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.glossaries = glossary.load()
        self.scanner = glossary.Scanner(self.glossaries)

    def scan(self, name, fake_path):
        return self.scanner.scan(fake_path, (GLOSSARY_FIXTURES / name).read_text(encoding="utf-8"))

    def test_glossary_is_valid(self):
        self.assertEqual(glossary.validate(self.glossaries), [])

    def test_glossary_md_is_up_to_date(self):
        expected = glossary.render(self.glossaries)
        self.assertEqual(glossary.OUTPUT.read_text(encoding="utf-8"), expected)

    def test_duplicate_translation_is_rejected(self):
        bad = copy.deepcopy(self.glossaries)
        clone = copy.deepcopy(bad[0]["terms"][0])
        clone["term_id"] = "GLOSS-BASE-OTHER-001"
        clone["term_es"] = "otro"
        bad[0]["terms"].append(clone)
        self.assertTrue(any("una sola traducción" in e for e in glossary.validate(bad)))

    def test_wildcard_legacy_contract_is_rejected(self):
        bad = copy.deepcopy(self.glossaries)
        term = next(t for g in bad for t in g["terms"] if t["legacy_en"])
        term["legacy_en"][0]["contracts"] = ["lf_client.*"]
        self.assertTrue(any("exacto" in e for e in glossary.validate(bad)))

    def test_positive_sql_has_no_violations(self):
        self.assertEqual(self.scan("positive.sql", "backend/src/main/resources/db/migration/V1__offers.sql"), [])

    def test_negative_sql_flags_spanish_and_rejected_forms(self):
        found = "\n".join(self.scan("negative.sql", "backend/src/main/resources/db/migration/V2__bad.sql"))
        self.assertIn("'deudas' usa 'deudas' en español", found)
        self.assertIn("'client_id' usa 'client'", found)
        self.assertIn("'portfolio_upload_id' usa 'portfolio_upload'", found)

    def test_legacy_contract_is_preserved(self):
        self.assertEqual(self.scan("legacy_ok.sql", "db/V3__legacy.sql"), [])

    def test_new_name_in_legacy_schema_is_flagged(self):
        found = "\n".join(self.scan("legacy_new_name.sql", "db/V4__new.sql"))
        self.assertIn("'client_notes' usa 'client'", found)

    def test_false_positives_are_not_flagged(self):
        self.assertEqual(self.scan("FalsePositive.java", "backend/src/main/java/lf/sandbox/core/PaymentGateway.java"), [])

    def test_coverage_positive(self):
        mapping = json.loads((GLOSSARY_FIXTURES / "coverage_ok.json").read_text(encoding="utf-8"))
        self.assertEqual(glossary.coverage(self.glossaries, mapping), [])

    def test_coverage_negative(self):
        mapping = json.loads((GLOSSARY_FIXTURES / "coverage_bad.json").read_text(encoding="utf-8"))
        found = "\n".join(glossary.coverage(self.glossaries, mapping))
        self.assertIn("REQUIRES_DECISION debt_collection_status: 'collection'", found)
        self.assertIn("term_id desconocido GLOSS-LF-NOPE-001", found)


if __name__ == "__main__":
    unittest.main()
