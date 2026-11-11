"""PG-11_C3: source-only suppression/waiver coverage inventory.

No authenticated waiver lookup, real Git diff scan, or deletion authorization.
Caller statements are untrusted, even when internally self-consistent.
"""
import hashlib
import json
from copy import deepcopy

SCHEMA = "PG11_C2_TERMINOLOGY_CANDIDATE_V2"
KINDS = {"FILE_DELETE", "FILE_RENAME_REMOVAL", "CODE_REMOVAL",
         "TEST_REMOVAL", "CHECK_REMOVAL", "CONTRACT_REMOVAL"}
class PG11C3Blocked(ValueError):
    pass

def fail(reason):
    raise PG11C3Blocked(reason)

def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()

def ref(x):
    return isinstance(x, str) and bool(x.strip()) and x == x.strip()

def prepare_pg11_c3(*, pg11_c2, suppression_observations, waiver_observations,
                    std_gen_05_source_ref):
    """Create typed suppression-to-waiver coverage, never an approval.

    Suppression: suppression_id, path, kind, removed_element_ref,
      requirement_ref, waiver_ref.
    Waiver: waiver_ref, standard_ref, scope_path, suppression_id,
      approving_authority_ref, approval_record_ref, approval_status_reported,
      effective_version_ref, rationale_ref.
    A waiver declaration cannot be used as permission to suppress code.
    """
    if not isinstance(pg11_c2, dict) or pg11_c2.get("schema_version") != SCHEMA:
        fail("PG11_C3_C2_SCHEMA_INVALID")
    sha = digest({k:v for k,v in pg11_c2.items() if k != "candidate_sha256"})
    if pg11_c2.get("candidate_sha256") != sha:
        fail("PG11_C3_C2_DIGEST_INVALID")
    flags = ("pg11_c2_pass", "pg11_c2_admitted", "handoff_allowed",
             "production_authority", "positive_coverage_verified")
    if pg11_c2.get("status") != "CANDIDATE_NOT_ADMITTED" or any(pg11_c2.get(f) is not False for f in flags):
        fail("PG11_C3_C2_AUTHORITY_INVALID")
    if not ref(std_gen_05_source_ref):
        fail("PG11_C3_STANDARD_REFERENCE_REQUIRED")
    if not isinstance(suppression_observations, list) or not isinstance(waiver_observations, list):
        fail("PG11_C3_OBSERVATIONS_INVALID")
    suppressions = {}
    for row in suppression_observations:
        fields = {"suppression_id", "path", "kind", "removed_element_ref",
                  "requirement_ref", "waiver_ref"}
        if not isinstance(row, dict) or set(row) != fields:
            fail("PG11_C3_SUPPRESSION_SHAPE_INVALID")
        sid = row["suppression_id"]
        if (not ref(sid) or sid in suppressions or not ref(row["path"])
            or row["kind"] not in KINDS
            or not ref(row["removed_element_ref"]) or not ref(row["requirement_ref"])
            or (row["waiver_ref"] is not None and not ref(row["waiver_ref"]))):
            fail("PG11_C3_SUPPRESSION_INVALID")
        suppressions[sid] = deepcopy(row)
    waivers = {}
    for row in waiver_observations:
        fields = {"waiver_ref", "standard_ref", "scope_path", "suppression_id",
                  "approving_authority_ref", "approval_record_ref",
                  "approval_status_reported", "effective_version_ref",
                  "rationale_ref"}
        if not isinstance(row, dict) or set(row) != fields:
            fail("PG11_C3_WAIVER_SHAPE_INVALID")
        wid = row["waiver_ref"]
        if (not ref(wid) or wid in waivers or row["standard_ref"] != "STD-GEN-05"
            or not all(ref(row[k]) for k in (
                "scope_path", "suppression_id", "approving_authority_ref",
                "approval_record_ref", "effective_version_ref", "rationale_ref"))
            or row["approval_status_reported"] not in ("APPROVED", "PENDING", "REJECTED", "EXPIRED")):
            fail("PG11_C3_WAIVER_INVALID")
        waivers[wid] = deepcopy(row)
    output, referenced = [], set()
    for sid, s in sorted(suppressions.items()):
        wid = s["waiver_ref"]
        row = waivers.get(wid) if wid else None
        matches = row is not None and row["scope_path"] == s["path"] and row["suppression_id"] == sid
        if wid:
            referenced.add(wid)
        if not wid:
            reason = "WAIVER_MISSING"
        elif not row:
            reason = "WAIVER_NOT_IN_DECLARED_SET"
        elif not matches:
            reason = "WAIVER_SCOPE_MISMATCH"
        elif row["approval_status_reported"] != "APPROVED":
            reason = "WAIVER_NOT_APPROVED_REPORTED"
        else:
            reason = "APPROVED_REPORTED_BUT_UNAUTHENTICATED"
        output.append({
            "suppression_id": sid,
            "path_reported": s["path"],
            "kind_reported": s["kind"],
            "removed_element_ref_reported": s["removed_element_ref"],
            "requirement_ref_reported": s["requirement_ref"],
            "waiver_ref_reported": wid,
            "declared_waiver_match": bool(matches),
            "diagnostic": reason,
            "waiver_record_authenticated": False,
            "approval_authority_verified": False,
            "waiver_version_current_verified": False,
            "suppression_allowed": False,
            "real_diff_suppression_verified": False
        })
    extra = sorted(set(waivers) - referenced)
    result = {
        "schema_version": "PG11_C3_SUPPRESSION_WAIVER_CANDIDATE_V2",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg11_c2_sha256": sha,
        "std_gen_05_source_ref_reported": std_gen_05_source_ref,
        "suppression_observations_sha256": digest(suppression_observations),
        "waiver_observations_sha256": digest(waiver_observations),
        "suppressions": output,
        "unreferenced_waiver_refs_reported": extra,
        "declared_suppression_count": len(output),
        "real_diff_suppressions_extracted": False,
        "waivers_read_from_canonical_register": False,
        "waiver_signatures_verified": False,
        "all_suppressions_authorized": False,
        "code_deleted": False,
        "pg11_c3_pass": False,
        "pg11_c3_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "REAL_DIFF_SUPPRESSION_EXTRACTION_AND_STD_GEN_05_WAIVER_AUTHENTICATION"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
