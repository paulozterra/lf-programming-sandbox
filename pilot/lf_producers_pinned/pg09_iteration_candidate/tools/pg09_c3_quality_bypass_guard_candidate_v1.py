"""PG-09_C3: reject declared quality-gate bypasses during iterations.

No actual diff inspection, waiver verification, test execution or write
permission. All change declarations and references are untrusted.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN = {"RULE_DISABLE", "TEST_DELETE", "QUALITY_GATE_BYPASS"}
WAIVER_REQUIRED = {"SUPPRESSION_ADD"}
CLASSIFICATIONS = FORBIDDEN | WAIVER_REQUIRED | {"NORMAL_CHANGE"}


class PG09C3Blocked(ValueError):
    pass


def fail(code):
    raise PG09C3Blocked(code)


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def frozen(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        fail("PG09_C3_UPSTREAM_SCHEMA_INVALID")
    sha = value.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {key: val for key, val in value.items() if key != "candidate_sha256"}
    ):
        fail("PG09_C3_UPSTREAM_DIGEST_INVALID")
    if (value.get("status") != "CANDIDATE_NOT_ADMITTED" or
        value.get("production_authority") is not False or
        value.get("handoff_allowed") is not False):
        fail("PG09_C3_PREMATURE_AUTHORITY")
    return sha


def index(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG09_C3_SOLUTION_SET_INVALID")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not nonempty(row.get("solution_id")) or row["solution_id"] in out:
            fail("PG09_C3_SOLUTION_ID_INVALID")
        out[row["solution_id"]] = row
    return out


def prepare_pg09_c3(*, pg07_c5, pg09_c2, quality_change_observations):
    """Classify reported diff changes against protected quality controls.

    Each solution: solution_id, iterations.
    Each iteration: iteration_id, diff_ref, diff_sha256, changes.
    Each change: change_id, classification, path, evidence_ref,
      before_sha256, after_sha256, waiver_ref, waiver_decision_ref.

    Hashes identify a claimed artifact, NOT a verified diff. An optional
    waiver for SUPPRESSION_ADD only triggers REQUIRES_WAIVER_VERIFICATION,
    never permission to disable the quality control.
    """
    upstream07 = frozen(pg07_c5, "PG07_C5_ITERATION_GUARD_CANDIDATE_V1")
    upstream09 = frozen(pg09_c2, "PG09_C2_CONVERGENCE_GUARD_CANDIDATE_V1")
    if (pg09_c2.get("source_pg07_c5_sha256") != upstream07 or
        pg07_c5.get("iteration_applied") is not False or
        pg09_c2.get("repeat_execution_allowed") is not False or
        pg09_c2.get("retry_authorized") is not False or
        pg09_c2.get("pg09_c2_pass") is not False or
        pg09_c2.get("pg09_c2_admitted") is not False):
        fail("PG09_C3_SOURCE_CHAIN_OR_AUTHORITY_INVALID")
    proposals = index(pg07_c5.get("solutions"))
    convergence = index(pg09_c2.get("solutions"))
    supplied = index(quality_change_observations)
    if set(proposals) != set(convergence) or set(proposals) != set(supplied):
        fail("PG09_C3_SOLUTION_COVERAGE_DRIFT")
    solutions, all_blocks, all_decisions = [], [], []
    for sid in sorted(proposals):
        source = proposals[sid].get("iterations")
        previous = convergence[sid].get("iterations")
        observed = supplied[sid]
        if (not isinstance(source, list) or not isinstance(previous, list) or
            set(observed) != {"solution_id", "iterations"} or
            not isinstance(observed["iterations"], list) or
            len(source) != len(previous) or len(source) != len(observed["iterations"])):
            fail("PG09_C3_ITERATION_COVERAGE_INVALID")
        reports = []
        for proposal, converged, row in zip(source, previous, observed["iterations"]):
            if not isinstance(row, dict) or set(row) != {
                "iteration_id", "diff_ref", "diff_sha256", "changes"
            }:
                fail("PG09_C3_ITERATION_SHAPE_INVALID")
            if (row["iteration_id"] != proposal.get("iteration_id") or
                row["iteration_id"] != converged.get("iteration_id") or
                row["diff_ref"] != proposal.get("proposed_diff_ref") or
                row["diff_sha256"] != proposal.get("proposed_diff_sha256") or
                not isinstance(row["diff_sha256"], str) or
                not SHA256.fullmatch(row["diff_sha256"])):
                fail("PG09_C3_DIFF_OR_ITERATION_DRIFT")
            if not isinstance(row["changes"], list):
                fail("PG09_C3_CHANGES_INVALID")
            seen, blockers, decisions, changes = set(), [], [], []
            for change in row["changes"]:
                if not isinstance(change, dict) or set(change) != {
                    "change_id", "classification", "path", "evidence_ref",
                    "before_sha256", "after_sha256", "waiver_ref",
                    "waiver_decision_ref"
                }:
                    fail("PG09_C3_CHANGE_SHAPE_INVALID")
                cid, classification, path = (
                    change["change_id"], change["classification"], change["path"]
                )
                if (not nonempty(cid) or cid in seen or
                    classification not in CLASSIFICATIONS or not nonempty(path) or
                    path.startswith("/") or "\\" in path or ".." in path.split("/") or
                    not nonempty(change["evidence_ref"])):
                    fail("PG09_C3_CHANGE_IDENTITY_INVALID")
                seen.add(cid)
                for key in ("before_sha256", "after_sha256"):
                    if (change[key] is not None and
                        (not isinstance(change[key], str) or not SHA256.fullmatch(change[key]))):
                        fail("PG09_C3_CHANGE_DIGEST_INVALID")
                if (change["waiver_ref"] is not None and not nonempty(change["waiver_ref"])) or (
                    change["waiver_decision_ref"] is not None and
                    not nonempty(change["waiver_decision_ref"])
                ):
                    fail("PG09_C3_WAIVER_REF_INVALID")
                if classification == "TEST_DELETE" and change["after_sha256"] is not None:
                    fail("PG09_C3_TEST_DELETE_DIGEST_CONTRADICTION")
                if classification in FORBIDDEN:
                    action = "BLOCK"
                    blockers.append(cid)
                elif classification == "SUPPRESSION_ADD":
                    # Even if waiver references exist, authority is NOT
                    # granted without independent verification.
                    action = "REQUIRES_WAIVER_VERIFICATION"
                    decisions.append(cid)
                else:
                    if change["waiver_ref"] is not None or change["waiver_decision_ref"] is not None:
                        fail("PG09_C3_WAIVER_ON_NON_SUPPRESSION")
                    action = "NO_DECLARED_BYPASS_UNVERIFIED"
                changes.append({
                    "change_id": cid, "path_reported": path,
                    "classification_reported": classification,
                    "evidence_ref_reported": change["evidence_ref"],
                    "before_sha256_reported": change["before_sha256"],
                    "after_sha256_reported": change["after_sha256"],
                    "waiver_ref_reported": change["waiver_ref"],
                    "waiver_decision_ref_reported": change["waiver_decision_ref"],
                    "action_reported": action,
                    "waiver_authenticated": False,
                    "diff_change_verified": False,
                    "quality_gate_bypass_allowed": False
                })
            if blockers:
                all_blocks.extend({"solution_id": sid, "iteration_id": row["iteration_id"],
                                   "change_id": cid} for cid in blockers)
            if decisions:
                all_decisions.extend({"solution_id": sid, "iteration_id": row["iteration_id"],
                                      "change_id": cid} for cid in decisions)
            reports.append({
                "iteration_id": row["iteration_id"],
                "diff_ref_reported": row["diff_ref"],
                "diff_sha256_reported": row["diff_sha256"],
                "changes": sorted(changes, key=lambda r: r["change_id"]),
                "diagnostic": ("BLOCK" if blockers else
                    "REQUIRES_WAIVER_VERIFICATION" if decisions else
                    "NO_DECLARED_BYPASS_UNVERIFIED"),
                "quality_protection_verified": False,
                "retry_authorized": False
            })
        solutions.append({
            "solution_id": sid, "iterations": reports,
            "diagnostic": ("BLOCK" if any(r["diagnostic"] == "BLOCK" for r in reports) else
                           "REQUIRES_WAIVER_VERIFICATION" if any(
                               r["diagnostic"] == "REQUIRES_WAIVER_VERIFICATION" for r in reports)
                           else "NO_DECLARED_BYPASS_UNVERIFIED"),
            "real_diff_scanned": False,
            "quality_protection_verified": False
        })
    result = {
        "schema_version": "PG09_C3_QUALITY_BYPASS_GUARD_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg07_c5_sha256": upstream07,
        "source_pg09_c2_sha256": upstream09,
        "observations_sha256": digest(quality_change_observations),
        "solutions": solutions,
        "declared_blocks": all_blocks,
        "waiver_verification_requests": all_decisions,
        "real_diff_scanned": False,
        "ruleset_currentness_verified": False,
        "waivers_authenticated": False,
        "worker_execution_observed": False,
        "quality_gate_bypass_allowed": False,
        "retry_authorized": False,
        "pg09_c3_pass": False,
        "pg09_c3_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_DIFF_QUALITY_RULES_WAIVER_AUTHORITY_AND_NEGATIVE_TESTS"
    }
    result["candidate_sha256"] = digest(result)
    return result
