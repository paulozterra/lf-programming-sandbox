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


    def test_c5_spanish_forms_and_rendered_kit_are_clean(self):
        import kit
        import tempfile
        sql = ("CREATE TABLE x.consentimientos(id bigint, pantalla text, mensaje text, "
               "sesion_id uuid, ocurrencia_id bigint);")
        findings = self.scanner.scan("backend/src/main/resources/db/migration/V1__check.sql", sql)
        for form in ("consentimientos", "pantalla", "mensaje", "sesion", "ocurrencia"):
            with self.subTest(form=form):
                self.assertTrue(any(form in issue for issue in findings), findings)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            kit.render("kit_test", "KIT", output)
            for path in output.glob("*.sql"):
                with self.subTest(file=path.name):
                    findings = self.scanner.scan(
                        "backend/src/main/resources/db/migration/" + path.name,
                        path.read_text(encoding="utf-8"))
                    self.assertEqual(findings, [])

    def test_technical_tokens_must_not_shadow_glossary_terms(self):
        for value, fragment in (("", "vacío"), ("consent", "canónico")):
            with self.subTest(token=value):
                bad = copy.deepcopy(self.glossaries)
                bad[0]["technical_tokens"].append(value)
                self.assertTrue(any(fragment in issue for issue in glossary.validate(bad)))

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


    def test_check_refs_fail_closed_and_targets(self):
        import waivers
        import datetime as dt
        catalog, registry = waivers.load()
        as_of = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)
        fixture = "standards/tests/fixtures/waivers/"
        cases = [
            ("java-no-waiver.java", "NO_WAIVER"),
            ("java-array.java", "NO_WAIVER"),
            ("unparsed.java", "UNPARSED_SUPPRESSION"),
            ("wrong-target.ts", "TARGET_MISMATCH"),
        ]
        for path, reason in cases:
            with self.subTest(path=path):
                issues = waivers.check_refs(catalog, registry, [fixture + path], as_of)
                self.assertTrue(any(reason in issue for issue in issues), issues)
        java_targets = waivers.parse_suppression('@SuppressWarnings({"a","b"})')
        self.assertEqual([t["rule"] for t in java_targets], ["a", "b"])
        self.assertEqual(len(waivers.check_refs(catalog, registry, [fixture + "java-array.java"], as_of)), 1)
        self.assertEqual(waivers.check_refs(catalog, registry, ["standards/tests/fixtures/suppressions/good.ts"], as_of), [])
        self.assertTrue(any("NO_WAIVER" in issue for issue in waivers.check_refs(
            catalog, registry, ["standards/tests/fixtures/suppressions/bad.ts"], as_of)))

    def test_superseded_and_catalog_versions(self):
        import waivers
        import datetime as dt
        catalog, registry = waivers.load()
        future = copy.deepcopy(catalog)
        future["catalog_version"] = "0.3.1"
        self.assertEqual(waivers.validate(future, registry), [])
        future_waiver = copy.deepcopy(registry)
        future_waiver["waivers"][0]["catalog_version"] = "99.0.0"
        self.assertTrue(any("posterior" in msg for msg in waivers.validate(catalog, future_waiver)))
        invalid = copy.deepcopy(registry)
        invalid["waivers"][0]["catalog_version"] = "not-semver"
        self.assertTrue(any("semver" in msg for msg in waivers.validate(catalog, invalid)))
        amended = copy.deepcopy(registry)
        newer = copy.deepcopy(amended["waivers"][0])
        newer["waiver_id"] = "WAIVER-0002"
        newer["supersedes"] = "WAIVER-0001"
        amended["waivers"].append(newer)
        path = "standards/tests/fixtures/suppressions/good.ts"
        target = {"kind": "LINTER_RULE", "tool": "eslint", "rule": "no-console"}
        day = dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)
        self.assertEqual(waivers.evaluate(catalog, {"waivers":[amended["waivers"][0], newer]}, path, target, day)[0], "AUTHORIZED")
        self.assertEqual(waivers.evaluate(catalog, {"waivers":[amended["waivers"][0], newer]}, path, target, day)[2], ["WAIVER-0002"])
        self.assertEqual(waivers.evaluate(catalog, {"waivers":[amended["waivers"][0], newer], "restricted":True}, path, target, day)[0], "AUTHORIZED")
        # A aislado de B para comprobar el motivo SUPERSEDED dentro del registro global.
        old = amended["waivers"][0]
        old["scope"]["paths"] = ["standards/tests/fixtures/waivers/old.ts"]
        self.assertEqual(waivers.evaluate(catalog, amended, "standards/tests/fixtures/waivers/old.ts", target, day)[1], "SUPERSEDED")

    def test_list_json_shape(self):
        import waivers
        import io
        import contextlib
        path = "standards/tests/fixtures/suppressions/good.ts"
        args = ["list", "--path", path, "--linter", "eslint:no-console",
                "--as-of", "2026-10-23T00:00:00Z", "--format", "json"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(waivers.main(args), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(set(payload), {"catalog_version", "registry_version", "as_of",
                                       "path", "target", "decision", "reason_code", "matches"})
        self.assertEqual(payload["decision"], "AUTHORIZED")

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



class KitBaseTests(unittest.TestCase):
    def test_verify_and_render(self):
        import kit
        import tempfile
        self.assertEqual(kit.verify(), [])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            kit.render("kit_test", "KIT", out)
            self.assertEqual(len(list(out.glob("*.sql"))), 8)
            self.assertIn("kit_test.errors", (out / "V0_1__common_tables.sql").read_text(encoding="utf-8"))
            self.assertIn("KIT-[0-9]{8}", (out / "V0_1__common_tables.sql").read_text(encoding="utf-8"))
            self.assertNotIn("\u0024{schema}", (out / "V0_1__common_tables.sql").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "INVALID_PLACEHOLDER"):
                kit.render("../bad", "KIT", out)
            with self.assertRaisesRegex(ValueError, "INVALID_PLACEHOLDER"):
                kit.render("kit_test", "lowercase", out)

    def test_migration_filenames(self):
        import db_catalog_lint as lint
        self.assertEqual(lint.check_files(str(ROOT / "kit-base/migrations")), [])
        bad = lint.check_files(str(ROOT / "kit-base/tests/negative"))
        self.assertTrue(any(x["reason_code"] == "INVALID_MIGRATION_NAME" and x["object"] == "V1__FechaPago.sql" for x in bad))

    def test_lint_parser_negative(self):
        import db_catalog_lint as lint
        data = {
            "tables": [{"name":"bad_table","comment":"mutable","rls":False}],
            "columns":[{"table":"bad_table","name":"id","type":"integer","identity":"","nullable":False,"default":None},
                       {"table":"bad_table","name":"created_at","type":"timestamp with time zone","nullable":False,"default":"now()"},
                       {"table":"bad_table","name":"active","type":"boolean","nullable":True,"default":None}],
            "constraints":[],"indexes":[{"table":"bad_table","name":"idx_custom"}],
            "triggers":[],"functions":[{"name":"unsafe","definer":True,"search_path":None,"public_execute":True}],
            "public_privileges":[{"name":"bad_table","privilege":"SELECT"}]}
        result = lint.lint_data(data)
        self.assertEqual(result["verdict"], "FAIL")
        codes = {x["reason_code"] for x in result["findings"]}
        self.assertTrue({"INVALID_PRIMARY_KEY", "INVALID_BOOLEAN_NAME", "INVALID_TIMESTAMP",
                         "CUSTOM_INDEX_NAME", "MISSING_UPDATED_AT_TRIGGER", "UNSAFE_SECURITY_DEFINER",
                         "RLS_REQUIRED"} <= codes)
        self.assertEqual(set(result) & {"schema","catalog_version","kit_version","findings","verdict"},
                         {"schema","catalog_version","kit_version","findings","verdict"})



class ChangeCircuitTests(unittest.TestCase):
    """Árboles sintéticos: ninguna prueba cambia main."""
    def test_classes_and_negative_codes(self):
        import changes
        old={"catalog_version":"0.4.0","rules":[{"id":"STD-FE-07","severity":"WARN","rule":"Mismo texto","enforcement":{"state":"shadow"}}]}
        chg={"schema_version":"LF_STANDARD_CHANGE_V1","change_id":"CHG-0001",
             "change_class":"ADDITIVE","title":"test","reason":"test",
             "trigger":{"kind":"C9","reference":"synthetic"},
             "artifacts":[{"artifact":"catalog","from_version":"0.4.0","to_version":"0.5.0"}],
             "affected":{"rule_ids":[],"term_ids":[],"paths":[]},
             "existing_code_impact":{"mode":"NEW_OR_MODIFIED_ONLY"},
             "security_pin_invalidation":{"invalidates":False},
             "requested_by":"test","approved_by":"paulozterra",
             "evidence":{"pr_url":"https://github.com/example/repo/pull/1"}}
        path="standards/catalog.json"
        changed=[path]
        def run(new,c=chg,paths=changed):
            return changes.check_transition({path:old},{path:new},paths,c)["findings"]
        newer=copy.deepcopy(old);newer["change_registry"]="standards/changes";newer["catalog_version"]="0.5.0"
        self.assertEqual(run(newer),[])
        self.assertIn("MISSING_CHG",run(newer,None))
        self.assertIn("VERSION_NOT_BUMPED",run({**newer,"catalog_version":"0.4.0"}))
        self.assertIn("UNEXPLAINED_VERSION_BUMP",run({**old,"catalog_version":"0.5.0"}))
        severity=copy.deepcopy(old);severity["rules"][0]["severity"]="BLOCK";severity["catalog_version"]="0.5.0"
        self.assertIn("CHANGE_CLASS_MISMATCH",run(severity,{**chg,"change_class":"EDITORIAL"}))
        mixed=copy.deepcopy(severity);mixed["rules"][0]["enforcement"]["state"]="planned"
        self.assertIn("MIXED_CHANGE_REQUIRES_SPLIT",run(mixed))
        self.assertIn("MISSING_RELAXING_EVIDENCE",changes.validate_record({**chg,"change_class":"RELAXING"}))
        self.assertIn("INDEPENDENT_REVIEW_MISSING",changes.validate_record({**chg,"change_class":"SECURITY"}))
        stale={**chg,"change_class":"SECURITY","review_content_sha256":"a",
               "independent_review":{"reviewed_sha256":"b","reviewer_ref":"hash",
                   "separation_declaration":"separate chat, memory off","provider_attested":False},
               "security_pin_invalidation":{"invalidates":True}}
        self.assertIn("REVIEW_STALE_SHA",changes.validate_record(stale))
        self.assertIn("SECURITY_PIN_NOT_INVALIDATED",changes.validate_record({
            **stale,"independent_review":{**stale["independent_review"],"reviewed_sha256":"a"},
            "security_pin_invalidation":{"invalidates":False}}))
        invalid=copy.deepcopy(newer);invalid["magic_unknown_policy"]="bad"
        self.assertIn("UNCLASSIFIED_FIELD_CHANGE",run(invalid))
        self.assertIn("DUPLICATE_CHG_ID",changes.validate_all([
            (Path("CHG-0001.json"),chg),(Path("CHG-0001.json"),chg)]))
        self.assertIn("BASELINE_INCREASE",changes.baseline_check({
            "STD-GEN-01":{"count":0,"fingerprints":[]}},{"STD-GEN-01":["new"]}))
        self.assertIn("PIN_MINIMUM_DECREASED",changes.check_pins(
            {"minimum_safe_versions":{"catalog":"0.4.0"}},
            {"minimum_safe_versions":{"catalog":"0.5.0"}}))
        self.assertIn("DERIVED_ONLY_EDIT",changes.check_transition({}, {},
            ["standards/GLOSARIO.md"],None)["findings"])

    def test_semver_and_security_domains(self):
        import changes
        for key in ("STD-SEC-01","STD-GEN-03","STD-DB-06","STD-API-04",
                    "STD-AUD-01","STD-CONS-01"):
            self.assertTrue(changes.security_rule(key))
        self.assertEqual(changes.classify_fields([("/rules/STD-FE-07/examples/good",["a"],["b"])])[0],"EDITORIAL")
        self.assertEqual(changes.classify_fields([("/rules/STD-FE-07/severity","WARN","BLOCK")])[0],"TIGHTENING")
        self.assertEqual(changes.classify_fields([("/rules/STD-FE-07/waiver_policy/allowed",False,True)])[0],"RELAXING")
        self.assertEqual(changes.classify_fields([("/rules/STD-SEC-01/severity","WARN","BLOCK")])[0],"SECURITY")
        self.assertEqual(changes.classify_fields([("/rules/STD-FE-07/new_rule",None,"new")])[0],"ADDITIVE")

if __name__ == "__main__":
    unittest.main()
