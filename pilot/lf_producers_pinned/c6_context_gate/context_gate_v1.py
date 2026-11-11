"""PG C6 context admission candidate. Pure, isolated, no runtime / DB writes."""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

CONTRACT = "LF_PG_C6_ASSEMBLED_CONTEXT_V1"
CATALOG_REF = "ab361cf947fb9a34c874bf3e786b7f7478c85aa9"
REQUIRED = {"schema_version", "run_id", "catalog_version", "catalog_sha256",
            "skills", "active_domains", "rule_ids", "pending_rule_ids",
            "bytes", "approx_tokens", "assembled_sha256", "warnings"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verdict(status: str, code: str, **details: Any) -> dict:
    return {"status": status, "code": code, **details}


def gate(
    *,
    text: bytes,
    receipt: dict,
    source_catalog: bytes,
    source_skills: dict[str, bytes],
    approved_budget: dict | None,
    trusted_source: dict | None,
    expected_run_id: str,
    expected_domains: list[str],
    expected_required_ids: list[str],
    qualification_only: bool = True,
) -> dict:
    """All source/authority inputs must be obtained from a separate trusted control plane.

    This function verifies consistency; it does NOT authenticate its own caller or
    certify Git/Train/C3 provenance. Qualification PASS is never production admission.
    """
    if not qualification_only:
        return verdict("BLOCKED", "PRODUCTION_RELEASE_NOT_ATTESTED")
    if not trusted_source or trusted_source.get("commit") != CATALOG_REF or not trusted_source.get("qualification_approved"):
        return verdict("BLOCKED", "SOURCE_PROVENANCE_UNVERIFIED")
    if not isinstance(receipt, dict) or not REQUIRED.issubset(receipt):
        return verdict("BLOCKED", "INVALID_RECEIPT_SCHEMA")
    if receipt["schema_version"] != CONTRACT or receipt["run_id"] != expected_run_id:
        return verdict("BLOCKED", "RECEIPT_RUN_BINDING_MISMATCH")
    try:
        catalog = json.loads(source_catalog)
    except (ValueError, TypeError):
        return verdict("BLOCKED", "INVALID_CATALOG")
    if catalog.get("status") != "BORRADOR_EN_REPO_DE_CALIFICACION":
        return verdict("BLOCKED", "QUALIFICATION_SOURCE_STATUS_MISMATCH")
    if receipt["catalog_version"] != catalog.get("catalog_version") or receipt["catalog_sha256"] != _sha(source_catalog):
        return verdict("BLOCKED", "CATALOG_PIN_MISMATCH")
    if receipt["active_domains"] != expected_domains:
        return verdict("BLOCKED", "DOMAIN_BINDING_MISMATCH")
    if not isinstance(receipt["skills"], list) or not receipt["skills"]:
        return verdict("BLOCKED", "SKILL_SET_MISSING")
    if len({x.get("skill") for x in receipt["skills"] if isinstance(x, dict)}) != len(receipt["skills"]):
        return verdict("BLOCKED", "SKILL_DUPLICATE_OR_INVALID")
    for skill in receipt["skills"]:
        if not isinstance(skill, dict) or skill.get("skill") not in source_skills:
            return verdict("BLOCKED", "UNKNOWN_SKILL")
        try:
            spec = json.loads(source_skills[skill["skill"]])
        except (TypeError, ValueError):
            return verdict("BLOCKED", "INVALID_SKILL")
        expected = ".".join(catalog["catalog_version"].split(".")[:2])
        if spec.get("catalog_compat") != expected or skill.get("skill_version") != spec.get("skill_version"):
            return verdict("BLOCKED", "SKILL_VERSION_INCOMPATIBLE")
        if skill.get("skill_json_sha256") != _sha(source_skills[skill["skill"]]):
            return verdict("BLOCKED", "SKILL_HASH_MISMATCH")
        if skill.get("exclude_rule_ids"):
            return verdict("BLOCKED", "UNATTESTED_SKILL_EXCLUSIONS")
        if spec.get("exclude_rule_ids"):
            return verdict("BLOCKED", "SKILL_EXCLUSIONS_REQUIRE_REVIEW")
    active = set(expected_domains)
    known = {x["id"]: x for x in catalog["rules"]}
    mandatory = {rid for rid, rule in known.items() if rule["domain"] in active and rule.get("status") == "APROBADO"}
    if len(set(expected_required_ids)) != len(expected_required_ids) or set(expected_required_ids) != mandatory:
        return verdict("BLOCKED", "REQUIRED_RULE_SET_INVALID")
    if not isinstance(receipt["rule_ids"], list) or len(set(receipt["rule_ids"])) != len(receipt["rule_ids"]):
        return verdict("BLOCKED", "RULE_LIST_INVALID")
    if not mandatory.issubset(set(receipt["rule_ids"])):
        return verdict("BLOCKED", "REQUIRED_RULE_OMITTED")
    if any(x not in known or known[x]["domain"] not in active for x in receipt["rule_ids"]):
        return verdict("BLOCKED", "RULE_SCOPE_MISMATCH")
    expected_pending = [rid for rid in receipt["rule_ids"] if known[rid].get("status") in ("PENDIENTE_REVISION", "VALIDAR_CON_LEGAL")]
    if receipt["pending_rule_ids"] != expected_pending:
        return verdict("BLOCKED", "PENDING_RULE_MISMATCH")
    if receipt["assembled_sha256"] != _sha(text):
        return verdict("BLOCKED", "ASSEMBLED_CONTEXT_TAMPERED")
    try:
        decoded = text.decode("utf-8")
    except UnicodeDecodeError:
        return verdict("BLOCKED", "INVALID_CONTEXT_ENCODING")
    if receipt["bytes"] != len(text) or receipt["approx_tokens"] != (len(decoded) + 3) // 4:
        return verdict("BLOCKED", "CONTEXT_SIZE_RECEIPT_MISMATCH")
    if not isinstance(receipt["warnings"], list):
        return verdict("BLOCKED", "WARNING_SCHEMA_INVALID")
    if receipt["approx_tokens"] > 3000 and "CONTEXT_SIZE_WARNING" not in receipt["warnings"]:
        return verdict("BLOCKED", "CONTEXT_WARNING_OMITTED")
    if not isinstance(approved_budget, dict) or approved_budget.get("status") != "APPROVED":
        return verdict("REQUIRES_DECISION", "CONTEXT_BUDGET_NOT_APPROVED")
    limit = approved_budget.get("max_estimated_tokens")
    if type(limit) is not int or limit <= 0 or not approved_budget.get("decision_ref"):
        return verdict("REQUIRES_DECISION", "CONTEXT_BUDGET_NOT_APPROVED")
    if receipt["approx_tokens"] > limit:
        return verdict("REQUIRES_DECISION", "CONTEXT_BUDGET_EXCEEDED",
                       estimated_tokens=receipt["approx_tokens"], approved_max_tokens=limit)
    return verdict("PASS", "QUALIFICATION_CONTEXT_VALIDATED_NOT_RUNTIME_AUTHORIZED",
                   run_id=expected_run_id, context_sha256=_sha(text),
                   catalog_sha256=receipt["catalog_sha256"], estimated_tokens=receipt["approx_tokens"])
