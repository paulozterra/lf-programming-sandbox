"""PG-11_C2: candidate terminology, catalog-code and message trace inventory.

All glossary, code, message and neighbor matches are DECLARED, not independently
read from real sources. Never infer a PASS from a zero-finding declaration.
"""
import hashlib
import json
from copy import deepcopy

SOURCE_SCHEMA = "PG11_C1_DIFF_HYGIENE_CANDIDATE_V1"
KIND = {"DOMAIN_IDENTIFIER", "CATALOG_CODE", "USER_MESSAGE", "NEIGHBOR_CONVENTION"}
STANDARD = {"DOMAIN_IDENTIFIER": "STD-GEN-01",
            "CATALOG_CODE": "STD-GEN-07",
            "USER_MESSAGE": "STD-MSG-02",
            "NEIGHBOR_CONVENTION": "MODULE_NEIGHBOR"}

class PG11C2Blocked(ValueError):
    pass

def fail(reason):
    raise PG11C2Blocked(reason)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()

def ref(v):
    return isinstance(v, str) and bool(v.strip()) and v == v.strip()

def prepare_pg11_c2(*, pg11_c1, declared_changed_paths, terminology_observations,
                    glossary_snapshot_ref, catalog_snapshot_ref, messages_snapshot_ref,
                    neighbor_baseline_ref):
    """Prepare a full declaration per *reported* changed identifier/code/message.

    Each observation: path, symbol_ref, kind, literal_value, source_ref, term_ids,
      term_exists_reported, term_matches_reported, literal_match_reported,
      neighbor_match_reported. DOMAIN_IDENTIFIER requires at least one term_id.
    """
    if not isinstance(pg11_c1, dict) or pg11_c1.get("schema_version") != SOURCE_SCHEMA:
        fail("PG11_C2_UPSTREAM_SCHEMA_INVALID")
    source_sha = digest({k:v for k,v in pg11_c1.items() if k != "candidate_sha256"})
    if pg11_c1.get("candidate_sha256") != source_sha:
        fail("PG11_C2_UPSTREAM_DIGEST_INVALID")
    if (pg11_c1.get("status") != "CANDIDATE_NOT_ADMITTED" or
        pg11_c1.get("pg11_c1_pass") is not False or
        pg11_c1.get("pg11_c1_admitted") is not False or
        pg11_c1.get("handoff_allowed") is not False or
        pg11_c1.get("production_authority") is not False or
        pg11_c1.get("real_git_diff_readback_verified") is not False):
        fail("PG11_C2_UPSTREAM_AUTHORITY_INVALID")
    if not all(ref(x) for x in (glossary_snapshot_ref, catalog_snapshot_ref,
                               messages_snapshot_ref, neighbor_baseline_ref)):
        fail("PG11_C2_BASELINE_REFERENCE_REQUIRED")
    if not isinstance(declared_changed_paths, list) or not declared_changed_paths or (
        not all(ref(p) for p in declared_changed_paths)
        or len(set(declared_changed_paths)) != len(declared_changed_paths)):
        fail("PG11_C2_PATH_SET_INVALID")
    if not isinstance(terminology_observations, list) or not terminology_observations:
        fail("PG11_C2_OBSERVATIONS_EMPTY")
    seen, rows, findings = set(), [], []
    observed_paths = set()
    for row in terminology_observations:
        fields = {"path", "symbol_ref", "kind", "literal_value", "source_ref", "term_ids",
                  "term_exists_reported", "term_matches_reported",
                  "literal_match_reported", "neighbor_match_reported"}
        if not isinstance(row, dict) or set(row) != fields:
            fail("PG11_C2_OBSERVATION_SHAPE_INVALID")
        p, symbol, kind = row["path"], row["symbol_ref"], row["kind"]
        if p not in declared_changed_paths or not ref(symbol) or kind not in KIND:
            fail("PG11_C2_OBSERVATION_ID_INVALID")
        key = (p, symbol, kind)
        if key in seen:
            fail("PG11_C2_DUPLICATE_OBSERVATION")
        seen.add(key)
        observed_paths.add(p)
        if not ref(row["literal_value"]) or not ref(row["source_ref"]):
            fail("PG11_C2_LITERAL_OR_SOURCE_MISSING")
        terms = row["term_ids"]
        if not isinstance(terms, list) or not all(ref(x) for x in terms) or len(set(terms)) != len(terms):
            fail("PG11_C2_TERM_ID_LIST_INVALID")
        if kind == "DOMAIN_IDENTIFIER" and not terms:
            fail("PG11_C2_DOMAIN_IDENTIFIER_WITHOUT_TERM_ID")
        for field in ("term_exists_reported", "term_matches_reported",
                      "literal_match_reported", "neighbor_match_reported"):
            if type(row[field]) is not bool:
                fail("PG11_C2_DECLARATION_BOOLEAN_REQUIRED")
        if kind == "DOMAIN_IDENTIFIER":
            if not row["term_exists_reported"]:
                findings.append({"path":p,"symbol_ref":symbol,"reason":"GLOSSARY_TERM_NOT_FOUND_REPORTED"})
            if not row["term_matches_reported"]:
                findings.append({"path":p,"symbol_ref":symbol,"reason":"GLOSSARY_TERM_MISMATCH_REPORTED"})
        if kind in {"CATALOG_CODE", "USER_MESSAGE"} and not row["literal_match_reported"]:
            findings.append({"path":p,"symbol_ref":symbol,"reason":"CANONICAL_LITERAL_MISMATCH_REPORTED"})
        if not row["neighbor_match_reported"]:
            findings.append({"path":p,"symbol_ref":symbol,"reason":"NEIGHBOR_CONVENTION_MISMATCH_REPORTED"})
        rows.append({
            "path": p, "symbol_ref":symbol, "kind":kind, "standard_ref":STANDARD[kind],
            "literal_value_reported":row["literal_value"],
            "source_ref_reported":row["source_ref"], "term_ids_reported":sorted(terms),
            "term_exists_reported":row["term_exists_reported"],
            "term_matches_reported":row["term_matches_reported"],
            "literal_match_reported":row["literal_match_reported"],
            "neighbor_match_reported":row["neighbor_match_reported"],
            "real_source_verified":False,
            "term_ids_positively_verified":False,
            "literal_compared_to_canonical":False,
        })
    unobserved = sorted(set(declared_changed_paths) - observed_paths)
    if unobserved:
        findings.extend({"path":p,"symbol_ref":None,"reason":"NO_OBSERVATION_FOR_CHANGED_PATH"} for p in unobserved)
    result = {
        "schema_version":"PG11_C2_TERMINOLOGY_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg11_c1_sha256":source_sha,
        "declared_changed_paths_sha256":digest(declared_changed_paths),
        "observations_sha256":digest(terminology_observations),
        "glossary_snapshot_ref_reported":glossary_snapshot_ref,
        "catalog_snapshot_ref_reported":catalog_snapshot_ref,
        "messages_snapshot_ref_reported":messages_snapshot_ref,
        "neighbor_baseline_ref_reported":neighbor_baseline_ref,
        "observations":sorted(rows,key=lambda x:(x["path"],x["symbol_ref"],x["kind"])),
        "reported_findings":sorted(findings,key=lambda x:(x["path"],x["symbol_ref"] or "",x["reason"])),
        "all_new_domain_identifiers_extracted":False,
        "changed_files_scanned":False,
        "glossary_terms_verified":False,
        "catalog_codes_verified":False,
        "messages_verified":False,
        "neighbor_consistency_verified":False,
        "positive_coverage_verified":False,
        "pg11_c2_pass":False,"pg11_c2_admitted":False,
        "handoff_allowed":False,"production_authority":False,
        "next_gate":"REAL_DIFF_IDENTIFIER_EXTRACTION_AND_CANONICAL_GLOSSARY_READBACK"
    }
    result["candidate_sha256"]=digest(result)
    return deepcopy(result)
