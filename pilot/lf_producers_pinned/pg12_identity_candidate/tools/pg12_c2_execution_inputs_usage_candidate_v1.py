"""PG-12_C2: input, environment, usage and glossary manifest (source-only).

This never asserts model billing accuracy, cache accounting, authenticated
catalog/skills/EKB, canonical term IDs, or an actual execution receipt.
"""
import hashlib
import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation

C1_SCHEMA = "PG12_C1_CANDIDATE_IDENTITY_V1"
OPTIMIZATIONS = {"NONE", "CONTEXT_SELECTION", "SKILL_SELECTION", "CACHE_REUSE",
                 "MODEL_ROUTING", "HYBRID", "OTHER_TYPED"}
QUERY_REASONS = {"EVIDENCE_GAP", "REQUIREMENT_GAP", "TOOLCHAIN_GAP",
                 "CONTRACT_GAP", "DEPENDENCY_GAP", "GLOSSARY_GAP"}
class PG12C2Blocked(ValueError):
    pass

def fail(code):
    raise PG12C2Blocked(code)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()

def ref(x):
    return isinstance(x, str) and bool(x.strip()) and x == x.strip()

def unique_refs(values):
    return isinstance(values, list) and all(ref(x) for x in values) and len(set(values)) == len(values)

def count(x):
    return type(x) is int and x >= 0

def money(x):
    if not isinstance(x, str):
        return False
    try:
        value = Decimal(x)
        return value.is_finite() and value >= 0 and value.as_tuple().exponent >= -6
    except (InvalidOperation, ValueError):
        return False

def usage(row, *, key_required):
    fields = {"stage_ref", "input_tokens", "output_tokens", "cached_input_tokens",
              "cost_reported", "wasted_cost_reported"}
    if not isinstance(row, dict) or set(row) != fields or (
        key_required and not ref(row["stage_ref"])):
        fail("PG12_C2_USAGE_SHAPE_INVALID")
    if not all(count(row[k]) for k in ("input_tokens", "output_tokens", "cached_input_tokens")):
        fail("PG12_C2_USAGE_COUNT_INVALID")
    if row["cached_input_tokens"] > row["input_tokens"]:
        fail("PG12_C2_CACHE_EXCEEDS_INPUT")
    if not money(row["cost_reported"]) or not money(row["wasted_cost_reported"]):
        fail("PG12_C2_USAGE_COST_INVALID")
    if Decimal(row["wasted_cost_reported"]) > Decimal(row["cost_reported"]):
        fail("PG12_C2_WASTE_EXCEEDS_COST")

