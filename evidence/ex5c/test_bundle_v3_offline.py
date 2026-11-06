"""V3 structural regressions, no private data, no model or external downloads."""
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class V3BundleOfflineTests(unittest.TestCase):
    def test_historical_evidence_pins_preserved(self):
        s = (HERE / "build_bundle_v3.py").read_text()
        self.assertIn("436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b", s)
        self.assertIn("0988de2e39f5139596d05c3cbfcbe8c8998c753cdb009414e5b38da65172217b", s)
        self.assertIn("FORMAT_REMEDIATION", s)
        self.assertIn("V3_OVERWRITE_BLOCK", s)

    def test_aosp_compiled_bytes_and_real_smoke_are_required(self):
        s = (HERE / "build_bundle_v3.py").read_text()
        for needle in ("--aosp", "N1_NOT_EXACT_AOSP_TRANSFORM",
                       "N1_CLASS_BYTES_CHANGED", "-g:none",
                       "N1_MAVEN_VERIFY_BLOCK", "http = smoke()"):
            self.assertIn(needle, s)
        self.assertIn('"production_authority": False', s)
        self.assertIn('"tool_execution_verified": False', s)
        self.assertIn('"receipt_authenticated": False', s)

    def test_v3_is_separate_manual_workflow_mode(self):
        s = (ROOT / ".github/workflows/evidence-bundle.yml").read_text()
        self.assertIn("evidence_version == 'v3'", s)
        self.assertIn("lf-evidence-bundle-v3.sha256", s)
        self.assertIn("ex5c-real-sandbox-format-remediation-v3", s)
        self.assertNotIn("gh pr merge", s)


if __name__ == "__main__":
    unittest.main()
