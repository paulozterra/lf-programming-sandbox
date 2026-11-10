"""Offline PG00 catalog source pin and fail-closed candidate policy."""
from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import project_stack_resolver_exp as resolver

EXPECTED_COMMIT="f18b2d96b7e1a8263749d35a7afcc9c043521cb8"
EXPECTED_SHA256="26ca9cf9936ef01b50f9af504e4a9b796ee7d7d538d5724ff388c9fb90e8ddb3"
COUNTS={"STD-BE":6,"STD-FE":7,"STD-DB":10}

class PinnedCatalogQualification(unittest.TestCase):
    def test_immutable_repo_source_and_byte_hash(self):
        meta=resolver.load_json("pg00_catalog_sources_exp.json")
        raw=(ROOT/meta["snapshot_path"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),EXPECTED_SHA256)
        self.assertEqual(meta["source_commit_sha"],EXPECTED_COMMIT)
        self.assertEqual(meta["source_repository"],"paulozterra/lf-programming-sandbox")
        self.assertEqual(meta["source_path"],"standards/catalog.json")
        self.assertEqual(meta["source_sha256"],EXPECTED_SHA256)
        self.assertIs(meta["promotion_allowed"],False)
        self.assertIs(meta["production_authority"],False)

    def test_every_rule_is_literal_source_text(self):
        catalog=resolver.load_json("pg00_normative_catalog_snapshot.json")
        self.assertEqual(catalog["status"],"BORRADOR_EN_REPO_DE_CALIFICACION")
        for code,count in COUNTS.items():
            actual=resolver.pg00_source_status(code)
            original=[r for r in catalog["rules"] if r["domain"]==code]
            self.assertEqual(len(original),count)
            self.assertEqual(actual["rules"],[
                {"id":r["id"],"text":r["rule"],"severity":r.get("severity"),
                 "status":r.get("status")} for r in original])
            self.assertTrue(actual["normative_text_available"])
            self.assertTrue(actual["qualification_only"])
            self.assertFalse(actual["production_authority"])
            self.assertEqual(actual["source_sha256"],EXPECTED_SHA256)

    def test_drift_fails_closed(self):
        original=(ROOT/"pg00_catalog_sources_exp.json").read_bytes()
        raw=(ROOT/"pg00_normative_catalog_snapshot.json").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            (directory/"pg00_catalog_sources_exp.json").write_bytes(original)
            target=directory/"pg00_normative_catalog_snapshot.json"
            target.write_bytes(raw+b" ")
            with patch.object(resolver,"ROOT",directory):
                with self.assertRaisesRegex(resolver.StackBlocked,"PG00_STANDARD_SOURCE_SHA256_DRIFT"):
                    resolver.pg00_source_status("STD-BE")
            target.unlink()
            with patch.object(resolver,"ROOT",directory):
                with self.assertRaisesRegex(resolver.StackBlocked,"PG00_STANDARD_TEXT_UNAVAILABLE"):
                    resolver.pg00_source_status("STD-BE")

    def test_unknown_family_blocked(self):
        with self.assertRaisesRegex(resolver.StackBlocked,"PG00_STD_FAMILY_UNKNOWN"):
            resolver.pg00_source_status("STD-UNVERIFIED")

if __name__=="__main__":
    unittest.main(verbosity=2)
