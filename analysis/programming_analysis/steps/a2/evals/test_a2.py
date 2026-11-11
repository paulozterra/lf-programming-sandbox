"""Source-only tests for the canonical A2 policy and candidate A1->A2 seam."""
import copy
import importlib.util
import json
import unittest
from unittest.mock import patch
from pathlib import Path

STAGE = Path(__file__).resolve().parents[3]
A1 = STAGE / "steps/a1"
A2 = STAGE / "steps/a2"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUN = load(A2 / "validators/run.py", "a2_runner")
RUN_A1 = load(A1 / "validators/run.py", "a1_runner")
BRIDGE = load(STAGE / "adapters/a1_a2_candidate_bridge_v1.py", "a1_a2_bridge")


def a1input():
    return json.loads((A1 / "fixtures/valid_lf.json").read_text(encoding="utf-8"))


def low():
    return {
        "schema_version": "ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1",
        "business": "LF",
        "target_ref": "B2B-AUTH-001",
        "change_type": "REVIEW",
        "target_granularity": "SCREEN",
        "nested_parent_ref": None,
        "evidence_refs": ["capability://SAFE_CHANGE_ADMISSION@1.0.1"],
        "depth_signals": {
            "materiality_level": "LOW",
            "scope_bounded": "TRUE",
            "authority_state": "SUFFICIENT",
            "reversibility_state": "DEMONSTRATED",
            "currentness_decision": "CURRENT",
            "material_contradiction": False,
            "known_cross_scope_impact": False,
            "unresolved_material_signal_count": 0,
            "required_specialist_count": 0,
        },
    }


