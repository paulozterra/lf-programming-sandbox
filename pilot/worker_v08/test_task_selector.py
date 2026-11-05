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

    def test_exercise2_spec_available_but_holdout_unregistered(self):
        task=selector.select("exercise-2",require_holdout=False)
        self.assertEqual(task["spec_sha256"],selector.SPEC_SHA)
        self.assertIsNone(task["holdout_sha256"])
        self.assertEqual(task["write_path_patterns"],[
            "standards/tools/migrations.py","standards/tools/checks.py"])
        with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_HOLDOUT_SHA_UNREGISTERED:exercise-2"):
            selector.select("exercise-2")

    def test_unknown_exercise_blocked(self):
        with self.assertRaisesRegex(selector.TaskBlocked,"PILOT_TASK_NOT_ALLOWED"):
            selector.select("exercise-3")

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
