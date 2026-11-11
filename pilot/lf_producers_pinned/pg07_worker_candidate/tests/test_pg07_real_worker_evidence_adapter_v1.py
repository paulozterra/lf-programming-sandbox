"""Standalone adversarial unit tests. Real fixture is NOT fabricated.

The integration test on the exact real bundle must be added only after the
sandbox workflow generates its SHA-pinned JSON. No real chain PASS claimed here.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pg07_real_worker_evidence_adapter_v1 as a


def rec(raw: bytes):
    return {"base64": base64.b64encode(raw).decode(), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def command():
    return {"argv": ["mvn", "-B", "-f", "apps/time-service/pom.xml", "verify"],
            "stdout": rec(b"BUILD SUCCESS\n"), "stderr": rec(b""),
            "result": "PASS", "exit_code": 0}


def smoke():
    statuses = [("healthcheck", 200), ("create", 201), ("search", 200),
                ("delete", 204), ("get_after_delete", 404)]
    return {"stdout": rec(b"server started"), "stderr": rec(b""),
            "steps": [{"step": name, "status": status, "body_base64": rec(b"ok")["base64"],
                       "body_sha256": a.digest(b"ok"), "body_bytes": 2}
                      for name, status in statuses]}


def sample_patch():
    path = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
    files = ["InMemoryReminderRepository.java", "ReminderController.java",
             "ReminderRepository.java"]
    fragments = []
    rows = []
    for name, count in zip(files, (2, 3, 1)):
        fragments.append("diff --git a/" + path + name + " b/" + path + name + "\n")
        for i in range(count):
            h = "@@ -" + str(i+1) + ",1 +" + str(i+1) + ",1 @@\n"
            raw = (h + "-old\n+new\n").encode()
            fragments.append(raw.decode())
            rows.append({"path": path + name, "header": h.strip(),
                         "sha256": a.digest(raw), "bytes": len(raw),
                         "content_base64": base64.b64encode(raw).decode(),
                         "requirements": ["REM-C" + str(len(rows) + 1)] +
                         (["REM-C7"] if len(rows) == 5 else [])})
    full = "".join(fragments).encode()
    return {"text_base64": base64.b64encode(full).decode(),
            "sha256": a.digest(full), "worker_patch_sha256": a.digest(full),
            "bytes": len(full), "hunks": rows}


FIXTURE_SHA256 = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures/lf-evidence-bundle-v1.json"


class RealEvidenceBundleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(FIXTURE_PATH.is_file())
        self.original = a.load_real_bundle(FIXTURE_PATH, FIXTURE_SHA256)

    def test_real_bundle_all_bytes_recomputed_and_non_authoritative(self):
        self.assertEqual(self.original["git"]["commit"], a.COMMIT)
        self.assertEqual(a.rebuild_subtree(self.original["files"]), a.SUBTREE)
        self.assertEqual(len(a.check_patch(self.original)), 6)
        self.assertEqual(a.check_execution(self.original)["maven"]["exit_code"], 0)
        self.assertEqual(a.pg08_c1_observations(self.original)[0]["diff_sha256"], a.PATCH_SHA)
        self.assertEqual(a.pg09_usage(self.original)[0]["calls"][0]["reported_cost"], "0.070022")
        self.assertFalse(self.original["production_authority"])
        self.assertFalse(self.original["tool_execution_verified"])
        self.assertFalse(self.original["receipt_authenticated"])
        self.assertFalse(self.original["worker_invoked"])

    def test_real_pg08_c1_producer_receives_recomputed_stdout_stderr(self):
        """The first actual PG08 producer, NOT a synthetic C1 stand-in."""
        output = a.run_real_pg08_c1(self.original)
        c1 = output["pg08_c1"]
        self.assertEqual(c1["source_pg07_c6_sha256"],
                         output["pg07_c6"]["candidate_sha256"])
        self.assertEqual(c1["solutions"][0]["diff_sha256_reported"], a.PATCH_SHA)
        self.assertEqual(c1["solutions"][0]["reported_build_outcome"],
                         "REPORTED_PASS_UNVERIFIED")
        self.assertFalse(c1["production_authority"])
        self.assertEqual(output["evidence_kind"], "REAL_SANDBOX_UNAUTHENTICATED")

    def test_real_chain_blocks_at_missing_pg08_c2_lint_baseline(self):
        """C1 succeeds from real bytes, but C2 must NOT use the PG06 synthetic fixture."""
        c1 = a.run_real_pg08_c1(self.original)
        self.assertIn("pg08_c1", c1)
        with self.assertRaisesRegex(a.RealEvidenceBlocked,
                                    "PG08_C2_REAL_BASELINE_AND_LINT_EVIDENCE_MISSING_BLOCK"):
            a.require_pg08_c2_real_source(self.original)

    def test_real_pg08_c1_rejects_unverified_maven_exit(self):
        bad = copy.deepcopy(self.original)
        bad["execution"]["maven"]["exit_code"] = 11
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "PG08_EXIT_CODE_RESULT_BLOCK"):
            a.run_real_pg08_c1(bad)

    def test_changed_byte_of_pinned_fixture_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bundle.json"
            raw = bytearray(FIXTURE_PATH.read_bytes())
            raw[len(raw) // 2] ^= 1
            p.write_bytes(raw)
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "SHA_CHANGED"):
                a.load_real_bundle(p, FIXTURE_SHA256)

    def test_rehashed_authority_injection_still_blocked(self):
        value = copy.deepcopy(self.original)
        value["production_authority"] = True
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "AUTHORITY_INJECTION"):
            a.check_authority(value)

    def test_real_execution_stdout_and_stderr_tamper_block(self):
        for channel in ("stdout", "stderr"):
            for kind in ("hash_only", "body_only"):
                x = copy.deepcopy(self.original)
                stream = x["execution"]["maven"][channel]
                if kind == "hash_only":
                    stream["sha256"] = "0" * 64
                else:
                    stream["base64"] = base64.b64encode(b"ALTERED").decode("ascii")
                with self.subTest(channel=channel, kind=kind), self.assertRaisesRegex(
                    a.RealEvidenceBlocked, "PG08_"
                ):
                    a.check_execution(x)

    def test_real_pg09_c1_source_only_cost_and_attempt_limit(self):
        projection = a.run_real_pg09_c1(self.original)
        c1 = projection["pg09_c1"]
        self.assertEqual(c1["reported_request_known_cost"], "0.070022")
        # Existing PG09 producer preserves exhaustion of the real 1-of-1 limit.
        self.assertEqual(c1["request_diagnostic"], "REQUIRES_DECISION")
        self.assertTrue(c1["iteration_limit_reached_reported"])
        self.assertFalse(c1["production_authority"])

    def test_real_patch_and_hunk_tamper_block(self):
        x = copy.deepcopy(self.original)
        x["patch"]["hunks"][0]["requirements"] = []
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "HUNK_REQUIREMENT"):
            a.check_patch(x)
        x = copy.deepcopy(self.original)
        x["patch"]["hunks"][0]["content_base64"] = base64.b64encode(b"modified").decode()
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "HUNK_SHA"):
            a.check_patch(x)

    def test_real_git_blob_and_commit_mutations_block(self):
        x = copy.deepcopy(self.original)
        x["files"][0]["content_base64"] = base64.b64encode(b"tampered").decode()
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "PG12_BLOB_OID"):
            a.rebuild_subtree(x["files"])
        x = copy.deepcopy(self.original)
        x["git"]["raw_commit_base64"] = base64.b64encode(b"tampered").decode()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "altered.json"
            raw = (json.dumps(x) + "\n").encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "PG12_GIT_COMMIT"):
                a.load_real_bundle(p, a.digest(raw))

    def test_real_subtree_oid_altered_blocks(self):
        with patch.object(a, "SUBTREE", "f" * 40):
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "PG12_SUBTREE_OID_BLOCK"):
                a.rebuild_subtree(self.original["files"])

    def test_real_package_rehash_cannot_bypass_pinned_sha(self):
        value = copy.deepcopy(self.original)
        value["git"]["tree"] = "f" * 40
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "new_bundle.json"
            raw = (json.dumps(value, sort_keys=True) + "\n").encode()
            path.write_bytes(raw)
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "SHA_CHANGED"):
                a.load_real_bundle(path, FIXTURE_SHA256)

    def test_real_cost_boundary_and_author_review(self):
        self.assertEqual(a.cost_verdict("0.28"), "WARN")
        self.assertEqual(a.cost_verdict("0.35"), "REQUIRES_DECISION")
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "OVER_CAP"):
            a.cost_verdict("0.350001")
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "SELF_REVIEW"):
            a.independent_review_label("worker:claude-sonnet-5-5", "worker:claude-sonnet-5-5")


class RealEvidenceNegativeTests(unittest.TestCase):
    def test_missing_fixture_or_sha_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "not-created.json"
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "SHA_NOT_PINNED"):
                a.load_real_bundle(p, "")
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "FIXTURE_MISSING"):
                a.load_real_bundle(p, "0" * 64)

    def test_replaced_package_sha_blocks_before_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bundle.json"
            p.write_bytes(b'{"fake":"replacement"}')
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "SHA_CHANGED"):
                a.load_real_bundle(p, "0" * 64)

    def test_injected_authority_blocks_even_when_json_rehashed(self):
        content = {"production_authority": True, "nested": [{"receipt_authenticated": False}]}
        # Rehashing the packet cannot make True authority acceptable.
        self.assertEqual(len(a.digest(json.dumps(content).encode())), 64)
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "AUTHORITY_INJECTION"):
            a.check_authority(content)

    def test_command_stdout_digest_tamper_and_inverse_block(self):
        base = {"maven": command(), "smoke": smoke()}
        for kind in ("hash_only", "bytes_only", "exit_pass"):
            x = copy.deepcopy(base)
            if kind == "hash_only":
                x["maven"]["stdout"]["sha256"] = "f" * 64
            if kind == "bytes_only":
                x["maven"]["stdout"]["base64"] = base64.b64encode(b"DIFFERENT").decode()
            else:
                x["maven"]["exit_code"] = 1
            with self.subTest(kind=kind), self.assertRaises(a.RealEvidenceBlocked):
                a.check_execution({"execution": x})

    def test_cost_warning_decision_and_over_cap_block(self):
        self.assertEqual(a.cost_verdict("0.070022"), "REPORTED_WITHIN_BUDGET_UNVERIFIED")
        self.assertEqual(a.cost_verdict("0.28"), "WARN")
        self.assertEqual(a.cost_verdict("0.35"), "REQUIRES_DECISION")
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "OVER_CAP"):
            a.cost_verdict("0.350001")

    def test_changed_patch_byte_blocks(self):
        obj = sample_patch()
        with patch.object(a, "PATCH_SHA", obj["sha256"]):
            original = copy.deepcopy(obj)
            altered = bytearray(base64.b64decode(original["text_base64"]))
            altered[-1] = ord("x")
            original["text_base64"] = base64.b64encode(altered).decode()
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "PATCH_SHA"):
                a.check_patch({"patch": original})

    def test_hunk_without_requirement_blocks(self):
        obj = sample_patch()
        obj["hunks"][0]["requirements"] = []
        with patch.object(a, "PATCH_SHA", obj["sha256"]):
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "HUNK_REQUIREMENT"):
                a.check_patch({"patch": obj})

    def test_requirement_without_hunk_blocks(self):
        obj = sample_patch()
        obj["hunks"][-1]["requirements"] = ["REM-C6"]
        with patch.object(a, "PATCH_SHA", obj["sha256"]):
            with self.assertRaisesRegex(a.RealEvidenceBlocked, "REQUIREMENT_COVERAGE"):
                a.check_patch({"patch": obj})

    def test_blob_oid_tampering_blocks(self):
        rows = [{"path": f"apps/time-service/file{i}.txt", "mode": "100644",
                 "bytes": 29347 if i == 0 else 0, "oid": "f"*40,
                 "content_base64": base64.b64encode(b"x"*29347 if i==0 else b"").decode()}
                for i in range(18)]
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "BLOB_OID"):
            a.rebuild_subtree(rows)

    def test_author_cannot_self_review(self):
        with self.assertRaisesRegex(a.RealEvidenceBlocked, "SELF_REVIEW"):
            a.independent_review_label("worker:claude-sonnet-5-5", "worker:claude-sonnet-5-5")

    def test_untrusted_commit_altered_oid(self):
        original = b"tree " + a.TREE.encode() + b"\n\nmsg\n"
        self.assertNotEqual(a.oid("commit", original + b"x"), a.oid("commit", original))


if __name__ == "__main__":
    unittest.main(verbosity=2)
