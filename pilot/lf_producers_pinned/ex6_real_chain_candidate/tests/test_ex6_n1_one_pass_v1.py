"""H4 immutable dual-artifact proof plus genuine one-pass EX6 N+1 diagnostics."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/"tools"))
from ex6_n1_receipts_v1 import EXPECTED, load, verify_both, ReceiptIntegrityError, EVIDENCE
from ex6_build_lint_inputs_v1 import using_receipt, observed, active_label

class H4N1EvidenceTests(unittest.TestCase):
    def test_both_zip_sha_both_json_sha_and_sidecars(self):
        both=verify_both()
        self.assertEqual(both["N"]["candidate_commit"],EXPECTED["N"]["candidate"])
        self.assertEqual(both["N1"]["candidate_commit"],EXPECTED["N1"]["candidate"])
        self.assertEqual(both["N"]["snapshots"][1]["commands"]["format_aosp"]["exit_code"],1)
        self.assertEqual(both["N1"]["snapshots"][1]["commands"]["format_aosp"]["exit_code"],0)
        self.assertEqual(both["N1"]["snapshots"][1]["commands"]["visible_ex6"]["exit_code"],0)
        self.assertFalse(both["N1"]["production_authority"])
    def test_one_bit_zip_change_rejected_both_sources(self):
        for label in ("N","N1"):
            raw=bytearray((EVIDENCE/EXPECTED[label]["name"]).read_bytes())
            raw[-1]^=1
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"tampered.zip"
                path.write_bytes(raw)
                with self.assertRaisesRegex(ReceiptIntegrityError,"ZIP_SHA_DRIFT"):
                    load(label,path)
    def test_n_remains_default_and_n1_scoped(self):
        self.assertEqual(active_label(),"N")
        self.assertEqual(observed()["candidate_commit"],EXPECTED["N"]["candidate"])
        with using_receipt("N1"):
            self.assertEqual(active_label(),"N1")
            self.assertEqual(observed()["candidate_commit"],EXPECTED["N1"]["candidate"])
        self.assertEqual(active_label(),"N")
    def test_one_single_pg04_to_pg14_n1_pass(self):
        from ex6_n1_one_pass_v1 import run_n1
        result=run_n1()
        self.assertEqual([x["stage"] for x in result["stages"]],["PG-%02d"%i for i in range(4,15)])
        self.assertEqual(result["evidence"]["pg08_c2_format_aosp_exit_code"],0)
        self.assertTrue(result["evidence"]["rem_d4_process"]["process_requirement_satisfied"])
        self.assertEqual(result["evidence"]["local_v2"]["pg13_local_mutations_blocked"],5)
        self.assertEqual(result["evidence"]["local_v2"]["pg14_tampered_verdict"],"BLOCK")
        self.assertEqual(result["evidence_lineage"]["active_build_and_lint_receipt"],"N1")
        self.assertEqual(result["evidence_lineage"]["pg12_c1_git_identity"],"N_ORIGINAL_PATCH_NOT_REBASED_TO_N1")
        self.assertFalse(result["evidence_lineage"]["PG12_13_14_N1_production_admission"])
        self.assertTrue(all(s["production_authority"] is False for s in result["stages"]))
        self.assertNotIn("ex5c",json.dumps(result).lower())

if __name__=="__main__":
    unittest.main()
