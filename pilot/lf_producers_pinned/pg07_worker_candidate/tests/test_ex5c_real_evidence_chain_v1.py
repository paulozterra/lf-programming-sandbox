"""One real EX5C chain test, strictly fail-closed at first missing evidence.

Uses actual PG08_C1 producer and the existing PG13 Git mutation helper.
Does not convert synthetic PG06/PG08..14 fixtures into real results.

The real V2 baseline and candidate are available, but PG08 C2 reports new
blocking format findings. The original producers must preserve that outcome;
PG14 ACCEPT is not authorized.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pg07_worker_candidate/tools"))
sys.path.insert(0, str(ROOT / "pg13_freeze_candidate/tools"))
import pg07_real_worker_evidence_adapter_v1 as adapter
from pg13_ex5c_reconstructed_freeze_attack_v1 import local_freeze_and_attacks
from pg08_ex5c_v2_format_lint_adapter_v1 import (
    load_v2, V2_FIXTURE_PATH, V2_FIXTURE_SHA256, run_real_pg06_c4_pg08_c2
)

FIXTURE = ROOT / "pg07_worker_candidate/fixtures/lf-evidence-bundle-v1.json"
FIXED = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"


class EX5CRealChainTests(unittest.TestCase):
    def test_real_chain_producers_and_stop_on_missing_evidence(self):
        real = adapter.load_real_bundle(FIXTURE, FIXED)
        upstream = adapter.run_real_pg08_c1(real)
        self.assertEqual(upstream["pg08_c1"]["solutions"][0]["reported_build_outcome"],
                         "REPORTED_PASS_UNVERIFIED")
        self.assertEqual(upstream["pg08_c1"]["source_pg07_c6_sha256"],
                         upstream["pg07_c6"]["candidate_sha256"])
        self.assertFalse(upstream["pg08_c1"]["production_authority"])

        # Separate original PG09 C1 producer consumes the true public cost
        # and respects the actual one-of-one Worker attempt ceiling.
        cost = adapter.run_real_pg09_c1_to_c4(real)
        self.assertEqual(cost["pg09_c1"]["reported_request_known_cost"], "0.070022")
        self.assertEqual(cost["pg09_c1"]["request_diagnostic"], "REQUIRES_DECISION")
        self.assertEqual(cost["pg09_c4"]["solutions"][0]["reason_codes"], ["BUDGET_DECISION"])
        self.assertEqual(cost["pg09_c4"]["solutions"][0]["escalation_type"], "RETURN")
        self.assertFalse(cost["pg09_c4"]["retry_authorized"])
        self.assertFalse(cost["pg09_c4"]["production_authority"])
        self.assertEqual(cost["pg10_owner_decision_reference"]["decision_date"], "2026-11-06")

        # Independent real-byte Git subtree attack suite. We do NOT treat
        # this isolated result as a PG13 C1-C3 chain output or Testing admission.
        mutation = local_freeze_and_attacks()
        self.assertEqual(mutation["subtree_oid"], adapter.SUBTREE)
        self.assertEqual(mutation["blocked_mutation_count"], 5)
        self.assertFalse(mutation["production_authority"])

        # V2 is real and SHA-pinned. Original PG06 C4 and PG08 C2 MUST
        # classify new format findings as blockers, not silently promote PASS.
        v2 = load_v2(V2_FIXTURE_PATH, V2_FIXTURE_SHA256)
        lint = run_real_pg06_c4_pg08_c2(v1=real, v2=v2)
        self.assertEqual(lint["pg08_c2"]["solutions"][0]["reported_diagnostic"],
                         "REPORTED_NEW_BLOCKERS")
        self.assertGreater(len(lint["pg08_c2"]["solutions"][0]["reported_new_blockers"]), 0)
        self.assertFalse(lint["pg08_c2"]["pg08_c2_pass"])
        self.assertFalse(lint["pg08_c2"]["production_authority"])
        print("EX5C_PG08_C1_REAL_PRODUCER_SOURCE_ONLY_PASS")
        print("EX5C_PG06_C4_REAL_BASELINE_REPORTED_FAILURE")
        print("EX5C_PG08_C2_REAL_NEW_FORMAT_BLOCKERS=BLOCK")
        print("EX5C_PG09_C1_C4_REAL_COST_PRODUCERS_REQUIRES_DECISION_RETURN")
        print("EX5C_PG10_OWNER_DECISION_REFERENCE_SHA_PINNED")
        print("EX5C_PG13_REAL_SUBTREE_MUTATIONS_BLOCKED=5")
        print("EX5C_PG14_REAL_CHAIN_ADMISSION=BLOCKED")
        print("EX5C_PRODUCTION_AUTHORITY=FALSE")


if __name__ == "__main__":
    unittest.main()
