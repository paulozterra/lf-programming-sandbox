"""Adversarial unit checks for the source-only PG-03_C6 boundary."""
import copy
import unittest
try:
    from .pg03_sufficiency_v1 import assess_sufficiency, SufficiencyBlocked
except ImportError:
    from pg03_sufficiency_v1 import assess_sufficiency, SufficiencyBlocked

BASE = {"status": "CANDIDATE_NOT_ADMITTED", "production_authority": False, "handoff_allowed": False, "requirement_ids": ["R1"], "acceptance_ids": ["A1"], "candidate_sha256": "test"}
R = [{"id": "R1", "source_ref": "analysis:R1"}]
A = [{"id": "A1", "source_ref": "analysis:A1"}]
Q = [{"id": "Q1", "source_ref": "PG01:Q1", "status": "RESOLVED", "evidence_ref": "evidence:q1"}]

def run(strategy=None, questions=None, requirements=None, acceptance=None, findings=None):
    return assess_sufficiency(strategy=BASE if strategy is None else strategy,
        pg01_questions=Q if questions is None else questions,
        requirement_evidence=R if requirements is None else requirements,
        acceptance_evidence=A if acceptance is None else acceptance,
        blocking_findings=[] if findings is None else findings)

class C6Tests(unittest.TestCase):
    def test_complete_candidate_remains_non_authoritative(self):
        result=run()
        self.assertEqual(result["status"], "CANDIDATE_SUFFICIENT_NOT_ADMITTED")
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["handoff_allowed"])
        self.assertEqual(result["gaps"], [])
    def test_missing_requirement_blocks(self):
        self.assertEqual(run(requirements=[])["gaps"][0]["code"], "REQUIREMENT_EVIDENCE_MISSING")
    def test_missing_acceptance_blocks(self):
        self.assertEqual(run(acceptance=[])["status"], "BLOCKED")
    def test_pending_human_decision(self):
        q=[dict(Q[0],status="REQUIRES_DECISION")]
        self.assertEqual(run(questions=q)["status"], "REQUIRES_DECISION")
    def test_open_question_blocks(self):
        self.assertEqual(run(questions=[dict(Q[0],status="OPEN")])["status"], "BLOCKED")
    def test_open_finding_blocks(self):
        self.assertEqual(run(findings=[{"id":"F1","source_ref":"review:F1","status":"OPEN"}])["status"],"BLOCKED")
    def test_missing_question_resolution_proof_rejected(self):
        with self.assertRaises(SufficiencyBlocked):
            run(questions=[{"id":"Q1","source_ref":"PG01:Q1","status":"RESOLVED"}])
    def test_duplicate_or_missing_provenance_rejected(self):
        for rows in (R+R,[{"id":"R1","source_ref":""}]):
            with self.subTest(rows=rows),self.assertRaises(SufficiencyBlocked):
                run(requirements=rows)
    def test_authority_escalation_rejected(self):
        for field in ("production_authority","handoff_allowed"):
            strategy=dict(BASE,**{field:True})
            with self.subTest(field=field),self.assertRaises(SufficiencyBlocked):
                run(strategy=strategy)
    def test_invalid_finding_status_rejected(self):
        with self.assertRaises(SufficiencyBlocked):
            run(findings=[{"id":"F1","source_ref":"review:F1","status":"ACCEPTED"}])
    def test_resolved_finding_without_proof_rejected(self):
        with self.assertRaises(SufficiencyBlocked):
            run(findings=[{"id":"F1","source_ref":"review:F1","status":"RESOLVED"}])
if __name__=="__main__": unittest.main()
