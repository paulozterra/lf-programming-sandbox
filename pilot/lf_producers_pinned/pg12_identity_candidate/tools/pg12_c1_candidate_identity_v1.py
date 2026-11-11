"""PG-12_C1 — candidate reproducible identity envelope, source only.

Supplied Git objects, digests, paths and builders are NOT authenticated.
The SHA-256 seals this declaration, not the repository or diff contents.
"""
import hashlib
import json
import re
from copy import deepcopy

OID = re.compile(r"^[0-9a-f]{40,64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHANGES = {"ADDED", "MODIFIED", "DELETED", "RENAMED"}
C5_SCHEMA = "PG11_C5_INDEPENDENT_REVIEW_CANDIDATE_V1"

class PG12C1Blocked(ValueError):
    pass

def fail(reason):
    raise PG12C1Blocked(reason)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()

def ref(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()

def oid(value):
    return isinstance(value, str) and bool(OID.fullmatch(value))

def valid_path(value):
    if not ref(value) or value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    parts = value.split("/")
    return all(p not in ("", ".", "..") for p in parts)

def prepare_pg12_c1(*, pg11_c5, repo_ref, base_commit_sha, candidate_commit_sha,
                    candidate_tree_sha, diff_sha256, changed_objects,
                    builder_principal_ref, builder_provenance_ref):
    """One record per changed path.

    changed_objects: [{path, change_type, old_path, object_type,
                       object_oid, old_object_oid}].
    object_type: blob|tree|gitlink. Deletions require object_oid=None and
    old_object_oid present. Adds require old_object_oid=None; renames and
    modifications require both. These are identity declarations, not Git reads.
    """
    if not isinstance(pg11_c5, dict) or pg11_c5.get("schema_version") != C5_SCHEMA:
        fail("PG12_C1_UPSTREAM_SCHEMA_INVALID")
    s5 = digest({k: v for k, v in pg11_c5.items() if k != "candidate_sha256"})
    if pg11_c5.get("candidate_sha256") != s5:
        fail("PG12_C1_UPSTREAM_DIGEST_INVALID")
    if (pg11_c5.get("status") != "CANDIDATE_NOT_ADMITTED"
        or pg11_c5.get("pg11_c5_pass") is not False
        or pg11_c5.get("pg11_c5_admitted") is not False
        or pg11_c5.get("production_authority") is not False
        or pg11_c5.get("handoff_allowed") is not False
        or pg11_c5.get("independent_review_executed") is not False):
        fail("PG12_C1_UPSTREAM_AUTHORITY_INVALID")
    if not all(ref(x) for x in (repo_ref, builder_principal_ref, builder_provenance_ref)):
        fail("PG12_C1_IDENTITY_REF_INVALID")
    if not all(oid(x) for x in (base_commit_sha, candidate_commit_sha, candidate_tree_sha)):
        fail("PG12_C1_GIT_OID_INVALID")
    if base_commit_sha == candidate_commit_sha:
        fail("PG12_C1_BASE_EQUALS_CANDIDATE")
    if not isinstance(diff_sha256, str) or not SHA256.fullmatch(diff_sha256):
        fail("PG12_C1_DIFF_DIGEST_INVALID")
    reviews = pg11_c5.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        fail("PG12_C1_UPSTREAM_REVIEW_SET_INVALID")
    review_paths = set()
    for review in reviews:
        if not isinstance(review, dict) or not valid_path(review.get("path")):
            fail("PG12_C1_UPSTREAM_PATH_INVALID")
        p = review["path"]
        if p in review_paths:
            fail("PG12_C1_UPSTREAM_DUPLICATE_PATH")
        review_paths.add(p)
        if (review.get("builder_principal_ref_reported") != builder_principal_ref or
            review.get("builder_provenance_ref_reported") != builder_provenance_ref):
            fail("PG12_C1_BUILDER_DRIFT")
    if not isinstance(changed_objects, list) or len(changed_objects) != len(review_paths):
        fail("PG12_C1_CHANGED_OBJECT_COVERAGE_INVALID")
    seen = set()
    recorded = []
    for obj in changed_objects:
        fields = {"path", "change_type", "old_path", "object_type",
                  "object_oid", "old_object_oid"}
        if not isinstance(obj, dict) or set(obj) != fields:
            fail("PG12_C1_OBJECT_SHAPE_INVALID")
        p = obj["path"]
        if not valid_path(p) or p in seen or p not in review_paths:
            fail("PG12_C1_OBJECT_PATH_INVALID")
        seen.add(p)
        change = obj["change_type"]
        if change not in CHANGES or obj["object_type"] not in {"blob", "tree", "gitlink"}:
            fail("PG12_C1_OBJECT_KIND_INVALID")
        old_path = obj["old_path"]
        if change == "RENAMED":
            if not valid_path(old_path) or old_path == p:
                fail("PG12_C1_RENAME_PATH_INVALID")
        elif old_path is not None:
            fail("PG12_C1_UNEXPECTED_OLD_PATH")
        old_oid, new_oid = obj["old_object_oid"], obj["object_oid"]
        if change == "ADDED":
            valid = old_oid is None and oid(new_oid)
        elif change == "DELETED":
            valid = oid(old_oid) and new_oid is None
        else:
            valid = oid(old_oid) and oid(new_oid)
        if not valid:
            fail("PG12_C1_OBJECT_OIDS_INCONSISTENT")
        recorded.append({**deepcopy(obj), "git_object_readback_verified": False})
    if seen != review_paths:
        fail("PG12_C1_CHANGED_OBJECT_COVERAGE_DRIFT")
    result = {
        "schema_version": "PG12_C1_CANDIDATE_IDENTITY_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg11_c5_sha256": s5,
        "repository_ref_reported": repo_ref,
        "base_commit_sha_reported": base_commit_sha,
        "candidate_commit_sha_reported": candidate_commit_sha,
        "candidate_tree_sha_reported": candidate_tree_sha,
        "diff_sha256_reported": diff_sha256,
        "changed_paths_reported": sorted(seen),
        "changed_objects_reported": sorted(recorded, key=lambda x: x["path"]),
        "changed_objects_manifest_sha256": digest(changed_objects),
        "builder_principal_ref_reported": builder_principal_ref,
        "builder_provenance_ref_reported": builder_provenance_ref,
        "base_commit_readback_verified": False,
        "candidate_commit_readback_verified": False,
        "candidate_tree_readback_verified": False,
        "actual_diff_digest_verified": False,
        "changed_objects_readback_verified": False,
        "builder_authenticated": False,
        "identity_reconstructable_verified": False,
        "pg12_c1_pass": False,
        "pg12_c1_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXACT_GIT_OBJECT_DIFF_AND_BUILDER_PROVENANCE_READBACK"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
