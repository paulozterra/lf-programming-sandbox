"""No network/model/holdout. Verify fixed public Git binding and hunk contract."""
import json
import re
import unittest
import urllib.request
from pathlib import Path
from build_bundle import (BASE, COMMIT, EXPECTED_PATCH, EXPECTED_SUBTREE,
                          REQS, git_oid, sha, StripAuthOnSignedArtifactRedirect)

HERE = Path(__file__).resolve().parent


class EvidenceBundleOfflineTests(unittest.TestCase):
    def test_signed_artifact_redirect_strips_bearer_credentials(self):
        source = urllib.request.Request(
            "https://api.github.com/repos/paulozterra/lf-programming-sandbox/actions/artifacts/1/zip",
            headers={"Authorization": "Bearer TEST_TOKEN", "Accept": "application/vnd.github+json"})
        redirected = StripAuthOnSignedArtifactRedirect().redirect_request(
            source, None, 302, "Found", {},
            "https://productionresultssa0.blob.core.windows.net/actions-results/sample?sig=redacted")
        self.assertIsNotNone(redirected)
        self.assertFalse(any(k.lower() == "authorization" for k in
                             list(redirected.headers) + list(redirected.unredirected_hdrs)))
        self.assertIn("sig=redacted", redirected.full_url)

    def test_redirect_refuses_untrusted_or_http_destinations(self):
        handler = StripAuthOnSignedArtifactRedirect()
        source = urllib.request.Request("https://api.github.com/runs/1",
                                        headers={"Authorization": "Bearer TEST_TOKEN"})
        for url in ("http://productionresultssa0.blob.core.windows.net/r",
                    "https://malicious.example.org/r"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(source, None, 302, "Found", {}, url)

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

    def test_no_mutable_authority_implicitly_granted(self):
        code = (HERE / "build_bundle.py").read_text(encoding="utf-8")
        for key in ("production_authority", "receipt_authenticated",
                    "tool_execution_verified", "worker_invoked"):
            self.assertIn('"' + key + '": False', code)
        self.assertIn("REAL_SANDBOX_UNAUTHENTICATED", code)

if __name__ == "__main__":
    unittest.main()
