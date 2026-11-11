"""PG-09_C2: source-only convergence diagnostics for repeated iterations.

A repeated attempt with neither new evidence nor fewer findings is reported
as STOP_AND_RECLASSIFY. Nothing executes, authenticates receipts or approves retries.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PG09C2Blocked(ValueError):
    pass


def fail(code):
    raise PG09C2Blocked(code)


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")).hexdigest()


def ref(value):
    return isinstance(value, str) and bool(value.strip())


def frozen(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        fail("PG09_C2_SOURCE_SCHEMA_INVALID")
    sha = value.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {k: v for k, v in value.items() if k != "candidate_sha256"}
    ):
        fail("PG09_C2_SOURCE_DIGEST_INVALID")
    if (value.get("status") != "CANDIDATE_NOT_ADMITTED" or
        value.get("handoff_allowed") is not False or
        value.get("production_authority") is not False):
        fail("PG09_C2_PREMATURE_SOURCE_AUTHORITY")
    return sha


def indexed(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG09_C2_SOLUTION_SET_EMPTY")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not ref(row.get("solution_id")) or row["solution_id"] in out:
            fail("PG09_C2_SOLUTION_ID_INVALID")
        out[row["solution_id"]] = row
    return out


def identifiers(values, code):
    if (not isinstance(values, list) or
        any(not ref(value) for value in values) or
        len(set(values)) != len(values)):
        fail(code)
    return set(values)


def prepare_pg09_c2(*, pg07_c5, pg09_c1, iteration_observations):
    """Project whether a declared iteration improved, without permitting retries.

    Each solution observation: solution_id, iterations.
    Each iteration: iteration_id, previous_iteration_ref,
      before_finding_refs, after_finding_refs, before_evidence_refs,
      after_evidence_refs, comparison_receipt_ref, comparison_tool_ref.

    The source PG07_C5 may contain no iteration proposals: then iterations
    must be empty too. Every declared iteration must match the PG07_C5 chain.
    For the first attempt, comparison still requires a baseline snapshot.
    """
    c5sha = frozen(pg07_c5, "PG07_C5_ITERATION_GUARD_CANDIDATE_V1")
    c1sha = frozen(pg09_c1, "PG09_C1_ITERATION_COST_GOVERNOR_CANDIDATE_V1")
    if (pg09_c1.get("source_pg07_c5_sha256") != c5sha or
        pg07_c5.get("iteration_applied") is not False or
        pg07_c5.get("pg10_routing_executed") is not False or
        pg09_c1.get("retry_authorized") is not False or
        pg09_c1.get("iteration_authorized") is not False or
        pg09_c1.get("pg09_c1_pass") is not False or
        pg09_c1.get("pg09_c1_admitted") is not False):
        fail("PG09_C2_SOURCE_CHAIN_OR_AUTHORITY_INVALID")
    declared = indexed(pg07_c5.get("solutions"))
    budget = indexed(pg09_c1.get("solutions"))
    supplied = indexed(iteration_observations)
    if set(declared) != set(budget) or set(declared) != set(supplied):
        fail("PG09_C2_SOLUTION_COVERAGE_DRIFT")
    output = []
    stop_requested = False
    for sid in sorted(declared):
        source_rows = declared[sid].get("iterations")
        provided = supplied[sid]
        if not isinstance(provided, dict) or set(provided) != {"solution_id", "iterations"}:
            fail("PG09_C2_OBSERVATION_SHAPE_INVALID")
        snapshots = provided["iterations"]
        if (not isinstance(source_rows, list) or not isinstance(snapshots, list) or
            len(snapshots) != len(source_rows)):
            fail("PG09_C2_ITERATION_CHAIN_LENGTH_DRIFT")
        reports = []
        last_after_findings = None
        last_after_evidence = None
        for idx, (src, row) in enumerate(zip(source_rows, snapshots)):
            if not isinstance(src, dict) or not isinstance(row, dict) or set(row) != {
                "iteration_id", "previous_iteration_ref",
                "before_finding_refs", "after_finding_refs",
                "before_evidence_refs", "after_evidence_refs",
                "comparison_receipt_ref", "comparison_tool_ref"
            }:
                fail("PG09_C2_ITERATION_SHAPE_INVALID")
            if (row["iteration_id"] != src.get("iteration_id") or
                row["previous_iteration_ref"] != src.get("previous_iteration_ref") or
                not ref(row["comparison_receipt_ref"]) or not ref(row["comparison_tool_ref"])):
                fail("PG09_C2_ITERATION_ID_OR_RECEIPT_DRIFT")
            before_f = identifiers(row["before_finding_refs"], "PG09_C2_BEFORE_FINDINGS_INVALID")
            after_f = identifiers(row["after_finding_refs"], "PG09_C2_AFTER_FINDINGS_INVALID")
            before_e = identifiers(row["before_evidence_refs"], "PG09_C2_BEFORE_EVIDENCE_INVALID")
            after_e = identifiers(row["after_evidence_refs"], "PG09_C2_AFTER_EVIDENCE_INVALID")
            if idx > 0 and (before_f != last_after_findings or before_e != last_after_evidence):
                fail("PG09_C2_NONCONTIGUOUS_COMPARISON_CHAIN")
            new_evidence = sorted(after_e - before_e)
            resolved_findings = sorted(before_f - after_f)
            introduced_findings = sorted(after_f - before_f)
            reduced = len(after_f) < len(before_f)
            repeated = idx > 0
            stagnated = repeated and not new_evidence and not reduced
            material_drift = bool(src.get("changed_fields"))
            if material_drift:
                diagnostic = "BLOCK_ROUTE_PG10"
            elif stagnated:
                diagnostic = "STOP_AND_RECLASSIFY"
            elif not repeated:
                diagnostic = "FIRST_ITERATION_BASELINE_REPORTED"
            else:
                diagnostic = "REPORTED_PROGRESS_UNVERIFIED"
            if diagnostic in ("STOP_AND_RECLASSIFY", "BLOCK_ROUTE_PG10"):
                stop_requested = True
            reports.append({
                "iteration_id": row["iteration_id"],
                "previous_iteration_ref": row["previous_iteration_ref"],
                "iteration_index": idx,
                "new_evidence_refs_reported": new_evidence,
                "resolved_finding_refs_reported": resolved_findings,
                "introduced_finding_refs_reported": introduced_findings,
                "before_finding_count_reported": len(before_f),
                "after_finding_count_reported": len(after_f),
                "finding_count_reduced_reported": reduced,
                "comparison_receipt_ref_reported": row["comparison_receipt_ref"],
                "comparison_tool_ref_reported": row["comparison_tool_ref"],
                "diagnostic": diagnostic,
                "comparison_authenticated": False,
                "iteration_executed_by_this_component": False,
                "retry_authorized": False
            })
            last_after_findings = after_f
            last_after_evidence = after_e
        budget_row = budget[sid]
        if budget_row.get("attempt_limit_reached") is True or budget_row.get("cost_unknown") is True:
            stop_requested = True
        output.append({
            "solution_id": sid,
            "iterations": reports,
            "budget_diagnostic_reported": pg09_c1.get("request_diagnostic"),
            "diagnostic": "STOP_AND_RECLASSIFY" if any(
                r["diagnostic"] == "STOP_AND_RECLASSIFY" for r in reports
            ) else "BLOCK_ROUTE_PG10" if any(
                r["diagnostic"] == "BLOCK_ROUTE_PG10" for r in reports
            ) else "REQUIRES_DECISION" if (
                budget_row.get("attempt_limit_reached") is True or
                budget_row.get("cost_unknown") is True or
                pg09_c1.get("requires_decision_reported") is True
            ) else "NO_STAGNATION_REPORTED_UNVERIFIED",
            "comparison_authenticated": False,
            "retry_authorized": False
        })
    if pg09_c1.get("requires_decision_reported") is True:
        stop_requested = True
    result = {
        "schema_version": "PG09_C2_CONVERGENCE_GUARD_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg07_c5_sha256": c5sha,
        "source_pg09_c1_sha256": c1sha,
        "iteration_observations_sha256": digest(iteration_observations),
        "solutions": output,
        "stop_or_reclassify_reported": stop_requested,
        "comparison_receipts_authenticated": False,
        "worker_iterations_observed": False,
        "finding_equivalence_verified": False,
        "new_evidence_verified": False,
        "repeat_execution_allowed": False,
        "retry_authorized": False,
        "pg09_c2_pass": False,
        "pg09_c2_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "AUTHENTICATED_ITERATION_HISTORY_FINDING_EQUIVALENCE_AND_CONVERGENCE_NEGATIVE_TESTS"
    }
    result["candidate_sha256"] = digest(result)
    return result
