"""L1/L2 source-only regression, LF vs SALY and approved-scope language.

These are deterministic mocks, NOT a native model judge, A3 currentness proof,
or operational qualification. Run only from the repository exact HEAD.
"""
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

from test_a2 import RUN, RUN_A1, a1input, low
from test_a2_a3_business_handoff_v1 import inputs, prepare_candidate
from test_intent_brief_v1 import fixture as brief_fixture, mod as BRIEF

A1_PATH = Path(__file__).resolve().parents[2] / "a1"
spec = importlib.util.spec_from_file_location(
    "semantic_candidate_l1_l2", A1_PATH / "semantic_intake_candidate_v1.py"
)
SEM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SEM)

RAW = (
    "Programa la pantalla b2b inicio de sesión o login utiliza todas sus "
    "reglas y definiciones que ya están aprobadas, si hay reglas que aún "
    "están pendientes no las consideres no es requisito para continuar  "
    "la implementación"
)
POSITIVE = "utiliza todas sus reglas y definiciones que ya están aprobadas"
NEGATIVE = "si hay reglas que aún están pendientes no las consideres"
CONTINUATION = "no es requisito para continuar  la implementación"
TARGET = "pantalla b2b inicio de sesión o login"
CONSTRAINTS = [POSITIVE, NEGATIVE, CONTINUATION]


def quote_span(needle, kind):
    start = RAW.index(needle)
    return {"dimension": kind, "quote": needle,
            "start": start, "end": start + len(needle)}


def candidate():
    return {
        "schema_version": "A1_INTENT_ANALYSIS_CANDIDATE_V1",
        "operation": {"kind": "IMPLEMENT", "user_assumed_state": "UNSPECIFIED",
                      "repo_verification_state": "PENDING_INVENTORY"},
        "target": {
            "artifact_kind": "SCREEN", "functional_archetype": "AUTH_FLOW",
            "canonical_capability": "IDENTITY_AND_ACCESS", "actor_scope": "B2B",
            "raw_mentions": [TARGET],
        },
        "desired_outcome": "Implementar el login B2B solo bajo definiciones aprobadas",
        "analysis_hints": ["AUTHORITY_REVIEW", "SOURCE_CURRENTNESS_REVIEW"],
        "dimensions_to_investigate": ["SCREEN_IMPLEMENTATION", "APPROVED_RULES"],
        "evidence_spans": [
            quote_span("Programa", "OPERATION"),
            quote_span(TARGET, "ARTIFACT"),
            quote_span("inicio de sesión", "CAPABILITY"),
            quote_span("b2b", "ACTOR_SCOPE"),
            quote_span(POSITIVE, "CONSTRAINT"),
            quote_span(NEGATIVE, "NEGATION"),
            quote_span(CONTINUATION, "NEGATION"),
        ],
        "explicit_constraints": [{"text": p} for p in CONSTRAINTS],
        "material_ambiguities": [],
    }


def producer(raw):
    assert raw == RAW
    return candidate()


def review_fixture(raw, draft):
    # A model-independent test fixture, not an independent semantic judge.
    passed = (raw == RAW and
              [x["text"] for x in draft["explicit_constraints"]] == CONSTRAINTS)
    return {"verdict": "PASS" if passed else "FAIL",
            "candidate_sha256": SEM._hash(draft),
            "reviewer_ref": "fixture://L1-L2-20261108",
            "issues": [] if passed else ["APPROVED_OR_PENDING_SCOPE_LOST"]}


