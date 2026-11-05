#!/usr/bin/env python3
"""Exercise routing preflight unit tests. NO REAL holdout bytes and NO model.

The only mocked value is the private oracle byte digest. These tests assert the
routing/legacy-manifest guards, not that Claude's secret content has been seen.
"""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_live_pilot as pilot
from task_selector import EX1_SHA, EX2_SHA


class PilotPreflightRoutingTests(unittest.TestCase):
    def verify_route(self, name, simulated_sha, expected_block=None):
        with tempfile.TemporaryDirectory(prefix="lf-pilot-routing-unit-") as tmp:
            private=Path(tmp)
            # Placeholder exercises routing only, NOT a holdout or an oracle.
            (private/"holdout.oracle.json").write_bytes(b"NOT_A_REAL_ORACLE")
            env={"PILOT_PROVIDER":"anthropic","PILOT_MODEL":"claude-haiku-5-5",
                 "PILOT_MAX_ATTEMPTS":"1","PILOT_TASK":name,"GITHUB_SHA":""}
            with (patch.dict(os.environ,env),
                  patch.object(pilot,"verify_adapter_snapshot"),
                  patch("verify_vendor.verify"),
                  patch.object(pilot.subprocess,"run",return_value=SimpleNamespace(stdout="")),
                  patch.object(pilot,"digest",return_value=simulated_sha)):
                if expected_block:
                    with self.assertRaisesRegex(pilot.PilotBlocked,expected_block):
                        pilot.validate_common(private)
                else:
                    pilot.validate_common(private)

    def test_exercise1_legacy_manifest_still_passes_preflight_routing(self):
        self.verify_route("exercise-1",EX1_SHA)

    def test_exercise2_registered_sha_reaches_preflight_routing(self):
        self.verify_route("exercise-2",EX2_SHA)

    def test_exercise2_given_exercise1_digest_blocks(self):
        self.verify_route("exercise-2",EX1_SHA,"HIDDEN_HOLDOUT_SHA_MISMATCH")


if __name__=="__main__":
    unittest.main(verbosity=2)
