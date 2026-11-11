"""Hermetic negative tests of the live-v0.1 judge policy gap.

Fixture mirrors 2026-11-09 Supabase READBACK, not server attestation.
Does not execute core SQL or an independent native model judge.
"""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "judge_policy_guard",
    Path(__file__).resolve().parents[1] / "adapters/judge_policy_gap_readback_v1.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def live_policy_fixture():
    return {
        "operation_code": "EJECUCION_SKILL_LF",
        "skill_code": "PROGRAMMING_ANALYSIS_LF",
        "step_id": "semantic_judge",
        "judge": {
            "judge_code": "JUDGE-EJECUCION-SKILL-LF-v0.1",
            "status": "ACTIVE_ENFORCEMENT",
            "pass_if": [], "fail_if": [],
        },
        "binding": {
            "judge_code": "JUDGE-EJECUCION-SKILL-LF-v0.1",
            "status": "ACTIVE_ENFORCEMENT",
            "required_evidence_keys": ["semantic_judge_result", "unsupported_claims"],
            "clean_result_value": "STEP_PASS_WITH_EVIDENCE",
            "blocked_result_value": "BLOCKED_STEP_NOT_CLEAN",
        },
    }


class JudgePolicyReadback(unittest.TestCase):
    def test_01_live_empty_positive_and_negative_is_blocked(self):
        out = module.inspect(live_policy_fixture())
        self.assertEqual(out["blocking_codes"],
                         ["SEMANTIC_JUDGE_POSITIVE_AND_NEGATIVE_RULES_MISSING"])
        self.assertFalse(out["runtime_qualified"])

    def test_02_positive_only_is_not_sufficient(self):
        x = live_policy_fixture()
        x["judge"]["pass_if"] = ["INDEPENDENT_REVIEW_PASS"]
        self.assertEqual(module.inspect(x)["status"], "BLOCKED")

    def test_03_negative_only_is_not_sufficient(self):
        x = live_policy_fixture()
        x["judge"]["fail_if"] = ["UNSUPPORTED_CLAIMS_PRESENT"]
        self.assertEqual(module.inspect(x)["status"], "BLOCKED")

    def test_04_nonempty_policy_is_still_not_runtime_admission(self):
        x = live_policy_fixture()
        x["judge"]["pass_if"] = ["INDEPENDENT_REVIEW_PASS"]
        x["judge"]["fail_if"] = ["UNSUPPORTED_CLAIMS_PRESENT"]
        out = module.inspect(x)
        self.assertEqual(out["status"], "POLICY_STRUCTURE_ONLY_UNATTESTED")
        self.assertFalse(out["a3_allowed"])
        self.assertFalse(out["independent_judge_verified"])
        self.assertFalse(out["source_attested"])

    def test_05_same_positive_and_negative_rule_is_blocked(self):
        x = live_policy_fixture()
        x["judge"]["pass_if"] = ["REVIEW_VERDICT"]
        x["judge"]["fail_if"] = ["REVIEW_VERDICT"]
        self.assertEqual(module.inspect(x)["blocking_codes"],
                         ["JUDGE_PASS_FAIL_PREDICATE_OVERLAP"])

    def test_06_wrong_operation_fails(self):
        x = live_policy_fixture()
        x["operation_code"] = "CREACION_SKILL_LF"
        self.assertEqual(module.inspect(x)["blocking_codes"],
                         ["JUDGE_OPERATION_OR_STEP_MISMATCH"])

    def test_07_wrong_skill_fails(self):
        x = live_policy_fixture()
        x["skill_code"] = "PROGRAMMING_ANALYSIS_SALY"
        self.assertEqual(module.inspect(x)["status"], "BLOCKED")

    def test_08_wrong_step_fails(self):
        x = live_policy_fixture()
        x["step_id"] = "report_output"
        self.assertEqual(module.inspect(x)["status"], "BLOCKED")

    def test_09_missing_unsupported_claims_binding_fails(self):
        x = live_policy_fixture()
        x["binding"]["required_evidence_keys"].pop()
        self.assertEqual(module.inspect(x)["blocking_codes"],
                         ["JUDGE_REQUIRED_EVIDENCE_INCOMPLETE"])

    def test_10_source_claim_is_not_accepted_from_snapshot(self):
        x = live_policy_fixture()
        x["source_attested"] = True
        x["judge"]["pass_if"] = ["INDEPENDENT_REVIEW_PASS"]
        x["judge"]["fail_if"] = ["UNSUPPORTED_CLAIMS_PRESENT"]
        self.assertFalse(module.inspect(x)["source_attested"])

    def test_11_wrong_binding_state_fails(self):
        x = live_policy_fixture()
        x["binding"]["status"] = "DISABLED"
        self.assertEqual(module.inspect(x)["status"], "BLOCKED")

    def test_12_nonarray_rule_fails(self):
        x = live_policy_fixture()
        x["judge"]["pass_if"] = "PASS"
        self.assertEqual(module.inspect(x)["blocking_codes"],
                         ["JUDGE_PREDICATE_SCHEMA_INVALID"])

    def test_13_duplicate_rule_fails(self):
        x = live_policy_fixture()
        x["judge"]["pass_if"] = ["PASS", "PASS"]
        x["judge"]["fail_if"] = ["FAIL"]
        self.assertEqual(module.inspect(x)["blocking_codes"],
                         ["JUDGE_PREDICATE_SCHEMA_INVALID"])

    def test_14_no_snapshot_fails(self):
        self.assertEqual(module.inspect(None)["blocking_codes"],
                         ["JUDGE_SOURCE_READBACK_REQUIRED"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
