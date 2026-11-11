"""V3 fail-closed negatives; no fabricated v3 fixture or fake PG14 PASS."""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pg07_ex5c_format_remediation_v3_adapter_v1 as v3


def class_record(path, raw):
    return {"path": path, "bytes": len(raw), "sha256": v3.sha(raw),
            "content_base64": base64.b64encode(raw).decode()}


class EX5CV3ExactBundleTests(unittest.TestCase):
    """The actual published N+1 fixture, not manufactured synthetic evidence."""

    def setUp(self):
        self.real = v3.load_v3(v3.V3_FIXTURE, v3.V3_SHA)

    def test_exact_real_bundle_recalculates_commit_tree_classes_and_smoke(self):
        self.assertEqual(self.real["git"]["commit"], v3.EXPECTED_COMMIT)
        self.assertEqual(self.real["git"]["base_commit"], v3.N)
        self.assertEqual(self.real["lineage_reason"], "FORMAT_REMEDIATION")
        self.assertEqual(self.real["formatter_mode"], "--aosp")
        self.assertEqual(self.real["class_equivalence"]["class_count"], 9)
        self.assertEqual(len(self.real["git"]["files"]), 18)
        self.assertEqual(self.real["execution"]["baseline_format_check"]["exit_code"], 1)
        self.assertEqual(self.real["execution"]["candidate_format_check"]["exit_code"], 0)
        self.assertEqual(len(self.real["execution"]["baseline_format_findings"]), 18)
        self.assertEqual(self.real["execution"]["candidate_format_findings"], [])
        self.assertEqual(self.real["class_equivalence"]["candidate_lint_findings"], [])
        self.assertFalse(self.real["production_authority"])
        print("EX5C_V3_EXACT_GIT_CLASS_MAVEN_SMOKE_BYTES_PASS")
        print("EX5C_V3_REAL_PRODUCTION_AUTHORITY_FALSE")

    def test_real_v3_original_pg06_c4_pg08_c1_c2_imported_not_admitted(self):
        import pg08_ex5c_v3_candidate_bridge_v1 as bridge
        result = bridge.run_real_n1_pg06_pg08_c1_c2(v3.V3_FIXTURE, v3.V3_SHA)
        self.assertEqual(result["pg08_c1"]["solutions"][0]["reported_build_outcome"],
                         "REPORTED_PASS_UNVERIFIED")
        self.assertEqual(result["pg08_c2"]["solutions"][0]["reported_diagnostic"],
                         "REPORTED_NO_NEW_BLOCKERS_UNVERIFIED")
        self.assertEqual(result["pg08_c2"]["solutions"][0]["reported_new_blockers"], [])
        self.assertEqual(result["pg08_c2"]["source_pg06_c4_sha256"],
                         result["pg06_c4"]["candidate_sha256"])
        self.assertFalse(result["pg08_c2"]["pg08_c2_pass"])
        self.assertFalse(result["production_authority"])
        print("EX5C_V3_ORIGINAL_PG06_C4_PG08_C1_C2_UNVERIFIED_PASS")
        print("EX5C_V3_PG08_C2_NO_NEW_BLOCKERS_BUT_NOT_ADMITTED")

    def test_real_package_replacement_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "v3.json"
            raw = bytearray(v3.V3_FIXTURE.read_bytes())
            raw[-20] ^= 1
            p.write_bytes(raw)
            with self.assertRaisesRegex(v3.EX5CV3Blocked, "BUNDLE_BYTE_TAMPER_BLOCK"):
                v3.load_v3(p, v3.V3_SHA)

    def test_real_class_bytes_modified_even_with_rehashed_bundle_are_rejected(self):
        evidence = copy.deepcopy(self.real)
        evidence["class_equivalence"]["candidate_class_objects"][0]["content_base64"] = (
            base64.b64encode(b"edited compiled class").decode()
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "v3.json"
            raw = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(v3.EX5CV3Blocked, "CLASS_BYTE_SHA_BLOCK"):
                v3.load_v3(p, hashlib.sha256(raw).hexdigest())

class EX5CV3FailClosedTests(unittest.TestCase):
    def test_v3_missing_bundle_and_sha_block(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "v3.json"
            with self.assertRaisesRegex(v3.EX5CV3Blocked, "SHA_NOT_PINNED"):
                v3.load_v3(missing, "")
            with self.assertRaisesRegex(v3.EX5CV3Blocked, "FIXTURE_NOT_FOUND"):
                v3.load_v3(missing, "0" * 64)

    def test_v3_swapped_json_cannot_reuse_fixed_sha(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "v3.json"
            p.write_text('{"fake":"substituted"}\n')
            with self.assertRaisesRegex(v3.EX5CV3Blocked, "BUNDLE_BYTE_TAMPER"):
                v3.load_v3(p, "0" * 64)

    def test_byte_identical_class_records_are_required(self):
        raw = b"\xca\xfe\xba\xbe"
        ce = {"baseline_class_objects": [class_record("pkg/A.class", raw)],
              "candidate_class_objects": [class_record("pkg/A.class", raw)],
              "baseline": {"pkg/A.class": v3.sha(raw)},
              "candidate": {"pkg/A.class": v3.sha(raw)},
              "class_count": 1, "identical": True,
              "javac_flags": ["--release", "21", "-g:none"]}
        self.assertEqual(v3.class_objects(ce), {"pkg/A.class": v3.sha(raw)})
        altered = copy.deepcopy(ce)
        altered["candidate_class_objects"][0]["content_base64"] = base64.b64encode(raw + b"X").decode()
        with self.assertRaisesRegex(v3.EX5CV3Blocked, "CLASS_BYTE_SHA_BLOCK"):
            v3.class_objects(altered)
        changed = copy.deepcopy(ce)
        changed["candidate_class_objects"][0] = class_record("pkg/A.class", raw + b"X")
        with self.assertRaisesRegex(v3.EX5CV3Blocked, "CLASS_EQUIVALENCE_BLOCK"):
            v3.class_objects(changed)

    def test_commit_raw_byte_tamper_changes_oid(self):
        raw = b"tree 922f74a8ffaab9b8233625c804b8c92a17d8b8a3\n\nOriginal\n"
        self.assertNotEqual(v3.oid("commit", raw), v3.oid("commit", raw + b"."))
        self.assertNotEqual(v3.oid("blob", b"source"), v3.oid("blob", b"Source"))

    def test_authority_injection_blocks_even_when_record_rehashed(self):
        injected = {"evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
                    "git": {"files": []},
                    "production_authority": False,
                    "new": {"receipt_authenticated": True}}
        self.assertEqual(len(v3.sha(json.dumps(injected).encode())), 64)
        with self.assertRaisesRegex(v3.EX5CV3Blocked, "AUTHORITY_INJECTION_BLOCK"):
            v3.flags_false(injected)


if __name__ == "__main__":
    unittest.main()
