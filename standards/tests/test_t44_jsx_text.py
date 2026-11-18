"""T44: visible JSX text is UI copy, not an identifier (STD-GEN-01)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import glossary  # noqa: E402

PAGE = "frontend/src/app/sbx-b2b-login/page.tsx"


class JsxText(unittest.TestCase):
    def setUp(self):
        self.scanner = glossary.Scanner(glossary.load())

    def test_mandated_spanish_copy_in_jsx_is_allowed(self):
        self.assertEqual(self.scanner.scan(PAGE, "export const A = () => <strong>Backoffice Empresa</strong>;\n"), [])

    def test_spanish_identifiers_are_still_rejected(self):
        found = self.scanner.scan(PAGE, "const empresaId = 1;\nexport const A = () => <b>{empresaId}</b>;\n")
        self.assertTrue(found and all("empresaId" in f for f in found))

    def test_generic_type_arguments_are_still_code(self):
        self.assertTrue(self.scanner.scan(PAGE, "const m: Map<string, Empresa> = new Map();\n"))


if __name__ == "__main__":
    unittest.main()