def prepare_pg12_c2(*, pg12_c1, context_id, catalog_version_ref, skill_versions,
                    stack_profile_ref, provider_ref, model_ref, ekb_snapshot_ref,
                    toolchain_versions, linter_config_sha256, optimization_mode,
                    usage_totals, usage_by_stage, extra_queries, identifier_term_map,
                    billing_currency):
    """Prepare complete declared PG-12_C2 metadata.

    skill_versions/toolchain_versions: [{name, version_ref}]
    usage_totals: usage row, stage_ref="TOTAL"
    usage_by_stage: usage rows, stage_ref nonempty and != "TOTAL"
    extra_queries: [{query_id, reason_type, resolver_ref, exact_query_ref}]
    identifier_term_map: [{identifier_ref, term_ids:[...], glossary_source_ref}]
    """
    if not isinstance(pg12_c1, dict) or pg12_c1.get("schema_version") != C1_SCHEMA:
        fail("PG12_C2_C1_SCHEMA_INVALID")
    c1_sha = digest({k:v for k,v in pg12_c1.items() if k != "candidate_sha256"})
    if pg12_c1.get("candidate_sha256") != c1_sha:
        fail("PG12_C2_C1_DIGEST_INVALID")
    for k in ("pg12_c1_pass","pg12_c1_admitted","handoff_allowed",
              "production_authority","identity_reconstructable_verified"):
        if pg12_c1.get(k) is not False:
            fail("PG12_C2_C1_AUTHORITY_INVALID")
    if pg12_c1.get("status") != "CANDIDATE_NOT_ADMITTED":
        fail("PG12_C2_C1_STATUS_INVALID")
    if not all(ref(v) for v in (context_id, catalog_version_ref, stack_profile_ref,
                               provider_ref, model_ref, ekb_snapshot_ref, billing_currency)):
        fail("PG12_C2_REQUIRED_INPUT_REFERENCE_INVALID")
    if not isinstance(linter_config_sha256, str) or len(linter_config_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in linter_config_sha256):
        fail("PG12_C2_LINTER_DIGEST_INVALID")
    if optimization_mode not in OPTIMIZATIONS:
        fail("PG12_C2_OPTIMIZATION_MODE_INVALID")
    def versioned(values, code):
        if not isinstance(values, list) or not values:
            fail(code)
        seen = set()
        for item in values:
            if not isinstance(item, dict) or set(item) != {"name","version_ref"} or (
                not ref(item["name"]) or not ref(item["version_ref"]) or item["name"] in seen):
                fail(code)
            seen.add(item["name"])
        return sorted(deepcopy(values), key=lambda x: x["name"])
    skills = versioned(skill_versions, "PG12_C2_SKILLS_INVALID")
    tools = versioned(toolchain_versions, "PG12_C2_TOOLCHAIN_INVALID")
    usage(usage_totals, key_required=True)
    if usage_totals["stage_ref"] != "TOTAL" or not isinstance(usage_by_stage,list) or not usage_by_stage:
        fail("PG12_C2_USAGE_STAGES_INVALID")
    seen, costs, waste = set(), Decimal("0"), Decimal("0")
    amounts = {"input_tokens":0, "output_tokens":0, "cached_input_tokens":0}
    for row in usage_by_stage:
        usage(row, key_required=True)
        stage = row["stage_ref"]
        if stage == "TOTAL" or stage in seen:
            fail("PG12_C2_STAGE_DUPLICATE")
        seen.add(stage)
        for key in amounts:
            amounts[key] += row[key]
        costs += Decimal(row["cost_reported"])
        waste += Decimal(row["wasted_cost_reported"])
    if any(usage_totals[k] != amounts[k] for k in amounts) or (
        Decimal(usage_totals["cost_reported"]) != costs) or (
        Decimal(usage_totals["wasted_cost_reported"]) != waste):
        fail("PG12_C2_USAGE_TOTAL_MISMATCH")
    if not isinstance(extra_queries, list) or not isinstance(identifier_term_map,list):
        fail("PG12_C2_EXTRA_OR_GLOSSARY_INVALID")
    qseen, queries = set(), []
    for query in extra_queries:
        if not isinstance(query,dict) or set(query) != {
            "query_id","reason_type","resolver_ref","exact_query_ref"}:
            fail("PG12_C2_QUERY_SHAPE_INVALID")
        qid = query["query_id"]
        if not ref(qid) or qid in qseen or query["reason_type"] not in QUERY_REASONS or not (
            ref(query["resolver_ref"]) and ref(query["exact_query_ref"])):
            fail("PG12_C2_QUERY_INVALID")
        qseen.add(qid)
        queries.append(deepcopy(query))
    iseen, terms = set(), []
    for row in identifier_term_map:
        if not isinstance(row,dict) or set(row) != {
            "identifier_ref","term_ids","glossary_source_ref"}:
            fail("PG12_C2_TERM_MAP_SHAPE_INVALID")
        identifier = row["identifier_ref"]
        if not ref(identifier) or identifier in iseen or not ref(row["glossary_source_ref"]) or (
            not unique_refs(row["term_ids"]) or not row["term_ids"]):
            fail("PG12_C2_TERM_MAP_INVALID")
        iseen.add(identifier)
        terms.append(deepcopy(row))
    result = {
        "schema_version":"PG12_C2_EXECUTION_INPUTS_USAGE_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg12_c1_sha256":c1_sha,
        "context_id_reported":context_id,
        "catalog_version_ref_reported":catalog_version_ref,
        "skill_versions_reported":skills,
        "stack_profile_ref_reported":stack_profile_ref,
        "provider_ref_reported":provider_ref,
        "model_ref_reported":model_ref,
        "ekb_snapshot_ref_reported":ekb_snapshot_ref,
        "toolchain_versions_reported":tools,
        "linter_config_sha256_reported":linter_config_sha256,
        "optimization_mode_reported":optimization_mode,
        "billing_currency_reported":billing_currency,
        "usage_totals_reported":deepcopy(usage_totals),
        "usage_by_stage_reported":sorted(deepcopy(usage_by_stage),key=lambda x:x["stage_ref"]),
        "extra_queries_reported":sorted(queries,key=lambda x:x["query_id"]),
        "identifier_term_map_reported":sorted(terms,key=lambda x:x["identifier_ref"]),
        "real_run_receipt_verified":False,
        "billing_ledger_readback_verified":False,
        "token_usage_authenticated":False,
        "sources_version_readback_verified":False,
        "extra_queries_verified":False,
        "glossary_coverage_verified":False,
        "cost_accuracy_verified":False,
        "pg12_c2_pass":False,"pg12_c2_admitted":False,
        "handoff_allowed":False,"production_authority":False,
        "next_gate":"AUTHENTIC_RUN_CONTEXT_COST_AND_TERM_ID_READBACK"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
