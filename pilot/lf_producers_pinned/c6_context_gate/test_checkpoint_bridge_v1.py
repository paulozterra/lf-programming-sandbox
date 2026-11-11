"""E2E simulation: checkpoint must gate model dispatch before the callback."""
import copy
import unittest
from test_context_gate_v1 import GateTests
from checkpoint_bridge_v1 import PLAN, CHECKPOINT, pre_model_checkpoint


class BridgeTests(unittest.TestCase):
    def setUp(self):
        fixture=GateTests()
        fixture.setUp()
        self.kw=fixture.kw
        self.calls=[]
        self.context=self.kw["text"]
        self.state={"plan_code":PLAN,"checkpoint_code":CHECKPOINT,
                    "checkpoint_required":True,"run_id":"E-RUN-1",
                    "current_receipts":{"PG-01_C4":"E-RUN-1","PG-01_C6":"E-RUN-1",
                                        "PG-02_C1":"E-RUN-1","PG-03_C1":"E-RUN-1"},
                    "checkpoint_validation_mode":"BLOCKING_AUTOMATIC"}
    def run_gate(self, **overrides):
        state=copy.deepcopy(self.state)
        params=copy.deepcopy(self.kw)
        state.update(overrides.pop("state",{}))
        params.update(overrides.pop("gate_arguments",{}))
        context=overrides.pop("context",self.context)
        def dispatch(value):
            self.calls.append(value)
            return "mock-only"
        return pre_model_checkpoint(state=state,gate_arguments=params,context=context,
                                     dispatch=dispatch)
    def test_success_calls_model_once(self):
        result=self.run_gate()
        self.assertEqual((result["status"],len(self.calls)),("PASS",1))
    def test_wrong_checkpoint_blocks(self):
        self.assertEqual(self.run_gate(state={"checkpoint_code":"PG-03_C3"})["code"],"CHECKPOINT_NOT_REQUIRED")
        self.assertFalse(self.calls)
    def test_missing_upstream_blocks(self):
        self.assertEqual(self.run_gate(state={"current_receipts":{}})["code"],"UPSTREAM_CHECKPOINT_RECEIPT_MISSING")
        self.assertFalse(self.calls)
    def test_wrong_run_blocks(self):
        self.assertEqual(self.run_gate(state={"run_id":"other"})["code"],"UPSTREAM_CHECKPOINT_RECEIPT_MISSING")
        self.assertFalse(self.calls)
    def test_inactive_validator_blocks(self):
        self.assertEqual(self.run_gate(state={"checkpoint_validation_mode":"CHECK_ONLY"})["code"],"CHECKPOINT_ADMISSION_NOT_ACTIVE")
        self.assertFalse(self.calls)
    def test_no_budget_blocks(self):
        self.assertEqual(self.run_gate(gate_arguments={"approved_budget":None})["status"],"REQUIRES_DECISION")
        self.assertFalse(self.calls)
    def test_context_tampered_blocks(self):
        self.assertEqual(self.run_gate(context=b"tampered")["code"],"PRE_DISPATCH_CONTEXT_CHANGED")
        self.assertFalse(self.calls)
    def test_source_untrusted_blocks(self):
        self.assertEqual(self.run_gate(gate_arguments={"trusted_source":None})["code"],"SOURCE_PROVENANCE_UNVERIFIED")
        self.assertFalse(self.calls)
    def test_production_denied(self):
        self.assertEqual(self.run_gate(gate_arguments={"qualification_only":False})["code"],"PRODUCTION_RELEASE_NOT_ATTESTED")
        self.assertFalse(self.calls)


if __name__=="__main__":
    unittest.main()