class BusinessIsolation(unittest.TestCase):
    def test_biz01_lf_a2_candidate_no_admission(self):
        a1 = RUN_A1.run(a1input())
        output = RUN.run(a1, low())
        self.assertEqual(output["business"], "LF")
        self.assertFalse(output["source_attested"])
        self.assertIsNone(output["next_step"])

    def test_biz02_saly_a1_scope_rejected(self):
        out = RUN_A1.run(RAW, business="SALY")
        self.assertEqual(out["blocking_codes"],
                         ["BUSINESS_SCOPE_NOT_PROVIDED_OR_NOT_LF"])

    def test_biz03_forged_same_business_saly_a2_rejected(self):
        a1 = RUN_A1.run(a1input())
        signal = low()
        a1["business"] = "SALY"
        signal["business"] = "SALY"
        out = RUN.run(a1, signal)
        self.assertEqual(out["blocking_codes"],
                         ["A2_BUSINESS_NOT_ENABLED_FOR_SKILL"])

    def test_biz04_lf_to_saly_a2_rejected(self):
        signal = low()
        signal["business"] = "SALY"
        out = RUN.run(RUN_A1.run(a1input()), signal)
        self.assertEqual(out["blocking_codes"], ["A2_BUSINESS_SCOPE_MISMATCH"])

    def test_biz05_direct_saly_a3_handoff_rejected(self):
        a1, a2 = inputs()
        a1["business"] = "SALY"
        a2["business"] = "SALY"
        out = prepare_candidate(a1, a2, "SALY")
        self.assertEqual(out["blocking_codes"],
                         ["BUSINESS_NOT_ENABLED_FOR_LF_SKILL"])

    def test_biz06_wrong_expected_business_rejected(self):
        a1, a2 = inputs()
        out = prepare_candidate(a1, a2, "SALY")
        self.assertEqual(out["blocking_codes"],
                         ["CROSS_BUSINESS_HANDOFF_FORBIDDEN"])

    def test_biz07_foreign_target_business_fact_rejected(self):
        a1, a2 = inputs()
        a1["payload"]["provided_facts"] = [
            {"fact_code": "TARGET_BUSINESS", "value": "SALY",
             "source_ref": "user://origin"}
        ]
        self.assertEqual(prepare_candidate(a1, a2, "LF")["blocking_codes"],
                         ["BUSINESS_IDENTITY_FACT_CONFLICT"])

    def test_biz08_explicit_saly_source_rejected_by_a1(self):
        payload = a1input()
        payload["source_refs"].append("supabase://saly.reglas")
        result = RUN_A1.run(payload)
        self.assertEqual(result["blocking_codes"],
                         ["CROSS_BUSINESS_SOURCE_REQUIRES_QUALIFIED_BINDING"])

    def test_biz09_related_business_does_not_rewrite_scope(self):
        a1, a2 = inputs()
        a1["payload"]["provided_facts"] = [
            {"fact_code": "RELATED_BUSINESS", "value": "SALY",
             "source_ref": "user://origin"}
        ]
        out = prepare_candidate(a1, a2, "LF")
        self.assertEqual(out["business"], "LF")
        self.assertFalse(out["a3_allowed"])

    def test_biz10_unresolved_reference_never_attested(self):
        a1, a2 = inputs()
        a1["payload"]["source_refs"].append(
            "https://example.invalid/opaque-source"
        )
        out = prepare_candidate(a1, a2, "LF")
        self.assertFalse(out["source_attested"])
        self.assertFalse(out["runtime_qualified"])
        self.assertFalse(out["a3_allowed"])


