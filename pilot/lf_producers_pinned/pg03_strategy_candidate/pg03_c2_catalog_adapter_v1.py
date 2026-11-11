"""PG-03_C2 catalog-shape adapter for the EXISTING domain rules projector.

This module does not resolve stack, select skills, release a catalog, decide
precedence or grant authority. Raw catalog bytes are pinned by the caller; the
pin alone does not authenticate source or currentness.
"""
import hashlib
import json

class C2CatalogBlocked(ValueError):
    pass

def adapt_catalog_for_domain_projection(*, raw_catalog, expected_sha256, requested_domains):
    if not isinstance(raw_catalog, bytes) or not raw_catalog:
        raise C2CatalogBlocked("CATALOG_SOURCE_MISSING")
    sha = hashlib.sha256(raw_catalog).hexdigest()
    if not isinstance(expected_sha256, str) or expected_sha256 != sha:
        raise C2CatalogBlocked("CATALOG_DIGEST_DRIFT")
    try:
        catalog = json.loads(raw_catalog)
    except (ValueError, UnicodeDecodeError):
        raise C2CatalogBlocked("CATALOG_JSON_INVALID")
    if not isinstance(catalog, dict) or catalog.get("schema_version") != "LF_STANDARDS_CATALOG_V1":
        raise C2CatalogBlocked("CATALOG_SCHEMA_INVALID")
    if catalog.get("status") != "BORRADOR_EN_REPO_DE_CALIFICACION":
        # Only this untrusted/source-only qualification shape is supported.
        # Do not infer that another status is a valid governed release.
        raise C2CatalogBlocked("CATALOG_QUALIFICATION_STATUS_INVALID")
    if not isinstance(requested_domains, list) or not requested_domains or any(
        not isinstance(domain, str) or not domain.strip() for domain in requested_domains
    ) or len(requested_domains) != len(set(requested_domains)):
        raise C2CatalogBlocked("ACTIVE_DOMAINS_INVALID")
    declared = catalog.get("domains")
    rules = catalog.get("rules")
    if not isinstance(declared, list) or not isinstance(rules, list):
        raise C2CatalogBlocked("CATALOG_STRUCTURE_INVALID")
    domain_map = {}
    for row in declared:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in domain_map:
            raise C2CatalogBlocked("CATALOG_DOMAINS_INVALID")
        applies = row.get("applies_to")
        if not isinstance(applies, list) or any(not isinstance(x, str) for x in applies):
            raise C2CatalogBlocked("CATALOG_DOMAINS_INVALID")
        domain_map[row["id"]] = applies
    if any(d not in domain_map for d in requested_domains):
        raise C2CatalogBlocked("UNKNOWN_ACTIVE_DOMAIN")
    selected = []
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not rule["id"]:
            raise C2CatalogBlocked("CATALOG_RULE_INVALID")
        rid, domain = rule["id"], rule.get("domain")
        if rid in seen or domain not in domain_map:
            raise C2CatalogBlocked("CATALOG_RULE_INVALID")
        seen.add(rid)
        # Preserve L1 transversal applicability but do not copy the entire
        # catalog into model context. PG-03's existing projector understands
        # the explicit GLOBAL sentinel for these rules.
        applies_all = "all" in domain_map[domain]
        if domain not in requested_domains and not applies_all:
            continue
        if not isinstance(rule.get("rule"), str) or not rule["rule"].strip():
            raise C2CatalogBlocked("CATALOG_RULE_TEXT_MISSING")
        selected.append({
            "id": rid,
            "domain": "GLOBAL" if applies_all and domain not in requested_domains else domain,
            "text": rule["rule"],
            "status": rule.get("status"),
            "source_domain": domain,
        })
    if not selected:
        raise C2CatalogBlocked("NO_APPLICABLE_RULES")
    return {
        "status": "CANDIDATE_NOT_ADMITTED",
        "authority": False,
        "catalog_sha256": sha,
        "catalog_version": catalog.get("catalog_version"),
        "catalog": {"rules": selected},
        "source_rules_count": len(rules),
        "projected_rules_count": len(selected),
        "skills_selection_verified": False,
        "precedence_verified": False,
        "l3_type_b_verified": False,
        "catalog_release_verified": False,
    }
