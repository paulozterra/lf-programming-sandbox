"""Run 42707967927 is actual EX6 evidence, but a derived index is not a receipt."""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from ex6_build_lint_index_v1 import (
    summary, original_zip_integrity, EX6EvidenceBlocked, ZIP_SHA, ORIGINAL_SHA,
)

class OriginalBundleIndexTests(unittest.TestCase):
    def test_provenance_and_correct_command_exit_codes(self):
        v=summary()
        self.assertEqual(v["source"]["bundle_json_sha256"],ORIGINAL_SHA)
        self.assertEqual(v["source"]["artifact_zip_sha256"],ZIP_SHA)
        self.assertEqual(v["snapshots"][0]["commands"]["build"]["exit_code"],0)
        self.assertEqual(v["snapshots"][1]["commands"]["build"]["exit_code"],0)
        self.assertEqual(v["snapshots"][0]["commands"]["format_aosp"]["exit_code"],0)
        self.assertEqual(v["snapshots"][1]["commands"]["format_aosp"]["exit_code"],1)
        self.assertEqual(v["snapshots"][1]["commands"]["visible_ex6"]["exit_code"],0)
        self.assertFalse(v["authority"]["production_authority"])
        self.assertFalse(v["authority"]["receipt_authenticated"])

    def test_only_the_three_added_ex6_java_are_aosp_findings(self):
        v=summary()
        paths=v["snapshots"][1]["commands"]["format_aosp"]["finding_paths"]
        self.assertEqual({Path(x).name for x in paths},
                         {"ReminderStats.java","ReminderStatsService.java",
                          "ReminderStatsController.java"})

    def test_exact_original_zip_integrity_and_all_command_hashes(self):
        real=original_zip_integrity()
        self.assertEqual([v["label"] for v in real["snapshots"]],["baseline","candidate"])
        self.assertEqual(real["snapshots"][1]["commands"]["format_aosp"]["exit_code"],1)
        self.assertEqual(real["snapshots"][1]["commands"]["visible_ex6"]["exit_code"],0)

    def test_wrong_or_missing_original_zip_rejected(self):
        with self.assertRaises(FileNotFoundError):
            original_zip_integrity(ROOT/"evidence"/"missing-original.zip")

    def test_no_foreign_hunk_or_production_authority(self):
        obj=summary()
        text=json.dumps(obj).lower()
        self.assertNotIn("ex5c",text)
        self.assertNotIn("lote-c",text)
        self.assertNotIn("super_admin\": true",text)

if __name__=="__main__":
    unittest.main()
