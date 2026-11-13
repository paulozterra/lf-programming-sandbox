"""Project a pinned single-screen source into the F1 readback interfaces.

This adapter constructs **simulation-only** typed input from the existing
single-source file. It never contacts Supabase, asserts live authority, or
modifies the pinned A1-A5 producers. Every derived row is traceable to the
SHA-checked source.json; absent facts remain absent.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


class NormalizeBlocked(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _source_compatible_ref(value: str, kind: str) -> str:
    """Project numeric fixture IDs, without asserting live provider identity."""
    from urllib.parse import urlsplit
    import re
    if not isinstance(value, str):
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    parsed = urlsplit(value)
    match = re.fullmatch(r"/(?:rules|assoc)/([1-9][0-9]*)", parsed.path)
    if parsed.scheme != "fixture" or not match:
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    prefix = ("supabase://lf_ops.reglas/" if kind == "rule"
              else "supabase://lf_ops.reglas_pantallas/")
    return prefix + match.group(1)


def normalize(root: Path, request: str) -> tuple[str, dict, dict]:
    pinpath = root / "SOURCE_PIN.json"
    if pinpath.is_symlink() or not pinpath.is_file():
        raise NormalizeBlocked("PANTALLA_NO_EN_CATALOGO")
    try:
        pin = json.loads(pinpath.read_text("utf-8"))
        sourcepath = root / pin["source_file"]
        if (pin.get("schema_version") != "SOURCE_SCREEN_PIN_V1"
                or pin.get("source_file") != "source.json"
                or pin.get("simulation_only") is not True
                or sourcepath.is_symlink() or not sourcepath.is_file()):
            raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
        raw = sourcepath.read_bytes()
        if _sha(raw) != pin["sha256"]:
            raise NormalizeBlocked("SBX_FIXTURE_SHA256_MISMATCH")
        source = json.loads(raw)
    except (KeyError, TypeError, OSError, ValueError) as exc:
        if isinstance(exc, NormalizeBlocked):
            raise
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE") from exc
    target = pin.get("fixture_id")
    if (source.get("schema_version") != "SECOND_SCREEN_SOURCE_V1"
            or source.get("target_ref") != target
            or not isinstance(request, str) or not request.strip()
            or not isinstance(source.get("screen_contract"), dict)
            or not isinstance(source.get("effective_rules"), dict)
            or not isinstance(source.get("requirements"), list)
            or not isinstance(source.get("inventory"), dict)):
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    contract = source["screen_contract"]
    rules = contract.get("rules")
    if not isinstance(rules, list) or not rules:
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    effective = source["effective_rules"]
    if set(row.get("code") for row in rules) != set(effective):
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    original_ref = f"fixture://{root.name}/source.json@{pin['sha256']}"
    direct = []
    effective_rows = []
    configs = []
    for rule in rules:
        code = rule.get("code")
        e = effective.get(code)
        if not isinstance(e, dict) or e.get("source_ref") != rule.get("source_ref"):
            raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
        common = {
            "code": code, "title": rule.get("title"), "status": rule.get("status"),
            "pending_decision": rule.get("pending_decision", False),
            "source_ref": _source_compatible_ref(rule.get("source_ref"), "rule"),
            "categoria": e.get("categoria"),
        }
        if not all(isinstance(common.get(k), str) and common[k]
                   for k in ("code", "title", "status", "source_ref", "categoria")):
            raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
        direct.append({**common, "association_ref": _source_compatible_ref(
            rule.get("association_ref"), "association")})
        effective_rows.append({**common, "binding_source": e.get("binding_source"),
                               "config": deepcopy(e.get("config", {}))})
        configs.append({"code": code, "valor_config": deepcopy(e.get("config", {}))})
    screen_sections = {key: deepcopy(contract.get(key, typ))
                       for key, typ in (("fields", []), ("errors", []),
                                        ("visual", {}), ("context", {}),
                                        ("metadata", {}), ("profiles", []),
                                        ("analytics", []), ("evidence", []))}
    if not all(key in contract for key in
               ("fields", "errors", "visual", "context", "metadata")):
        raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    sections = {**screen_sections, "rules": deepcopy(rules),
                "policies": deepcopy(contract.get("policies", []))}
    # These identities are deliberately synthetic, never provider IDs.
    fixture_number = int(pin["sha256"][:8], 16) or 1
    unknown = {"materiality_level": "HIGH", "scope_bounded": "TRUE",
               "authority_state": "UNKNOWN", "reversibility_state": "NOT_DEMONSTRATED",
               "currentness_decision": "UNKNOWN_FAIL_CLOSED",
               "material_contradiction": False, "known_cross_scope_impact": False,
               "unresolved_material_signal_count": 0, "required_specialist_count": 0}
    a1 = {
        "business": "LF",
        "request_identity": {"request_ref": original_ref, "request_kind": "USER_REQUEST"},
        "objective": {"problem_statement": request, "desired_outcome": request},
        "target_hints": [target], "source_refs": [original_ref],
        "provided_facts": [{"fact_code": "SOURCE_SCREEN_HINT",
                            "value": target, "source_ref": original_ref}],
        "constraints": [str(item["outcome"]) for item in source["requirements"]
                        if isinstance(item, dict) and isinstance(item.get("outcome"), str)],
        "ambiguities": [], "declared_intent_kind": "CREATE",
    }
    a2 = {
        "schema_version": "ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1",
        "business": "LF", "target_ref": target, "change_type": "CREATE",
        "target_granularity": "SCREEN", "nested_parent_ref": None,
        "evidence_refs": [original_ref], "depth_signals": unknown,
    }
    # The simulated CREATE classification above is scoped to the empty,
    # source-declared inventory. A non-empty inventory needs a typed decision.
    inv = source["inventory"]
    if any(inv.get(k) for k in ("objects", "impacts", "dependencies")):
        raise NormalizeBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    policy_links = []
    policy_objects = []
    # Only project policy fields that the single-file source actually contains.
    for policy in contract.get("policies", []):
        ref = policy.get("source_ref")
        if not isinstance(ref, str):
            raise NormalizeBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
        policy_links.append({"source_ref": ref, "reference_role": "fixture_policy",
                             "policy_target_ref": ref, "status": "VIGENTE",
                             "policy_kind": "SIMULATED"})
        policy_objects.append({"source_ref": ref, "status": "VIGENTE",
                               "read_origin": "SOURCE_FIXTURE_ONLY",
                               "policy_code": policy.get("policy_code")})
    data = {
        "screen_contract.json": {"imitates": "lf_ops.fn_screen_contract_v1",
            "schema_version": "SBX_SCREEN_CONTRACT_FIXTURE_V1",
            "target_ref": target, "screen_status": "VIGENTE",
            "contract_version": "SOURCE_PIN_SHA256:" + pin["sha256"],
            "contract": sections},
        "direct_rules.json": {"imitates": "lf_ops.pantallas + lf_ops.reglas_pantallas + lf_ops.reglas",
            "linked_rules": direct, "valor_config": configs},
        "effective_rules.json": {"imitates": "programacion.fn_input_effective_rule_links_v1",
            "schema_version": "LF_EFFECTIVE_RULE_LINKS_FIXTURE_V1",
            "screen_id": fixture_number, "consumer": "INPUT_GOVERNANCE", "rules": effective_rows},
        "policies.json": {"imitates": "lf_ops.pantallas_politicas + lf_ops.politicas_*",
            "schema_version": "LF_SCREEN_POLICIES_READBACK_V1",
            "policy_links": policy_links, "policy_objects": policy_objects},
        "elements.json": {"imitates": "lf_ops.pantalla_elementos",
            "elements": deepcopy(contract["fields"])},
        "states.json": {"imitates": "lf_ops.pantallas_estados",
            "states": deepcopy(contract["errors"])},
        "variants.json": {"imitates": "lf_ops.pantalla_variantes",
            "variants": deepcopy(contract["visual"].get("variants", []))},
        "relations.json": {"imitates": "lf_ops.relaciones_b2b", "relations": []},
        "inventory.json": {"imitates": "inventory.objects + inventory.fn_impact_analysis_v1 + inventory.fn_dependencies_v1",
            "schema_version": "A4_EXISTING_IMPACT_CORE_READBACK_V1",
            "business": "LF", "target_ref": target, "source_attested": False,
            "objects": [], "impacts": [], "dependencies": []},
        "ekb.json": {"imitates": "EKB exact governed lookup", "entries": []},
        "adr.json": {"imitates": "programacion.fn_engineering_current_adr_assert_v1 / transversal.decision_log",
            "records": []},
        "decision_asof.json": {"imitates": "public.fn_lf_decision_context_asof_resolve_v1",
            "schema_version": "LF_DECISION_CONTEXT_ASOF_RESOLUTION_V1",
            "state": "UNKNOWN", "subject_ref": target},
        "semantic_signals.json": {"imitates": "external semantic producer for A1 / typed classification signals for A2",
            "simulation": True, "request_text": request,
            "a1_structured": a1, "a2_signals": a2},
    }
    evidence = {name: f"fixture://{root.name}/{name}@{_sha(_bytes(obj))}"
                for name, obj in sorted(data.items())}
    # Retain an explicit authentic source pin in every provenance record.
    evidence["source.json"] = original_ref
    return target, data, evidence
