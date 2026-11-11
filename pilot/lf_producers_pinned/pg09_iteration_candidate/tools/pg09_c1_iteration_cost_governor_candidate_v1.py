"""PG-09_C1 source-only iteration and real-usage-budget projection.

All usage receipts and budgets are caller supplied. This code never invokes
models, charges providers, authorizes retries or authenticates usage.
"""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

SHA256 = re.compile(r"^[0-9a-f]{64}$")
MODES = {"GPT_NATIVE", "CLAUDE_NATIVE", "WORKER_API"}


class PG09C1Blocked(ValueError):
    pass


def fail(reason):
    raise PG09C1Blocked(reason)


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def ref(x):
    return isinstance(x, str) and bool(x.strip())


def money(x):
    if not isinstance(x, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,9})?", x):
        fail("PG09_C1_DECIMAL_FORMAT_INVALID")
    try:
        amount = Decimal(x)
    except InvalidOperation:
        fail("PG09_C1_DECIMAL_INVALID")
    if not amount.is_finite() or amount < 0:
        fail("PG09_C1_DECIMAL_RANGE_INVALID")
    return amount


def frozen(obj, schema):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG09_C1_SOURCE_SCHEMA_INVALID")
    sha = obj.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {k: v for k, v in obj.items() if k != "candidate_sha256"}
    ):
        fail("PG09_C1_SOURCE_DIGEST_INVALID")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED" or
        obj.get("production_authority") is not False or
        obj.get("handoff_allowed") is not False):
        fail("PG09_C1_SOURCE_AUTHORITY_INVALID")
    return sha


