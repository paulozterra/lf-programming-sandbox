"""PG04 uncovered edges: coverage C3/C7, C6 split, PG05 exit, PG07 budget.

All tests use the existing semantic partition producer and are source-only.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome
from pg04_c7_coverage_dossier_v1 import build_coverage_dossier, CoverageDossierBlocked
from pg04_pg07_budget_feedback_candidate_v1 import prepare_pg07_budget_feedback, BudgetFeedbackBlocked
from pg04_c6_repartition_proposal_v1 import propose_repartition, RepartitionBlocked
from pg04_pg05_exit_candidate_v1 import assemble_pg04_exit_candidate, ExitPackageBlocked
from pg04_definition_of_done_candidate_v1 import prepare_dod
from pg04_independent_review_request_v1 import prepare_partition_review_request
from test_pg04_semantic_partition_candidate_v1 import args
from test_pg04_definition_of_done_candidate_v1 import fixtures as dod_fixtures
from test_pg04_independent_review_request_v1 import baseline as review_fixture

def base():
    inputs = args()
    return inputs, partition_by_semantic_outcome(**inputs)

def budget(partition, status="RED", solution="SOL-001"):
    return prepare_pg07_budget_feedback(
        partition=partition,
        budget_feedback={
            "schema_version":"PG07_CONTEXT_BUDGET_FEEDBACK_CANDIDATE_V1",
            "source_capability":"CONTEXT_BUDGET_GOVERNANCE",
            "budget_evaluation_ref":"fixture://budget-eval",
            "partition_sha256":partition["candidate_sha256"],
            "solution_id":solution,"context_status":status,
            "source_mode":"CALLER_SUPPLIED_UNVERIFIED",
            "material_ref_ids":["R1","R2"],"jit_candidate_ref_ids":["R1"],
            "model_profile_ref":"fixture://model-profile"
        }
    )

def exit_fixture():
    inputs, partition = base()
    dossier = build_coverage_dossier(
        partition=partition, strategy=inputs["strategy"],
        original_obligations=inputs["obligations"])
    df = dod_fixtures()
    assert df["partition"]["candidate_sha256"] == partition["candidate_sha256"]
    dod = prepare_dod(**df)
    src = review_fixture()
    assert src["partition"]["candidate_sha256"] == partition["candidate_sha256"]
    review = prepare_partition_review_request(
        partition=partition, sources=src["sources"],
        producer_execution_id="fixture:pg04",
        coverage_dossier=dossier)
    return dict(partition=partition, dod=dod,
                coverage_dossier=dossier, review_request=review)

class C3AndC7Coverage(unittest.TestCase):
    def test_positive_bidirectional_coverage(self):
        inputs, partition = base()
        result = build_coverage_dossier(
            partition=partition, strategy=inputs["strategy"],
            original_obligations=inputs["obligations"])
        self.assertEqual(result["coverage"]["requirements"],3)
        self.assertEqual(result["coverage"]["acceptances"],3)
        self.assertEqual(result["coverage_deterministic_check"],"PASS_SOURCE_ONLY")
        self.assertFalse(result["independent_review_executed"])
        self.assertFalse(result["handoff_allowed"])

    def test_forged_digest_blocks(self):
        inputs, partition = base()
        partition["solutions"][0]["id"]="FORGED"
        with self.assertRaises(CoverageDossierBlocked):
            build_coverage_dossier(partition=partition,
                strategy=inputs["strategy"],
                original_obligations=inputs["obligations"])

    def test_missing_atom_blocks(self):
        inputs, partition = base()
        with self.assertRaises(CoverageDossierBlocked):
            build_coverage_dossier(partition=partition,
                strategy=inputs["strategy"],
                original_obligations=inputs["obligations"][:-1])

class C6BudgetAndRepartition(unittest.TestCase):
    def test_red_budget_source_only(self):
        _, partition=base()
        edge=budget(partition)
        self.assertTrue(edge["repair_required"])
        self.assertEqual(edge["repair_edge"]["kind"],"CONTROL_RETURN_NOT_SOLUTION_DAG_EDGE")
        self.assertFalse(edge["budget_engine_invoked"])
        self.assertFalse(edge["auto_repartition_allowed"])

    def test_green_no_repair_and_no_pass(self):
        _, partition=base()
        edge=budget(partition,"GREEN")
        self.assertFalse(edge["repair_required"])
        self.assertFalse(edge["pg07_budget_pass_claim_allowed"])

    def test_foreign_budget_solution_blocked(self):
        _, partition=base()
        with self.assertRaises(BudgetFeedbackBlocked):
            budget(partition,solution="SOL-999")

    def test_red_semantic_split_preserves_material_and_dag(self):
        inputs, partition=base()
        edge=budget(partition)
        split={
            "target_solution_id":"SOL-001",
            "separation_evidence_ref":"fixture://semantic-distinction",
            "jit_attempt_disposition":"INSUFFICIENT_WITH_EVIDENCE",
            "groups":[
                {"solution_id":"SOL-003","atom_ids":["API"],
                 "semantic_boundary_reason":"API contract atomic",
                 "evidence_ref":"fixture://API"},
                {"solution_id":"SOL-004","atom_ids":["DB"],
                 "semantic_boundary_reason":"DB migration atomic",
                 "evidence_ref":"fixture://DB"}
            ]
        }
        result=propose_repartition(partition=partition,budget_edge=edge,
             original_obligations=inputs["obligations"][:2],split_plan=split)
        self.assertEqual(result["coverage_preserved"]["requirements"],3)
        self.assertEqual(result["coverage_preserved"]["acceptances"],3)
        self.assertEqual(result["downstream_rebound_conservatively"],["SOL-002"])
        self.assertFalse(result["pg07_remeasurement_executed"])
        self.assertFalse(result["handoff_allowed"])

    def test_non_red_repartition_rejected(self):
        inputs, partition=base()
        edge=budget(partition,"YELLOW")
        split={"target_solution_id":"SOL-001","separation_evidence_ref":"fixture://sem",
               "jit_attempt_disposition":"INSUFFICIENT_WITH_EVIDENCE","groups":[]}
        with self.assertRaises(RepartitionBlocked):
            propose_repartition(partition=partition,budget_edge=edge,
                original_obligations=inputs["obligations"][:2],split_plan=split)

    def test_missing_atom_in_split_blocked(self):
        inputs, partition=base()
        edge=budget(partition)
        split={"target_solution_id":"SOL-001","separation_evidence_ref":"fixture://sem",
               "jit_attempt_disposition":"INSUFFICIENT_WITH_EVIDENCE",
               "groups":[{"solution_id":"SOL-003","atom_ids":["API"],
                          "semantic_boundary_reason":"API","evidence_ref":"fixture://API"},
                         {"solution_id":"SOL-004","atom_ids":["UI"],
                          "semantic_boundary_reason":"UI","evidence_ref":"fixture://UI"}]}
        with self.assertRaises(RepartitionBlocked):
            propose_repartition(partition=partition,budget_edge=edge,
                original_obligations=inputs["obligations"][:2],split_plan=split)

class PG04ToPG05Exit(unittest.TestCase):
    def test_positive_candidate_without_scope_authority(self):
        result=assemble_pg04_exit_candidate(**exit_fixture())
        self.assertEqual(result["schema_version"],"PG04_TO_PG05_EXIT_CANDIDATE_V1")
        self.assertEqual(result["first_pg05_blocker"],"PG05_TARGET_BINDING_MISSING")
        self.assertIsNone(result["target_binding"]["repo_full_name"])
        self.assertFalse(result["pg05_admission_allowed"])
        self.assertFalse(result["pg05_branch_creation_allowed"])

    def test_bound_target_still_requires_review(self):
        f=exit_fixture()
        f["target_binding"]={
            "repo_full_name":"sandbox/example","base_head_sha":"a"*40,
            "target_binding_ref":"fixture://target"}
        result=assemble_pg04_exit_candidate(**f)
        self.assertEqual(result["first_pg05_blocker"],"PG04_INDEPENDENT_REVIEW_NOT_EXECUTED")
        self.assertFalse(result["pg05_write_allowed"])

    def test_foreign_coverage_dossier_blocks(self):
        f=exit_fixture()
        f["coverage_dossier"]["partition_sha256"]="f"*64
        with self.assertRaises(ExitPackageBlocked):
            assemble_pg04_exit_candidate(**f)

    def test_forged_review_receipt_blocks(self):
        f=exit_fixture()
        f["review_request"]["subject_receipt_id"]="fake-uuid"
        with self.assertRaises(ExitPackageBlocked):
            assemble_pg04_exit_candidate(**f)

if __name__ == "__main__":
    unittest.main()
