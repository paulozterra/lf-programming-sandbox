"""EX6 real-receipt positive and negative PG09 C1 v2, original WORKER_API parity."""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path

TOOLS=Path(__file__).resolve().parents[1]/"tools"
sys.path.insert(0,str(TOOLS))
import ex6_real_chain_v1 as chain
import ex6_one_pass_v1 as one
from ex6_source_truth_v1 import source_truth, RUN_REF

class EX6PG09V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chain.install()
        import test_pg09_iteration_chain_v1 as t9
        from pg09_c1_iteration_cost_governor_candidate_v1 import prepare_pg09_c1 as original
        from pg09_c1_iteration_cost_governor_candidate_v2 import (
            prepare_pg09_c1 as revised, PG09NativeV2Blocked)
        cls.t9=t9
        cls.original=staticmethod(original)
        cls.revised=staticmethod(revised)
        cls.blocked=PG09NativeV2Blocked
        cls.truth=source_truth()
        cls.pg05=chain.make_pg05()
        cls.pg06=one.stage06(cls.pg05)
        cls.pg07=one.stage07(cls.pg06,cls.pg05,cls.truth)
        cls.pg09=one.stage09(cls.pg07,cls.truth)

    @classmethod
    def tearDownClass(cls):
        chain.uninstall()

    def evidence(self):
        return {"executor_mode":"GPT_NATIVE",
            "api_calls":self.truth["cost"]["api_calls"],
            "proposal_sha256":self.truth["proposal_sha256"],
            "expected_proposal_sha256":self.truth["status"]["proposal_sha256"],
            "tool_receipt_ref":None,
            "cost_receipt_ref":RUN_REF+"#cost.json",
            "status_receipt_ref":RUN_REF+"#status.json",
            "subscription_cost":self.truth["subscription_cost"]}

    def call(self,ev,obs=None):
        return self.revised(pg07_c1=self.pg07["c1"],pg07_c5=self.pg07["c5"],
           budget_policy=self.pg09["budget_fixture"],
           usage_observations=self.pg09["usage"] if obs is None else obs,
           native_execution_evidence=ev)

    def test_real_native_v1_requires_decision_and_v2_is_known_zero(self):
        self.assertEqual(self.pg09["c1"]["request_diagnostic"],"REQUIRES_DECISION")
        self.assertTrue(self.pg09["c1"]["missing_usage_requires_decision"])
        x=self.call(self.evidence())
        self.assertEqual(x["request_diagnostic"],"REPORTED_WITHIN_BUDGET_UNVERIFIED")
        self.assertFalse(x["missing_usage_requires_decision"])
        self.assertFalse(x["requires_decision_reported"])
        self.assertEqual(x["reported_request_known_cost"],"0")
        self.assertEqual(x["native_subscription_cost"],"NOT_EVALUATED")
        self.assertEqual(x["native_proposal_binding_sha256"],self.truth["proposal_sha256"])
        self.assertFalse(x["production_authority"])
        self.assertFalse(x["retry_authorized"])

    def test_positive_deterministic_tool_only_with_receipt(self):
        e=self.evidence()
        e.update(executor_mode="DETERMINISTIC_TOOL",proposal_sha256=None,
                 expected_proposal_sha256=None,tool_receipt_ref="ex6://source/tool/receipt")
        obs=copy.deepcopy(self.pg09["usage"])
        obs[0]["executor_mode"]="DETERMINISTIC_TOOL"
        x=self.call(e,obs)
        self.assertEqual(x["solutions"][0]["executor_mode_reported"],"DETERMINISTIC_TOOL")
        self.assertEqual(x["native_incremental_api_calls_reported"],0)

    def test_api_calls_positive_is_blocked(self):
        e=self.evidence();e["api_calls"]=1
        with self.assertRaisesRegex(self.blocked,"NONZERO_API_CALLS"):
            self.call(e)

    def test_missing_proposal_sha_is_blocked(self):
        e=self.evidence();e["proposal_sha256"]=None
        with self.assertRaisesRegex(self.blocked,"PROPOSAL_SHA_MISSING"):
            self.call(e)

    def test_wrong_proposal_sha_is_blocked(self):
        e=self.evidence();e["proposal_sha256"]="f"*64
        with self.assertRaisesRegex(self.blocked,"PROPOSAL_SHA_DRIFT"):
            self.call(e)

    def test_unknown_executor_mode_is_blocked(self):
        e=self.evidence();e["executor_mode"]="UNKNOWN"
        with self.assertRaisesRegex(self.blocked,"EXECUTOR_MODE_INVALID"):
            self.call(e)

    def test_missing_tool_receipt_is_blocked(self):
        e=self.evidence()
        e.update(executor_mode="DETERMINISTIC_TOOL",proposal_sha256=None,
                 expected_proposal_sha256=None,tool_receipt_ref=None)
        with self.assertRaisesRegex(self.blocked,"TOOL_RECEIPT_MISSING"):
            self.call(e)

    def test_gpt_native_with_calls_nonempty_is_blocked(self):
        obs=copy.deepcopy(self.pg09["usage"])
        obs[0]["calls"]=[{"call_ref":"ex6://invalid/unobserved"}]
        with self.assertRaisesRegex(self.blocked,"NATIVE_USAGE_CONFLICT"):
            self.call(self.evidence(),obs)

    def test_worker_api_v1_exact_equality(self):
        # Official unchanged synthetic setup is used ONLY for equivalence.
        test=self.t9.make_chain()
        original=self.original(pg07_c1=test["pg07"]["c1"],
            pg07_c5=test["pg07"]["c5"],budget_policy=self.t9.policy(),
            usage_observations=self.t9.cost_observations(test["pg07"]))
        revised=self.revised(pg07_c1=test["pg07"]["c1"],
            pg07_c5=test["pg07"]["c5"],budget_policy=self.t9.policy(),
            usage_observations=self.t9.cost_observations(test["pg07"]))
        self.assertEqual(json.dumps(original,sort_keys=True),
                         json.dumps(revised,sort_keys=True))
        self.assertEqual(original["candidate_sha256"],revised["candidate_sha256"])

if __name__=="__main__":
    unittest.main()
