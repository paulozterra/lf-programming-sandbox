#!/usr/bin/env python3
"""Offline adversarial tests of full vendored Worker integrity gate."""
from __future__ import annotations
import shutil
import tempfile
import unittest
from pathlib import Path
from verify_vendor import verify,VendorIntegrityError

SOURCE=Path(__file__).resolve().parents[2]/"vendor/programming-agent"

class VendorIntegrityTests(unittest.TestCase):
    def test_original_exact(self):
        row=verify(SOURCE)
        self.assertEqual(row["files"],72)
        self.assertEqual(row["total_bytes"],675415)

    def staged(self,mutation):
        with tempfile.TemporaryDirectory(prefix="lf-vendor-integrity-") as d:
            target=Path(d)/"vendor"
            shutil.copytree(SOURCE,target)
            mutation(target)
            with self.assertRaises(VendorIntegrityError):
                verify(target)

    def test_modified_file_blocked(self):
        def change(p):
            target=p/"src/programming_agent_runner/worker_spec.py"
            target.write_bytes(target.read_bytes()+b"\n# tampered\n")
        self.staged(change)

    def test_extra_file_blocked(self):
        self.staged(lambda p:(p/"src/extra.py").write_text("not approved"))

    def test_missing_file_blocked(self):
        self.staged(lambda p:(p/"src/programming_agent_runner/worker_spec.py").unlink())

    def test_symlink_blocked(self):
        self.staged(lambda p:(p/"src/alias.py").symlink_to("programming_agent_runner/worker_spec.py"))

if __name__=="__main__":
    unittest.main(verbosity=2)
