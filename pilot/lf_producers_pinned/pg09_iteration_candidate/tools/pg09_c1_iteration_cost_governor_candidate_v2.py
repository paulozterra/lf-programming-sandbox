"""PG09 C1 v2: native zero-*incremental API* use, strict original-v1 fallback.

This candidate never authenticates the subscription price or grants authority.
The returned envelope retains the v1 schema for downstream original C2-C4
producers; v2 metadata is included and its digest recomputed only when the
native source receipt passes the additional fail-closed evidence gate.
Original WORKER_API requests are delegated byte-for-byte to v1.
"""
from __future__ import annotations

import copy
import re
from pg09_c1_iteration_cost_governor_candidate_v1 import (
    prepare_pg09_c1 as prepare_pg09_c1_v1, digest as _digest
)

SHA = re.compile(r"^[0-9a-f]{64}$")
NATIVE_MODES = {"GPT_NATIVE","DETERMINISTIC_TOOL"}

class PG09NativeV2Blocked(ValueError):
    pass

def _block(code):
    raise PG09NativeV2Blocked(code)

def prepare_pg09_c1(*, pg07_c1, pg07_c5, budget_policy,
                     usage_observations, native_execution_evidence=None):
    """For native paths require exact source-bound zero-call proof.

    native_execution_evidence fields (all required):
        executor_mode, api_calls, proposal_sha256,
        expected_proposal_sha256, tool_receipt_ref,
        cost_receipt_ref, status_receipt_ref, subscription_cost.
    A producer-supplied expected SHA is only a *binding*, not an authenticated
    source. The caller must obtain the expected SHA from original receipts.
    """
    if native_execution_evidence is None:
        # Unmodified v1 semantics and JSON/digest for every original call.
        return prepare_pg09_c1_v1(
            pg07_c1=pg07_c1,pg07_c5=pg07_c5,
            budget_policy=budget_policy,usage_observations=usage_observations)
    e=native_execution_evidence
    required={"executor_mode","api_calls","proposal_sha256",
              "expected_proposal_sha256","tool_receipt_ref",
              "cost_receipt_ref","status_receipt_ref","subscription_cost"}
    if not isinstance(e,dict) or set(e)!=required:
        _block("PG09_C1_V2_NATIVE_EVIDENCE_SHAPE_INVALID")
    mode=e["executor_mode"]
    if mode not in NATIVE_MODES:
        _block("PG09_C1_V2_EXECUTOR_MODE_INVALID")
    if type(e["api_calls"]) is not int or e["api_calls"] != 0:
        _block("PG09_C1_V2_NONZERO_API_CALLS")
    proposal=e["proposal_sha256"]
    tool=e["tool_receipt_ref"]
    if mode=="GPT_NATIVE" and (not isinstance(proposal,str) or not proposal):
        _block("PG09_C1_V2_PROPOSAL_SHA_MISSING")
    if proposal is not None and not (isinstance(proposal,str) and SHA.fullmatch(proposal)):
        _block("PG09_C1_V2_PROPOSAL_SHA_INVALID")
    if mode=="DETERMINISTIC_TOOL" and not proposal and not (isinstance(tool,str) and tool.strip()):
        _block("PG09_C1_V2_TOOL_RECEIPT_MISSING")
    if proposal and proposal != e["expected_proposal_sha256"]:
        _block("PG09_C1_V2_PROPOSAL_SHA_DRIFT")
    if (not isinstance(e["cost_receipt_ref"],str) or not e["cost_receipt_ref"].strip()
        or not isinstance(e["status_receipt_ref"],str) or not e["status_receipt_ref"].strip()):
        _block("PG09_C1_V2_SOURCE_RECEIPT_MISSING")
    if e["subscription_cost"]!="NOT_EVALUATED":
        _block("PG09_C1_V2_SUBSCRIPTION_COST_SCOPE_INVALID")
    if not isinstance(usage_observations,list) or not usage_observations:
        _block("PG09_C1_V2_USAGE_NOT_PRESENT")
    for row in usage_observations:
        if (not isinstance(row,dict) or row.get("executor_mode")!=mode or
            not isinstance(row.get("calls"),list) or row["calls"] or
            type(row.get("attempts_used")) is not int):
            _block("PG09_C1_V2_NATIVE_USAGE_CONFLICT")
    # The original v1 provider COST governor is run, not bypassed.
    # Only deterministic tool is mapped to a valid v1 internal mode;
    # the public result keeps the actual GPT_NATIVE/TOOL mode.
    adapted=copy.deepcopy(usage_observations)
    if mode=="DETERMINISTIC_TOOL":
        for row in adapted:
            row["executor_mode"]="GPT_NATIVE"
    out=prepare_pg09_c1_v1(pg07_c1=pg07_c1,pg07_c5=pg07_c5,
                           budget_policy=budget_policy,usage_observations=adapted)
    for row in out["solutions"]:
        row["executor_mode_reported"]=mode
        row["cost_unknown"]=False
        row["known_cost_subtotal_reported"]="0"
        row["calls_reported"]=[]
    for row in out["batch_diagnostics"]:
        row["cost_unknown"]=False
        row["reported_known_cost"]="0"
        row["diagnostic"]="REPORTED_WITHIN_BUDGET_UNVERIFIED"
    out["reported_request_known_cost"]="0"
    out["request_diagnostic"]="REPORTED_WITHIN_BUDGET_UNVERIFIED"
    out["requires_decision_reported"]=False
    out["missing_usage_requires_decision"]=False
    out["eighty_percent_warning_reported"]=False
    out["native_zero_api_attestation_ref"]=e["cost_receipt_ref"]
    out["native_proposal_binding_sha256"]=proposal
    out["native_tool_receipt_ref"]=tool
    out["native_status_receipt_ref"]=e["status_receipt_ref"]
    out["native_incremental_api_calls_reported"]=0
    out["native_incremental_api_cost_reported"]="0"
    out["native_subscription_cost"]="NOT_EVALUATED"
    out["native_evidence_sha256"]=_digest(e)
    out["cost_scope"]="incremental_api"
    # All source-only flags stay False. No retry or production authorization.
    for key in ("iteration_authorized","retry_authorized","model_invoked",
                "production_authority","handoff_allowed","provider_costs_verified",
                "usage_receipts_authenticated","budget_policy_authenticated"):
        if out[key] is not False:
            _block("PG09_C1_V2_AUTHORITY_INVARIANT")
    out["candidate_sha256"]=_digest({k:v for k,v in out.items()
                                      if k!="candidate_sha256"})
    return out
