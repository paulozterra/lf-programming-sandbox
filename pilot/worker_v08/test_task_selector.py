#!/usr/bin/env python3
"""Offline exercise admission tests; no secret, oracle body or model invocation."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import task_selector as selector

class TaskSelectionTests(unittest.TestCase):
    def test_exercise1_pinned_holdout_and_scope(self):
        task=selector.select("exercise-1")
        self.assertEqual(task["holdout_sha256"],selector.EX1_SHA)
        self.assertEqual(task["write_path_patterns"],["standards/tools/checks.py"])

    def test_exercise2_registered_sha_and_scope_reach_offline_preflight(self):
        task=selector.select("exercise-2")
        self.assertEqual(task["spec_sha256"],selector.SPEC_SHA)
        self.assertEqual(task["holdout_sha256"],
            "44f75fa89fa6974cdcecc43bb2c2669d73eb4bf45fbebb3ec0f2308fce3551ee")
        self.assertEqual(task["write_path_patterns"],[
            "standards/tools/migrations.py","standards/tools/checks.py"])
        self.assertEqual(task["context_path_patterns"],[
            "standards/tools/MIGRATIONS_SPEC.md","standards/tools/checks.py",
            "standards/tests/test_migrations.py"])

    def test_exercise2_reusing_exercise1_holdout_is_blocked(self):
        saved=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
        tampered=copy.deepcopy(saved)
        tampered["tasks"]["exercise-2"]["holdout_sha256"]=selector.EX1_SHA
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"tasks.json"
            root.write_text(json.dumps(tampered),encoding="utf-8")
            with patch.object(selector,"CATALOG",root):
                with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_EXERCISE2_HOLDOUT_SHA_DRIFT"):
                    selector.select("exercise-2")

    def test_exercise3_spec_and_claude_holdout_sha_are_pinned(self):
        task=selector.select("exercise-3",require_holdout=False)
        self.assertEqual(task["spec_sha256"],selector.EX3_SPEC_SHA)
        self.assertEqual(task["holdout_sha256"],
                         "e721cd1f8ec1ca32cfee81bc84df1f38f0385587e9081ab2a3ced47beefc3dbc")
        self.assertEqual(task["write_path_patterns"],[
            "apps/time-service/pom.xml","apps/time-service/src/main/**"])
        self.assertEqual(task["context_path_patterns"],[
            "apps/time-service/TIME_SERVICE_SPEC.md",
            "apps/time-service/src/test/**","backend/pom.xml"])
        self.assertEqual(task["protected_path_patterns"],["apps/time-service/src/test/**"])
        self.assertEqual(task["acceptance_commands"][0]["argv"],[
            "mvn","-B","-q","-f","apps/time-service/pom.xml","verify"])
        self.assertEqual(task["acceptance_commands"][0]["timeout_seconds"],600)
        self.assertEqual(selector.select("exercise-3")["holdout_sha256"],task["holdout_sha256"])

    def test_exercise3_missing_or_malformed_digest_stays_fail_closed(self):
        saved=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
        for invalid in (None, "", "0" * 63, "NOT_A_DIGEST"):
            with self.subTest(invalid=invalid):
                tampered=copy.deepcopy(saved)
                tampered["tasks"]["exercise-3"]["holdout_sha256"]=invalid
                with tempfile.TemporaryDirectory() as temp:
                    path=Path(temp)/"tasks.json"
                    path.write_text(json.dumps(tampered),encoding="utf-8")
                    with patch.object(selector,"CATALOG",path):
                        with self.assertRaises(selector.TaskBlocked):
                            selector.select("exercise-3")

    def test_exercise3_cannot_reuse_any_previous_holdout(self):
        saved=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
        for old_sha in (selector.EX1_SHA,selector.EX2_SHA):
            tampered=copy.deepcopy(saved)
            tampered["tasks"]["exercise-3"]["holdout_sha256"]=old_sha
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp)/"tasks.json"
                root.write_text(json.dumps(tampered),encoding="utf-8")
                with patch.object(selector,"CATALOG",root):
                    with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_EXERCISE3_HOLDOUT_REUSED"):
                        selector.select("exercise-3",require_holdout=False)

    def test_exercise3_rejects_scope_drift_and_spec_tamper(self):
        saved=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
        changed=copy.deepcopy(saved)
        changed["tasks"]["exercise-3"]["write_path_patterns"].append("backend/**")
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"tasks.json"
            target.write_text(json.dumps(changed),encoding="utf-8")
            with patch.object(selector,"CATALOG",target):
                with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_EXERCISE3_SCOPE_DRIFT"):
                    selector.select("exercise-3",require_holdout=False)

    def test_unknown_exercise_blocked(self):
        with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_TASK_NOT_ALLOWED"):
            selector.select("exercise-4")

    def test_scope_or_spec_sha_tamper_blocked(self):
        saved=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
        tampered=copy.deepcopy(saved)
        tampered["tasks"]["exercise-2"]["write_path_patterns"].append("standards/tests/test_migrations.py")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"tasks.json"
            root.write_text(json.dumps(tampered),encoding="utf-8")
            with patch.object(selector,"CATALOG",root):
                with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_EXERCISE2_SCOPE_DRIFT"):
                    selector.select("exercise-2",require_holdout=False)

    def test_mismatched_oracle_sha_for_task1_blocked(self):
        saved=json.loads(selector.CATALOG.read_text(encoding="utf-8"))
        modified=copy.deepcopy(saved)
        modified["tasks"]["exercise-1"]["holdout_sha256"]="0"*64
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"tasks.json"
            root.write_text(json.dumps(modified),encoding="utf-8")
            with patch.object(selector,"CATALOG",root):
                with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_EXERCISE1_SCOPE_DRIFT"):
                    selector.select("exercise-1")

if __name__=="__main__":
    unittest.main(verbosity=2)
