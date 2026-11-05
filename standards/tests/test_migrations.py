"""Ejercicio 2: pruebas VISIBLES MIG-01..07 (14 escenarios).

Antes de implementar standards/tools/migrations.py se espera RED:
el nuevo módulo no existe; su creación corresponde exclusivamente al Worker.
El holdout adicional es PRIVADO y Claude lo prepara por separado.
"""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from migrations import check_migrations


class MigrationsVisibleTests(unittest.TestCase):
    def assert_issue(self, paths, rule, name):
        findings = check_migrations(paths)
        self.assertTrue(
            any(rule in msg and name in msg for msg in findings),
            (rule, name, findings),
        )

    # MIG-01: patrón de nombre V<n>__<desc>.sql.
    def test_mig01_positive(self):
        self.assertEqual(check_migrations(["db/V1__init.sql"]), [])

    def test_mig01_negative(self):
        self.assert_issue(["db/migration_one.sql"], "MIG-01", "migration_one.sql")

    # MIG-02: descripción [a-z0-9_] de 1 a 60 caracteres.
    def test_mig02_positive(self):
        self.assertEqual(check_migrations(["V1__create_table.sql"]), [])

    def test_mig02_negative(self):
        self.assert_issue(["V1__Bad.sql"], "MIG-02", "V1__Bad.sql")

    # MIG-03: versiones únicas.
    def test_mig03_positive(self):
        self.assertEqual(check_migrations(["V1__alpha.sql", "V2__beta.sql"]), [])

    def test_mig03_negative(self):
        self.assert_issue(
            ["V1__alpha.sql", "V1__beta.sql"],
            "MIG-03", "V1__beta.sql",
        )

    # MIG-04: versiones consecutivas desde 1.
    def test_mig04_positive(self):
        self.assertEqual(check_migrations(["V1__alpha.sql", "V2__beta.sql"]), [])

    def test_mig04_negative(self):
        self.assert_issue(
            ["V1__alpha.sql", "V3__gamma.sql"],
            "MIG-04", "V3__gamma.sql",
        )

    # MIG-05: no hay ceros iniciales.
    def test_mig05_positive(self):
        self.assertEqual(check_migrations(["V1__alpha.sql"]), [])

    def test_mig05_negative(self):
        self.assert_issue(["V01__alpha.sql"], "MIG-05", "V01__alpha.sql")

    # MIG-06: ignorar entradas que no terminan exactamente en .sql.
    def test_mig06_positive(self):
        self.assertEqual(check_migrations(["README.md", "V5__draft.SQL"]), [])

    def test_mig06_negative(self):
        self.assert_issue(
            ["notes.md", "migration_bad.sql"],
            "MIG-01", "migration_bad.sql",
        )

    # MIG-07: orden estable y [] para entrada vacía.
    def test_mig07_positive(self):
        self.assertEqual(check_migrations([]), [])

    def test_mig07_negative(self):
        # Desorden deliberado: versión, luego nombre, sin versión al final.
        findings = check_migrations([
            "bad_name.sql",
            "db/V3__zeta.sql",
            "db/V3__alpha.sql",
            "db/V1__Bad.sql",
        ])
        self.assertGreaterEqual(len(findings), 4, findings)
        ordered = [
            next(i for i, msg in enumerate(findings) if marker in msg)
            for marker in ("V1__Bad.sql", "V3__alpha.sql",
                           "V3__zeta.sql", "bad_name.sql")
        ]
        self.assertEqual(ordered, sorted(ordered), findings)


if __name__ == "__main__":
    unittest.main(verbosity=2)
