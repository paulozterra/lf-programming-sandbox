"""No network/model/holdout. Verify fixed public Git binding and hunk contract."""
import json
import re
import unittest
from unittest.mock import patch
import tempfile
import os
from pathlib import Path
from build_bundle import (BASE, COMMIT, EXPECTED_PATCH, EXPECTED_SUBTREE,
                          REQS, git_oid, sha, load_run_artifacts, RUN_ID)

HERE = Path(__file__).resolve().parent


class EvidenceBundleOfflineTests(unittest.TestCase):
    def test_git_object_hashing_known_vectors(self):
        self.assertEqual(git_oid("blob", b"hello\n"),
                         "ce013625030ba8dba906f756967f9e9ca394464a")
        self.assertEqual(git_oid("blob", b""),
                         "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")

    def test_pinned_real_ids_are_full_hex(self):
        for value in (BASE, COMMIT, EXPECTED_SUBTREE):
            self.assertRegex(value, r"^[a-f0-9]{40}$")
        self.assertRegex(EXPECTED_PATCH, r"^[a-f0-9]{64}$")

    def test_all_manual_hunk_requirements_covered_once(self):
        data = json.loads((HERE / "hunk_requirements.json").read_text())
        self.assertEqual(data["base_commit"], BASE)
        self.assertEqual(data["candidate_commit"], COMMIT)
        self.assertEqual(len(data["mapping"]), 6)
        # Exact headers read from the verified Run C worker.patch artifact.
        self.assertEqual([r["header"] for r in data["mapping"]], [
            "@@ -4,6 +4,7 @@ import java.time.LocalTime;",
            "@@ -50,4 +51,24 @@ public class InMemoryReminderRepository implements ReminderRepository {",
            "@@ -8,10 +8,12 @@ import java.time.format.ResolverStyle;",
            "@@ -47,8 +49,9 @@ public class ReminderController {",
            "@@ -64,6 +67,20 @@ public class ReminderController {",
            "@@ -8,4 +8,6 @@ public interface ReminderRepository {",
        ])
        keys = {(r["path"], r["header"]) for r in data["mapping"]}
        self.assertEqual(len(keys), 6)
        seen = set()
        for row in data["mapping"]:
            self.assertTrue(row["path"].startswith(
                "apps/time-service/src/main/java/lf/sandbox/time/reminder/"))
            self.assertRegex(row["header"], r"^@@ -[0-9]+")
            self.assertTrue(row["requirements"])
            self.assertLessEqual(set(row["requirements"]), REQS)
            seen.update(row["requirements"])
        self.assertEqual(seen, REQS)

    def test_binary_artifacts_require_local_explicit_gh_download(self):
        # Regression for Run #42294437650: fail closed without local downloads.
        with tempfile.TemporaryDirectory() as root:
            api_root = "https://api.github.com/repos/paulozterra/lf-programming-sandbox"
            def fake_api(url, token):
                if url == api_root + "/actions/runs/" + str(RUN_ID):
                    return json.dumps({
                        "head_sha": "5b5f860f2c142c9741a4dfad93f25bf4914c710d",
                        "conclusion": "success", "run_attempt": 1
                    }).encode()
                if url.endswith("/artifacts?per_page=100"):
                    return json.dumps({"artifacts": [
                        {"name": "worker-pilot-receipts-cost-logs", "id": 13537565729, "expired": False},
                        {"name": "worker-pilot-verified-patch", "id": 13537475831, "expired": False}
                    ]}).encode()
                raise AssertionError("Binary redirect/network request forbidden: " + url)
            with patch.dict(os.environ, {"GH_TOKEN": "offline-test-token",
                                         "LF_EVIDENCE_ARTIFACT_DIR": root}):
                with patch("build_bundle.api_bytes", side_effect=fake_api):
                    with self.assertRaisesRegex(ValueError, "LOCAL_ARTIFACT_MISSING"):
                        load_run_artifacts()

    def test_no_mutable_authority_implicitly_granted(self):
        code = (HERE / "build_bundle.py").read_text(encoding="utf-8")
        for key in ("production_authority", "receipt_authenticated",
                    "tool_execution_verified", "worker_invoked"):
            self.assertIn('"' + key + '": False', code)
        self.assertIn("REAL_SANDBOX_UNAUTHENTICATED", code)

if __name__ == "__main__":
    unittest.main()
