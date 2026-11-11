"""H2-C4 / PG-03_C2 qualification-only, using existing PG-02 and C6 modules.
No DB/authenticated receipt, production authority, or model runtime.
"""
import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
C6 = HERE.parent / "c6_context_gate"
sys.path.insert(0, str(C6))
from test_pg02_classifier_v1 import s, m, pg01_binding
from pg02_classification_outcome_v1 import classify_with_outcome
from test_context_gate_v1 import GateTests
from checkpoint_bridge_v1 import PLAN, CHECKPOINT, pre_model_checkpoint

# Align the qualified sample to the exact STD-BE C6 domain instead of
# accepting two unrelated standalone fixtures as an integration positive.
aligned_mapping = copy.deepcopy(m)
aligned_mapping["front_kind_domains"]["UI_VISUAL"] = ["STD-BE"]
aligned_mapping["domain_stack_layers"]["STD-BE"] = ["BACKEND"]
aligned_binding = copy.deepcopy(pg01_binding)
aligned_binding["architecture_profile"]["active_layers"] = ["BACKEND"]
classification = classify_with_outcome(copy.deepcopy(s),aligned_mapping,pg01_binding=aligned_binding)
assert classification["decision"] == "CANDIDATE_ONLY"
assert classification["dispatch_allowed"] is False
assert classification["status"] == "CANDIDATE_NOT_ADMITTED"

fixture = GateTests()
fixture.setUp()
classified_domains = sorted({d for row in classification["candidate"]["scopes"] for d in row["candidate_domains"]})
assert classified_domains == sorted(fixture.kw["expected_domains"])
run_id = fixture.kw["expected_run_id"]
state = {"plan_code": PLAN, "checkpoint_code": CHECKPOINT,
         "checkpoint_required": True, "run_id": run_id,
         "checkpoint_validation_mode": "BLOCKING_AUTOMATIC",
         "current_receipts": {}}  # Must NOT derive receipt from candidate.
called=[]
def dispatch(data):
    called.append(data)
    return "qualification-mock"

blocked = pre_model_checkpoint(state=copy.deepcopy(state),context=fixture.text,
                                gate_arguments=copy.deepcopy(fixture.kw),dispatch=dispatch)
assert blocked["code"] == "UPSTREAM_CHECKPOINT_RECEIPT_MISSING",blocked
assert blocked["model_called"] is False and not called

# Synthetic receipts are explicitly injected solely to exercise the existing mock.
simulated=copy.deepcopy(state)
simulated["current_receipts"] = {cp:run_id for cp in ("PG-01_C4","PG-01_C6","PG-02_C1","PG-03_C1")}
ok=pre_model_checkpoint(state=simulated,context=fixture.text,
                        gate_arguments=copy.deepcopy(fixture.kw),dispatch=dispatch)
assert ok["code"] == "QUALIFICATION_DISPATCH_SIMULATED",ok
assert ok["model_called"] is True and len(called)==1
assert classification["dispatch_allowed"] is False

# A mismatched C6 domain cannot be silently promoted to a mock dispatch.
domain_drift = copy.deepcopy(fixture.kw)
domain_drift["expected_domains"] = ["STD-FE"]
bad_domain = pre_model_checkpoint(state=copy.deepcopy(simulated),context=fixture.text,
                                  gate_arguments=domain_drift,dispatch=dispatch)
assert bad_domain["code"] == "DOMAIN_BINDING_MISMATCH",bad_domain
assert len(called)==1

replay=copy.deepcopy(simulated)
replay["current_receipts"]["PG-02_C1"]="OTHER-RUN"
denied=pre_model_checkpoint(state=replay,context=fixture.text,
                            gate_arguments=copy.deepcopy(fixture.kw),dispatch=dispatch)
assert denied["code"]=="UPSTREAM_CHECKPOINT_RECEIPT_MISSING"
assert len(called)==1
print("H2C4_PG03_C6_INTEGRATION_PASS candidate_block=1 mock_positive=1 domain_drift_block=1 replay_block=1 production_authority=0")
