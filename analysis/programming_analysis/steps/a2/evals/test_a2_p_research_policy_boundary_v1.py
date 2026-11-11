"""P0 tests for A2-P research preclassification: no unproven boolean cast.

Source-only specialized regressions. Existing canonical A2 policy is read
and used; this file never creates another depth classifier, calls A3 or SQL.
"""
import json
import unittest
from pathlib import Path

from test_a2 import RUN, RUN_A1, a1input, low
from test_unresolved_research_preview_v1 import impl as PREVIEW, make


class ResearchPreclassificationBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = RUN._json(RUN.CONTRACT_PATH)["classification"]["depth_policy"]

    def test_01_contradiction_is_canonical_boolean_only(self):
        self.assertEqual(self.policy["signals"]["material_contradiction"], "BOOLEAN")
        signals = low()["depth_signals"]
        signals["material_contradiction"] = "UNKNOWN"
        self.assertFalse(RUN._signals_valid(signals, self.policy))

    def test_02_do_not_reinterpret_unknown_as_false(self):
        signals = low()["depth_signals"]
        for value in ("UNKNOWN", None, 0, "false", ""):
            with self.subTest(value=value):
                signals["material_contradiction"] = value
                self.assertFalse(RUN._signals_valid(signals, self.policy))

    def test_03_truly_typed_boolean_is_not_authority(self):
        signals = low()["depth_signals"]
        for value in (False, True):
            with self.subTest(value=value):
                signals["material_contradiction"] = value
                self.assertTrue(RUN._signals_valid(signals, self.policy))
        # Type correctness is not evidence of source currentness or admission.
        a1 = RUN_A1.run(a1input())
        out = RUN.run(a1, low())
        self.assertFalse(out["source_attested"])
        self.assertFalse(out["independent_judge_verified"])
        self.assertIsNone(out["next_step"])

    def test_04_unknown_materiality_never_l1_even_with_false_contradiction(self):
        signals = low()["depth_signals"]
        signals["materiality_level"] = "UNKNOWN"
        level, _reasons = RUN._depth(signals, self.policy)
        self.assertEqual(level, "L2")

    def test_05_true_contradiction_priority_l3_with_other_unknown(self):
        signals = low()["depth_signals"]
        signals["materiality_level"] = "UNKNOWN"
        signals["authority_state"] = "UNKNOWN"
        signals["material_contradiction"] = True
        level, reasons = RUN._depth(signals, self.policy)
        self.assertEqual(level, "L3")
        self.assertIn("material_contradiction=true", reasons)

    def test_06_research_preview_preserves_open_a1_and_never_dispatches(self):
        result = PREVIEW.prepare(make("02"))
        self.assertEqual(result["status"], "RESEARCH_PLAN_ONLY")
        self.assertIsNone(result["a2_classification"])
        self.assertIsNone(result["a3_canonical_inputs"])
        self.assertFalse(result["a3_dispatch_allowed"])
        self.assertFalse(result["independent_judge_attested"])

    def test_07_negated_reuse_scope_stays_exact_and_non_dispatchable(self):
        result = PREVIEW.prepare(make("04"))
        self.assertEqual(result["research_plan"]["operation_hint"], "REUSE")
        self.assertEqual(result["research_plan"]["constraints"],
                         ["No crees otra pantalla"])
        self.assertFalse(result["a3_dispatch_allowed"])

    def test_08_material_open_a1_cannot_be_auto_promoted_to_a2(self):
        source = a1input()
        source["ambiguities"] = [{
            "code": "MATERIAL_PORTAL_MODE",
            "statement": "Sin definición de modo de acceso",
            "materiality": "MATERIAL",
            "resolution_state": "OPEN",
        }]
        a1 = RUN_A1.run(source)
        self.assertEqual(a1["status"], "REQUIRES_DECISION")
        output = RUN.run(a1, low())
        self.assertEqual(output["blocking_codes"],
                         ["A1_SEMANTIC_OR_STATUS_GATE_UNRESOLVED"])
        self.assertIsNone(output["classification"])
        self.assertIsNone(output["next_step"])

    def test_09_a3_canonical_inputs_remain_exactly_two(self):
        contract = json.loads((RUN.REPO /
            "sandbox/lf_contract_gate_test/programming_agent_four_stage/"
            "wave1_boundary_contracts/analysis_targeted_evidence_contract_v1.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(contract["input_contracts"], [
            "REQUEST_CONTEXT_V1", "ANALYSIS_CHANGE_CLASSIFICATION_V1"
        ])

    def test_10_saly_not_enabled_in_lf_candidate(self):
        a1 = RUN_A1.run(a1input())
        a1["business"] = "SALY"
        signal = low()
        signal["business"] = "SALY"
        out = RUN.run(a1, signal)
        self.assertEqual(out["blocking_codes"],
                         ["A2_BUSINESS_NOT_ENABLED_FOR_SKILL"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
