"""PG-03_C2 pre-model checkpoint bridge candidate; never a second scheduler."""
import hashlib
import json
from context_gate_v1 import gate

PLAN = "PROGRAMMING_AGENT_PROGRAMMING_REMEDIATION_V1"
CHECKPOINT = "PG-03_C2"


def pre_model_checkpoint(*, state, context, gate_arguments, dispatch):
    """Requires current-run PG-01 & PG-02 evidence, current checkpoint and gate PASS.

    Dispatch callback is invoked only after all qualifications. This is
    *qualification simulation*; runtime must enforce the same predicate at
    the actual model invocation boundary, not trust a returned status.
    """
    def deny(code, status="BLOCKED"):
        return {"status": status, "code": code, "model_called": False}
    if not isinstance(state, dict) or state.get("plan_code") != PLAN:
        return deny("PLAN_BINDING_INVALID")
    if state.get("checkpoint_code") != CHECKPOINT or state.get("checkpoint_required") is not True:
        return deny("CHECKPOINT_NOT_REQUIRED")
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return deny("RUN_MISSING")
    if state.get("current_receipts") != {"PG-01_C4": run_id, "PG-01_C6": run_id,
                                        "PG-02_C1": run_id, "PG-03_C1": run_id}:
        return deny("UPSTREAM_CHECKPOINT_RECEIPT_MISSING")
    if state.get("checkpoint_validation_mode") != "BLOCKING_AUTOMATIC":
        return deny("CHECKPOINT_ADMISSION_NOT_ACTIVE")
    if gate_arguments.get("expected_run_id") != run_id:
        return deny("VALIDATION_RUN_MISMATCH")
    result = gate(**gate_arguments)
    if result["status"] != "PASS":
        return {**result, "model_called": False}
    if not isinstance(context, bytes) or hashlib.sha256(context).hexdigest() != result["context_sha256"]:
        return deny("PRE_DISPATCH_CONTEXT_CHANGED")
    if gate_arguments.get("text") != context:
        return deny("PRE_DISPATCH_CONTEXT_CHANGED")
    # The receiver must verify the exact binding immediately before dispatch.
    if not callable(dispatch):
        return deny("DISPATCH_UNAVAILABLE")
    output = dispatch(context)
    return {"status": "PASS", "code": "QUALIFICATION_DISPATCH_SIMULATED",
            "model_called": True, "run_id": run_id,
            "context_sha256": result["context_sha256"], "dispatch_result": output}
