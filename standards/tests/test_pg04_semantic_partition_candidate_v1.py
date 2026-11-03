"""PG-04 semantic outcome partition: generated candidates only, never authority."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome as partition,PartitionBlocked
from pg04_partition_admission_probe_v1 import inspect_candidate

POLICY={
    "schema_version":"PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1",
    "unit":"PG-04","runtime_activation":False,"production_activation":False,
    "partition_policy":{
        "semantic_boundary_first":True,"dependency_closure_required":True,
        "risk_boundary_considered":True,"write_scope_boundary_considered":True,
        "shared_contracts_referenced_not_copied":True,
        "token_count_alone_must_not_define_partition":True,
        "file_count_alone_must_not_define_partition":True,
        "partition_unit":"SOLUTION","minimum_rule":"SMALLEST_COHERENT_VALID_CHANGE",
        "canonical_spec_count":1},
    "coverage":{
        "material_requirement_coverage_required_percent":100,
        "acceptance_obligation_coverage_required_percent":100}}
STRATEGY={
    "status":"CANDIDATE_NOT_ADMITTED","production_authority":False,
    "handoff_allowed":False,"scope_ids":["S1"],
    "requirement_ids":["R1","R2","R3"],"acceptance_ids":["A1","A2","A3"]}
STRATEGY["candidate_sha256"]=hashlib.sha256(
    json.dumps(STRATEGY,sort_keys=True,separators=(",",":")).encode()).hexdigest()
OUTCOMES=[
    {"outcome_id":"PAY","business_outcome":"Confirm payment","evidence_ref":"analysis://O1"},
    {"outcome_id":"HISTORY","business_outcome":"Show history","evidence_ref":"analysis://O2"}]
def atom(oid,outcome,req,acc,depends=None,**changes):
    row={"atom_id":oid,"outcome_id":outcome,"source_ref":"analysis://"+oid,
         "scope_id":"S1","risk_level":"MEDIUM",
         "semantic_rationale":"Separately source-backed change",
         "write_scope_reason":"Scoped to component","write_scope":["backend/api"],
         "shared_contract_refs":["contract://payment-v1"],
         "implementation_state":"NEW",
         "bounded_reuse_assessment_ref":"analysis://reuse-check",
         "requirement_ids":[req],"acceptance_ids":[acc],
         "depends_on":depends or [],"coimplement_with":[]}
    row.update(changes)
    return row
ATOMS=[
    atom("API","PAY","R1","A1",write_scope=["backend/api"]),
    atom("DB","PAY","R2","A2",write_scope=["database/migration"]),
    atom("UI","HISTORY","R3","A3",depends=["API"],write_scope=["frontend/ui"])]
def args():
    return {"strategy":copy.deepcopy(STRATEGY),
            "partition_contract":copy.deepcopy(POLICY),
            "obligations":copy.deepcopy(ATOMS),
            "outcome_registry":copy.deepcopy(OUTCOMES)}
class Tests(unittest.TestCase):
    def denied(self,code,mutate):
        values=args();mutate(values)
        with self.assertRaisesRegex(PartitionBlocked,"^"+code+"$"):
            partition(**values)
    def test_multilayer_outcome_and_dependency(self):
        p=partition(**args())
        self.assertEqual(len(p["solutions"]),2)
        self.assertEqual(p["solutions"][0]["atom_ids"],["API","DB"])
        self.assertEqual(p["solutions"][0]["write_scope"],["backend/api","database/migration"])
        self.assertEqual(p["solutions"][1]["atom_ids"],["UI"])
        self.assertEqual(p["solutions"][1]["depends_on"],["SOL-001"])
        self.assertEqual(p["coverage"],{"requirements":3,"acceptance":3,"orphans":0,"duplicate_owners":0})
        self.assertFalse(p["handoff_allowed"])
    def test_determinism(self):
        self.assertEqual(partition(**args()),partition(**args()))
    def test_order_independent(self):
        a=args();a["obligations"].reverse()
        self.assertEqual(partition(**args()),partition(**a))
    def test_existing_admission_probe_compatibility(self):
        p=partition(**args())
        sources={"contract_path":"contract.json","contract_commit":"a"*40,
                 "j02_source_path":"j02.md","j02_source_commit":"b"*40}
        x=inspect_candidate(partition_policy=POLICY,strategy=STRATEGY,
                            source_refs=sources,solutions=p["solutions"])
        self.assertEqual(x["status"],"CANDIDATE_NOT_ADMITTED")
        self.assertEqual(x["solution_count"],2)
    def test_strategy_mutation(self):
        self.denied("STRATEGY_DIGEST_DRIFT",lambda a:a["strategy"].update(requirement_ids=["OTHER"]))
    def test_unknown_outcome(self):
        self.denied("SOURCE_SCOPE_OR_OUTCOME_UNKNOWN",lambda a:a["obligations"][0].update(outcome_id="NO"))
    def test_missing_outcome_provenance(self):
        self.denied("OUTCOME_EVIDENCE_INVALID",lambda a:a["outcome_registry"][0].update(evidence_ref=""))
    def test_duplicate_requirement(self):
        self.denied("DUPLICATE_OBLIGATION_OWNERSHIP",lambda a:a["obligations"][1].update(requirement_ids=["R1"]))
    def test_lost_requirement(self):
        self.denied("COVERAGE_INCOMPLETE_OR_FOREIGN",lambda a:a["obligations"][1].update(requirement_ids=[]))
    def test_inline_shared_contract(self):
        self.denied("INLINE_SHARED_CONTRACT_FORBIDDEN",lambda a:a["obligations"][0].update(shared_contracts=[{"definition":"copy"}]))
    def test_existing_without_delta(self):
        self.denied("EXISTING_DELTA_MISSING",lambda a:a["obligations"][0].update(implementation_state="EXISTING",as_is_ref="git://old",delta_ref=""))
    def test_new_without_reuse_evidence(self):
        self.denied("NEW_REUSE_EVIDENCE_MISSING",lambda a:a["obligations"][0].update(bounded_reuse_assessment_ref=""))
    def test_unknown_implementation_state(self):
        self.denied("IMPLEMENTATION_STATE_UNKNOWN",lambda a:a["obligations"][0].update(implementation_state="UNKNOWN"))
    def test_unknown_atom_dependency(self):
        self.denied("UNKNOWN_ATOM_DEPENDENCY",lambda a:a["obligations"][0].update(depends_on=["OTHER"]))
    def test_cycle(self):
        self.denied("SOLUTION_DEPENDENCY_CYCLE",lambda a:a["obligations"][0].update(depends_on=["UI"]))
    def test_nonreciprocal_atomicity(self):
        self.denied("COIMPLEMENT_NOT_RECIPROCAL",lambda a:a["obligations"][0].update(coimplement_with=["UI"],coimplement_evidence_ref="analysis://join"))
    def test_explicit_atomicity_merges_different_outcomes(self):
        a=args()
        a["obligations"][0].update(coimplement_with=["UI"],coimplement_evidence_ref="analysis://join")
        a["obligations"][2].update(coimplement_with=["API"],coimplement_evidence_ref="analysis://join")
        self.assertEqual(len(partition(**a)["solutions"]),1)
    def test_atomicity_conflicting_implementation(self):
        def bad(a):
            a["obligations"][0].update(coimplement_with=["UI"],coimplement_evidence_ref="analysis://join")
            a["obligations"][2].update(coimplement_with=["API"],coimplement_evidence_ref="analysis://join",implementation_state="EXISTING",as_is_ref="git://s",delta_ref="analysis://delta")
        self.denied("COIMPLEMENT_STATE_CONFLICT",bad)
    def test_atomicity_conflicting_risk(self):
        def bad(a):
            a["obligations"][0].update(coimplement_with=["UI"],coimplement_evidence_ref="analysis://join",risk_level="HIGH")
            a["obligations"][2].update(coimplement_with=["API"],coimplement_evidence_ref="analysis://join",risk_level="LOW")
        self.denied("COIMPLEMENT_RISK_CONFLICT",bad)
    def test_partition_policy_drift(self):
        self.denied("PARTITION_POLICY_DRIFT",lambda a:a["partition_contract"]["partition_policy"].update(semantic_boundary_first=False))
    def test_no_authority_or_semantic_judge(self):
        p=partition(**args())
        self.assertFalse(p["production_authority"])
        self.assertFalse(p["dispatch_allowed"])
        self.assertFalse(p["semantic_judge_executed"])
        self.assertEqual(p["source_authenticity"],"UNVERIFIED")
if __name__=="__main__":
    unittest.main()
