"""PG04 candidate probe: source-only, no partition generator or authority."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pg04_partition_admission_probe_v1 import inspect_candidate, PartitionProbeBlocked

POLICY = {
    "schema_version": "PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1",
    "unit": "PG-04", "runtime_activation": False, "production_activation": False,
    "partition_policy": {
        "semantic_boundary_first": True, "dependency_closure_required": True,
        "risk_boundary_considered": True, "write_scope_boundary_considered": True,
        "shared_contracts_referenced_not_copied": True,
        "token_count_alone_must_not_define_partition": True,
        "file_count_alone_must_not_define_partition": True,
        "partition_unit": "SOLUTION",
        "minimum_rule": "SMALLEST_COHERENT_VALID_CHANGE",
        "canonical_spec_count": 1,
    },
    "coverage": {
        "material_requirement_coverage_required_percent": 100,
        "acceptance_obligation_coverage_required_percent": 100,
    },
}
STRATEGY = {
    "status": "CANDIDATE_NOT_ADMITTED",
    "handoff_allowed": False, "production_authority": False,
    "requirement_ids": ["R1", "R2"], "acceptance_ids": ["A1", "A2"],
}
STRATEGY["candidate_sha256"] = hashlib.sha256(
    json.dumps(STRATEGY, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
SOURCES = {
    "contract_path": "wave1_boundary_contracts/programming_solution_partition_contract_v1.json",
    "contract_commit": "a" * 40,
    "j02_source_path": "skills/creating-integral-user-stories/references/screen-decomposition-protocol.md",
    "j02_source_commit": "b" * 40,
}
SOLUTIONS = [
    {
        "id": sid, "strategy_ref": STRATEGY["candidate_sha256"],
        "partition_basis": "SEMANTIC_SOLUTION",
        "business_outcome": "Observable business outcome " + sid,
        "semantic_boundary_reason": "single coherent goal",
        "risk_boundary_reason": "risk scoped with outcome",
        "write_scope_reason": "isolated changes",
        "write_scope": ["backend/src"],
        "shared_contract_refs": ["contract://canonical/shared"],
        "implementation_state": "EXISTING",
        "as_is_ref": "git://as-is", "delta_ref": "analysis://delta",
        "requirement_ids": [req], "acceptance_ids": [acc],
        "depends_on": depends,
    }
    for sid, req, acc, depends in [
        ("S1", "R1", "A1", []), ("S2", "R2", "A2", ["S1"])
    ]
]

def args():
    return dict(
        partition_policy=copy.deepcopy(POLICY),
        strategy=copy.deepcopy(STRATEGY),
        source_refs=copy.deepcopy(SOURCES),
        solutions=copy.deepcopy(SOLUTIONS),
    )

class ProbeTests(unittest.TestCase):
    def block(self, reason, mutate):
        candidate = args()
        mutate(candidate)
        with self.assertRaisesRegex(PartitionProbeBlocked, reason):
            inspect_candidate(**candidate)

    def test_positive_stays_untrusted(self):
        out = inspect_candidate(**args())
        self.assertEqual(out["status"], "CANDIDATE_NOT_ADMITTED")
        self.assertFalse(out["dispatch_allowed"])
        self.assertEqual(out["semantic_partition"], "DECLARED_NOT_INDEPENDENTLY_JUDGED")

    def test_deterministic(self):
        self.assertEqual(inspect_candidate(**args()), inspect_candidate(**args()))

    def test_disjoint_requirement_and_acceptance_solutions(self):
        case = args()
        case["solutions"][0]["acceptance_ids"] = []
        case["solutions"][1]["requirement_ids"] = []
        case["solutions"].append({
            **copy.deepcopy(case["solutions"][0]),
            "id": "S3", "requirement_ids": ["R2"], "acceptance_ids": [],
            "depends_on": ["S1"],
        })
        case["solutions"].append({
            **copy.deepcopy(case["solutions"][1]),
            "id": "S4", "requirement_ids": [], "acceptance_ids": ["A1"],
            "depends_on": ["S2"],
        })
        case["solutions"][1]["acceptance_ids"] = ["A2"]
        case["solutions"][1]["requirement_ids"] = []
        result = inspect_candidate(**case)
        self.assertEqual(result["requirement_coverage_count"], 2)
        self.assertEqual(result["acceptance_coverage_count"], 2)
        self.assertFalse(result["handoff_allowed"])

    def test_empty_material_solution_rejected(self):
        self.block("SOLUTION_WITHOUT_MATERIAL_OBLIGATION",
                   lambda a: a["solutions"][0].update(requirement_ids=[], acceptance_ids=[]))

    def test_empty_global_coverage_rejected(self):
        case = args()
        case["strategy"]["requirement_ids"] = []
        case["strategy"]["candidate_sha256"] = hashlib.sha256(
            json.dumps({k: v for k, v in case["strategy"].items() if k != "candidate_sha256"},
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for row in case["solutions"]:
            row["strategy_ref"] = case["strategy"]["candidate_sha256"]
            row["requirement_ids"] = []
        with self.assertRaisesRegex(PartitionProbeBlocked, "STRATEGY_REQUIREMENTS_INVALID"):
            inspect_candidate(**case)

    def test_existing_atom_binding_matches_envelope(self):
        a=args()
        a["solutions"][0]["atom_ids"]=["ATOM-1"]
        a["solutions"][0]["source_bindings"]=[{
            "atom_id":"ATOM-1","implementation_state":"EXISTING",
            "as_is_ref":"git://as-is","delta_ref":"analysis://delta"}]
        self.assertEqual(inspect_candidate(**a)["status"],"CANDIDATE_NOT_ADMITTED")

    def test_existing_atom_delta_drift_blocked(self):
        def bad(a):
            a["solutions"][0]["atom_ids"]=["ATOM-1"]
            a["solutions"][0]["source_bindings"]=[{
                "atom_id":"ATOM-1","implementation_state":"EXISTING",
                "as_is_ref":"git://as-is","delta_ref":"analysis://other"}]
        self.block("ATOM_IMPLEMENTATION_EVIDENCE_DRIFT",bad)

    def test_existing_atom_state_drift_blocked(self):
        def bad(a):
            a["solutions"][0]["source_bindings"]=[{
                "atom_id":"ATOM-1","implementation_state":"NEW",
                "bounded_reuse_assessment_ref":"analysis://reuse"}]
        self.block("ATOM_IMPLEMENTATION_STATE_DRIFT",bad)

    def test_duplicate_atom_binding_blocked(self):
        def bad(a):
            row={"atom_id":"A1","implementation_state":"EXISTING",
                 "as_is_ref":"git://as-is","delta_ref":"analysis://delta"}
            a["solutions"][0]["source_bindings"]=[row,copy.deepcopy(row)]
        self.block("ATOM_IMPLEMENTATION_BINDINGS_INVALID",bad)

    def test_new_atom_reuse_binding_mismatch_blocked(self):
        def bad(a):
            sol=a["solutions"][0]
            sol.pop("as_is_ref")
            sol.pop("delta_ref")
            sol["implementation_state"]="NEW"
            sol["bounded_reuse_assessment_ref"]="analysis://reused"
            sol["source_bindings"]=[{
                "atom_id":"ATOM-1","implementation_state":"NEW",
                "bounded_reuse_assessment_ref":"analysis://forged"}]
        self.block("ATOM_IMPLEMENTATION_EVIDENCE_DRIFT",bad)

    def test_new_solution_forbids_existing_fields(self):
        def bad(a):
            a["solutions"][0].update(implementation_state="NEW",
                bounded_reuse_assessment_ref="analysis://reuse")
        self.block("NEW_CONTAINS_EXISTING_EVIDENCE",bad)

    def test_source_trace(self):
        self.block("SOURCE_TRACE_MISSING", lambda a: a["source_refs"].pop("j02_source_path"))

    def test_policy(self):
        self.block("PG04_POLICY_DRIFT", lambda a: a["partition_policy"]["partition_policy"].update(shared_contracts_referenced_not_copied=False))

    def test_semantic_basis(self):
        self.block("FILE_OR_TOKEN_BASED_PARTITION_FORBIDDEN", lambda a: a["solutions"][0].update(partition_basis="FILE_COUNT"))

    def test_semantic_rationale(self):
        self.block("SEMANTIC_RATIONALE_MISSING", lambda a: a["solutions"][0].update(semantic_boundary_reason=""))

    def test_digest(self):
        self.block("PG03_STRATEGY_DIGEST_DRIFT", lambda a: a["strategy"].update(capability_selector="FORGED"))

    def test_strategy_ref(self):
        self.block("STRATEGY_REF_DRIFT", lambda a: a["solutions"][0].update(strategy_ref="other"))

    def test_inline_contract(self):
        self.block("INLINE_SHARED_CONTRACT_FORBIDDEN", lambda a: a["solutions"][0].update(shared_contracts=[{"definition": "copied"}]))

    def test_missing_contract_refs(self):
        self.block("SHARED_CONTRACT_REFS_INVALID", lambda a: a["solutions"][0].pop("shared_contract_refs"))

    def test_existing_delta(self):
        self.block("EXISTING_DELTA_MISSING", lambda a: a["solutions"][0].pop("delta_ref"))

    def test_new_reuse(self):
        self.block("NEW_REUSE_ASSESSMENT_MISSING", lambda a: a["solutions"][0].update(implementation_state="NEW"))

    def test_missing_state(self):
        self.block("IMPLEMENTATION_STATE_MISSING", lambda a: a["solutions"][0].pop("implementation_state"))

    def test_duplicate_ownership(self):
        self.block("DUPLICATE_MATERIAL_OWNERSHIP", lambda a: a["solutions"][1].update(requirement_ids=["R1"]))

    def test_coverage(self):
        self.block("MATERIAL_COVERAGE_MISMATCH", lambda a: a["solutions"][1].update(requirement_ids=["R3"]))

    def test_cycle(self):
        self.block("DEPENDENCY_CYCLE", lambda a: a["solutions"][0].update(depends_on=["S2"]))

    def test_unknown_dependency(self):
        self.block("DEPENDENCY_UNKNOWN", lambda a: a["solutions"][1].update(depends_on=["MISSING"]))

if __name__ == "__main__":
    unittest.main()
