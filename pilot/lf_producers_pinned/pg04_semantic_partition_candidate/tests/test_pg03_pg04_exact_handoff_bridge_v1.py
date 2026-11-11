"""Source-only PG03 C8 -> PG04 positive and adversarial chain test."""
import hashlib
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

STAGE=Path(__file__).resolve().parents[1]
ROOT=STAGE.parent
sys.path.insert(0,str(STAGE))
sys.path.insert(0,str(ROOT/"pg03_strategy_candidate"))

from pg03_handoff_boundary_v1 import prepare_pg04_handoff
from tools.pg03_pg04_exact_handoff_bridge_v1 import (
    partition_from_pg03_c8,BridgeBlocked
)

def digest(o):
    return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def fixture():
    policy=json.loads((ROOT/"wave1_boundary_contracts"/"programming_solution_partition_contract_v1.json").read_text())
    strategy={
        "status":"CANDIDATE_NOT_ADMITTED",
        "production_authority":False,"handoff_allowed":False,
        "requirement_ids":["R1"],"acceptance_ids":["A1"],"scope_ids":["S1"],
    }
    strategy["candidate_sha256"]=digest(strategy)
    suff={
        "status":"CANDIDATE_SUFFICIENT_NOT_ADMITTED",
        "production_authority":False,"handoff_allowed":False,
        "gaps":[],"source_strategy_sha256":strategy["candidate_sha256"]
    }
    exceptions={
        "status":"CANDIDATE_NOT_ADMITTED","production_authority":False,
        "waiver_authorized":False,"handoff_allowed":False,"exceptions":[]
    }
    coverage=[{
        "solution_id":"SOL1","scope_ids":["S1"],"strategy_ref":strategy["candidate_sha256"],
        "requirement_ids":["R1"],"acceptance_ids":["A1"],"depends_on":[]
    }]
    handoff=prepare_pg04_handoff(
        strategy=strategy,sufficiency=suff,exceptions_result=exceptions,
        partition_contract=policy,solution_coverage=coverage
    )
    atoms=[{
        "atom_id":"AT1","outcome_id":"OUT1","source_ref":"fixture:analysis-A9",
        "scope_id":"S1","risk_level":"LOW","write_scope_reason":"local scope",
        "semantic_rationale":"single coherent result",
        "write_scope":["src/feature.py"],"shared_contract_refs":[],
        "implementation_state":"NEW",
        "bounded_reuse_assessment_ref":"fixture:bounded-reuse",
        "requirement_ids":["R1"],"acceptance_ids":["A1"],
        "depends_on":[],"coimplement_with":[]
    }]
    outcomes=[{"outcome_id":"OUT1","business_outcome":"new valid capability",
               "evidence_ref":"fixture:outcome"}]
    return dict(pg03_handoff=handoff,strategy=strategy,partition_contract=policy,
                obligations=atoms,outcome_registry=outcomes)

class PG03ToPG04ChainTests(unittest.TestCase):
    def test_real_pg03_c8_producer_positive(self):
        output=partition_from_pg03_c8(**fixture())
        self.assertEqual(output["schema_version"],"PG03_PG04_CONNECTED_PARTITION_CANDIDATE_V1")
        self.assertEqual(output["partition"]["coverage"]["orphans"],0)
        self.assertEqual(output["partition"]["solutions"][0]["requirement_ids"],["R1"])
        self.assertTrue(output["pg03_pg04_chain_shape_verified"])
        self.assertFalse(output["handoff_allowed"])
        self.assertFalse(output["production_authority"])
        self.assertFalse(output["semantic_judge_executed"])
    def test_corrupted_pg03_c8_digest_blocks(self):
        f=fixture();f["pg03_handoff"]["strategy_sha256"]="tampered"
        with self.assertRaisesRegex(BridgeBlocked,"DIGEST_DRIFT"):
            partition_from_pg03_c8(**f)
    def test_foreign_strategy_blocks(self):
        f=fixture();f["strategy"]["candidate_sha256"]="f"*64
        with self.assertRaisesRegex(BridgeBlocked,"STRATEGY_HANDOFF_DRIFT"):
            partition_from_pg03_c8(**f)
    def test_missing_material_obligation_blocks(self):
        f=fixture();f["obligations"][0]["requirement_ids"]=[]
        with self.assertRaises(Exception):
            partition_from_pg03_c8(**f)
    def test_unauthorized_handoff_blocks(self):
        f=fixture();f["pg03_handoff"]["handoff_allowed"]=True
        f["pg03_handoff"]["candidate_sha256"]=digest({
            k:v for k,v in f["pg03_handoff"].items() if k!="candidate_sha256"
        })
        with self.assertRaisesRegex(BridgeBlocked,"AUTHORITY_INVALID"):
            partition_from_pg03_c8(**f)
    def test_not_pg03_c8_envelope_blocks(self):
        f=fixture();f["pg03_handoff"]["schema_version"]="FAKE"
        with self.assertRaisesRegex(BridgeBlocked,"HANDOFF_REQUIRED"):
            partition_from_pg03_c8(**f)

if __name__=="__main__":
    unittest.main()
