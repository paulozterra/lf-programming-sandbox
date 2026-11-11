"""PG-03_C2 qualification-only boundary for EXISTING C6 skills.select receipt.

Does not select skills, calculate authoritative catalog release, run a model,
resolve project L3 or create a dispatcher. An authenticated readback of the
selector/source and current run must be provided by governed runtime.
"""
import hashlib
import json
import re

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SELECTOR_SOURCE = "standards/tools/skills.py"

def _block(code):
    return {"status": "BLOCKED", "code": code, "authority": False,
            "dispatch_allowed": False, "selector_execution_verified": False}

def validate_skill_selection_receipt(*, selection, source_skill_jsons,
                                     expected_run_id, expected_domains,
                                     expected_stack_commit, expected_catalog_sha256,
                                     expected_selector_commit):
    """Check exact version/digest/domain coverage, but not selection algorithm."""
    if not isinstance(selection, dict) or selection.get("status") != "CANDIDATE_NOT_ADMITTED":
        return _block("SELECTION_CANDIDATE_REQUIRED")
    if not all(isinstance(x, str) and x for x in (expected_run_id, expected_stack_commit,
             expected_catalog_sha256, expected_selector_commit)):
        return _block("EXPECTED_BINDINGS_INVALID")
    if not SHA40.fullmatch(expected_stack_commit) or not SHA40.fullmatch(expected_selector_commit) or not SHA64.fullmatch(expected_catalog_sha256):
        return _block("EXPECTED_DIGEST_INVALID")
    if selection.get("run_id") != expected_run_id or selection.get("stack_commit") != expected_stack_commit:
        return _block("RUN_OR_STACK_DRIFT")
    if selection.get("catalog_sha256") != expected_catalog_sha256:
        return _block("CATALOG_PIN_DRIFT")
    if selection.get("selector_repo") != "paulozterra/lf-programming-sandbox" or selection.get("selector_path") != SELECTOR_SOURCE or selection.get("selector_commit") != expected_selector_commit:
        return _block("SELECTOR_PROVENANCE_DRIFT")
    if not isinstance(expected_domains, list) or not expected_domains or any(
        not isinstance(d, str) or not d for d in expected_domains
    ) or len(set(expected_domains)) != len(expected_domains):
        return _block("EXPECTED_DOMAINS_INVALID")
    if selection.get("active_domains") != sorted(expected_domains):
        return _block("DOMAIN_BINDING_DRIFT")
    skills = selection.get("skills")
    if not isinstance(skills, list) or not skills:
        return _block("SKILLS_MISSING")
    if not isinstance(source_skill_jsons, dict):
        return _block("SKILL_SOURCES_MISSING")
    observed = set()
    covered = set()
    for skill in skills:
        if not isinstance(skill, dict) or not isinstance(skill.get("skill"), str):
            return _block("SKILL_RECEIPT_INVALID")
        slug = skill["skill"]
        if slug in observed:
            return _block("SKILL_DUPLICATE")
        observed.add(slug)
        raw = source_skill_jsons.get(slug)
        if not isinstance(raw, bytes):
            return _block("SKILL_SOURCE_MISSING")
        if skill.get("skill_json_sha256") != hashlib.sha256(raw).hexdigest():
            return _block("SKILL_DIGEST_DRIFT")
        try:
            source = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return _block("SKILL_SOURCE_INVALID")
        if not isinstance(source, dict) or source.get("schema_version") != "LF_STACK_SKILL_V1":
            return _block("SKILL_SOURCE_INVALID")
        if source.get("skill_id") != slug or source.get("skill_version") != skill.get("skill_version"):
            return _block("SKILL_VERSION_DRIFT")
        if not isinstance(source.get("domains"), list) or len(set(source["domains"])) != len(source["domains"]):
            return _block("SKILL_DOMAINS_INVALID")
        allowed = set(source["domains"]) & set(expected_domains)
        if not allowed:
            return _block("UNNEEDED_SKILL_FOR_ACTIVE_DOMAINS")
        if source.get("exclude_rule_ids"):
            return _block("SKILL_EXCLUSIONS_REQUIRE_REVIEW")
        covered.update(allowed)
    if covered != set(expected_domains):
        return _block("ACTIVE_DOMAIN_SKILL_COVERAGE_MISSING")
    # Source shape/hash checks are not independent evidence that skills.select
    # produced this set or the source was authenticated via a trusted reader.
    return {"status": "CANDIDATE_NOT_ADMITTED",
            "code": "SKILL_RECEIPT_SHAPE_BOUND_SELECTION_UNATTESTED",
            "authority": False, "dispatch_allowed": False,
            "selector_execution_verified": False, "skills": sorted(observed),
            "active_domains": sorted(covered),
            "l3_type_b_verified": False, "precedence_verified": False,
            "catalog_release_verified": False}
