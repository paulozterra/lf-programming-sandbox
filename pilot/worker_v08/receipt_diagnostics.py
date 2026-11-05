#!/usr/bin/env python3
"""Allowlist-only public diagnostics derived from the ORIGINAL sealed Worker receipts.

Private originals are never uploaded. This deliberately does NOT claim the
projected public JSON remains an original cryptographic receipt. Preserve its
source hash for independent examination by an authorized auditor.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

MISSING_USAGE_MESSAGE="usage no disponible – verificar en la consola de Anthropic"
PUBLIC_FIELDS=("schema_version","task_id","task_sha256","base_head_sha",
               "source_snapshot_sha256","model_provider","requested_model",
               "resolved_model","visible_status","status","patch_delivered",
               "visible_receipt_sha256","receipt_sha256")
TOKEN_REASON=re.compile(r"^(MODEL_ERROR|MODEL_REFUSAL|MODEL_NOT_CALLED|PROPOSAL_INVALID|"
                        r"ACCEPTANCE_FAILED|VISIBLE_[A-Z_]+|BLOCKED|FAIL|PASS)")
HTTP_CODE=re.compile(r"\b(?:HTTP|status(?:_code)?)[ :=\x27\"]+(400|401|403|404|408|409|422|429|500|502|503|504)\b",re.I)

def safe_reason(original, proposal_reason=None):
    """Never propagate arbitrary exceptions, provider messages or model outputs.

    A model-error code and a limited HTTP status are enough to distinguish
    incorrect model identifiers, refusals, rate limits and transport failures
    without accidentally exporting API response bodies, tokens or prompts.
    """
    a=str(proposal_reason or "")
    b=str(original or "")
    category=(a if a in ("MODEL_ERROR","MODEL_REFUSAL","MODEL_NOT_CALLED") else None)
    if category is None:
        m=TOKEN_REASON.search(b)
        category=m.group(1) if m else "WORKER_ERROR_REDACTED"
    code=HTTP_CODE.search(b)
    return category+(": HTTP "+code.group(1) if code else " (detalle privado redactado)")

def public_receipt(receipt, kind, model_category=None):
    if not isinstance(receipt,dict) or kind not in ("visible","verified"):
        raise ValueError("RECEIPT_DIAGNOSTIC_BAD_INPUT")
    projected={k:receipt[k] for k in PUBLIC_FIELDS if k in receipt}
    attempts=receipt.get("attempts",[])
    if not isinstance(attempts,list):
        attempts=[]
    projected["attempts"]=[
        {"attempt":a.get("attempt"),"proposal_reason":safe_reason(
            a.get("proposal_reason"),a.get("proposal_reason")),
         "usage_available":bool(isinstance(a.get("usage"),dict) and
             type(a["usage"].get("input_tokens")) is int and
             type(a["usage"].get("output_tokens")) is int)}
        for a in attempts if isinstance(a,dict)
    ]
    # The verified receipt does not contain attempts, so the original visible
    # receipt is essential to understand MODEL_ERROR/MODEL_REFUSAL.
    first=next((a.get("proposal_reason") for a in attempts
                if isinstance(a,dict) and a.get("proposal_reason") in
                ("MODEL_ERROR","MODEL_REFUSAL")),None)
    projected["reason"]=safe_reason(receipt.get("reason"),model_category or first)
    projected["source_receipt_sha256"]=receipt.get("receipt_sha256")
    projected["diagnostic_kind"]=kind
    projected["sanitized"]=True
    projected["original_seal_not_claimed"]=True
    projected["response_text_exported"]=False
    return projected

def write_public_receipt(directory:Path,receipt:dict,kind:str,model_category=None):
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=directory/("visible-worker-receipt.json" if kind=="visible" else "verified-worker-receipt.json")
    if path.exists():
        raise ValueError("PUBLIC_RECEIPT_ALREADY_PRESENT")
    raw=json.dumps(public_receipt(receipt,kind,model_category),ensure_ascii=False,
                   sort_keys=True,indent=2,allow_nan=False).encode()+b"\n"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path

def write_usage_unavailable(directory:Path,visible:dict,verified:dict):
    """Report uncertainty without inventing token counts or USD amount."""
    category=next((a.get("proposal_reason") for a in visible.get("attempts",[])
                   if isinstance(a,dict) and a.get("proposal_reason") in
                   ("MODEL_ERROR","MODEL_REFUSAL")),None)
    if category is None:
        return False
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=directory/"cost.json"
    if path.exists():
        raise ValueError("PUBLIC_COST_ALREADY_PRESENT")
    value={"schema_version":"LF_WORKER_MISSING_USAGE_DIAGNOSTIC_V1",
           "usage_status":"UNAVAILABLE",
           "message":MISSING_USAGE_MESSAGE,
           "reason":safe_reason(visible.get("reason"),category),
           "task_id":visible.get("task_id"),
           "visible_source_receipt_sha256":visible.get("receipt_sha256"),
           "verified_source_receipt_sha256":verified.get("receipt_sha256"),
           "total_estimated_usd":None,
           "billing_status":"UNKNOWN_NOT_ZERO",
           "model_call_was_attempted":True,
           "charge_verification_required":True}
    path.write_bytes(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False).encode()+b"\n")
    path.chmod(0o600)
    return True
