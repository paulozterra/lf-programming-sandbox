#!/usr/bin/env python3
"""External-only Worker usage cost estimate. NEVER mutates sealed Worker receipt."""
import json
from decimal import Decimal
from pathlib import Path
from pg07_to_worker_v1_adapter import AdapterBlocked,sha_bytes,canonical,fail

PRICING=Path(__file__).resolve().with_name("pricing_v1.json")
def _counts(usage):
    if not isinstance(usage,dict):fail("USAGE_MISSING")
    i=usage.get("input_tokens");o=usage.get("output_tokens")
    if type(i) is not int or i<0 or type(o) is not int or o<0:
        fail("USAGE_INPUT_OUTPUT_TOKENS_MISSING")
    return i,o
def price_receipt(worker_receipt,pricing=None):
    if not isinstance(worker_receipt,dict):fail("RECEIPT_INVALID")
    provider=worker_receipt.get("model_provider")
    model=worker_receipt.get("resolved_model") or worker_receipt.get("requested_model")
    if provider=="fake":
        # Bounded only to the deterministic FakeModel in original
        # programming-agent tests/test_worker.py. NEVER priced as Anthropic.
        if (worker_receipt.get("requested_model")!="fake-code-model" or
            model!="fake-code-model-001" or pricing is not None):
            fail("FAKE_MODEL_ID_OR_OVERRIDE_FORBIDDEN")
        table={"schema_version":"LF_WORKER_PILOT_PRICE_TABLE_V1",
               "version":"FAKE_MODEL_NO_BILLING_V1",
               "currency":"USD","price_unit":"per_1_000_000_tokens",
               "source_kind":"TEST_ONLY_MODEL_FAKE_NOT_BILLABLE",
               "models":{"fake-code-model-001":{
                    "provider":"fake","input_usd_per_million":"0",
                    "output_usd_per_million":"0"}}}
    elif provider=="anthropic":
        table=pricing or json.loads(PRICING.read_text(encoding="utf-8"))
    else:
        fail("PROVIDER_INVALID")
    if table.get("schema_version")!="LF_WORKER_PILOT_PRICE_TABLE_V1":fail("PRICE_TABLE_SCHEMA_INVALID")
    if not isinstance(model,str) or model not in table.get("models",{}):
        fail("UNPRICED_MODEL_BLOCKED")
    amounts=table["models"][model]
    if amounts.get("provider")!=provider:fail("PRICE_PROVIDER_MISMATCH")
    try:
        ip=Decimal(amounts["input_usd_per_million"])
        op=Decimal(amounts["output_usd_per_million"])
    except Exception:fail("PRICE_TABLE_INVALID")
    if ip<0 or op<0:fail("PRICE_NEGATIVE")
    attempts=worker_receipt.get("attempts")
    # The original Worker receipt has attempts[*].usage; hardened receipts may
    # wrap it under visible_receipt. Do not fabricate zero usage.
    if not isinstance(attempts,list) and isinstance(worker_receipt.get("visible_receipt"),dict):
        attempts=worker_receipt["visible_receipt"].get("attempts")
    if not isinstance(attempts,list) or not attempts:fail("ATTEMPT_USAGE_MISSING")
    records=[]
    total_in=total_out=0
    total=Decimal("0")
    for index,a in enumerate(attempts,1):
        if not isinstance(a,dict) or a.get("attempt")!=index:fail("ATTEMPT_SEQUENCE_INVALID")
        i,o=_counts(a.get("usage"))
        cost=(Decimal(i)*ip+Decimal(o)*op)/Decimal(1000000)
        total_in+=i;total_out+=o;total+=cost
        records.append({"attempt":index,"input_tokens":i,"output_tokens":o,
                        "estimated_usd":str(cost.normalize())})
    result={"schema_version":"LF_WORKER_COST_V1","price_table_version":table["version"],
            "price_table_sha256":sha_bytes(canonical(table)),"model":model,
            "currency":"USD","receipt_sha256":worker_receipt.get("receipt_sha256"),
            "model_provider":provider,"real_api_usage":provider!="fake",
            "attempts":records,"total_input_tokens":total_in,
            "total_output_tokens":total_out,"total_estimated_usd":str(total.normalize()),
            "estimation_not_invoice":True}
    return result
def write_cost_outside(worker_receipt_path,output_path):
    receipt=json.loads(Path(worker_receipt_path).read_text(encoding="utf-8"))
    result=price_receipt(receipt)
    source=Path(worker_receipt_path).resolve();dest=Path(output_path).resolve()
    if dest==source or dest.exists():fail("COST_OUTPUT_CONFLICT")
    dest.write_bytes(canonical(result)+b"\n")
    return result
