"""Offline mandatory gate inspection; never invokes model or downloads jar."""
from __future__ import annotations
import pathlib
import unittest


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class FormatRemediationOfflineTests(unittest.TestCase):
    def test_generation_and_pr_gate_pin_same_formatter(self):
        src = (HERE / "format_remediation.py").read_text()
        checker = (HERE / "verify_format_remediation.py").read_text()
        for token in ("--aosp", "--replace", "-g:none",
                      "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"):
            self.assertIn(token, src)
        for token in ("--aosp", "CLASS_BYTE_COMPARISON_BLOCK",
                      "NOT_EXACT_AOSP_FORMAT", "old_hashes == new_hashes"):
            self.assertIn(token, checker)

    def test_compare_all_class_paths_bytewise_not_just_count(self):
        src = (HERE / "format_remediation.py").read_text()
        check = (HERE / "verify_format_remediation.py").read_text()
        self.assertIn('output[key] = hashlib.sha256(p.read_bytes()).hexdigest()', src)
        self.assertIn("before == after", src)
        self.assertIn("old_hashes == new_hashes", check)

    def test_src_only_and_original_git_pin(self):
        src = (HERE / "format_remediation.py").read_text()
        self.assertIn("e76b213cb2f367f787e0eba3bf8ff74136edd883", src)
        self.assertIn("JAVA_DRIFT_FROM_ORIGINAL_N", src)
        self.assertIn("CHANGED_PATHS_OUTSIDE_FORMAT", src)
        self.assertIn("NON_JAVA_FILE_MODIFIED", src)

    def test_workflows_do_not_call_model_or_auto_merge(self):
        manual = (ROOT / ".github/workflows/ex5c-format-remediation.yml").read_text()
        gate = (ROOT / ".github/workflows/ex5c-aosp-class-equivalence.yml").read_text()
        self.assertIn("workflow_dispatch", manual)
        self.assertIn("verify_format_remediation.py", gate)
        self.assertIn("format_remediation.py", manual)
        self.assertIn('git push origin "$branch"', manual)
        self.assertNotIn("gh pr merge", manual)
        self.assertNotIn("anthropic", manual.lower())


if __name__ == "__main__":
    unittest.main()
