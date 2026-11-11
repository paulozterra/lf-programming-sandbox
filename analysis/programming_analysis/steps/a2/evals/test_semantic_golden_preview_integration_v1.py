"""Regression cases for real-language A1 -> A2 -> Golden -> preview.

Source-only candidate. These tests do not attest the model reviewer, sources,
A3 dispatch, or a governed RUN. Execute against the exact PR HEAD.
"""
from __future__ import annotations

import copy
import unittest

from test_business_semantic_scope_l1_l2_20261108 import (
    RAW, TARGET, producer, review_fixture, RUN_A1, RUN, low,
)
from test_golden_handoff_v03 import run as golden_run
from test_a2_a3_intake_preview_v1 import prepare_preview, fixture as structured_fixture


def semantic_fixture():
    a1 = RUN_A1.run(
        RAW, business="LF", semantic_producer=producer,
        semantic_reviewer=review_fixture,
    )
    assert a1["status"] == "VALID_OUTPUT", a1
    signals = low()
    signals["change_type"] = "IMPLEMENT"
    signals["target_ref"] = TARGET
    a2 = RUN.run(a1, signals)
    assert a2["status"] in ("CANDIDATE_UNATTESTED", "NEED_MORE_EVIDENCE"), a2
    return a1, a2, signals


class SemanticGoldenPreviewIntegration(unittest.TestCase):
    def test_semantic_a1_golden_12_59_prepared_unattested(self):
        a1, a2, signals = semantic_fixture()
        golden = golden_run(a1, a2, signals)
        self.assertEqual(golden["schema_version"], "A2_GOLDEN_HANDOFF_PROPOSAL_V0_3")
        self.assertEqual(len(golden["dimension_results"]), 12)
        self.assertEqual(sum(len(d["elements"]) for d in golden["dimension_results"]), 59)
        self.assertTrue(all(
            e["fulfilment"] == "PENDING_EVIDENCE"
            for d in golden["dimension_results"] for e in d["elements"]
        ))
        self.assertFalse(golden["producer_assertions"]["source_attested"])
        self.assertFalse(golden["producer_assertions"]["independent_judge_verified"])

    def test_semantic_a1_preview_preserves_scope_no_a3(self):
        a1, a2, signals = semantic_fixture()
        golden = golden_run(a1, a2, signals)
        preview = prepare_preview(a1, a2, signals, golden)
        self.assertEqual(preview["status"], "PREVIEW_PREPARED_NOT_DISPATCHABLE")
        self.assertFalse(preview["a3_allowed"])
        self.assertFalse(preview["source_authenticated"])
        self.assertFalse(preview["judge_verified"])
        self.assertEqual(
            preview["human_intent_brief"]["scope_constraints_declared"],
            a1["payload"]["constraints"],
        )
        self.assertEqual(set(preview["a3_input_preview"]), {
            "REQUEST_CONTEXT_V1", "ANALYSIS_CHANGE_CLASSIFICATION_V1",
        })

    def test_semantic_loss_of_negation_blocks_golden(self):
        a1, a2, signals = semantic_fixture()
        a1["payload"]["constraints"].pop()
        result = golden_run(a1, a2, signals)
        self.assertEqual(result["blocking_codes"],
                         ["GOLDEN_A1_SEMANTIC_BINDING_INVALID"])

    def test_semantic_loss_of_negation_blocks_preview(self):
        a1, a2, signals = semantic_fixture()
        golden = golden_run(a1, a2, signals)
        a1["payload"]["constraints"].pop()
        result = prepare_preview(a1, a2, signals, golden)
        self.assertEqual(result["blocking_codes"],
                         ["A2_A3_SEMANTIC_BINDING_INVALID"])

    def test_forged_judge_attestation_blocks_semantic_golden(self):
        a1, a2, signals = semantic_fixture()
        a1["semantic_review_identity_verified"] = True
        result = golden_run(a1, a2, signals)
        self.assertEqual(result["blocking_codes"],
                         ["GOLDEN_A1_SEMANTIC_BINDING_INVALID"])

    def test_materially_unresolved_a1_stays_blocked(self):
        a1, a2, signals = semantic_fixture()
        a1["status"] = "REQUIRES_DECISION"
        self.assertEqual(
            golden_run(a1, a2, signals)["blocking_codes"],
            ["GOLDEN_A1_SEMANTIC_GATE_NOT_RESOLVED"],
        )

    def test_existing_prestructured_path_regression(self):
        a1, a2, signals, golden = structured_fixture()
        result = prepare_preview(a1, a2, signals, golden)
        self.assertEqual(result["status"], "PREVIEW_PREPARED_NOT_DISPATCHABLE")
        self.assertFalse(result["a3_allowed"])

    def test_saly_forgery_still_blocks(self):
        a1, a2, signals = semantic_fixture()
        for row in (a1, a2, signals):
            row["business"] = "SALY"
        result = golden_run(a1, a2, signals)
        self.assertEqual(result["blocking_codes"],
                         ["GOLDEN_A1_SEMANTIC_BINDING_INVALID"])

    def test_signal_mutation_still_blocks(self):
        a1, a2, signals = semantic_fixture()
        signals["depth_signals"]["materiality_level"] = "HIGH"
        result = golden_run(a1, a2, signals)
        self.assertEqual(result["blocking_codes"],
                         ["GOLDEN_A1_SEMANTIC_BINDING_INVALID"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