class ApprovedScopeSemantics(unittest.TestCase):
    def test_sem01_all_three_literal_clauses_grounded(self):
        draft = candidate()
        self.assertEqual(SEM._grounding_errors(RAW, draft), [])
        self.assertEqual([v["text"] for v in draft["explicit_constraints"]],
                         CONSTRAINTS)

    def test_sem02_positive_clause_omitted_reviewer_rejects(self):
        draft = candidate()
        draft["explicit_constraints"].pop(0)
        self.assertEqual(
            SEM.extract(RAW, lambda _: draft, review_fixture)["status"],
            "REQUIRES_SEMANTIC_REVIEW"
        )

    def test_sem03_pending_exclusion_omitted_reviewer_rejects(self):
        draft = candidate()
        draft["explicit_constraints"].pop(1)
        self.assertEqual(
            SEM.extract(RAW, lambda _: draft, review_fixture)["status"],
            "REQUIRES_SEMANTIC_REVIEW"
        )

    def test_sem04_forged_review_hash_rejected(self):
        result = SEM.extract(
            RAW, producer,
            lambda _raw, _draft: {
                "verdict": "PASS", "candidate_sha256": "f" * 64,
                "reviewer_ref": "fixture://forged", "issues": []
            }
        )
        self.assertEqual(result["blocking_codes"],
                         ["SEMANTIC_REVIEW_NOT_PASSED"])

    def test_sem05_a1_retains_scopes_verbatim(self):
        result = RUN_A1.run(
            RAW, business="LF", semantic_producer=producer,
            semantic_reviewer=review_fixture
        )
        self.assertEqual(result["status"], "VALID_OUTPUT")
        self.assertEqual(result["payload"]["constraints"], CONSTRAINTS)
        self.assertEqual(result["payload"]["objective"]["problem_statement"], RAW)
        self.assertNotIn("original_request", result["payload"])
        self.assertEqual(result["original_request_sha256"], __import__("hashlib").sha256(RAW.encode("utf-8")).hexdigest())

    def test_sem06_a2_does_not_authorize_implementation(self):
        a1 = RUN_A1.run(
            RAW, business="LF", semantic_producer=producer,
            semantic_reviewer=review_fixture
        )
        signal = low()
        signal["change_type"] = "IMPLEMENT"
        signal["target_ref"] = TARGET
        out = RUN.run(a1, signal)
        self.assertIn(out["status"],
                      ("NEED_MORE_EVIDENCE", "CANDIDATE_UNATTESTED"))
        self.assertIsNone(out["next_step"])
        self.assertFalse(out["source_attested"])
        self.assertEqual(a1["payload"]["constraints"], CONSTRAINTS)

    def test_sem07_a2_brief_preserves_all_inclusions_exclusions(self):
        a1, a2, signals, golden = brief_fixture()
        a1 = copy.deepcopy(a1)
        a1["payload"]["constraints"] = CONSTRAINTS[:]
        result = BRIEF.build_brief(a1, a2, signals, golden)
        self.assertEqual(result["scope_constraints_declared"], CONSTRAINTS)
        self.assertEqual(result["constraints_status"], "DECLARED_UNVERIFIED")
        self.assertTrue(all(x in result["human_readable_document"]
                            for x in CONSTRAINTS))

    def test_sem08_pending_is_not_waived_by_user_text(self):
        a1, a2, signals, golden = brief_fixture()
        a1["payload"]["constraints"] = CONSTRAINTS[:]
        result = BRIEF.build_brief(a1, a2, signals, golden)
        self.assertFalse(result["a3_allowed"])
        self.assertFalse(result["source_attested"])
        self.assertFalse(result["independent_judge_verified"])
        self.assertEqual(len(result["required_evidence_gaps"]), 33)


class AuxiliaryBusinessScope(unittest.TestCase):
    def test_biz11_golden_rejects_saly_same_business(self):
        from test_golden_dimensions_v1 import fixture as golden_fixture, build_golden, CATALOG
        a1, a2, signals = golden_fixture()
        for value in (a1, a2, signals):
            value["business"] = "SALY"
        out = build_golden(a1, a2, signals, catalog_path=CATALOG)
        self.assertEqual(out["blocking_codes"],
                         ["GOLDEN_BUSINESS_NOT_ENABLED_FOR_SKILL"])

    def test_biz12_preview_rejects_saly_same_business(self):
        from test_a2_a3_intake_preview_v1 import fixture as preview_fixture, prepare_preview
        a1, a2, signals, golden = preview_fixture()
        for value in (a1, a2, signals):
            value["business"] = "SALY"
        out = prepare_preview(a1, a2, signals, golden)
        self.assertEqual(out["blocking_codes"],
                         ["A2_A3_BUSINESS_NOT_ENABLED_FOR_SKILL"])

    def test_biz13_human_brief_rejects_saly_same_business(self):
        a1, a2, signals, golden = brief_fixture()
        for value in (a1, a2, signals):
            value["business"] = "SALY"
        out = BRIEF.build_brief(a1, a2, signals, golden)
        self.assertEqual(out["blocking_codes"],
                         ["INTENT_BUSINESS_NOT_ENABLED_FOR_SKILL"])


if __name__ == "__main__":
    unittest.main()
