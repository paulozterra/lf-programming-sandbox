#!/usr/bin/env python3
"""T2: source-only, deterministic contract skeleton; operations belong to constructor."""
from __future__ import annotations

from copy import deepcopy
import json

from contract_validate import ContractBlocked, deny


def _contract_sections(package):
    """Use A9's retained A3 screen-contract readback, not invented API endpoints."""
    try:
        ledger = package["programming_context_snapshot"]["decision_context"]["material_ledger"]
        sections = ledger["source_detail"]["a3_material_contract"]["contract_sections"]
    except (KeyError, TypeError):
        deny("T2_SCREEN_CONTRACT_SOURCE_UNRESOLVED")
    if not isinstance(sections, dict):
        deny("T2_SCREEN_CONTRACT_SOURCE_UNRESOLVED")
    return sections


def generate(module, package, atoms):
    if not isinstance(module, str) or not module or not isinstance(package, dict):
        deny("T2_SKELETON_INPUT_INVALID")
    sections = _contract_sections(package)
    related = [a for a in atoms if a.get("functional_module") == module
               and a.get("area") in ("BACKEND", "FRONTEND")]
    if {a["area"] for a in related} != {"BACKEND", "FRONTEND"}:
        deny("T2_CONTRACT_UNPAIRED")
    requirement_ids = sorted({rid for atom in related
                              for rid in atom.get("requirement_ids", [])})
    source_req_ids = {r.get("requirement_id") for r in package.get("requirements", [])}
    if not requirement_ids or not set(requirement_ids).issubset(source_req_ids):
        deny("T2_REQUIREMENT_SOURCE_UNRESOLVED")
    fields, errors = [], []
    for source_key, code_key, output in (
            ("fields", "field_code", fields), ("errors", "error_code", errors)):
        entries = sections.get(source_key)
        if not isinstance(entries, list):
            deny("T2_SCREEN_" + source_key.upper() + "_UNRESOLVED")
        seen = set()
        for row in entries:
            if not isinstance(row, dict) or not isinstance(row.get(code_key), str) or not row[code_key]:
                deny("T2_SCREEN_" + source_key.upper() + "_INVALID")
            if row.get("status") != "VIGENTE":
                continue
            if row[code_key] in seen:
                deny("T2_SCREEN_" + source_key.upper() + "_DUPLICATE")
            seen.add(row[code_key])
            item = {code_key: row[code_key]}
            if source_key == "fields":
                if not isinstance(row.get("required"), bool):
                    deny("T2_FIELD_REQUIRED_UNRESOLVED")
                item["required"] = row["required"]
            elif "generic" in row:
                if not isinstance(row["generic"], bool):
                    deny("T2_ERROR_GENERIC_INVALID")
                item["generic"] = row["generic"]
            output.append(item)
    if not fields and not errors:
        deny("T2_SCREEN_OBLIGATIONS_EMPTY")
    rules = []
    for rule in package.get("applicable_rules", []):
        if not isinstance(rule, dict):
            deny("T2_RULE_SOURCE_INVALID")
        rid = rule.get("requirement_id")
        if rid not in requirement_ids:
            continue
        if (not isinstance(rule.get("rule_code"), str)
                or not isinstance(rule.get("source_ref"), str)
                ):
            deny("T2_RULE_SOURCE_INVALID")
        rules.append({key: deepcopy(rule[key]) for key in (
            "rule_code", "requirement_id", "source_ref", "source_status")
            if key in rule})
    rules.sort(key=lambda row: (row["requirement_id"], row["rule_code"]))
    if not rules:
        deny("T2_RULES_UNRESOLVED")
    return {
        "schema_version": "T2_CONTRACT_SKELETON_V1",
        "functional_module": module,
        "source": "A9.programming_context_snapshot.decision_context.material_ledger.source_detail.a3_material_contract.contract_sections",
        "fields": fields,
        "errors": errors,
        "requirement_ids": requirement_ids,
        "rules": rules,
        "production_authority": False,
    }


def render(module, package, atoms):
    return json.dumps(generate(module, package, atoms), sort_keys=True,
                      ensure_ascii=False, separators=(",", ":")) + "\n"
