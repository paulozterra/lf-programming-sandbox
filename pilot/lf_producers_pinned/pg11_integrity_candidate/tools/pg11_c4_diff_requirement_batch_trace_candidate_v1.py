"""PG-11_C4: source-only diff -> requirement -> batch traceability.

All upstream manifests are caller supplied. Digest consistency is NOT proof of
authentic diff, approved requirements or legitimate batch assignments.
"""
import hashlib
import json
from copy import deepcopy

SCHEMAS = {
    "c1": "PG11_C1_DIFF_HYGIENE_CANDIDATE_V1",
    "c2": "PG11_C2_TERMINOLOGY_CANDIDATE_V1",
    "c3": "PG11_C3_SUPPRESSION_WAIVER_CANDIDATE_V1",
}
class PG11C4Blocked(ValueError):
    pass

def fail(code):
    raise PG11C4Blocked(code)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()

def ref(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()

def frozen(obj, schema, checkpoint):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG11_C4_UPSTREAM_SCHEMA_INVALID")
    sha = digest({k:v for k,v in obj.items() if k != "candidate_sha256"})
    if sha != obj.get("candidate_sha256"):
        fail("PG11_C4_UPSTREAM_DIGEST_INVALID")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED" or
        obj.get("pg11_"+checkpoint+"_pass") is not False or
        obj.get("pg11_"+checkpoint+"_admitted") is not False or
        obj.get("handoff_allowed") is not False or
        obj.get("production_authority") is not False):
        fail("PG11_C4_PREMATURE_AUTHORITY")
    return sha

def unique(rows, keys, error):
    if not isinstance(rows, list):
        fail(error)
    lookup = {}
    for r in rows:
        if not isinstance(r, dict) or set(r) != keys or not ref(r.get("path")):
            fail(error)
        path = r["path"]
        if path in lookup:
            fail(error)
        lookup[path] = r
    return lookup

def prepare_pg11_c4(*, pg11_c1, pg11_c2, pg11_c3, declared_diff,
                    authorized_scope, trace_observations):
    """One or more requirement+batch links per changed path, including deletions.

    trace_observations:
    [{path, links:[{requirement_ref, batch_ref, scope_ref, evidence_ref,
                    change_reason_ref}], status_reported}].
    A declared link is not evidence of an actual requirement or valid batch.
    """
    s1 = frozen(pg11_c1, SCHEMAS["c1"], "c1")
    s2 = frozen(pg11_c2, SCHEMAS["c2"], "c2")
    s3 = frozen(pg11_c3, SCHEMAS["c3"], "c3")
    if (pg11_c2.get("source_pg11_c1_sha256") != s1 or
        pg11_c3.get("source_pg11_c2_sha256") != s2):
        fail("PG11_C4_UPSTREAM_CHAIN_DRIFT")
    if (pg11_c1.get("declared_diff_sha256") != digest(declared_diff) or
        pg11_c1.get("authorized_scope_sha256") != digest(authorized_scope)):
        fail("PG11_C4_MANIFEST_DIGEST_DRIFT")
    diff_keys = {"path", "change_type", "old_path"}
    scope_keys = diff_keys | {"scope_ref", "requirement_ref", "batch_ref"}
    diffs = unique(declared_diff, diff_keys, "PG11_C4_DIFF_INVALID")
    scopes = unique(authorized_scope, scope_keys, "PG11_C4_SCOPE_INVALID")
    if not diffs:
        fail("PG11_C4_EMPTY_DIFF")
    if set(scopes) != set(diffs):
        fail("PG11_C4_SCOPE_COVERAGE_DRIFT")
    for path, change in diffs.items():
        scope = scopes[path]
        if any(change[k] != scope[k] for k in diff_keys):
            fail("PG11_C4_CHANGE_SCOPE_MISMATCH")
        if not all(ref(scope[k]) for k in ("requirement_ref", "batch_ref", "scope_ref")):
            fail("PG11_C4_SCOPE_PROVENANCE_MISSING")
    observations = unique(trace_observations, {"path","links","status_reported"},
                          "PG11_C4_TRACES_INVALID")
    if set(observations) != set(diffs):
        fail("PG11_C4_TRACE_COVERAGE_DRIFT")
    rows = []
    for path in sorted(diffs):
        item = observations[path]
        if item["status_reported"] not in {"LINKED", "NEEDS_REVIEW"}:
            fail("PG11_C4_TRACE_STATUS_INVALID")
        links = item["links"]
        if not isinstance(links, list) or not links:
            fail("PG11_C4_ORPHAN_CHANGE")
        seen, mapped = set(), []
        for link in links:
            keys = {"requirement_ref","batch_ref","scope_ref","evidence_ref","change_reason_ref"}
            if not isinstance(link, dict) or set(link) != keys or not all(ref(link[k]) for k in keys):
                fail("PG11_C4_LINK_SHAPE_INVALID")
            key = (link["requirement_ref"], link["batch_ref"], link["scope_ref"])
            if key in seen:
                fail("PG11_C4_DUPLICATE_TRACE_LINK")
            seen.add(key)
            if any(link[k] != scopes[path][k] for k in ("requirement_ref","batch_ref","scope_ref")):
                fail("PG11_C4_LINK_NOT_AUTHORIZED_SCOPE")
            mapped.append({**deepcopy(link), "evidence_authenticated":False,
                           "requirement_verified":False,"batch_membership_verified":False})
        rows.append({"path":path, "change_type_reported":diffs[path]["change_type"],
                     "old_path_reported":diffs[path]["old_path"],
                     "status_reported":item["status_reported"],
                     "links":mapped,"trace_verified":False})
    # Supressions may be partial edits; each declared suppression path must exist
    # among the declared changes. A waiver reference does not grant authority.
    suppressions = pg11_c3.get("suppressions")
    if not isinstance(suppressions,list):
        fail("PG11_C4_SUPPRESSIONS_INVALID")
    suppression_ids=set()
    for suppression in suppressions:
        if not isinstance(suppression,dict) or suppression.get("path_reported") not in diffs:
            fail("PG11_C4_SUPPRESSION_OUTSIDE_DIFF")
        sid = suppression.get("suppression_id")
        if not ref(sid) or sid in suppression_ids or suppression.get("suppression_allowed") is not False:
            fail("PG11_C4_SUPPRESSION_AUTHORITY_INVALID")
        suppression_ids.add(sid)
        path=suppression["path_reported"]
        if suppression.get("requirement_ref_reported") != scopes[path]["requirement_ref"]:
            fail("PG11_C4_SUPPRESSION_REQUIREMENT_DRIFT")
    result = {
        "schema_version":"PG11_C4_DIFF_REQUIREMENT_BATCH_TRACE_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg11_c1_sha256":s1,"source_pg11_c2_sha256":s2,
        "source_pg11_c3_sha256":s3,
        "declared_diff_sha256":digest(declared_diff),
        "trace_observations_sha256":digest(trace_observations),
        "changes":rows,
        "changed_path_count_reported":len(rows),
        "suppression_paths_cross_checked_reported":len(suppressions),
        "real_diff_verified":False,
        "requirement_source_verified":False,
        "batch_source_verified":False,
        "trace_complete_verified":False,
        "orphan_changes_excluded_verified":False,
        "pg11_c4_pass":False,"pg11_c4_admitted":False,
        "handoff_allowed":False,"production_authority":False,
        "next_gate":"REAL_DIFF_TO_REQUIREMENT_AND_BATCH_SOURCE_READBACK"
    }
    result["candidate_sha256"]=digest(result)
    return deepcopy(result)
