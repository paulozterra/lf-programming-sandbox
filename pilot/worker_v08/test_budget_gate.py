#!/usr/bin/env python3
"""Offline, fail-closed pilot pricing tests; no API calls, no secrets."""
from decimal import Decimal
import unittest
from budget_gate import quote,require,BudgetBlocked,MODEL_ATTEMPT_LIMITS

class BudgetTests(unittest.TestCase):
    def test_haiku_one_two_three_permitted(self):
        for attempts in (1,2,3):
            with self.subTest(attempts=attempts):
                result=require("claude-haiku-5-5",attempts)
                self.assertTrue(result["allowed"])
                self.assertEqual(Decimal(result["worst_case_usd"]),Decimal("0.010")*attempts)
                self.assertEqual(result["ceiling_usd"],"0.03")

    def test_sonnet_one_permitted(self):
        result=require("claude-sonnet-5-5",1)
        self.assertTrue(result["allowed"])
        self.assertEqual(Decimal(result["worst_case_usd"]),Decimal("0.200"))
        self.assertEqual(result["ceiling_usd"],"0.20")

    def test_sonnet_two_three_blocked(self):
        for attempts in (2,3):
            with self.subTest(attempts=attempts):
                with self.assertRaisesRegex(BudgetBlocked,"PILOT_MODEL_ATTEMPTS_EXCEEDED"):
                    require("claude-sonnet-5-5",attempts)

    def test_exercise3_only_sonnet_one_attempt_and_035_ceiling(self):
        result=require("claude-sonnet-5-5",1,task="exercise-3")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["max_output_tokens"],16000)
        self.assertEqual(result["ceiling_usd"],"0.35")
        self.assertEqual(Decimal(result["worst_case_usd"]),Decimal("0.280"))
        for model,attempts in (("claude-haiku-5-5",1),("claude-sonnet-5-5",2),
                               ("claude-sonnet-5-5",3)):
            with self.subTest(model=model,attempts=attempts):
                with self.assertRaises(BudgetBlocked):
                    require(model,attempts,task="exercise-3")
        self.assertEqual(require("claude-sonnet-5-5",1,task="exercise-2")["ceiling_usd"],"0.20")
        self.assertEqual(require("claude-haiku-5-5",1,task="exercise-1")["max_output_tokens"],8000)

    def test_haiku_four_impossible(self):
        self.assertEqual(MODEL_ATTEMPT_LIMITS["claude-haiku-5-5"],3)
        with self.assertRaisesRegex(BudgetBlocked,"PILOT_ATTEMPTS_FORBIDDEN"):
            require("claude-haiku-5-5",4)

    def test_invalid_attempts_and_model_block(self):
        for attempts in (0,-1,1.1,True,None):
            with self.subTest(attempts=attempts), self.assertRaises(BudgetBlocked):
                require("claude-haiku-5-5",attempts)
        with self.assertRaises(BudgetBlocked):
            require("claude-opus-5-5",1)

    def test_prices_are_versioned_and_exact(self):
        h=quote("claude-haiku-5-5",3)
        s=quote("claude-sonnet-5-5",1)
        self.assertEqual((h["input_usd_per_million"],h["output_usd_per_million"]),("0.10","0.50"))
        self.assertEqual((s["input_usd_per_million"],s["output_usd_per_million"]),("2.00","10.00"))
        self.assertTrue(h["pricing_version"])
        self.assertEqual(s["pricing_version"],h["pricing_version"])
        self.assertEqual((h["ceiling_usd"],s["ceiling_usd"]),("0.03","0.20"))
        self.assertTrue(s["estimate_not_provider_cap"])

if __name__=="__main__":
    unittest.main(verbosity=2)
