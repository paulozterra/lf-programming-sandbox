"""PG10 owner decision gate: omission, tampering and wrong C4 always BLOCK."""
from __future__ import annotations
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pg09_pg10_ex5c_owner_decision_bridge_v1 import (
    DECISION_FILE, DECISION_SHA256, OwnerDecisionBlocked,
    load_registered_owner_decision, bridge_pg09_c4_owner_decision_to_pg10,
    digest
)


def c4():
    doc = {
        "schema_version":"PG09_C4_TYPED_ESCALATION_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "run_ref":"sandbox:run:42284754122",
        "solutions":[{"solution_id":"EX5C",
                      "reason_codes":["BUDGET_DECISION"],"escalation_type":"RETURN"}],
        "production_authority":False,"handoff_allowed":False
    }
    doc["candidate_sha256"]=digest(doc)
    return doc


class OwnerDecisionGateTests(unittest.TestCase):
    def test_exact_record_is_pinned_and_non_authoritative(self):
        obj=load_registered_owner_decision()
        self.assertEqual(obj["decision_date"],"2026-11-06")
        self.assertEqual(obj["decision_ref"],"LF-OWNER-EX5C-ATTEMPT-1-20261106")
        self.assertEqual(obj["decision_state"],"RESOLVED")
        self.assertFalse(obj["retry_authorized"])
        self.assertFalse(obj["decision_authenticated"])

    def test_recorded_accept_without_retry_projects_reference_for_original_pg10(self):
        result=bridge_pg09_c4_owner_decision_to_pg10(pg09_c4=c4())
        self.assertEqual(result["reason_code"],"BUDGET_DECISION")
        self.assertFalse(result["owner_decision_authenticated"])
        self.assertFalse(result["production_authority"])
        self.assertEqual(result["source_pg09_c4_sha256"],c4()["candidate_sha256"])

    def test_without_registered_decision_pg10_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(OwnerDecisionBlocked,"PG10_OWNER_DECISION_RECORD_MISSING_BLOCK"):
                bridge_pg09_c4_owner_decision_to_pg10(
                    pg09_c4=c4(),decision_path=Path(d)/"missing.json")

    def test_rehashed_or_modified_decision_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            obj=load_registered_owner_decision()
            obj["retry_authorized"]=True
            p=Path(d)/"record.json"
            p.write_text(json.dumps(obj),encoding="utf-8")
            with self.assertRaisesRegex(OwnerDecisionBlocked,"SHA_MISMATCH"):
                bridge_pg09_c4_owner_decision_to_pg10(pg09_c4=c4(),decision_path=p)

    def test_c4_without_budget_decision_blocks(self):
        bad=c4()
        bad["solutions"][0]["reason_codes"]=["REVIEW_REQUIRED"]
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(OwnerDecisionBlocked,"BUDGET_DECISION_NOT_REFERENCED"):
            bridge_pg09_c4_owner_decision_to_pg10(pg09_c4=bad)

    def test_c4_authority_injection_even_resigned_blocks(self):
        bad=c4()
        bad["production_authority"]=True
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(OwnerDecisionBlocked,"SOURCE_INVALID"):
            bridge_pg09_c4_owner_decision_to_pg10(pg09_c4=bad)

if __name__=="__main__":
    unittest.main()
