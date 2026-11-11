"""PG11 source-only hardening: hunk coverage, waiver refusal, canonical identity.

This module does NOT inspect a real Git diff or authenticate waiver/identity
registries. Inputs are untrusted. It never grants PASS, approval or authority.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA = re.compile(r"^[0-9a-f]{64}$")
class PG11IntegrityBlocked(ValueError): pass
def block(code): raise PG11IntegrityBlocked(code)
def ref(x): return isinstance(x,str) and bool(x.strip()) and x==x.strip()
def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def frozen(x,schema):
    if not isinstance(x,dict) or x.get("schema_version")!=schema or x.get("status")!="CANDIDATE_NOT_ADMITTED":
        block("PG11_EXTENSION_UPSTREAM_SCHEMA")
    val=x.get("candidate_sha256")
    if not isinstance(val,str) or not SHA.fullmatch(val) or val!=digest({k:v for k,v in x.items() if k!="candidate_sha256"}):
        block("PG11_EXTENSION_UPSTREAM_DIGEST")
    if x.get("production_authority") is not False or x.get("handoff_allowed") is not False:
        block("PG11_EXTENSION_UNAUTHORIZED_SOURCE")
    return val

def prepare_pg11_hunk_trace(*,pg11_c4,hunk_manifest,hunk_links):
    """Each changed hunk, not only file, must map to C4 authorized scope.

    hunk_manifest: [{hunk_id,path,old_start,old_count,new_start,new_count,
      content_sha256,header_ref}].
    hunk_links: [{hunk_id,requirement_ref,batch_ref,scope_ref,evidence_ref}].
    Actual diff hunks/identity must be supplied by an external trusted reader.
    """
    h4=frozen(pg11_c4,"PG11_C4_DIFF_REQUIREMENT_BATCH_TRACE_CANDIDATE_V1")
    changes=pg11_c4.get("changes")
    if not isinstance(changes,list) or not changes:block("PG11_HUNK_C4_CHANGES_INVALID")
    scopes={}
    for change in changes:
        if not isinstance(change,dict) or not ref(change.get("path")) or change["path"] in scopes:
            block("PG11_HUNK_C4_PATH_INVALID")
        links=change.get("links")
        if not isinstance(links,list) or not links:block("PG11_HUNK_C4_LINKS_MISSING")
        scopes[change["path"]]={
            (l["requirement_ref"],l["batch_ref"],l["scope_ref"]) for l in links}
    if not isinstance(hunk_manifest,list) or not hunk_manifest or not isinstance(hunk_links,list):
        block("PG11_HUNK_INPUT_INVALID")
    manifest={}
    for h in hunk_manifest:
        if not isinstance(h,dict) or set(h)!={"hunk_id","path","old_start","old_count",
            "new_start","new_count","content_sha256","header_ref"}:
            block("PG11_HUNK_SHAPE_INVALID")
        hid=h["hunk_id"]
        if not ref(hid) or hid in manifest or h["path"] not in scopes or not ref(h["header_ref"]):
            block("PG11_HUNK_IDENTITY_INVALID")
        if not isinstance(h["content_sha256"],str) or not SHA.fullmatch(h["content_sha256"]):
            block("PG11_HUNK_CONTENT_DIGEST_INVALID")
        for k in ("old_start","old_count","new_start","new_count"):
            if type(h[k]) is not int or h[k]<0:block("PG11_HUNK_RANGE_INVALID")
        if h["old_count"]+h["new_count"]==0:block("PG11_HUNK_EMPTY_RANGE")
        manifest[hid]=h
    if set(scopes)!={h["path"] for h in manifest.values()}:
        block("PG11_HUNK_CHANGED_PATH_UNCOVERED")
    linked={}
    for row in hunk_links:
        keys={"hunk_id","requirement_ref","batch_ref","scope_ref","evidence_ref"}
        if not isinstance(row,dict) or set(row)!=keys or any(not ref(row[k]) for k in keys):
            block("PG11_HUNK_LINK_SHAPE_INVALID")
        hid=row["hunk_id"]
        if hid not in manifest:block("PG11_HUNK_UNKNOWN_LINK")
        link=(row["requirement_ref"],row["batch_ref"],row["scope_ref"])
        if link not in scopes[manifest[hid]["path"]]:
            block("PG11_HUNK_LINK_NOT_AUTHORIZED")
        entries=linked.setdefault(hid,set())
        if link in entries:block("PG11_HUNK_DUPLICATE_LINK")
        entries.add(link)
    missing=sorted(set(manifest)-set(linked))
    if missing:block("PG11_HUNK_ORPHAN:"+",".join(missing))
    result={"schema_version":"PG11_C4_HUNK_TRACE_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED","source_pg11_c4_sha256":h4,
        "hunk_manifest_sha256":digest(hunk_manifest),"hunk_links_sha256":digest(hunk_links),
        "hunk_count_reported":len(manifest),
        "hunks":[{"hunk_id":hid,"path":manifest[hid]["path"],
                  "hunk_content_sha256_reported":manifest[hid]["content_sha256"],
                  "authorized_links_reported":[list(k) for k in sorted(linked[hid])],
                  "real_diff_hunk_verified":False,"requirement_verified":False}
                 for hid in sorted(manifest)],
        "git_diff_readback_verified":False,"hunk_coverage_verified":False,
        "handoff_allowed":False,"production_authority":False}
    result["candidate_sha256"]=digest(result)
    return result

def reject_invalid_waiver(*,pg11_c3,waiver_observations,expected_standard="STD-GEN-05"):
    """Reject expired/wrong-standard waiver even when its ref is well formed."""
    h3=frozen(pg11_c3,"PG11_C3_SUPPRESSION_WAIVER_CANDIDATE_V1")
    if expected_standard!="STD-GEN-05" or not isinstance(waiver_observations,list):
        block("PG11_WAIVER_STANDARD_INVALID")
    rows={}
    for w in waiver_observations:
        if not isinstance(w,dict) or not ref(w.get("waiver_ref")) or w["waiver_ref"] in rows:
            block("PG11_WAIVER_SHAPE_OR_DUPLICATE")
        rows[w["waiver_ref"]]=w
        if w.get("standard_ref")!=expected_standard:
            block("PG11_WAIVER_WRONG_STD_GEN_05")
        if w.get("approval_status_reported")=="EXPIRED":
            block("PG11_WAIVER_EXPIRED")
        if w.get("approval_status_reported")!="APPROVED":
            block("PG11_WAIVER_NOT_APPROVED")
    suppressions=pg11_c3.get("suppressions")
    if not isinstance(suppressions,list):block("PG11_WAIVER_SOURCE_INVALID")
    for row in suppressions:
        wid=row.get("waiver_ref_reported")
        if not ref(wid) or wid not in rows:block("PG11_WAIVER_MISSING")
        w=rows[wid]
        if w.get("scope_path")!=row.get("path_reported") or w.get("suppression_id")!=row.get("suppression_id"):
            block("PG11_WAIVER_SCOPE_MISMATCH")
        if row.get("diagnostic")!="APPROVED_REPORTED_BUT_UNAUTHENTICATED":
            block("PG11_WAIVER_C3_DECLARATION_INVALID")
    result={"schema_version":"PG11_C3_WAIVER_BOUNDARY_CANDIDATE_V1",
       "status":"CANDIDATE_NOT_ADMITTED",
       "source_pg11_c3_sha256":h3,"waiver_observations_sha256":digest(waiver_observations),
       "waivers_reported":len(rows),"waiver_authenticity_verified":False,
       "waiver_expiry_checked_against_clock":False,"suppression_allowed":False,
       "production_authority":False,"handoff_allowed":False}
    result["candidate_sha256"]=digest(result)
    return result

def guard_pg11_reviewer_aliases(*,pg11_c5,principal_alias_records):
    """Use caller-supplied canonical principal mappings. Never trust display names.

    Each record: {principal_ref,canonical_person_ref,identity_provider_ref}.
    Both builder and reviewer must map; missing mappings FAIL closed.
    Same canonical person across different aliases is SELF_REVIEW.
    """
    h5=frozen(pg11_c5,"PG11_C5_INDEPENDENT_REVIEW_CANDIDATE_V1")
    if not isinstance(principal_alias_records,list):block("PG11_REVIEW_ALIAS_RECORDS_INVALID")
    mapping={}
    for item in principal_alias_records:
        if not isinstance(item,dict) or set(item)!={"principal_ref","canonical_person_ref","identity_provider_ref"} or any(
            not ref(item[k]) for k in item):
            block("PG11_REVIEW_ALIAS_SHAPE_INVALID")
        pid=item["principal_ref"]
        if pid in mapping:block("PG11_REVIEW_ALIAS_DUPLICATE")
        mapping[pid]=item["canonical_person_ref"]
    rows=pg11_c5.get("reviews")
    if not isinstance(rows,list) or not rows:block("PG11_REVIEW_ROWS_MISSING")
    for row in rows:
        b=row["builder_principal_ref_reported"]
        r=row["reviewer_principal_ref_reported"]
        if b not in mapping or r not in mapping:block("PG11_REVIEW_CANONICAL_IDENTITY_MISSING")
        if mapping[b]==mapping[r]:block("PG11_SELF_REVIEW_CANONICAL_ALIAS")
    result={"schema_version":"PG11_C5_CANONICAL_IDENTITY_GUARD_CANDIDATE_V1",
       "status":"CANDIDATE_NOT_ADMITTED","source_pg11_c5_sha256":h5,
       "principal_alias_records_sha256":digest(principal_alias_records),
       "review_count_reported":len(rows),
       "canonical_differences_reported_unverified":True,
       "identity_provider_readback_verified":False,"review_executed":False,
       "independence_verified":False,"production_authority":False,"handoff_allowed":False}
    result["candidate_sha256"]=digest(result)
    return result


def reject_waiver_expired_at(*, pg11_c3, waiver_observations, evaluated_at):
    """Check expiry using explicit timezone-aware ISO-8601 evaluation instant.

    Each waiver must supply expires_at as an ISO-8601 instant with timezone.
    EXPIRES_AT <= EVALUATED_AT is expired (exact boundary is blocked).
    Inputs/clock remain caller-supplied; no source/clock authentication here.
    """
    from datetime import datetime, timezone
    original = reject_invalid_waiver(
        pg11_c3=pg11_c3, waiver_observations=waiver_observations)
    def instant(value, error):
        if (not isinstance(value, str) or not value.strip()
                or value != value.strip()):
            block(error)
        try:
            parsed = datetime.fromisoformat(
                value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError:
            block(error)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            block(error)
        return parsed.astimezone(timezone.utc)
    current = instant(evaluated_at, "PG11_WAIVER_EVALUATION_TIME_INVALID")
    dates = []
    for w in waiver_observations:
        if "expires_at" not in w:
            block("PG11_WAIVER_EXPIRY_MISSING")
        expiry = instant(w["expires_at"], "PG11_WAIVER_EXPIRES_AT_INVALID")
        if current >= expiry:
            block("PG11_WAIVER_EXPIRED_BY_TIMESTAMP")
        dates.append({"waiver_ref": w["waiver_ref"],
            "expires_at_reported": w["expires_at"]})
    result = {
        "schema_version": "PG11_C3_WAIVER_TIME_BOUNDARY_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg11_c3_sha256": original["source_pg11_c3_sha256"],
        "waiver_observations_sha256": digest(waiver_observations),
        "evaluated_at_reported": evaluated_at,
        "expiration_rows_reported": sorted(dates, key=lambda x: x["waiver_ref"]),
        "expiry_compared_to_supplied_clock": True,
        "evaluation_clock_authenticated": False,
        "waiver_registry_authenticated": False,
        "suppression_allowed": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "TRUSTED_UTC_CLOCK_AND_CANONICAL_STD_GEN_05_WAIVER_READBACK",
    }
    result["candidate_sha256"] = digest(result)
    return result
