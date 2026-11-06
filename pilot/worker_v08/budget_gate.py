#!/usr/bin/env python3
"""Pre-API conservative USD budget gate for the LF Worker manual pilot.

60,000 context *BYTES* are counted as 60,000 input-token units, conservatively
(no favorable bytes-to-tokens conversion). Output is the fixed 8,000 token cap.
Actual consumption is checked again using the original sealed Worker receipt.
"""
from __future__ import annotations
import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

PRICING = Path(__file__).resolve().parent/"cost_adapter/pricing_v1.json"
MAX_CONTEXT_UNITS=60000
MAX_OUTPUT_TOKENS=8000
ALLOWED={"claude-haiku-5-5":Decimal("0.03"),
         "claude-sonnet-5-5":Decimal("0.20")}
MODEL_ATTEMPT_LIMITS={"claude-haiku-5-5":3,"claude-sonnet-5-5":1}
EX3_CEILING=Decimal("0.35")
EX3_OUTPUT_TOKENS=16000
MAX_ATTEMPTS=3

class BudgetBlocked(ValueError):
    pass

def quote(model: str,attempts: int,pricing_path:Path=PRICING,*,task:str="exercise-1") -> dict:
    if task not in ("exercise-1","exercise-2","exercise-3"):
        raise BudgetBlocked("PILOT_TASK_FORBIDDEN")
    if task=="exercise-3" and (model!="claude-sonnet-5-5" or attempts!=1):
        raise BudgetBlocked("PILOT_EXERCISE3_MODEL_ATTEMPTS_FORBIDDEN")
    if model not in ALLOWED:raise BudgetBlocked("PILOT_MODEL_FORBIDDEN")
    if type(attempts) is not int or not 1<=attempts<=MAX_ATTEMPTS:
        raise BudgetBlocked("PILOT_ATTEMPTS_FORBIDDEN")
    if attempts>MODEL_ATTEMPT_LIMITS[model]:
        raise BudgetBlocked("PILOT_MODEL_ATTEMPTS_EXCEEDED")
    table=json.loads(pricing_path.read_text(encoding="utf-8"))
    if (table.get("schema_version")!="LF_WORKER_PILOT_PRICE_TABLE_V1" or
        table.get("currency")!="USD" or
        table.get("price_unit")!="per_1_000_000_tokens" or
        not isinstance(table.get("version"),str) or not table["version"]):
        raise BudgetBlocked("PILOT_PRICE_VERSION_INVALID")
    record=table.get("models",{}).get(model)
    if not isinstance(record,dict) or record.get("provider")!="anthropic":
        raise BudgetBlocked("PILOT_PRICE_MODEL_NOT_FOUND")
    try:
        ip=Decimal(record["input_usd_per_million"])
        op=Decimal(record["output_usd_per_million"])
    except (KeyError,ValueError,InvalidOperation,TypeError):
        raise BudgetBlocked("PILOT_PRICE_INVALID")
    if not all(x.is_finite() and x>0 for x in (ip,op)):
        raise BudgetBlocked("PILOT_PRICE_INVALID")
    # Explicit conservative upper-bound; using both rates separately, not an average.
    output_limit=EX3_OUTPUT_TOKENS if task=="exercise-3" else MAX_OUTPUT_TOKENS
    ceiling=EX3_CEILING if task=="exercise-3" else ALLOWED[model]
    per=(Decimal(MAX_CONTEXT_UNITS)*ip+Decimal(output_limit)*op)/Decimal(1000000)
    worst=per*attempts
    return {"model":model,"max_attempts":attempts,
            "pricing_version":table["version"],"assumed_max_input_tokens":MAX_CONTEXT_UNITS,
            "max_output_tokens":output_limit,
            "input_usd_per_million":str(ip),"output_usd_per_million":str(op),
            "worst_case_usd":str(worst),"ceiling_usd":str(ceiling),
            "allowed":worst<=ceiling,
            "estimate_not_provider_cap":True}

def require(model:str,attempts:int,pricing_path:Path=PRICING,*,task:str="exercise-1")->dict:
    result=quote(model,attempts,pricing_path,task=task)
    if not result["allowed"]:
        raise BudgetBlocked("PILOT_PREMODEL_BUDGET_EXCEEDED")
    return result

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--model",required=True,choices=sorted(ALLOWED))
    p.add_argument("--attempts",required=True,type=int)
    p.add_argument("--task",choices=("exercise-1","exercise-2","exercise-3"),default="exercise-1")
    args=p.parse_args()
    outcome=quote(args.model,args.attempts,task=args.task)
    print("PILOT_PREMODEL_BUDGET_"+("PASS" if outcome["allowed"] else "BLOCK")+
          " model="+outcome["model"]+" attempts="+str(outcome["max_attempts"])+
          " worst_usd="+outcome["worst_case_usd"]+" ceiling_usd="+outcome["ceiling_usd"])
    return 0 if outcome["allowed"] else 1

if __name__=="__main__":
    raise SystemExit(main())
