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

    def test_standalone_rejections_preserve_canonical_and_unrelated_names(self):
        path = "db/V10__offer_rules.sql"
        for identifier in (
            "offer_rule_id", "offer_condition_id", "prevention_rule",
            "lint_rule", "http_condition",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(self.scanner.scan(path, f"CREATE TABLE {identifier} (id bigint);"), [])

    def test_standalone_rejections_flag_bare_and_plural_forms(self):
        path = "db/V11__bare_rules.sql"
        for sql, rejected in (
            ("CREATE TABLE rules (id bigint);", "'rules' usa 'rule'"),
            ("CREATE TABLE example (rule_id bigint);", "'rule_id' usa 'rule'"),
            ("CREATE TABLE example (condition text);", "'condition' usa 'condition'"),
        ):
            with self.subTest(sql=sql):
                found = "\\n".join(self.scanner.scan(path, sql))
                self.assertIn(rejected, found)

    def test_invalid_rejection_match_is_rejected(self):
        bad = copy.deepcopy(self.glossaries)
        term = next(t for g in bad for t in g["terms"] if t["term_en"] == "offer_rule")
        term["rejected_en"][0]["match"] = "substring"
        self.assertTrue(any("match inválido" in e for e in glossary.validate(bad)))


    def test_waiver_registry_and_reference(self):
        import waivers
        import datetime as dt
        catalog, registry = waivers.load()
        self.assertEqual(waivers.validate(catalog, registry), [])
        day = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)
        target = {"kind": "LINTER_RULE", "tool": "eslint", "rule": "no-console"}
        self.assertEqual(waivers.evaluate(catalog, registry, "standards/tests/fixtures/suppressions/good.ts", target, day)[0], "AUTHORIZED")
        self.assertEqual(waivers.evaluate(catalog, registry, "frontend/src/demo.ts", target, day)[1], "OUT_OF_SCOPE")

    def test_waiver_negative_cases(self):
        import waivers
        import datetime as dt
        catalog, registry = waivers.load()
        day = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)
        good = "standards/tests/fixtures/suppressions/good.ts"
        target = {"kind": "LINTER_RULE", "tool": "eslint", "rule": "no-console"}
        cases = [
            ("duplicate", lambda c, r: r["waivers"].append(copy.deepcopy(r["waivers"][0])), "id duplicado"),
            ("approver_empty", lambda c, r: r["waivers"][0].update(approved_by=""), "approved_by inválido"),
            ("approver_same", lambda c, r: r["waivers"][0].update(approved_by="agent:gpt"), "approved_by inválido"),
            ("expired_period", lambda c, r: r["waivers"][0].update(expires_at="2028-10-22T00:00:00Z"), "plazo máximo"),
            ("universal", lambda c, r: r["waivers"][0]["scope"].update(paths=["**/*"]), "scope.paths inválido"),
            ("parent", lambda c, r: r["waivers"][0]["scope"].update(paths=["../bad.ts"]), "scope.paths inválido"),
            ("fixture_escape", lambda c, r: r["waivers"][0]["scope"].update(paths=["frontend/src/a.ts"]), "TEST_FIXTURE fuera"),
            ("denylist", lambda c, r: r["waivers"][0]["target"].update(rule="no-eval"), "RULE_NOT_WAIVABLE"),
            ("std_gen_05", lambda c, r: r["waivers"][0].update(target={"kind":"STD_RULE","rule_id":"STD-GEN-05","controls":[]}), "RULE_NOT_WAIVABLE"),
            ("std_not_allowed", lambda c, r: r["waivers"][0].update(target={"kind":"STD_RULE","rule_id":"STD-SEC-02","controls":[]}), "RULE_NOT_WAIVABLE"),
            ("std_default_deny", lambda c, r: r["waivers"][0].update(target={"kind":"STD_RULE","rule_id":"STD-DB-01","controls":[]}), "RULE_NOT_WAIVABLE"),
            ("revoked_missing", lambda c, r: r["waivers"][0].update(status="REVOKED"), "REVOKED"),
        ]
        for label, mutate, message in cases:
            with self.subTest(label=label):
                c, r = copy.deepcopy(catalog), copy.deepcopy(registry)
                mutate(c, r)
                self.assertIn(message, " ".join(waivers.validate(c, r)))
        expired = copy.deepcopy(registry)
        expired["waivers"][0]["expires_at"] = "2026-10-23T00:00:00Z"
        self.assertEqual(waivers.evaluate(catalog, expired, good, target, day)[1], "EXPIRED")
        revoked = copy.deepcopy(registry)
        revoked["waivers"][0]["status"] = "REVOKED"
        self.assertEqual(waivers.evaluate(catalog, revoked, good, target, day)[1], "REVOKED")
        self.assertEqual(waivers.evaluate(catalog, registry, good, {"kind":"LINTER_RULE","tool":"eslint","rule":"no-debugger"}, day)[0], "NOT_AUTHORIZED")
        self.assertEqual(waivers.evaluate(catalog, {"waivers":[]}, good, target, day)[1], "NO_WAIVER")
        self.assertEqual(waivers.parse_suppression("// eslint-disable -- WAIVER-0001"), [("MISSING_LINTER_RULE", None)])
        self.assertEqual(waivers.render(registry), waivers.OUTPUT.read_text(encoding="utf-8"))
        self.assertNotEqual(waivers.render(registry), waivers.render({**registry, "registry_version":"9.9.9"}))

    def test_coverage_positive(self):
        mapping = json.loads((GLOSSARY_FIXTURES / "coverage_ok.json").read_text(encoding="utf-8"))
        self.assertEqual(glossary.coverage(self.glossaries, mapping), [])

    def test_coverage_negative(self):
        mapping = json.loads((GLOSSARY_FIXTURES / "coverage_bad.json").read_text(encoding="utf-8"))
        found = "\n".join(glossary.coverage(self.glossaries, mapping))
        self.assertIn("REQUIRES_DECISION debt_collection_status: 'collection'", found)
        self.assertIn("term_id desconocido GLOSS-LF-NOPE-001", found)


    def test_invalid_payment_status_values_fails(self):
        bad = copy.deepcopy(self.glossaries)
        t = next(t for g in bad for t in g["terms"] if t["term_en"] == "payment_status")
        t["values"] = {"aprobado": "Invalid-Camel"}
        self.assertTrue(any("values" in e for e in glossary.validate(bad)))

    def test_english_spanish_homographs_not_flagged(self):
        scanner = glossary.Scanner(self.glossaries)
        text = "CREATE TABLE payment_plans (payment_plan_id bigint, original_debt numeric);"
        self.assertEqual(scanner.scan("db/V5__plans.sql", text), [])

    def test_new_spanish_business_identifiers_are_flagged(self):
        scanner = glossary.Scanner(self.glossaries)
        text = "CREATE TABLE bad (recaudo_total numeric, plazo_maximo integer);"
        found = "\\n".join(scanner.scan("db/V6__bad.sql", text))
        self.assertIn("recaudo", found)
        self.assertIn("plazo", found)

    def test_collection_legacy_exact_contract_and_new_identifier(self):
        scanner = glossary.Scanner(self.glossaries)
        legacy = "SELECT public.lf_b2b_pricing_config.collection_channel FROM public.lf_b2b_pricing_config;"
        self.assertEqual(scanner.scan("db/V7__legacy.sql", legacy), [])
        found = "\\n".join(scanner.scan("db/V8__new.sql", "CREATE TABLE bad (collection_amount numeric);"))
        self.assertIn("collection", found)


if __name__ == "__main__":
    unittest.main()
