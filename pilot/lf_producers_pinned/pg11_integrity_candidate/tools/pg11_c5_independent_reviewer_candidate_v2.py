"""PG-11_C5 source-only independent reviewer separation proposal.

Identity, permissions, review execution and independence are NOT authenticated.
A declared reviewer different from builder is not independent-review evidence.
"""
import hashlib
import json
from copy import deepcopy

SCHEMA = "PG11_C4_DIFF_REQUIREMENT_BATCH_TRACE_CANDIDATE_V2"

class PG11C5Blocked(ValueError):
    pass

def fail(reason):
    raise PG11C5Blocked(reason)

def digest(obj):
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")).hexdigest()

def ref(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()

def prepare_pg11_c5(*, pg11_c4, review_observations, review_policy_ref):
    """Freeze reviewer candidates per changed file; never issue a review.

    review_observations: [{
      path, builder_principal_ref, reviewer_principal_ref, reviewer_role_ref,
      builder_provenance_ref, reviewer_provenance_ref, review_scope_ref,
      reviewer_is_builder_reported, reviewer_independence_reported
    }]
    The caller cannot claim authenticity via *_reported fields.
    """
    if not isinstance(pg11_c4, dict) or pg11_c4.get("schema_version") != SCHEMA:
        fail("PG11_C5_UPSTREAM_SCHEMA_INVALID")
    source_sha = digest({k:v for k,v in pg11_c4.items() if k != "candidate_sha256"})
    if pg11_c4.get("candidate_sha256") != source_sha:
        fail("PG11_C5_UPSTREAM_DIGEST_INVALID")
    if (pg11_c4.get("status") != "CANDIDATE_NOT_ADMITTED" or
        pg11_c4.get("pg11_c4_pass") is not False or
        pg11_c4.get("pg11_c4_admitted") is not False or
        pg11_c4.get("handoff_allowed") is not False or
        pg11_c4.get("production_authority") is not False or
        pg11_c4.get("trace_complete_verified") is not False):
        fail("PG11_C5_UPSTREAM_AUTHORITY_INVALID")
    if not ref(review_policy_ref):
        fail("PG11_C5_REVIEW_POLICY_REFERENCE_REQUIRED")
    changes = pg11_c4.get("changes")
    if not isinstance(changes, list) or not changes:
        fail("PG11_C5_CHANGED_PATHS_INVALID")
    changed_paths = set()
    for row in changes:
        if not isinstance(row, dict) or not ref(row.get("path")) or row["path"] in changed_paths:
            fail("PG11_C5_CHANGED_PATHS_INVALID")
        changed_paths.add(row["path"])
    if not isinstance(review_observations, list) or len(review_observations) != len(changed_paths):
        fail("PG11_C5_REVIEW_COVERAGE_INVALID")
    review_paths, reviews = set(), []
    for row in review_observations:
        fields = {"path", "builder_principal_ref", "reviewer_principal_ref",
                  "reviewer_role_ref", "builder_provenance_ref",
                  "reviewer_provenance_ref", "review_scope_ref",
                  "reviewer_is_builder_reported", "reviewer_independence_reported"}
        if not isinstance(row, dict) or set(row) != fields:
            fail("PG11_C5_REVIEW_RECORD_SHAPE_INVALID")
        path = row["path"]
        if path not in changed_paths or path in review_paths:
            fail("PG11_C5_REVIEW_PATH_INVALID")
        review_paths.add(path)
        if not all(ref(row[k]) for k in (
                "builder_principal_ref", "reviewer_principal_ref",
                "reviewer_role_ref", "builder_provenance_ref",
                "reviewer_provenance_ref", "review_scope_ref")):
            fail("PG11_C5_REVIEW_IDENTITY_REFERENCE_INVALID")
        if (row["builder_principal_ref"] == row["reviewer_principal_ref"] or
            row["reviewer_is_builder_reported"] is not False):
            fail("PG11_C5_SELF_REVIEW_DECLARED")
        # A declaration of independence is stored, never promoted to verified.
        if type(row["reviewer_independence_reported"]) is not bool:
            fail("PG11_C5_INDEPENDENCE_DECLARATION_INVALID")
        reviews.append({
            "path": path,
            "builder_principal_ref_reported": row["builder_principal_ref"],
            "reviewer_principal_ref_reported": row["reviewer_principal_ref"],
            "reviewer_role_ref_reported": row["reviewer_role_ref"],
            "builder_provenance_ref_reported": row["builder_provenance_ref"],
            "reviewer_provenance_ref_reported": row["reviewer_provenance_ref"],
            "review_scope_ref_reported": row["review_scope_ref"],
            "reviewer_independence_reported": row["reviewer_independence_reported"],
            "identities_authenticated": False,
            "reviewer_independence_verified": False,
            "review_executed": False,
            "reviewer_decision_issued": False
        })
    if review_paths != changed_paths:
        fail("PG11_C5_REVIEW_COVERAGE_DRIFT")
    result = {
        "schema_version": "PG11_C5_INDEPENDENT_REVIEW_CANDIDATE_V2",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg11_c4_sha256": source_sha,
        "review_observations_sha256": digest(review_observations),
        "review_policy_ref_reported": review_policy_ref,
        "reviews": sorted(reviews, key=lambda x: x["path"]),
        "changed_path_count_reported": len(changed_paths),
        "identity_provider_readback_verified": False,
        "builder_identity_verified": False,
        "reviewer_identity_verified": False,
        "reviewer_independence_verified": False,
        "independent_review_executed": False,
        "independent_verdict_issued": False,
        "pg11_c5_pass": False,
        "pg11_c5_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "AUTHENTIC_BUILDER_REVIEWER_IDENTITY_AND_INDEPENDENT_REVIEW_EXECUTION"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
