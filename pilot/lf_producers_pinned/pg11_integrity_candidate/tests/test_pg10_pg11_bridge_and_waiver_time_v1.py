"""PG10 -> PG11 positive typed bridge using REAL source producers; waiver clock tests.

No authentic Git diff, PG10 decision ledger, waiver registry or clock.
"""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate", "pg05_target_binding_candidate",
             "pg06_preflight_candidate", "pg07_worker_candidate",
             "pg08_build_candidate", "pg09_iteration_candidate",
             "pg10_conflict_candidate", "pg11_integrity_candidate"):
    for sub in ("tests", "tools"):
        folder = ROOT / name / sub
        if folder.is_dir():
            sys.path.insert(0, str(folder))

from test_pg10_decision_chain_v1 import build as real_pg10_chain
from test_pg11_integrity_chain_v1 import fixture as real_pg11_chain
from pg11_pg10_handoff_bridge_candidate_v1 import (
    bridge_pg10_c5_to_pg11_c1, PG10PG11BridgeBlocked)
from pg11_integrity_extension_candidate_v1 import (
    reject_waiver_expired_at, PG11IntegrityBlocked)


def inputs():
    pg10 = real_pg10_chain()
    pg11 = real_pg11_chain()
    final = pg10["upstream"]["pg08"]["final"]
    binding = {
        "run_ref": pg10["c5"]["run_ref"],
        "target_repo": final["target_repo"],
        "base_head_sha": final["base_head_sha"],
        "expected_head_sha": pg11["c1"]["expected_head_sha"],
    }
    return dict(pg10_c5=pg10["c5"], pg10_c4=pg10["c4"],
                pg09_c4=pg10["upstream"]["c4"],
                pg08_final=final, pg11_c1=pg11["c1"],
                run_binding=binding), pg10, pg11


def dated_waivers(pg11, expiry="2026-11-05T00:00:00Z"):
    rows = copy.deepcopy(pg11["waivers"])
    for row in rows:
        row["expires_at"] = expiry
    return rows


class PG10PG11AndWaiverTime(unittest.TestCase):
    def test_positive_from_real_pg10_c5_to_real_pg11_c1(self):
        params, pg10, pg11 = inputs()
        out = bridge_pg10_c5_to_pg11_c1(**params)
        self.assertEqual(out["source_pg10_c5_sha256"], pg10["c5"]["candidate_sha256"])
        self.assertEqual(out["source_pg11_c1_sha256"], pg11["c1"]["candidate_sha256"])
        self.assertEqual(out["source_pg08_final_sha256"],params["pg08_final"]["candidate_sha256"])
        self.assertEqual(out["source_pg09_c4_sha256"],params["pg09_c4"]["candidate_sha256"])
        self.assertEqual(out["run_ref"],pg10["c5"]["run_ref"])
        self.assertEqual(out["base_head_sha"],pg11["c1"]["expected_base_sha"])
        self.assertTrue(out["pg10_pg11_chain_shape_verified"])
        self.assertFalse(out["real_git_diff_readback_verified"])
        self.assertFalse(out["handoff_allowed"])
        self.assertFalse(out["production_authority"])

    def test_reject_wrong_run_ref(self):
        params, _, _ = inputs()
        params["run_binding"]["run_ref"] = "fixture://other-run"
        with self.assertRaisesRegex(PG10PG11BridgeBlocked,"RUN_DRIFT"):
            bridge_pg10_c5_to_pg11_c1(**params)

    def test_reject_base_head_drift(self):
        params, _, _ = inputs()
        params["run_binding"]["base_head_sha"] = "f" * 40
        with self.assertRaisesRegex(PG10PG11BridgeBlocked,"BASE_COMMIT_DRIFT"):
            bridge_pg10_c5_to_pg11_c1(**params)

    def test_reject_candidate_head_drift(self):
        params, _, _ = inputs()
        params["run_binding"]["expected_head_sha"] = "f" * 40
        with self.assertRaisesRegex(PG10PG11BridgeBlocked,"CANDIDATE_HEAD_DRIFT"):
            bridge_pg10_c5_to_pg11_c1(**params)

    def test_reject_foreign_pg10_c5_sha(self):
        params, _, _ = inputs()
        params["pg10_c5"]["source_candidate_sha256"]["pg10_c4"] = "f" * 64
        with self.assertRaises(PG10PG11BridgeBlocked):
            bridge_pg10_c5_to_pg11_c1(**params)

    def test_reject_injected_pg10_c5_authority_even_rehashed(self):
        params, _, _ = inputs()
        params["pg10_c5"]["production_authority"] = True
        from pg11_pg10_handoff_bridge_candidate_v1 import _digest
        c = params["pg10_c5"]
        c["candidate_sha256"] = _digest({k:v for k,v in c.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(PG10PG11BridgeBlocked,"SOURCE_AUTHORITY"):
            bridge_pg10_c5_to_pg11_c1(**params)

    def test_waiver_valid_one_second_before_expiry(self):
        _, _, pg11 = inputs()
        out = reject_waiver_expired_at(
            pg11_c3=pg11["c3"],
            waiver_observations=dated_waivers(pg11),
            evaluated_at="2026-11-04T23:59:59Z")
        self.assertTrue(out["expiry_compared_to_supplied_clock"])
        self.assertFalse(out["evaluation_clock_authenticated"])
        self.assertFalse(out["suppression_allowed"])

    def test_waiver_expired_exact_instant_blocks(self):
        _, _, pg11 = inputs()
        with self.assertRaisesRegex(PG11IntegrityBlocked,"EXPIRED_BY_TIMESTAMP"):
            reject_waiver_expired_at(pg11_c3=pg11["c3"],
                waiver_observations=dated_waivers(pg11),
                evaluated_at="2026-11-05T00:00:00Z")

    def test_waiver_expired_one_second_after_blocks(self):
        _, _, pg11 = inputs()
        with self.assertRaisesRegex(PG11IntegrityBlocked,"EXPIRED_BY_TIMESTAMP"):
            reject_waiver_expired_at(pg11_c3=pg11["c3"],
                waiver_observations=dated_waivers(pg11),
                evaluated_at="2026-11-05T00:00:01Z")

    def test_waiver_expiry_compares_timezones_as_instants(self):
        _, _, pg11 = inputs()
        with self.assertRaisesRegex(PG11IntegrityBlocked,"EXPIRED_BY_TIMESTAMP"):
            reject_waiver_expired_at(pg11_c3=pg11["c3"],
                waiver_observations=dated_waivers(pg11,"2026-11-05T00:00:00Z"),
                evaluated_at="2026-11-04T19:00:00-05:00")

    def test_waiver_missing_expiry_blocks(self):
        _, _, pg11 = inputs()
        with self.assertRaisesRegex(PG11IntegrityBlocked,"EXPIRY_MISSING"):
            reject_waiver_expired_at(pg11_c3=pg11["c3"],
                waiver_observations=copy.deepcopy(pg11["waivers"]),
                evaluated_at="2026-11-04T23:59:59Z")

    def test_naive_clock_is_rejected(self):
        _, _, pg11 = inputs()
        with self.assertRaisesRegex(PG11IntegrityBlocked,"EVALUATION_TIME_INVALID"):
            reject_waiver_expired_at(pg11_c3=pg11["c3"],
                waiver_observations=dated_waivers(pg11),
                evaluated_at="2026-11-04T23:59:59")


if __name__=="__main__":
    unittest.main()
