"""A6 implementability projection: WHAT only; no runtime qualification.

Canonical A6 contract is a pinned F0 blob. The copied profile schema and
cross-field validator are the *future A9 envelope* gate, not an A6 bypass.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from analysis.host.simulated_admission_gate import (
    MODE, FALSE_FLAGS, AdmissionBlocked, digest, verify,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_implementability_contract_v1.json"
PROFILE = ROOT / "analysis/reference/profiles/programming_analysis_lf"
# Explicit reuse. Do not author competing runtime_output schema/validator.
RUNTIME_SCHEMA = PROFILE / "schemas/runtime_output.schema.json"
RUNTIME_VALIDATOR = PROFILE / "validators/runtime_validate.py"

# Closed fictitious SOURCE-BOUND test corpus: no inferred stack design,
# implementation class, data model, endpoint, or deployment choice.
EXPECTED = {
    "SBX-R-USER": ("Se exige identificar al usuario antes de autenticar.",
                   "Sin identificador de usuario, el acceso no se concede."),
    "SBX-R-PASS": ("Se exige una contraseña para autenticar.",
                   "Sin contraseña, el acceso no se concede."),
    "SBX-R-LOCK": ("Tras cinco intentos fallidos se impide el acceso durante quince minutos.",
                   "El quinto fallo activa el bloqueo; antes de quince minutos no se permite acceso."),
    "SBX-R-HASH": ("Las contraseñas almacenadas están protegidas con BCrypt.",
                   "La verificación confirma BCrypt y que no se guarda contraseña en claro."),
    "SBX-R-LOG": ("La contraseña jamás aparece en registros de operación.",
                  "Los registros de un intento de acceso no contienen la contraseña suministrada."),
    "SBX-R-ERR": ("Los fallos no revelan existencia de usuario y la sesión expira a los treinta minutos.",
                  "Errores de usuario inexistente y clave errónea son indistinguibles; sesión expira a los treinta minutos."),
}
HOW_FORBIDDEN = (" rounds", "en clase ", "class ", "controller", "repository",
                 "framework", "endpoint ", "método interno", "usar BCrypt 12")


def _blocked(code):
    raise AdmissionBlocked(code)


def _profile_reuse():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (contract.get("schema_version") != "ANALYSIS_IMPLEMENTABILITY_CONTRACT_V1"
            or contract.get("output_contract") != "IMPLEMENTABILITY_SCHEMA_V1"
            or contract.get("no_parallel_engine") is not True):
        _blocked("F2_A6_CANONICAL_CONTRACT_DRIFT")
    schema = json.loads(RUNTIME_SCHEMA.read_text(encoding="utf-8"))
    if (schema.get("properties", {}).get("schema_version", {}).get("const")
            != "ANALYSIS_IMPLEMENTATION_PACKAGE_V1"):
        _blocked("F2_A6_SHARED_RUNTIME_SCHEMA_DRIFT")
    spec = importlib.util.spec_from_file_location("sbx_a9_runtime_validator", RUNTIME_VALIDATOR)
    if spec is None or spec.loader is None:
        _blocked("F2_A6_SHARED_RUNTIME_VALIDATOR_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "validate", None)):
        _blocked("F2_A6_SHARED_RUNTIME_VALIDATOR_MISSING")
    # The existing validator applies to the final A9 package, not to A6.
    return contract


def validate_obligation(item, contract):
    required = [x.removesuffix("[]") for x in
                contract["requirement_contract"]["required_fields"]]
    if (not isinstance(item, dict)
            or any(k not in item for k in required)
            or not isinstance(item.get("acceptance_signals"), list)
            or not item["acceptance_signals"]
            or not all(isinstance(x, str) and x.strip()
                       for x in item["acceptance_signals"])):
        _blocked("F2_A6_ACCEPTANCE_CRITERION_REQUIRED")
    if item.get("area") not in ("UNKNOWN", "BACKEND", "FRONTEND", "DATA"):
        _blocked("F2_A6_AREA_INVALID")
    if item["area"] != "UNKNOWN" and not item.get("area_evidence_refs"):
        _blocked("F2_A6_AREA_WITHOUT_SOURCE")
    if any(term.casefold() in (" ".join([item["outcome"]] + item["acceptance_signals"])).casefold()
           for term in HOW_FORBIDDEN):
        _blocked("F2_A6_HOW_FORBIDDEN")
    if not item.get("evidence_refs") or not item.get("scope_refs"):
        _blocked("F2_A6_SOURCE_BINDING_REQUIRED")
    return True


def run(stages, signals, envelope, admission):
    verify(stages, signals, envelope, admission)
    contract = _profile_reuse()
    a3, a5 = stages["A3"], stages["A5"]
    profiles = a5.get("rule_profiles", {}).get("rules", [])
    included = sorted((p for p in profiles
                       if p.get("implementation_scope") == "APPROVED_SCOPE"),
                      key=lambda x: x["rule_code"])
    if {p["rule_code"] for p in included} != set(EXPECTED):
        _blocked("F2_A6_UNEXPECTED_SOURCE_RULES")
    requirements = []
    for row in included:
        code = row["rule_code"]
        description, acceptance = EXPECTED[code]
        ref = row["rule_source_ref"]
        if (not isinstance(ref, str)
                or ref not in a3.get("source_refs", [])
                or row.get("rule_status") != "VIGENTE"
                or row.get("pending_decision") is not False):
            _blocked("F2_A6_RULE_NOT_IN_APPROVED_SCOPE")
        layers = row.get("layers", {})
        supported = [key for key in ("BACKEND", "FRONTEND")
                     if isinstance(layers.get(key), dict)
                     and layers[key].get("applicability") == "APPLIES"
                     and layers[key].get("source_readback_state") == "SOURCE_CANDIDATE_UNATTESTED"
                     and ref in layers[key].get("evidence_refs", [])]
        area = supported[0] if len(supported) == 1 else "UNKNOWN"
        req = {
            "requirement_id": code,
            "scope_refs": ["SBX-AUTH-LOGIN"],
            "outcome": description,
            "obligation_mode": "MUST_PRESERVE_SEMANTICS",
            "authority_refs": [],
            "evidence_refs": [ref],
            "currentness_refs": [],
            "input_contract_refs": [],
            "output_contract_refs": [],
            "state_contract_refs": [],
            "error_behavior_refs": [],
            "permission_refs": [],
            "side_effect_class": "UNKNOWN",
            "preconditions": [],
            "blockers": ["SIMULATED_SANDBOX_ONLY_NO_PRODUCTION_AUTHORITY"],
            "acceptance_signals": [acceptance],
            "area": area,
            "area_evidence_refs": [ref] if area != "UNKNOWN" else [],
            "simulation_mode": MODE,
        }
        validate_obligation(req, contract)
        requirements.append(req)
    excluded = {x.get("rule_code") for x in a3["excluded_rule_items"]}
    if excluded & {x["requirement_id"] for x in requirements}:
        _blocked("F2_A6_EXCLUDED_RULE_INCLUDED")
    packet = {
        "schema_version": "IMPLEMENTABILITY_SCHEMA_V1",
        "simulation_mode": MODE,
        "attestation_mode": MODE,
        "candidate_only": True,
        "requirements": requirements,
        "canonical_implementation_bindings": [],
        "unresolved_material_items": [{
            "code": "SIMULATED_SANDBOX_ONLY_NO_PRODUCTION_AUTHORITY",
            "source_ref": "fixture://sbx_auth_login",
        }],
        "source_refs": sorted(set(ref for req in requirements for ref in req["evidence_refs"])),
        "currentness_refs": [],
        "source_attested": False,
        "authority_flags": deepcopy(FALSE_FLAGS),
        "admission_envelope_sha256": admission["envelope_sha256"],
        "stage_sha256": deepcopy(admission["stage_sha256"]),
        "profile_runtime_schema_ref": str(RUNTIME_SCHEMA.relative_to(ROOT)),
        "profile_runtime_validator_ref": str(RUNTIME_VALIDATOR.relative_to(ROOT)),
        "a9_runtime_validation": "DEFERRED_UNTIL_A9",
    }
    packet["implementability_fingerprint_sha256"] = digest(packet)
    return packet
