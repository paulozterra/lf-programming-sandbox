#!/usr/bin/env python3
"""Offline conservative budget tests; never imports/contacts a provider."""
from decimal import Decimal
import unittest
from budget_gate import quote,require,BudgetBlocked

class BudgetTests(unittest.TestCase):
    def test_haiku_one_to_three_permitted(self):
        for n in (1,2,3):
            with self.subTest(n=n):
                x=require("claude-haiku-5-5",n)
                self.assertEqual(Decimal(x["worst_case_usd"]),Decimal("0.010")*n)
                self.assertEqual(Decimal(x["ceiling_usd"]),Decimal("0.03"))
                self.assertTrue(x["allowed"])

    def test_sonnet_one_permitted(self):
        x=require("claude-sonnet-5-5",1)
        self.assertEqual(Decimal(x["worst_case_usd"]),Decimal("0.200"))
        self.assertEqual(Decimal(x["ceiling_usd"]),Decimal("0.20"))
        self.assertTrue(x["allowed"])

    def test_sonnet_two_and_three_blocked(self):
        for n in (2,3):
            with self.subTest(n=n), self.assertRaisesRegex(
                BudgetBlocked,"PILOT_MODEL_ATTEMPTS_EXCEEDED"
            ):
                require("claude-sonnet-5-5",n)

    def test_haiku_four_impossible(self):
        with self.assertRaisesRegex(BudgetBlocked,"PILOT_ATTEMPTS_FORBIDDEN"):
            require("claude-haiku-5-5",4)

    def test_invalid_attempts_and_model_block(self):
        for attempts in (0,4,-1,1.1,True,None):
            with self.subTest(attempts=attempts), self.assertRaises(BudgetBlocked):
                require("claude-haiku-5-5",attempts)
        with self.assertRaises(BudgetBlocked):
            require("claude-opus-5-5",1)

    def test_prices_are_versioned_and_exact(self):
        h=quote("claude-haiku-5-5",1)
        s=quote("claude-sonnet-5-5",1)
        self.assertEqual((h["input_usd_per_million"],h["output_usd_per_million"]),("0.10","0.50"))
        self.assertEqual((s["input_usd_per_million"],s["output_usd_per_million"]),("2.00","10.00"))
        self.assertTrue(s["pricing_version"])
        self.assertEqual(s["ceiling_usd"],"0.20")
        self.assertTrue(s["estimate_not_provider_cap"])

if __name__=="__main__":
    unittest.main(verbosity=2)
