"""PG-10_C1: source-only typed conflict inventory; no resolution or routing.

Reuses PG-07 scope drift and PG-09 typed escalation. Caller-supplied
references are not authenticated and never substitute Fase 1 analysis.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA256 = re.compile(r"^[a-f0-9]{64}$")
TYPES = {
    "REQUIREMENT_VS_STANDARD",
    "REQUIREMENT_VS_EXISTING_CONTRACT",
    "REQUIREMENT_VS_REUSE_AS_IS",
    "STANDARD_VS_EXISTING_CONTRACT",
    "STANDARD_VS_REUSE_AS_IS",
    "EXISTING_CONTRACT_VS_REUSE_AS_IS",
}
KIND = {"CONFLICT", "EVIDENCE_GAP", "REQUIREMENT_GAP"}

class PG10C1Blocked(ValueError):
    pass

def fail(reason):
    raise PG10C1Blocked(reason)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

def valid_ref(v):
    return isinstance(v, str) and bool(v.strip())

def frozen(obj, schema):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG10_C1_UPSTREAM_SCHEMA_INVALID")
    sha = obj.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {k: v for k, v in obj.items() if k != "candidate_sha256"}
    ):
        fail("PG10_C1_UPSTREAM_DIGEST_INVALID")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED" or
        obj.get("production_authority") is not False or
        obj.get("handoff_allowed") is not False):
        fail("PG10_C1_PREMATURE_AUTHORITY")
    return sha

def indexed(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG10_C1_SOLUTION_SET_INVALID")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not valid_ref(row.get("solution_id")) or row["solution_id"] in out:
            fail("PG10_C1_SOLUTION_ID_INVALID")
        out[row["solution_id"]] = row
    return out

def prepare_pg10_c1(*, pg07_c5, pg09_c4, conflict_observations):
    """Produce typed conflict/gap records for existing candidate solutions.

    Each observation row: solution_id, conflicts.
    Each conflict: conflict_id, classification, issue_kind,
      requirement_ref, standard_ref, existing_contract_ref,
      reuse_as_is_ref, evidence_refs, diagnosis_ref.

    Missing one side of a declared pair is blocked: it must instead be
    classified as a gap with an explicit diagnosis and target resolver.
    """
    s7 = frozen(pg07_c5, "PG07_C5_ITERATION_GUARD_CANDIDATE_V1")
    s9 = frozen(pg09_c4, "PG09_C4_TYPED_ESCALATION_CANDIDATE_V1")
    if (pg07_c5.get("iteration_applied") is not False or
        pg09_c4.get("retry_authorized") is not False or
        pg09_c4.get("escalation_delivered") is not False or
        pg09_c4.get("pg09_c4_pass") is not False or
        pg09_c4.get("pg09_c4_admitted") is not False):
        fail("PG10_C1_SOURCE_AUTHORITY_INVALID")
    proposals, escalations, observations = (
        indexed(pg07_c5.get("solutions")), indexed(pg09_c4.get("solutions")),
        indexed(conflict_observations))
    if set(proposals) != set(escalations) or set(proposals) != set(observations):
        fail("PG10_C1_SOLUTION_COVERAGE_DRIFT")
    output = []
    for sid in sorted(proposals):
        obs = observations[sid]
        if set(obs) != {"solution_id", "conflicts"} or not isinstance(obs["conflicts"], list):
            fail("PG10_C1_OBSERVATION_SHAPE_INVALID")
        conflicts = []
        seen = set()
        for item in obs["conflicts"]:
            if not isinstance(item, dict) or set(item) != {
                "conflict_id", "classification", "issue_kind",
                "requirement_ref", "standard_ref", "existing_contract_ref",
                "reuse_as_is_ref", "evidence_refs", "diagnosis_ref"
            }:
                fail("PG10_C1_CONFLICT_SHAPE_INVALID")
            cid, classification, kind = (
                item["conflict_id"], item["classification"], item["issue_kind"])
            if (not valid_ref(cid) or cid in seen or
                classification not in TYPES or kind not in KIND or
                not valid_ref(item["diagnosis_ref"])):
                fail("PG10_C1_CONFLICT_IDENTITY_INVALID")
            seen.add(cid)
            refs = {key: item[key] for key in (
                "requirement_ref", "standard_ref", "existing_contract_ref",
                "reuse_as_is_ref")}
            if any(value is not None and not valid_ref(value) for value in refs.values()):
                fail("PG10_C1_BAD_REFERENCE")
            parts = {
                "REQUIREMENT": "requirement_ref",
                "STANDARD": "standard_ref",
                "EXISTING_CONTRACT": "existing_contract_ref",
                "REUSE_AS_IS": "reuse_as_is_ref"}
            left, right = classification.split("_VS_")
            if kind == "CONFLICT" and (not refs[parts[left]] or not refs[parts[right]]):
                fail("PG10_C1_CONFLICT_WITHOUT_TWO_SOURCES")
            evidence = item["evidence_refs"]
            if (not isinstance(evidence, list) or not evidence or
                any(not valid_ref(e) for e in evidence) or
                len(set(evidence)) != len(evidence)):
                fail("PG10_C1_EVIDENCE_REFS_INVALID")
            resolution = ("RETURN_PHASE1_A3" if kind == "REQUIREMENT_GAP" else
                          "QUERY_EXACT_MISSING_EVIDENCE" if kind == "EVIDENCE_GAP" else
                          "PENDING_GOVERNED_CLASSIFICATION")
            conflicts.append({
                "conflict_id": cid,
                "classification_reported": classification,
                "issue_kind_reported": kind,
                "source_refs_reported": deepcopy(refs),
                "evidence_refs_reported": sorted(evidence),
                "diagnosis_ref_reported": item["diagnosis_ref"],
                "next_resolver_hint": resolution,
                "sources_authenticated": False,
                "human_decision_necessity_verified": False,
                "resolution_authorized": False
            })
        prior_pg10 = any("MATERIAL_SCOPE_DRIFT" in x.get("reason_codes", [])
                         for x in (escalations[sid],))
        output.append({
            "solution_id": sid,
            "run_ref": escalations[sid].get("run_ref"),
            "prior_pg09_escalation_type_reported": escalations[sid].get("escalation_type"),
            "prior_scope_drift_reported": prior_pg10,
            "conflicts": sorted(conflicts, key=lambda x: x["conflict_id"]),
            "diagnostic": "CONFLICTS_DECLARED_UNVERIFIED" if conflicts
                else "NO_CONFLICTS_DECLARED_NOT_PROOF_OF_ABSENCE",
            "diff_and_spec_readback_verified": False,
            "conflicts_detected_from_real_sources": False,
            "decision_issued": False
        })
    result = {
        "schema_version": "PG10_C1_CONFLICT_INVENTORY_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg07_c5_sha256": s7,
        "source_pg09_c4_sha256": s9,
        "observations_sha256": digest(conflict_observations),
        "run_ref": pg09_c4.get("run_ref"),
        "solutions": output,
        "analysis_modified": False,
        "real_spec_scanned": False,
        "real_contract_scanned": False,
        "conflict_detection_authenticated": False,
        "precedence_decided": False,
        "owner_question_sent": False,
        "pg10_c1_pass": False,
        "pg10_c1_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_REQUIREMENT_STANDARD_CONTRACT_REUSE_READBACK_AND_TYPED_CONFLICT_QUALIFICATION"
    }
    result["candidate_sha256"] = digest(result)
    return result
