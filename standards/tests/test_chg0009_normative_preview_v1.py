"""CHG-0009: isolated in-memory normative preview, NEVER a catalog release.

Checks proposed split against the real catalog validator and documents an
actual fail-closed security dependency on NON_WAIVABLE / SECURITY_IDS.
No production catalog file, changer, pins or policy module is mutated.
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

STD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STD / "tools"))
from validate_catalog import validate
from policy_invariants import NON_WAIVABLE
from changes import SECURITY_IDS, security_rule

SPLIT = {
    "STD-API-04": (
        ("STD-API-10", "L1",
         "Nunca exponer stack traces, consultas SQL ni detalles internos sensibles en respuestas de error."),
        ("STD-API-11", "L2",
         "Formato de errores conforme a D1 y D2 y a contratos vigentes, sin inventar mensajes ni códigos.")),
    "STD-API-05": (
        ("STD-API-12", "L1",
         "Para operaciones de riesgo: exigir garantías de idempotencia cuando apliquen; "
         "propagar identificador de petición y correlación; aplicar controles antiabuso cuando correspondan."),
        ("STD-API-13", "L2",
         "Headers según D8/D9: Idempotency-Key, X-Request-Id y X-Correlation-Id; "
         "documentar respuestas 429 y Retry-After conforme al contrato vigente.")),
    "STD-API-08": (
        ("STD-API-14", "L1",
         "Garantizar exactitud monetaria, sin cálculos con punto flotante que pierdan precisión."),
        ("STD-API-15", "L2",
         "Contrato D10: amount como texto decimal y currency; en BD numeric(18,2) "
         "o contrato vigente aprobado sin pérdida de exactitud.")),
}
LEVEL = {
    "STD-API-01": "L2", "STD-API-02": "L2", "STD-API-03": "L2",
    "STD-API-06": "L1", "STD-API-07": "L2", "STD-API-09": "L1",
}
SOURCE = {
    "STD-API-04": ("D1", "D2", "stack trace", "SQL"),
    "STD-API-05": ("Idempotency-Key", "X-Request-Id", "X-Correlation-Id", "429", "Retry-After"),
    "STD-API-08": ("decimal", "currency", "numeric(18,2)"),
}

def build_preview(source, proposal):
    original = {r["id"]: r for r in source["rules"] if r["domain"] == "STD-API"}
    assert set(original) == set(proposal["proposed_levels"]) == set(LEVEL) | set(SPLIT)
    assert proposal["proposed_reference_migration"] == proposal["provisional_splits"]
    updated = copy.deepcopy(source)
    updated["rules"] = [r for r in updated["rules"] if r["id"] not in SPLIT]
    for r in updated["rules"]:
        if r["id"] in LEVEL:
            r["level"] = LEVEL[r["id"]]
    for old, parts in SPLIT.items():
        assert [p[0] for p in parts] == proposal["provisional_splits"][old]
        old_rule = original[old]
        for new_id, level, meaning in parts:
            new = copy.deepcopy(old_rule)
            new["id"], new["level"], new["rule"] = new_id, level, meaning
            new["legacy_rule_id"] = old  # preview only; needs governed migration mapping
            # Preserve source examples for review; they remain bound to old rule
            # semantics until the owner approves example-level redistribution.
            if old == "STD-API-04" and level == "L1":
                new["waiver_policy"] = copy.deepcopy(old_rule["waiver_policy"])
            else:
                new.pop("waiver_policy", None)
            updated["rules"].append(new)
    return updated

def preview_security_gate(candidate, *, non_waivable, security_ids):
    rows = {r["id"]: r for r in candidate["rules"]}
    if "STD-API-10" not in non_waivable:
        return "BLOCK_MISSING_L1_NON_WAIVABLE"
    if not {"STD-API-10", "STD-API-11"}.issubset(security_ids):
        return "BLOCK_MISSING_SECURITY_DIFF_CLASSIFICATION"
    if rows["STD-API-10"]["waiver_policy"]["allowed"] is not False:
        return "BLOCK_L1_WAIVER"
    if "STD-API-04" not in non_waivable or "STD-API-04" not in security_ids:
        return "BLOCK_LEGACY_SECURITY_GUARD_REMOVED"
    return "STRUCTURAL_PREVIEW_ONLY_NO_AUTHORITY"

class CHG0009InMemoryPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=json.loads((STD/"catalog.json").read_text(encoding="utf-8"))
        cls.proposal=json.loads((STD/"changes/proposals/CHG-0009.draft.json").read_text(encoding="utf-8"))
        cls.preview=build_preview(cls.source,cls.proposal)

    def test_full_preview_shape_and_existing_validator(self):
        # Version and status deliberately stay draft; preview not publishable.
        self.assertEqual(self.preview["catalog_version"],"0.7.0")
        self.assertEqual(self.preview["status"],"BORRADOR_EN_REPO_DE_CALIFICACION")
        self.assertEqual(validate(self.preview),[])
        before={r["id"] for r in self.source["rules"]}
        after={r["id"] for r in self.preview["rules"]}
        self.assertEqual(len(after),len(before)+3)
        self.assertEqual(before-after,set(SPLIT))
        self.assertEqual(after-before,{f"STD-API-{n}" for n in range(10,16)})
        self.assertEqual({r["id"] for r in self.preview["rules"] if r["domain"]=="STD-API"},
                         set(LEVEL)|{f"STD-API-{n}" for n in range(10,16)})

    def test_atomic_source_obligations_accounted_for(self):
        source_rows={r["id"]:r for r in self.source["rules"]}
        for old, fragments in SOURCE.items():
            raw=source_rows[old]["rule"]
            for fragment in fragments:
                self.assertIn(fragment,raw,(old,fragment))
            joined=" ".join(part[2] for part in SPLIT[old])
            for fragment in fragments:
                # Some wording changes for semantic reasons: their obligations
                # remain in the proposal's full trace matrix for independent review.
                self.assertTrue(fragment in joined or fragment in
                                (STD.parent/"docs/programming/CHG-0009_STD_API_LEVEL_SPLIT_PROPOSAL_20261103.md")
                                .read_text(encoding="utf-8"))
        levels={r["id"]:r["level"] for r in self.preview["rules"] if r["domain"]=="STD-API"}
        self.assertEqual(sum(v=="L1" for v in levels.values()),5)
        self.assertEqual(sum(v=="L2" for v in levels.values()),7)

    def test_fail_closed_on_actual_unmigrated_security_authority(self):
        self.assertEqual(preview_security_gate(self.preview,
            non_waivable=NON_WAIVABLE,security_ids=SECURITY_IDS),
            "BLOCK_MISSING_L1_NON_WAIVABLE")
        self.assertFalse(security_rule("STD-API-10"))
        self.assertEqual(preview_security_gate(self.preview,
            non_waivable=set(NON_WAIVABLE)|{"STD-API-10"},
            security_ids=SECURITY_IDS),
            "BLOCK_MISSING_SECURITY_DIFF_CLASSIFICATION")
        self.assertEqual(preview_security_gate(self.preview,
            non_waivable=set(NON_WAIVABLE)|{"STD-API-10"},
            security_ids=set(SECURITY_IDS)|{"STD-API-10","STD-API-11"}),
            "STRUCTURAL_PREVIEW_ONLY_NO_AUTHORITY")

    def test_negative_security_waiver_or_legacy_guard_removal(self):
        bad=copy.deepcopy(self.preview)
        next(r for r in bad["rules"] if r["id"]=="STD-API-10")["waiver_policy"]["allowed"]=True
        secure=set(NON_WAIVABLE)|{"STD-API-10"}
        categorized=set(SECURITY_IDS)|{"STD-API-10","STD-API-11"}
        self.assertEqual(preview_security_gate(bad,non_waivable=secure,security_ids=categorized),
                         "BLOCK_L1_WAIVER")
        self.assertEqual(preview_security_gate(self.preview,
            non_waivable=secure-{"STD-API-04"},security_ids=categorized),
            "BLOCK_LEGACY_SECURITY_GUARD_REMOVED")

    def test_proposal_cannot_claim_release(self):
        ready=self.proposal["readiness"]
        for key in ("catalog_modified","change_active","owner_normative_go",
                    "independent_security_review","C3_release_verified","PG03_C2_admitted"):
            self.assertIs(ready[key],False)
        self.assertFalse((STD/"changes/CHG-0009.json").exists())
        self.assertEqual(set(self.proposal["proposed_split_levels"]),{
            f"STD-API-{n}" for n in range(10,16)})

if __name__=="__main__":
    unittest.main()