def indexed(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG09_C1_SOLUTIONS_MISSING")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not ref(row.get("solution_id")) or row["solution_id"] in out:
            fail("PG09_C1_SOLUTION_ID_INVALID")
        out[row["solution_id"]] = row
    return out


def prepare_pg09_c1(*, pg07_c1, pg07_c5, budget_policy, usage_observations):
    """Project budget thresholds and iteration limits, without authority.

    budget_policy: policy_ref, currency, request_budget, batch_budget,
      max_attempts_per_solution, existing_worker_limit_ref.
    usage_observations: one row per solution: solution_id, executor_mode,
      batch_id, attempts_used, attempt_limit_source_ref, calls.
    calls: call_ref, usage_receipt_ref, usage_authentication_ref,
      provider, model_id, reported_cost, currency, input_tokens,
      output_tokens, cached_input_tokens. If no authentic priced usage
      exists, pass null reported_cost and the projection requires decision.
    """
    c1sha = frozen(pg07_c1, "PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1")
    c5sha = frozen(pg07_c5, "PG07_C5_ITERATION_GUARD_CANDIDATE_V1")
    if (pg07_c5.get("iteration_applied") is not False or
        pg07_c1.get("worker_invoked") is not False or
        pg07_c1.get("dispatch_allowed") is not False):
        fail("PG09_C1_PREMATURE_EXECUTION")
    if not isinstance(budget_policy, dict) or set(budget_policy) != {
        "policy_ref", "currency", "request_budget", "batch_budget",
        "max_attempts_per_solution", "existing_worker_limit_ref"
    }:
        fail("PG09_C1_POLICY_SHAPE_INVALID")
    if not ref(budget_policy["policy_ref"]) or not ref(budget_policy["currency"]) or not ref(budget_policy["existing_worker_limit_ref"]):
        fail("PG09_C1_POLICY_REF_MISSING")
    if (type(budget_policy["max_attempts_per_solution"]) is not int or
        budget_policy["max_attempts_per_solution"] < 1):
        fail("PG09_C1_ATTEMPT_LIMIT_INVALID")
    request_cap, batch_cap = money(budget_policy["request_budget"]), money(budget_policy["batch_budget"])
    if request_cap <= 0 or batch_cap <= 0 or batch_cap > request_cap:
        fail("PG09_C1_BUDGET_LIMIT_INVALID")
    run = pg07_c1.get("run_binding")
    if not isinstance(run, dict) or not ref(run.get("run_ref")):
        fail("PG09_C1_RUN_BINDING_INVALID")
    c5 = indexed(pg07_c5.get("solutions"))
    obs = indexed(usage_observations)
    if set(c5) != set(obs):
        fail("PG09_C1_SOLUTION_COVERAGE_DRIFT")
    if budget_policy["currency"] != run.get("pricing_currency"):
        # No implicit conversion or exchange-rate guessing.
        fail("PG09_C1_CURRENCY_DRIFT")
    global_ids = set()
    batches = {}
    rows = []
    unknown_any = False
    for sid in sorted(obs):
        row = obs[sid]
        if not isinstance(row, dict) or set(row) != {
            "solution_id", "executor_mode", "batch_id", "attempts_used",
            "attempt_limit_source_ref", "calls"
        }:
            fail("PG09_C1_OBSERVATION_SHAPE_INVALID")
        if (row["executor_mode"] not in MODES or not ref(row["batch_id"]) or
            not ref(row["attempt_limit_source_ref"]) or
            type(row["attempts_used"]) is not int or row["attempts_used"] < 0):
            fail("PG09_C1_OBSERVATION_INVALID")
        calls = row["calls"]
        if not isinstance(calls, list):
            fail("PG09_C1_CALLS_INVALID")
        subtotal = Decimal("0")
        unknown = False
        reported_calls = []
        for call in calls:
            if not isinstance(call, dict) or set(call) != {
                "call_ref", "usage_receipt_ref", "usage_authentication_ref",
                "provider", "model_id", "reported_cost", "currency",
                "input_tokens", "output_tokens", "cached_input_tokens"
            }:
                fail("PG09_C1_CALL_SHAPE_INVALID")
            if (not ref(call["call_ref"]) or call["call_ref"] in global_ids or
                not ref(call["provider"]) or not ref(call["model_id"]) or
                call["currency"] != budget_policy["currency"]):
                fail("PG09_C1_CALL_IDENTITY_INVALID")
            global_ids.add(call["call_ref"])
            if any(type(call[k]) is not int or call[k] < 0 for k in (
                "input_tokens", "output_tokens", "cached_input_tokens"
            )):
                fail("PG09_C1_TOKEN_COUNTER_INVALID")
            # Native subscription/chat inference may lack billable usage.
            # Missing price must never be counted as free.
            priced = call["reported_cost"] is not None
            if priced and not ref(call["usage_receipt_ref"]):
                fail("PG09_C1_COST_WITHOUT_RECEIPT")
            if call["usage_receipt_ref"] is not None and not ref(call["usage_receipt_ref"]):
                fail("PG09_C1_RECEIPT_REF_INVALID")
            if call["usage_authentication_ref"] is not None and not ref(call["usage_authentication_ref"]):
                fail("PG09_C1_AUTH_REF_INVALID")
            if priced:
                subtotal += money(call["reported_cost"])
            else:
                unknown = True
            reported_calls.append({
                "call_ref": call["call_ref"],
                "usage_receipt_ref_reported": call["usage_receipt_ref"],
                "usage_authentication_ref_reported": call["usage_authentication_ref"],
                "provider_reported": call["provider"],
                "model_id_reported": call["model_id"],
                "reported_cost": call["reported_cost"],
                "input_tokens_reported": call["input_tokens"],
                "output_tokens_reported": call["output_tokens"],
                "cached_input_tokens_reported": call["cached_input_tokens"],
                "usage_authenticated": False
            })
        # A missing call ledger is not evidence of zero spend.
        if not calls and row["attempts_used"] > 0:
            unknown = True
        if row["executor_mode"] != "WORKER_API":
            # Native executions must not inherit an API pricing contract,
            # even if a caller supplied a numeric cost.
            unknown = True
        unknown_any |= unknown
        batches.setdefault(row["batch_id"], []).append((sid, subtotal, unknown))
        rows.append({
            "solution_id": sid, "batch_id": row["batch_id"],
            "executor_mode_reported": row["executor_mode"],
            "attempts_used_reported": row["attempts_used"],
            "existing_worker_limit_ref_reported": row["attempt_limit_source_ref"],
            "max_attempts_reported": budget_policy["max_attempts_per_solution"],
            "known_cost_subtotal_reported": str(subtotal),
            "cost_unknown": unknown,
            "calls_reported": reported_calls,
            "attempt_limit_reached": row["attempts_used"] >= budget_policy["max_attempts_per_solution"],
            "usage_authenticated": False
        })
    batch_diagnostics = []
    stop = False
    warn = False
    for bid, records in sorted(batches.items()):
        known_total = sum((s for _, s, _ in records), Decimal("0"))
        has_unknown = any(u for _, _, u in records)
        ratio = known_total / batch_cap
        status = ("REQUIRES_DECISION" if has_unknown or ratio >= 1 else
                  "WARN_80_PERCENT" if ratio >= Decimal("0.8") else
                  "REPORTED_WITHIN_BUDGET_UNVERIFIED")
        stop |= status == "REQUIRES_DECISION"
        warn |= status == "WARN_80_PERCENT"
        batch_diagnostics.append({
            "batch_id": bid, "reported_known_cost": str(known_total),
            "batch_cap": str(batch_cap), "cost_unknown": has_unknown,
            "diagnostic": status
        })
    request_known = sum((money(r["known_cost_subtotal_reported"]) for r in rows), Decimal("0"))
    request_ratio = request_known / request_cap
    attempts_reached = any(r["attempt_limit_reached"] for r in rows)
    request_status = ("REQUIRES_DECISION" if unknown_any or request_ratio >= 1 or stop or attempts_reached
        else "WARN_80_PERCENT" if request_ratio >= Decimal("0.8") or warn
        else "REPORTED_WITHIN_BUDGET_UNVERIFIED")
    result = {
        "schema_version": "PG09_C1_ITERATION_COST_GOVERNOR_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg07_c1_sha256": c1sha,
        "source_pg07_c5_sha256": c5sha,
        "run_ref": run["run_ref"],
        "budget_policy_ref": budget_policy["policy_ref"],
        "budget_policy_sha256": digest(budget_policy),
        "usage_observations_sha256": digest(usage_observations),
        "currency": budget_policy["currency"],
        "request_budget": str(request_cap),
        "batch_budget": str(batch_cap),
        "reported_request_known_cost": str(request_known),
        "request_diagnostic": request_status,
        "batch_diagnostics": batch_diagnostics,
        "solutions": rows,
        "eighty_percent_warning_reported": request_status == "WARN_80_PERCENT",
        "requires_decision_reported": request_status == "REQUIRES_DECISION",
        "missing_usage_requires_decision": unknown_any,
        "iteration_limit_reached_reported": attempts_reached,
        "usage_receipts_authenticated": False,
        "budget_policy_authenticated": False,
        "worker_limits_authenticated": False,
        "provider_costs_verified": False,
        "iteration_authorized": False,
        "retry_authorized": False,
        "model_invoked": False,
        "pg09_c1_pass": False,
        "pg09_c1_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "AUTHENTICATED_RUNTIME_USAGE_BUDGET_THRESHOLD_AND_WORKER_ATTEMPT_LIMIT"
    }
    result["candidate_sha256"] = digest(result)
    return result
