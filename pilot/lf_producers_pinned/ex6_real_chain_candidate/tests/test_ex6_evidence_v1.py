"""Tests for original EX6 GitHub Actions ZIP bytes. No synthetic PASS fixtures."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "ex6_real_world_v1.py"
spec = importlib.util.spec_from_file_location("ex6_real_world_v1", SCRIPT)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class EX6EvidenceTests(unittest.TestCase):
    def test_original_zip_checksums_and_public_status(self):
        obj = w.load_evidence()
        self.assertEqual(obj["status_reported"], "PASS")
        self.assertEqual(obj["changed_paths"], w.EXACT_PATHS)
        self.assertEqual(obj["api_calls_reported"], 0)
        self.assertEqual(obj["subscription_cost"], "NOT_EVALUATED")
        self.assertFalse(obj["receipt_authenticated"])
        self.assertFalse(obj["production_authority"])
        print("EX6_ZIP_BYTES_AND_PUBLIC_RECEIPTS_PASS")

    def test_exact_binary_git_objects(self):
        import hashlib
        for name in w.ARCHIVES:
            raw = (w.EVIDENCE / name).read_bytes()
            oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            self.assertEqual(oid, {
                "native-attempt-proof.zip": "b176e839dab6a526192bb2032e7a03e161667a0a",
                "native-visible-feedback-and-cost.zip": "ff719db0d05f037a845117810f69bcf95e4289fa",
                "native-verified-patch.zip": "81549f61cef3de587b136fba8af26a06ea6afd9e",
            }[name])

    def test_mutation_of_any_zip_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            for name in w.ARCHIVES:
                shutil.copyfile(w.EVIDENCE / name, target / name)
            for name in w.ARCHIVES:
                path = target / name
                raw = bytearray(path.read_bytes())
                raw[20] ^= 1
                path.write_bytes(raw)
                with self.assertRaisesRegex(w.EX6EvidenceBlocked, "EX6_ZIP_SHA256_DRIFT"):
                    w.load_evidence(target)
                shutil.copyfile(w.EVIDENCE / name, path)
        print("EX6_ORIGINAL_ZIP_ONE_BYTE_MUTATION_BLOCK")

    def test_no_stage_statuses_are_invented(self):
        rows = w.stage_matrix()
        self.assertEqual([r["stage"] for r in rows], [
            f"PG-{s:02d}" for s in range(4, 15)
        ])
        self.assertTrue(all(x["before"] == "NOT_RUN" and
                            x["after"] == "NOT_RUN" for x in rows))

    def test_reference_drift_denied(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)
            for name in w.ARCHIVES:
                shutil.copyfile(w.EVIDENCE / name, target / name)
            path = target / "native-attempt-proof.zip"
            path.unlink()
            with self.assertRaisesRegex(w.EX6EvidenceBlocked, "EX6_ZIP_MISSING"):
                w.load_evidence(target)


if __name__ == "__main__":
    unittest.main()
