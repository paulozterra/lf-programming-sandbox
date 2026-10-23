"""Contrato C11: precios, presupuestos y costos medidos. Solo stdlib."""
import argparse
import copy
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parents[1]/"consumption"
DECIMAL=re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]{1,12})?$")
FORBIDDEN={"prompt","response_text","messages","context","patch","payload"}
WASTED={"FAILED_ATTEMPT","EXPIRED_PACKAGE_REWORK","TESTING_FINDING_REWORK","NON_CONVERGENT_ITERATION"}
TTL={"5m","1h","30m","12h"}


def read():
    return [json.loads((BASE/name).read_text(encoding="utf8")) for name in ("pricing.json","policy.json")]


def digest(row):
    # El cierre permitido de valid_to no altera la identidad histórica del precio.
    immutable={k:v for k,v in row.items() if k!="valid_to"}
    return hashlib.sha256(json.dumps(immutable,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def date(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))


def validate(pricing,policy):
    errors=[]
    models=pricing.get("models",[])
    for i,row in enumerate(models):
        source=row.get("source_url","")
        if not source.startswith(("https://developers.openai.com/","https://platform.claude.com/","https://www.anthropic.com/")):
            errors.append("MISSING_PRICE_SOURCE")
        if row.get("status") not in ("VERIFIED","UNVERIFIED") or row.get("approved_for_use") is not False:
            errors.append("INVALID_PRICE_STATUS")
        for x in [row.get("prices",{}).get(k) for k in ("input","output","cache_read")]+list(row.get("prices",{}).get("cache_write_by_ttl",{}).values()):
            if not isinstance(x,str) or not DECIMAL.fullmatch(x):
                errors.append("FLOAT_PRICE_FORBIDDEN")
        if any(k not in TTL for k in row.get("prices",{}).get("cache_write_by_ttl",{})):
            errors.append("INVALID_TTL")
        for other in models[:i]:
            if (row["provider"],row["model"],row["service_tier"])!=(other["provider"],other["model"],other["service_tier"]):
                continue
            low=max(date(row["valid_from"]),date(other["valid_from"]))
            hi=min(date(row["valid_to"]) if row.get("valid_to") else datetime.max.replace(tzinfo=timezone.utc),
                   date(other["valid_to"]) if other.get("valid_to") else datetime.max.replace(tzinfo=timezone.utc))
            if low<hi:errors.append("OVERLAPPING_PRICE_VALIDITY")
    modes=policy.get("modes",{})
    if set(modes)!={"STANDARD"}:errors.append("CONTROL_OVERRIDE_FORBIDDEN")
    for mode in modes.values():
        if mode.get("difficulty_model_routing") is not False:errors.append("MODEL_ROUTING_FORBIDDEN")
        if not all(mode.get(k) is True for k in ("stable_context_cache","minimum_context","no_rediscovery","early_stop")) or mode.get("controls")!={"standards":True,"reviews":True,"tests":True}:
            errors.append("CONTROL_OVERRIDE_FORBIDDEN")
    if policy.get("budget",{}).get("warning_percent")!=80 or policy.get("budget",{}).get("decision_percent")!=100:
        errors.append("BUDGET_THRESHOLD_FIXED_BY_D17")
    if policy.get("budget",{}).get("amount")!="POR_DEFINIR":
        errors.append("UNAPPROVED_BUDGET_AMOUNT")
    return sorted(set(errors))


def select_price(pricing,event):
    at=date(event["occurred_at"])
    matches=[r for r in pricing["models"] if r["provider"]==event["provider"] and r["model"]==event["model"] and r["service_tier"]==event["service_tier"]
      and date(r["valid_from"])<=at and (r.get("valid_to") is None or at<date(r["valid_to"]))]
    if len(matches)!=1:raise ValueError("NO_UNAMBIGUOUS_PRICE")
    row=matches[0]
    if row["status"]!="VERIFIED":raise ValueError("UNVERIFIED_PRICE_USED")
    return row


def cost(pricing,event):
    if FORBIDDEN.intersection(event):raise ValueError("SCHEMA_REJECTED")
    if event.get("measurement")=="ESTIMATED":raise ValueError("ESTIMATED_TOKENS_FORBIDDEN")
    if event.get("measurement")=="MEASURED" and not event.get("provider_response_id"):
        raise ValueError("MEASUREMENT_WITHOUT_EVIDENCE")
    row=select_price(pricing,event)
    t=[event.get(x) for x in ("input_tokens","output_tokens","cache_read_tokens","cache_write_tokens")]
    if any(x is None or type(x) is not int or x<0 for x in t):raise ValueError("UNMEASURED_TOKENS")
    breakdown=event.get("cache_write_ttl_breakdown",{})
    if any(k not in row["prices"]["cache_write_by_ttl"] or type(v) is not int or v<0 for k,v in breakdown.items()):
        raise ValueError("INVALID_TTL")
    if sum(breakdown.values())!=t[3]:raise ValueError("CACHE_TTL_SUM_MISMATCH")
    ordinary=t[0]-t[2]-t[3] if row["cache_accounting"]=="INPUT_INCLUDES_CACHE" else t[0]
    if ordinary<0:raise ValueError("CACHE_EXCEEDS_INPUT")
    p=row["prices"]
    total=Decimal(ordinary)*Decimal(p["input"])+Decimal(t[1])*Decimal(p["output"])+Decimal(t[2])*Decimal(p["cache_read"])
    total+=sum((Decimal(v)*Decimal(p["cache_write_by_ttl"][k]) for k,v in breakdown.items()),Decimal(0))
    calculated=(total/Decimal(1000000)).quantize(Decimal("0.000000000001"))
    return {"cost":format(calculated,"f"),"currency":"USD","pricing_version":pricing["pricing_version"],"price_row_sha256":digest(row),"cost_status":"CALCULATED"}


def budget(policy,used,has_unmeasured=False):
    b=policy["budget"]
    if b["amount"]=="POR_DEFINIR":return {"decision":"BUDGET_UNCONFIGURED_MEASURE_ONLY"}
    limit=Decimal(b["amount"])
    if has_unmeasured:return {"decision":"REQUIRES_DECISION" if Decimal(used)>=limit*Decimal("0.8") else "UNMEASURED_BALANCE"}
    x=Decimal(used)/limit
    return {"decision":"REQUIRES_DECISION" if x>=1 else "WARNING_80_PERCENT" if x>=Decimal("0.8") else "WITHIN_BUDGET"}


def rendered(pricing,policy):
    lines=["# Consumo C11","","> Generado desde pricing.json y policy.json.","",
           f"Pricing {pricing['pricing_version']} · Policy {policy['policy_version']}","",
           "| Proveedor | Modelo | Tier | Input | Output | Cache read | Escrituras TTL | Estado | Aprobado |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in pricing["models"]:
        p=r["prices"]
        lines.append(f"| {r['provider']} | {r['model']} | {r['service_tier']} | {p['input']} | {p['output']} | {p['cache_read']} | {', '.join(k+': '+v for k,v in p['cache_write_by_ttl'].items())} | {r['status']} | {r['approved_for_use']} |")
    lines.extend(["",f"Modo: {policy['mode']} · Presupuesto: {policy['budget']['amount']}",""])
    return "\n".join(lines)


def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("validate")
    r=sub.add_parser("render");r.add_argument("--check",action="store_true")
    c=sub.add_parser("cost");c.add_argument("--event",required=True)
    b=sub.add_parser("budget");b.add_argument("--used",default="0");b.add_argument("--unmeasured",action="store_true")
    a=p.parse_args(argv)
    pricing,policy=read()
    if a.action=="validate":
        issues=validate(pricing,policy)
        print(json.dumps({"findings":issues,"verdict":"FAIL" if issues else "PASS"}))
        return int(bool(issues))
    if a.action=="render":
        content=rendered(pricing,policy);file=BASE/"CONSUMO.md"
        if a.check:return int(not file.exists() or file.read_text(encoding="utf8")!=content)
        file.write_text(content,encoding="utf8");return 0
    if a.action=="cost":
        try: print(json.dumps(cost(pricing,json.loads(Path(a.event).read_text(encoding="utf8")))));return 0
        except ValueError as ex:print(str(ex));return 1
    print(json.dumps(budget(policy,a.used,a.unmeasured)));return 0

if __name__=="__main__":
    raise SystemExit(main())
