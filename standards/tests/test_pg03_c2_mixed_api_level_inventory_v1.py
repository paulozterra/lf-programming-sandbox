"""Independent source inventory for PG-03_C2: mixed level is not a level."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT.parent/"docs/programming/PG03_C2_STD_API_MIXED_LEVEL_DECISION_20261103.md"
IDS={f"STD-API-{i:02d}" for i in range(1,10)}

class PG03C2MixedLevelAuditTests(unittest.TestCase):
    def test_canonical_order_is_explicit_not_inferred(self):
        catalog=json.loads((ROOT/"catalog.json").read_text(encoding="utf8"))
        self.assertEqual(catalog["precedence"],[
            "L1 (piso que nadie rebaja)",
            "Lo que trae el spec de la Fase 1 (reglas tipo A)",
            "Contratos existentes y perfil técnico del proyecto (reglas tipo B, por manifiesto)",
            "Valor por defecto del catálogo (L2)"])
    def test_mixed_domain_and_nine_unclassified_rules_are_reported(self):
        catalog=json.loads((ROOT/"catalog.json").read_text(encoding="utf8"))
        mixed={d["id"] for d in catalog["domains"] if d.get("level")=="L1/L2"}
        unresolved={r["id"] for r in catalog["rules"]
                    if r["domain"] in mixed and r.get("level") not in ("L1","L2")}
        self.assertEqual(mixed,{"STD-API"})
        self.assertEqual(unresolved,IDS)
        document=DOC.read_text(encoding="utf8")
        for rule in unresolved:
            self.assertIn(f"| {rule} |",document)
        self.assertIn("REQUIRES_OWNER_DECISION",document)
        self.assertIn("no modifica el reglamento",document)
    def test_severity_does_not_authorize_l1_assignment(self):
        catalog=json.loads((ROOT/"catalog.json").read_text(encoding="utf8"))
        api=[r for r in catalog["rules"] if r["domain"]=="STD-API"]
        self.assertEqual(len(api),9)
        self.assertIn("BLOCK",{r.get("severity") for r in api})
        self.assertIn("WARN",{r.get("severity") for r in api})
        self.assertTrue(all("level" not in r for r in api))

if __name__=="__main__":
    unittest.main()
