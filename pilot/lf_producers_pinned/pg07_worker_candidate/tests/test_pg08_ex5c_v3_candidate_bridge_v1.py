"""Real N+1 bridge must BLOCK until v3 SHA+fixture exist; no synthetic PASS."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pg08_ex5c_v3_candidate_bridge_v1 as bridge
from pg07_ex5c_format_remediation_v3_adapter_v1 import EX5CV3Blocked


class N1PG08BridgeOfflineTests(unittest.TestCase):
    def test_no_v3_fixture_or_unpinned_sha_blocks_before_any_original_producer(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "missing-v3.json"
            with self.assertRaisesRegex(EX5CV3Blocked, "SHA_NOT_PINNED_BLOCK"):
                bridge.run_real_n1_pg06_pg08_c1_c2(p, "")
            with self.assertRaisesRegex(EX5CV3Blocked, "FIXTURE_NOT_FOUND_BLOCK"):
                bridge.run_real_n1_pg06_pg08_c1_c2(p, "0" * 64)

    def test_historical_N_is_fixed_not_an_invented_new_base(self):
        self.assertEqual(bridge.N, "e76b213cb2f367f787e0eba3bf8ff74136edd883")
        self.assertEqual(bridge.REPO, "paulozterra/lf-programming-sandbox")
        self.assertIn("FORMATTER_SHA", bridge.projected_pg08_c2.__code__.co_names)

    def test_owner_authority_never_implicit_in_source_projection(self):
        s = bridge.source(
            "PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1",
            source_pg05_exit_sha256="0" * 64, execution_allowed=False)
        self.assertFalse(s["production_authority"])
        self.assertFalse(s["handoff_allowed"])
        self.assertEqual(len(s["candidate_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
