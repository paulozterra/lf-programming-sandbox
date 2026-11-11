#!/usr/bin/env python3
"""Offline simulated readback host. No Supabase, secrets, authority or network.

A3 requires literal canonical-shaped supabase:// references and business=LF.
Those are synthetic COMPATIBILITY IDENTIFIERS, never provenance or credentials.
Every actual input is pinned to fixture://...@sha256 and source_attested=False.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "analysis/fixtures/sbx_auth_login"
TARGET = "SBX-AUTH-LOGIN"
BUSINESS = "LF"  # A1-A5 fixed contract; all fixture entities remain SBX- synthetic.
FILES = ("screen_contract.json", "direct_rules.json", "effective_rules.json",
         "policies.json", "elements.json", "states.json", "variants.json",
         "relations.json", "inventory.json", "ekb.json", "adr.json",
         "decision_asof.json", "semantic_signals.json")
HASHES = ROOT / "analysis/fixture_sha256_pins.json"


class FixtureBlocked(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _required(row, *keys):
    if not isinstance(row, dict) or any(k not in row or row[k] is None for k in keys):
        raise FixtureBlocked("SBX_FIXTURE_REQUIRED_FIELD_MISSING")


def load(name, folder=FIXTURES):
    if name not in FILES:
        raise FixtureBlocked("SBX_FIXTURE_NOT_WHITELISTED")
    path = folder / name
    if not path.is_file():
        raise FixtureBlocked("SBX_FIXTURE_MISSING:" + name)
    raw = path.read_bytes()
    pins = json.loads(HASHES.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != pins[name]:
        raise FixtureBlocked("SBX_FIXTURE_SHA256_MISMATCH:" + name)
    try:
        row = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise FixtureBlocked("SBX_FIXTURE_JSON_INVALID:" + name) from None
    _required(row, "fixture_schema", "simulated", "source_attested", "authority_verified", "imitates", "payload")
    if (row["fixture_schema"] != "SBX_SOURCE_READBACK_V1"
            or row["simulated"] is not True or row["source_attested"] is not False
            or row["authority_verified"] is not False
            or not isinstance(row["payload"], dict)):
        raise FixtureBlocked("SBX_FIXTURE_SIMULATION_CONTRACT_INVALID:" + name)
    return row["payload"], "fixture://sbx_auth_login/" + name + "@" + pins[name]


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / "analysis/programming_analysis" / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_all(folder=FIXTURES):
    results = {name: load(name, folder) for name in FILES}
    screen, direct, effective, policies, inventory = [results[x][0] for x in (
        "screen_contract.json", "direct_rules.json", "effective_rules.json",
        "policies.json", "inventory.json")]
    _required(screen, "screen_code", "screen_status", "contract_version", "screen_id", "contract")
    _required(direct, "target_ref", "rules", "rule_definitions")
    _required(effective, "screen_id", "consumer", "rules")
    _required(policies, "policy_objects", "policy_links")
    _required(inventory, "objects", "impact_rows", "dependency_rows", "status")
    if screen["screen_code"] != TARGET or direct["target_ref"] != TARGET:
        raise FixtureBlocked("SBX_FIXTURE_TARGET_MISMATCH")
    if not isinstance(inventory["objects"], list):
        raise FixtureBlocked("SBX_INVENTORY_REQUIRED")
    for row in effective["rules"]:
        _required(row, "code", "status", "pending_decision", "binding_source", "source_ref", "config")
        if row["status"] == "VIGENTE" and not row["pending_decision"] and not row["config"]:
            raise FixtureBlocked("SBX_VIGENTE_RULE_VALUE_CONFIG_MISSING:" + row["code"])
    return results


def a3_sources(inputs):
    screen = inputs["screen_contract.json"][0]
    direct = inputs["direct_rules.json"][0]
    effective = inputs["effective_rules.json"][0]
    policies = inputs["policies.json"][0]
    screen_ref = "supabase://lf_ops.pantallas/" + TARGET
    effective_ref = ("supabase://programacion.fn_input_effective_rule_links_v1/"
                     + str(effective["screen_id"]) + "/INPUT_GOVERNANCE")
    objects = copy.deepcopy(policies["policy_objects"])
    supplemental = [p["source_ref"] for p in objects
                    if p["read_origin"] == "DIRECT_CANONICAL_POLICY_LOOKUP"]
    return {
        "schema_version": "LF_SCREEN_SOURCE_READBACK_V1",
        "business": BUSINESS,
        "source_function": "lf_ops.fn_screen_contract_v1",
        "target_ref": TARGET,
        "screen_ref": screen_ref,
        "screen_status": screen["screen_status"],
        "contract_version": screen["contract_version"],
        "contract_sections": {k: copy.deepcopy(screen["contract"][k]) for k in
                             ("fields", "errors", "visual", "context", "metadata",
                              "profiles", "analytics", "evidence")},
        "linked_rules": copy.deepcopy(direct["rules"]),
        "policy_links": copy.deepcopy(policies["policy_links"]),
        "effective_rule_readback": {
            "screen_id": effective["screen_id"],
            "source_function": "programacion.fn_input_effective_rule_links_v1",
            "business": BUSINESS, "target_ref": TARGET,
            "consumer": "INPUT_GOVERNANCE", "source_ref": effective_ref,
            "source_attested": False, "rules": copy.deepcopy(effective["rules"])
        },
        "policy_resolution_readback": {
            "schema_version": "LF_SCREEN_POLICIES_READBACK_V1",
            "source_function": "lf_ops.fn_screen_contract_v1",
            "business": BUSINESS, "target_ref": TARGET,
            "source_ref": screen_ref, "source_attested": False,
            "policy_objects": objects,
            "supplemental_policy_source_refs": supplemental,
        },
    }


def run(request="Crear la pantalla de login SBX-AUTH-LOGIN con las reglas vigentes",
        folder=FIXTURES):
    try:
        inputs = read_all(folder)
        refs = {name: ref for name, (_, ref) in inputs.items()}
        semantic = copy.deepcopy(inputs["semantic_signals.json"][0])
        semantic["evidence_refs"] = [refs["semantic_signals.json"]]
        structured = {
            "business": BUSINESS,
            "request_identity": {"request_ref": refs["semantic_signals.json"],
                                 "request_kind": "USER_REQUEST"},
            "objective": {"problem_statement": request,
                          "desired_outcome": "Crear pantalla ficticia " + TARGET},
            "target_hints": [TARGET],
            "source_refs": [refs["semantic_signals.json"]],
            "provided_facts": [{"fact_code": "SOURCE_SCREEN_HINT", "value": TARGET,
                                "source_ref": refs["semantic_signals.json"]}],
            "constraints": ["Aplicar solo reglas SBX- vigentes y no pendientes"],
            "ambiguities": [], "declared_intent_kind": "UNKNOWN"
        }
        a1 = _module("sbx_a1", "steps/a1/validators/run.py").run(structured)
        stages = {"A1": a1}
        if a1["status"] != "VALID_OUTPUT":
            raise FixtureBlocked("SBX_A1_" + a1["status"] + ":" + ",".join(a1.get("blocking_codes", [])))
        a2 = _module("sbx_a2", "steps/a2/validators/run.py").run(a1, semantic)
        stages["A2"] = a2
        if a2["status"] == "BLOCKED":
            raise FixtureBlocked("SBX_A2_BLOCKED:" + ",".join(a2["blocking_codes"]))
        classification = a2["classification"]
        a3 = _module("sbx_a3", "steps/a3/validators/run.py").run(
            {"REQUEST_CONTEXT_V1": a1["payload"],
             "ANALYSIS_CHANGE_CLASSIFICATION_V1": classification},
            a3_sources(inputs))
        stages["A3"] = a3
        if a3["status"] == "BLOCKED":
            raise FixtureBlocked("SBX_A3_BLOCKED:" + ",".join(a3["blocking_codes"]))
        inv = inputs["inventory.json"][0]
        # Empty inventory is evidence of *unknown* impact, never no impact.
        sidecar = {"schema_version": "A4_EXISTING_IMPACT_CORE_READBACK_V1",
                   "business": BUSINESS, "target_ref": TARGET,
                   "source_attested": False, "inventory": inv["objects"]}
        a4 = _module("sbx_a4", "steps/a4/validators/run.py").run(a3, classification, sidecar)
        stages["A4"] = a4
        if a4["status"] == "BLOCKED":
            raise FixtureBlocked("SBX_A4_BLOCKED:" + ",".join(a4["blocking_codes"]))
        adr = inputs["adr.json"][0]
        _required(adr, "adr_trigger_review")
        review = copy.deepcopy(adr["adr_trigger_review"])
        review["evidence_ref"] = a3["source_refs"][0]
        decision = {"schema_version": "A5_GOVERNED_DECISION_READBACK_V1",
                    "business": BUSINESS, "target_ref": TARGET,
                    "source_attested": False,
                    "adr_trigger_review": review,
                    "asof_resolution": copy.deepcopy(inputs["decision_asof.json"][0])}
        a5 = _module("sbx_a5", "steps/a5/validators/run.py").run(
            {"REQUEST_CONTEXT_V1": a1["payload"],
             "ANALYSIS_CHANGE_CLASSIFICATION_V1": classification,
             "TARGETED_EVIDENCE_SET_V1": a3,
             "SHARED_CHANGE_IMPACT_ANALYSIS": a4}, decision)
        stages["A5"] = a5
        if a5["status"] == "BLOCKED":
            raise FixtureBlocked("SBX_A5_BLOCKED:" + ",".join(a5["blocking_codes"]))
        return {"schema_version": "SBX_A1_A5_FIXTURE_RUN_V1", "simulated": True,
                "source_attested": False, "authority_verified": False,
                "source_provenance": refs, "stages": stages}
    except FixtureBlocked as exc:
        return {"schema_version": "SBX_A1_A5_FIXTURE_RUN_V1", "simulated": True,
                "status": "BLOCKED", "blocking_codes": [exc.code],
                "source_attested": False, "authority_verified": False}