class AnalysisA2Candidate(unittest.TestCase):
    def setUp(self):
        self.a1 = RUN_A1.run(a1input())
        self.signals = low()

    def test_business_carried_from_a1(self):
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["business"], "LF")
        self.assertEqual(result["classification"]["schema_version"], "ANALYSIS_CHANGE_CLASSIFICATION_V1")
        self.assertNotIn("business", result["classification"])

    def test_business_missing_from_a2_blocked(self):
        del self.signals["business"]
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["blocking_codes"], ["A2_BUSINESS_REQUIRED"])
        self.assertIsNone(result["business"])

    def test_business_cross_project_blocked(self):
        self.signals["business"] = "SALY"
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["blocking_codes"], ["A2_BUSINESS_SCOPE_MISMATCH"])
        self.assertIsNone(result["next_step"])

    def test_business_declared_fact_conflict(self):
        self.a1["payload"]["provided_facts"].append({"fact_code": "TARGET_BUSINESS", "value": "SALY",
                                                       "source_ref": "user://analysis-a1-case-001"})
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["blocking_codes"], ["A2_BUSINESS_FACT_CONFLICT"])

    def test_business_without_scope_from_a1_blocked(self):
        self.a1["business"] = None
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["blocking_codes"], ["A1_BUSINESS_SCOPE_INVALID"])

    def test_01_l1_typed_source_only(self):
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["status"], "CANDIDATE_UNATTESTED")
        self.assertEqual(result["classification"]["depth_level"], "L1")
        self.assertEqual(result["classification"]["target_ref"], "B2B-AUTH-001")
        self.assertEqual(result["classification"]["schema_version"], "ANALYSIS_CHANGE_CLASSIFICATION_V1")
        self.assertIsNone(result["next_step"])
        self.assertFalse(result["source_attested"])

    def test_02_l2_unknown_material_no_l1(self):
        self.signals["depth_signals"]["materiality_level"] = "UNKNOWN"
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["classification"]["depth_level"], "L2")
        self.assertEqual(result["status"], "NEED_MORE_EVIDENCE")

    def test_03_high_materiality_l3_dominates(self):
        self.signals["depth_signals"]["materiality_level"] = "HIGH"
        self.signals["depth_signals"]["authority_state"] = "UNKNOWN"
        result = RUN.run(self.a1, self.signals)
        self.assertEqual(result["classification"]["depth_level"], "L3")

    def test_04_cross_scope_l3(self):
        self.signals["depth_signals"]["known_cross_scope_impact"] = True
        self.assertEqual(RUN.run(self.a1, self.signals)["classification"]["depth_level"], "L3")

    def test_05_insufficient_authority_l3_and_not_ready(self):
        self.signals["depth_signals"]["authority_state"] = "INSUFFICIENT"
        res = RUN.run(self.a1, self.signals)
        self.assertEqual(res["classification"]["depth_level"], "L3")
        self.assertNotEqual(res["status"], "READY")
        self.assertIsNone(res["next_step"])

    def test_06_unverified_reversibility_not_l1(self):
        self.signals["depth_signals"]["reversibility_state"] = "NOT_DEMONSTRATED"
        self.assertEqual(RUN.run(self.a1, self.signals)["classification"]["depth_level"], "L2")

    def test_07_missing_material_evidence(self):
        self.signals["depth_signals"]["unresolved_material_signal_count"] = 2
        res = RUN.run(self.a1, self.signals)
        self.assertEqual(res["classification"]["depth_level"], "L2")
        self.assertEqual(res["status"], "NEED_MORE_EVIDENCE")

    def test_08_stale_evidence_l3(self):
        self.signals["depth_signals"]["currentness_decision"] = "STALE_AFFECTED"
        self.assertEqual(RUN.run(self.a1, self.signals)["classification"]["depth_level"], "L3")

    def test_09_no_model_candidate_bypass(self):
        value = a1input()
        value["original_request"] = "Evalúa reglas de login B2B"
        value["input_mode"] = "SEMANTIC_CANDIDATE"
        semantic = RUN_A1.run(value)
        self.assertEqual(semantic["status"], "REQUIRES_SEMANTIC_REVIEW")
        self.assertEqual(RUN.run(semantic, self.signals)["status"], "BLOCKED")

    def test_10_no_forged_review_in_a1(self):
        forged = copy.deepcopy(self.a1)
        forged["semantic_judge_passed"] = True
        self.assertEqual(RUN.run(forged, self.signals)["blocking_codes"],
                         ["A1_OUTPUT_CONTRACT_INVALID"])

    def test_11_no_fake_target(self):
        self.signals["target_ref"] = "NOT-IN-A1"
        self.assertEqual(RUN.run(self.a1, self.signals)["blocking_codes"],
                         ["A2_TARGET_NOT_PRESENT_IN_A1"])

    def test_12_nested_target_needs_parent(self):
        self.signals["target_granularity"] = "CONTROL"
        self.assertEqual(RUN.run(self.a1, self.signals)["blocking_codes"],
                         ["A2_NESTED_PARENT_REQUIRED"])

    def test_13_parent_allowed(self):
        inp = a1input()
        inp["target_hints"].append("B2B-AUTH-PARENT")
        self.a1 = RUN_A1.run(inp)
        self.signals["target_granularity"] = "CONTROL"
        self.signals["nested_parent_ref"] = "B2B-AUTH-PARENT"
        self.assertEqual(RUN.run(self.a1, self.signals)["status"], "CANDIDATE_UNATTESTED")

    def test_13b_self_parent_blocked(self):
        self.signals["target_granularity"] = "CONTROL"
        self.signals["nested_parent_ref"] = self.signals["target_ref"]
        self.assertEqual(RUN.run(self.a1, self.signals)["blocking_codes"],
                         ["A2_NESTED_PARENT_NOT_IN_A1"])

    def test_14_all_signals_must_be_typed(self):
        del self.signals["depth_signals"]["authority_state"]
        self.assertEqual(RUN.run(self.a1, self.signals)["blocking_codes"],
                         ["A2_DEPTH_SIGNALS_NOT_TYPED"])

    def test_15_boolean_not_str_or_int(self):
        self.signals["depth_signals"]["material_contradiction"] = 1
        self.assertEqual(RUN.run(self.a1, self.signals)["status"], "BLOCKED")

    def test_16_no_empty_evidence_refs(self):
        self.signals["evidence_refs"] = []
        self.assertEqual(RUN.run(self.a1, self.signals)["blocking_codes"],
                         ["A2_EVIDENCE_REFS_REQUIRED"])

    def test_17_no_injection_of_execution_authority(self):
        self.signals["service_role"] = "trusted"
        self.assertEqual(RUN.run(self.a1, self.signals)["status"], "BLOCKED")

    def test_18_source_unchanged(self):
        left, right = copy.deepcopy(self.a1), copy.deepcopy(self.signals)
        RUN.run(self.a1, self.signals)
        self.assertEqual(self.a1, left)
        self.assertEqual(self.signals, right)

    def test_19_bridge_no_runtime_claim(self):
        result = BRIDGE.prepare_candidate(a1input(), low())
        self.assertEqual(result["a1_result"]["status"], "VALID_OUTPUT")
        self.assertEqual(result["a2_result"]["status"], "CANDIDATE_UNATTESTED")
        self.assertFalse(result["runtime_qualified"])
        self.assertEqual(result["external_invocation_count"], 0)
        self.assertIsNone(result["next_step"])
        self.assertTrue(result["no_write_performed"])

    def test_20_bridge_semantic_fails_closed(self):
        inp = a1input()
        inp["original_request"] = "Evalúa B2B"
        inp["input_mode"] = "SEMANTIC_CANDIDATE"
        result = BRIDGE.prepare_candidate(inp, low())
        self.assertEqual(result["a2_result"]["status"], "BLOCKED")

    def test_21_canonical_policy_really_used(self):
        policy = json.loads(RUN.CONTRACT_PATH.read_text(encoding="utf-8"))["classification"]["depth_policy"]
        for name in ("L1_requires_all", "L2_if_no_L3_and_any", "L3_if_any"):
            self.assertTrue(policy[name])
        self.assertTrue(RUN._signals_valid(low()["depth_signals"], policy))

    def test_22a_json_schemas_reconcile_typed_candidate(self):
        from jsonschema import Draft202012Validator
        signal_schema = json.loads((A2 / "schemas/input.schema.json").read_text(encoding="utf-8"))
        output_schema = json.loads((A2 / "schemas/output.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(Draft202012Validator(signal_schema).is_valid(low()))
        self.assertTrue(Draft202012Validator(output_schema).is_valid(RUN.run(self.a1, low())))
        self.assertTrue(Draft202012Validator(output_schema).is_valid(RUN.run(None, low())))

    def test_22b_count_zero_is_a_canonical_l1_predicate(self):
        out = RUN.run(self.a1, low())
        self.assertEqual(out["classification"]["depth_level"], "L1")
        self.assertIn("unresolved_material_signal_count=0", out["classification"]["depth_reason_predicates"])

    def test_22_required_specialist_no_fake_selection(self):
        self.signals["depth_signals"]["required_specialist_count"] = 1
        res = RUN.run(self.a1, self.signals)
        self.assertEqual(res["status"], "NEED_MORE_EVIDENCE")
        self.assertEqual(res["classification"]["specialist_resolution"], "PENDING")
        self.assertNotIn("specialist_code", res["classification"])



    def test_23_invalid_generated_output_is_blocked(self):
        # Simulate an internal classification bug: the output schema must reject it.
        with patch.object(RUN, "_depth", return_value=("L1", [])):
            res = RUN.run(self.a1, self.signals)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["blocking_codes"], ["A2_CANDIDATE_OUTPUT_SCHEMA_DRIFT"])
        self.assertIsNone(res["next_step"])
        self.assertFalse(res["source_attested"])

    def test_24_unknown_depth_fails_output_schema(self):
        with patch.object(RUN, "_depth", return_value=("L4", ["unexpected-depth"])):
            res = RUN.run(self.a1, self.signals)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["blocking_codes"], ["A2_CANDIDATE_OUTPUT_SCHEMA_DRIFT"])

    def test_25_malformed_blocked_envelope_raises(self):
        # Do not return a malformed BLOCKED envelope if the schema drifts.
        original = RUN._valid

        def reject_blocked_output(value, schema):
            if (isinstance(value, dict)
                    and value.get("schema_version") == RUN.SCHEMA
                    and value.get("status") == "BLOCKED"):
                return False
            return original(value, schema)

        with patch.object(RUN, "_valid", side_effect=reject_blocked_output):
            with self.assertRaisesRegex(ValueError, "A2_BLOCKED_OUTPUT_SCHEMA_DRIFT"):
                RUN.run(None, self.signals)


if __name__ == "__main__":
    unittest.main()
