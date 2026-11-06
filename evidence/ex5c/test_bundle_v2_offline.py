"""No model, no downloads: structural / adversarial v2 evidence checks."""
import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("v2",Path(__file__).with_name("build_bundle_v2.py"))
v2=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


class V2OfflineTests(unittest.TestCase):
    def test_tool_version_and_digest_pinned(self):
        self.assertEqual(v2.VERSION,"1.30.0")
        self.assertEqual(v2.GJF_SHA256,
                         "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a")
        self.assertTrue(v2.GJF_URL.startswith("https://github.com/google/google-java-format/releases/"))
    def test_v1_digest_never_changes(self):
        self.assertEqual(v2.V1_SHA,"436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b")
        self.assertNotEqual(v2.BASE,v2.HEAD)
    def test_raw_capture_is_byte_recalculable(self):
        with tempfile.TemporaryDirectory() as tmp:
            observed=v2.run(["python3","-c","import sys;sys.stdout.buffer.write(b'hello\\n');sys.stderr.buffer.write(b'warn\\n')"],
                            Path(tmp))
            for name,expected in (("stdout",b"hello\n"),("stderr",b"warn\n")):
                item=observed[name]
                self.assertEqual(base64.b64decode(item["base64"]),expected)
                self.assertEqual(item["sha256"],v2.sha(expected))
                self.assertEqual(item["bytes"],len(expected))
            self.assertEqual(observed["exit_code"],0)
    def test_compiler_and_formatter_options_are_explicit(self):
        source=Path(v2.__file__).read_text(encoding="utf-8")
        for arg in ("--dry-run","--set-exit-if-changed","-Xlint:all","--release",'"21"'):
            self.assertIn(arg,source)
        self.assertIn("V2_GOOGLE_JAVA_FORMAT_SHA_BLOCK",source)
        self.assertIn("V2_V1_PIN_INVALID",source)
        self.assertIn("V2_JAVAC_COMPILE_BLOCK",source)
    def test_no_override_auth_or_expired_model_inputs(self):
        source=Path(v2.__file__).read_text(encoding="utf-8")
        for field in ("production_authority","tool_execution_verified","receipt_authenticated","worker_invoked"):
            self.assertIn('"'+field+'": False',source)
        self.assertNotIn("holdout_private",source)

if __name__=="__main__":
    unittest.main()
