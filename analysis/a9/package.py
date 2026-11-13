"""A9: full, source-only Analysis handoff + genuine CP3.2 intake compatibility.

The output is a candidate for an offline sandbox consumer only. It is NOT the
append-only LF decision ASOF record nor a PG-01 authorization or parity receipt.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from pilot.orchestrator import intake
from analysis.host.simulated_admission_gate import AdmissionBlocked, MODE, digest, verify
from analysis.a7.front_coverage import validate_coverage
from analysis.a9.front_bindings import partition as partition_fronts, FrontBindingGap

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts"
PARITY = CONTRACTS / "analysis_programming_handoff_parity_contract_v1.json"
ENTRY = CONTRACTS / "programming_entry_contract_v1.json"
STAGES = [f"A{i}" for i in range(1, 10)]
AUTHORITY_FALSE = ("production_authority", "handoff_allowed", "merge_allowed",
                   "deploy_allowed", "downstream_authorized", "pg01_consumer_verified")
SCOPE = "SBX-AUTH-LOGIN"


def fail(code):
    raise AdmissionBlocked(code)


def _contracts():
    parity = json.loads(PARITY.read_text(encoding="utf-8"))
    entry = json.loads(ENTRY.read_text(encoding="utf-8"))
    schema = entry["programming_context_snapshot"]
    if (parity["producer_unit"] != "A9"
            or parity["consumer_unit"] != "PG-01"
            or parity["shared_snapshot_contract"]["schema_version"] != "PROGRAMMING_CONTEXT_SNAPSHOT_V1"
            or parity["producer_requirements"]["full_material_payload_required"] is not True
            or parity["shared_snapshot_contract"]["parallel_receiver_schema_forbidden"] is not True
            or entry["canonical_upstream"] != "ANALYSIS_IMPLEMENTATION_PACKAGE_V1"
            or schema["schema_version"] != "PROGRAMMING_CONTEXT_SNAPSHOT_V1"):
        fail("F4_A9_CANONICAL_CONTRACT_DRIFT")
    return parity, schema


def _refs(rows):
    if not isinstance(rows, list) or any(not isinstance(x, str) or not x for x in rows):
        fail("F4_A9_SOURCE_REFS_INVALID")
    return sorted(set(rows))


def _stage_trace(result, package_receipt):
    upstream = result["stages"]
    a6, a7, a8 = (result[x] for x in ("a6", "a7", "a8"))
    outputs = {**upstream, "A6": a6, "A7": a7, "A8": a8, "A9": package_receipt}
    if set(outputs) != set(STAGES):
        fail("F4_A9_STAGE_SET_INVALID")
    return [{"stage": stage,
             "status": outputs[stage].get("status", "CANDIDATE_ONLY") if stage != "A9" else "SIMULATED_PACKAGE_CANDIDATE",
             "output_sha256": digest(outputs[stage])} for stage in STAGES]


def _classification(a1, a2, a3, a4):
    cls = a2.get("classification")
    if not isinstance(cls, dict):
        fail("F4_A9_A2_CLASSIFICATION_MISSING")
    granularity = cls.get("target_granularity", "UNKNOWN")
    depth = cls.get("depth_level", "UNKNOWN")
    if depth not in ("L1", "L2", "L3"):
        fail("F4_A9_A2_DEPTH_UNKNOWN")
    # Authority and implementation are independent. UNKNOWN source authority
    # is not EXISTING; for new screen A4 CREATE + no existing code => NEW.
    if a4.get("target_change_action") == "CREATE" and a4.get("target_code_destination") is None:
        implementation_state = "NEW"
    else:
        implementation_state = "UNKNOWN"
    authority = a3.get("authority_state", "UNKNOWN")
    if authority not in ("EXISTING", "NEW", "UNKNOWN"):
        authority = "UNKNOWN"
    return {"target_granularity": granularity, "depth": depth,
            "authority_state": authority, "implementation_state": implementation_state,
            "depth_reason_predicates": deepcopy(cls.get("depth_reason_predicates", [])),
            "change_type": cls.get("change_type", "UNKNOWN")}


def _readiness(scopes):
    order = {"READY_CANDIDATE": 0, "NEED_MORE_EVIDENCE": 1,
             "REQUIRES_DECISION": 2, "BLOCKED": 3}
    if not scopes:
        fail("F4_A9_SCOPES_EMPTY")
    return max(scopes, key=lambda x: order[x["readiness_candidate"]])["readiness_candidate"]



def _typed_rules(result, approved, requirements):
    """Only SHA-pinned fixture rows, checked against A3, A6 and A7 identities."""
    source = result.get("rule_sources")
    if not isinstance(source, dict) or set(source) != {"direct", "effective", "provenance"}:
        fail("F4_A9_RULE_PINNED_READBACK_MISSING")
    prov = source["provenance"]
    if not isinstance(prov, dict) or set(prov) != {"direct_rules.json", "effective_rules.json"}:
        fail("F4_A9_RULE_PINNED_PROVENANCE_INVALID")
    for name, ref in prov.items():
        if not isinstance(ref, str) or not ref.startswith("fixture://sbx_auth_login/" + name + "@") or len(ref.split("@")[-1]) != 64:
            fail("F4_A9_RULE_PINNED_PROVENANCE_INVALID")
    direct, effective = source["direct"], source["effective"]
    if not isinstance(direct, dict) or not isinstance(effective, dict):
        fail("F4_A9_RULE_TYPED_READBACK_INVALID")
    source_requirements = [r for r in requirements
                           if not r.get("derived_from_requirement_id")]
    req_by_code = {r["source_requirement_id"]: r for r in source_requirements}
    if len(req_by_code) != len(source_requirements):
        fail("F4_A9_RULE_REQUIREMENT_COVERAGE_MISMATCH")
    rules, seen = [], set()
    for a3 in approved:
        code, ref = a3.get("rule_code"), a3.get("source_ref")
        if code in seen or code not in effective or code not in req_by_code:
            fail("F4_A9_RULE_SOURCE_MISSING")
        seen.add(code)
        row = effective[code]
        if row.get("source_ref") != ref:
            fail("F4_A9_RULE_SOURCE_IDENTITY_MISMATCH")
        if (row.get("status") != "VIGENTE" or row.get("pending_decision") is not False
                or not isinstance(row.get("title"), str) or not row["title"]
                or not isinstance(row.get("categoria"), str) or not row["categoria"]
                or not isinstance(row.get("config"), dict)):
            fail("F4_A9_RULE_TYPED_READBACK_INVALID")
        binding = row.get("binding_source")
        if binding not in ("LEGACY_EXPLICIT", "DERIVED_GLOBAL"):
            fail("F4_A9_RULE_ORIGIN_INVALID")
        if binding == "LEGACY_EXPLICIT":
            d = direct.get(code)
            if (not isinstance(d, dict) or d.get("valor_config") != row["config"]
                    or any(d.get(k) != row.get(k)
                           for k in ("title", "categoria", "status", "source_ref", "pending_decision"))):
                fail("F4_A9_RULE_DIRECT_CONFIG_MISMATCH")
        elif code in direct:
            fail("F4_A9_RULE_GLOBAL_DIRECT_CONFLICT")
        requirement = req_by_code[code]
        if ref not in requirement.get("evidence_refs", []):
            fail("F4_A9_RULE_REQUIREMENT_SOURCE_MISMATCH")
        fronts = [f for f in result["a7"]["material_fronts"]
                  if code in f.get("obligation_refs", [])
                  and f.get("status") == "REQUIRED"
                  and ref in f.get("evidence_refs", [])]
        if len(fronts) != 1:
            fail("F4_A9_RULE_FRONT_BINDING_INVALID")
        rules.append({
            "rule_code": code, "source_ref": ref, "source_status": row["status"],
            "source_attested": False, "titulo": row["title"],
            "categoria": row["categoria"], "valor_config": deepcopy(row["config"]),
            "es_transversal": binding == "DERIVED_GLOBAL",
            "origen": "DERIVED_GLOBAL" if binding == "DERIVED_GLOBAL" else "DIRECT",
            "front_id": result.get("t1a_rule_area_ids", {}).get(code, fronts[0]["front_id"]),
            "requirement_id": requirement["requirement_id"],
        })
    if seen != set(req_by_code):
        fail("F4_A9_RULE_REQUIREMENT_COVERAGE_MISMATCH")
    return rules


def _guard_invariants(a3):
    """Empty only because fixture has no sourced invariants; future data blocks."""
    for k in ("applicable_invariants", "invariants", "invariant_bindings"):
        if k in a3 and a3[k] not in (None, []):
            fail("F4_A9_INVARIANTS_SOURCE_UNHANDLED")
    material = a3.get("material_contract_readback")
    if isinstance(material, dict):
        sections = material.get("contract_sections")
        if isinstance(sections, dict) and sections.get("invariants") not in (None, []):
            fail("F4_A9_INVARIANTS_SOURCE_UNHANDLED")


def _snapshot(result, requirements, fronts, scopes, classification):
    """Material parity fields are A3-A5/A6-A8 projections, never model guesses."""
    parity, entry = _contracts()
    a3, a4, a5 = (result["stages"][x] for x in ("A3", "A4", "A5"))
    approved = a3.get("policy_scope_clear_rule_candidates")
    if not isinstance(approved, list):
        fail("F4_A9_RULE_BINDINGS_MISSING")
    rules = _typed_rules(result, approved, requirements)
    _guard_invariants(a3)
    source_refs = _refs(a3.get("source_refs", []) + a4.get("evidence_refs", [])
                        + a5.get("evidence_refs", []))
    currentness_refs = _refs(a3.get("currentness_refs", []) + result["a7"].get("currentness_refs", []))
    authority_bindings = deepcopy(a3.get("authority_binding_refs", []))
    if not isinstance(authority_bindings, list):
        fail("F4_A9_AUTHORITY_BINDINGS_INVALID")
    # No invariants sourced in this fixture; future A3 invariants block closed.
    invariants = []
    schema_digest = digest(entry)
    source_snapshot = {
        "A3": digest(a3), "A4": digest(a4), "A5": digest(a5),
        "A6": digest(result["a6"]), "A7": digest(result["a7"]),
        "A8": digest(result["a8"]),
        "source_refs": source_refs, "currentness_refs": currentness_refs,
        "typed_rules": deepcopy(rules),
        "rule_fixture_provenance": deepcopy(result["rule_sources"]["provenance"]),
    }
    source_sha = digest(source_snapshot)
    authority_sha = digest({"authority_binding_refs": authority_bindings,
                            "authority_state": classification["authority_state"],
                            "source_attested": False, "currentness_refs": currentness_refs})
    matrix = [{"scope_id": row["scope_ids"][0], "front_id": row["front_id"],
               "front_status": row["obligation_mode"], "front_closure": row["closure"],
               "effect_on_scope": ("BLOCKS" if row["closure"] == "BLOCKED"
                                   else "NOT_APPLICABLE" if row["obligation_mode"] == "NOT_APPLICABLE"
                                   else "PRESERVE"),
               "evidence_refs": deepcopy(row["evidence_refs"]), "reason": row["reason"]}
              for row in fronts]
    scope_readiness = [{
        "scope_id": scope["scope_id"], "scope_kind": "SCREEN",
        "status": "READY" if scope["readiness_candidate"] == "READY_CANDIDATE"
                  else scope["readiness_candidate"],
        "depends_on_scope_ids": [],
        "material_front_refs": deepcopy(scope["material_front_refs"]),
        "authority_refs": [],
        "blockers": sorted(set(b for f in fronts
                               if scope["scope_id"] in f["scope_ids"]
                               for b in f["blockers"])),
        "reason": "Source-only simulated readiness, not PG-01 admission",
    } for scope in scopes]
    snap = {
        "schema_version": "PROGRAMMING_CONTEXT_SNAPSHOT_V1",
        "simulation_mode": MODE,
        "objective": result["stages"]["A1"].get("payload", {}).get("objective", {}),
        "target": SCOPE, "target_granularity": classification["target_granularity"],
        "authority_state": classification["authority_state"],
        "implementation_state": classification["implementation_state"],
        "requirements": deepcopy(requirements),
        "authority_bindings": authority_bindings, "applicable_rules": rules,
        "applicable_invariants": invariants,
        "preserve": [],
        "material_front_coverage": deepcopy(result["a7"]),
        "implementability_schema": deepcopy(result["a6"]),
        "decision_context": deepcopy(a5),
        "analysis_stop_rule": deepcopy(result["a8"]),
        "scope_front_matrix": matrix, "scope_readiness": scope_readiness,
        "package_readiness": _readiness(scopes),
        "unresolved_material_items": deepcopy(result["a6"].get("unresolved_material_items", [])),
        "source_refs": source_refs, "currentness_refs": currentness_refs,
        "snapshot_schema_digest_sha256": schema_digest,
        "authority_fingerprint_sha256": authority_sha,
        "source_snapshot_sha256": source_sha,
        "source_snapshot_inputs": source_snapshot,
        "source_attested": False,
        "production_authority": False, "handoff_allowed": False,
        "merge_allowed": False, "deploy_allowed": False,
        "downstream_authorized": False, "pg01_consumer_verified": False,
    }
    required = [x.removesuffix("[]") for x in entry["required_fields"]]
    if any(k not in snap for k in required):
        fail("F4_A9_PARITY_MATERIAL_PATH_MISSING")
    return snap


def build(result, request_raw):
    if not isinstance(result, dict) or not isinstance(request_raw, bytes):
        fail("F4_A9_INPUT_INVALID")
    stages = result.get("stages")
    if not isinstance(stages, dict):
        fail("F4_A9_UPSTREAM_STAGES_MISSING")
    verify(stages, result.get("a2_signals"), result.get("admission_envelope"),
           result.get("admission"))
    a6, a7, a8 = (result.get(k) for k in ("a6", "a7", "a8"))
    if not all(isinstance(x, dict) for x in (a6, a7, a8)):
        fail("F4_A9_UPSTREAM_MISSING")
    if (a6.get("implementability_fingerprint_sha256") !=
            digest({k:v for k,v in a6.items() if k != "implementability_fingerprint_sha256"})
            or a8.get("stop_rule_fingerprint_sha256") !=
            digest({k:v for k,v in a8.items() if k != "stop_rule_fingerprint_sha256"})
            or a7.get("coverage_fingerprint_sha256") !=
            digest({k:v for k,v in a7.items() if k != "coverage_fingerprint_sha256"})
            or a8.get("material_front_coverage_ref") != a7["coverage_fingerprint_sha256"]):
        fail("F4_A9_UPSTREAM_DIGEST_MISMATCH")
    validate_coverage(a7, stages["A3"], stages["A4"], a6,
                      result["admission"], result["category_sources"])
    if (a6.get("materiality_level") != "HIGH"
            or a7.get("materiality_level") != "HIGH"
            or a8.get("materiality_level") != "HIGH"
            or a8.get("simulation_mode") != MODE):
        fail("F4_A9_SECURITY_OR_SIMULATION_DRIFT")
    a1, a2, a3, a4, a5 = (stages[k] for k in ("A1", "A2", "A3", "A4", "A5"))
    classification = _classification(a1, a2, a3, a4)
    intent = a1.get("payload", {}).get("objective", {}).get("problem_statement")
    if not isinstance(intent, str) or not intent:
        fail("F4_A9_INTENT_MISSING")
    context = {"intent": intent, "target_ref": a3.get("target_ref"),
               "request_context_source": "A1", "simulation_mode": MODE}
    if context["target_ref"] != SCOPE:
        fail("F4_A9_TARGET_MISMATCH")
    reqs = []
    for row in a6.get("requirements", []):
        checks = row.get("acceptance_signals")
        if not isinstance(checks, list) or not checks or not all(isinstance(c, str) and c for c in checks):
            fail("F4_A9_ACCEPTANCE_SIGNAL_MISSING")
        code = row.get("requirement_id")
        if not isinstance(code, str) or not code:
            fail("F4_A9_REQUIREMENT_ID_MISSING")
        reqs.append({
            "requirement_id": "REQ-" + code,
            "source_requirement_id": code,
            "scope_id": SCOPE,
            "outcome": row["outcome"],
            "acceptance_signal": " | ".join(checks),
            "acceptance_checks": list(checks),
            "evidence_refs": _refs(row["evidence_refs"]),
            "materiality_level": row["materiality_level"],
            "requires_independent_exam": row["requires_independent_exam"],
            "simulation_mode": MODE,
        })
    if not reqs:
        fail("F4_A9_REQUIREMENTS_EMPTY")
    sections = stages["A3"]["material_contract_readback"]["contract_sections"]
    effective = result["rule_sources"]["effective"]
    inventory = result.get("verified_inventory", {})
    inv = inventory.get("value", {})
    if (not isinstance(inventory.get("source_ref"), str)
            or not isinstance(inv, dict)):
        fail("A9_PINNED_INVENTORY_MISSING")
    a4 = stages["A4"]
    empty_create = (a4.get("target_change_action") == "CREATE"
                    and a4.get("target_code_destination") is None
                    and all(inv.get(key) == [] for key in ("objects", "impacts", "dependencies")))
    try:
        front_rows, non_atomized = partition_fronts(
            a7["material_fronts"], reqs, sections, effective,
            scope=SCOPE, create_empty_inventory=empty_create)
    except FrontBindingGap as exc:
        fail(str(exc))
    if not empty_create and any(f["candidate_ref"].startswith("A4:unresolved:")
                                for f in a7["material_fronts"]):
        fail("A9_A4_INVENTORY_DEPENDENCY_BLOCKED")
    by_area = {row["execution_area"]: row["front_id"] for row in front_rows}
    source_form_codes = {"SBX-R-" + field["field_code"].removeprefix("SBX-F-")
                         for field in sections.get("fields", [])
                         if isinstance(field.get("field_code"), str)
                         and field.get("required") is True
                         and field.get("status") == "VIGENTE"}
    result["t1a_rule_area_ids"] = {
        req["source_requirement_id"]: by_area[
            "FRONTEND" if req["source_requirement_id"] in source_form_codes else "BACKEND"]
        for req in reqs}
    # PG04 owns each executable obligation exactly once. Shared business
    # requirements use area-qualified implementation IDs with their parent.
    scopes_by_area = {area: SCOPE + "-" + area for area in ("BACKEND", "FRONTEND")}
    originals = {r["requirement_id"]: deepcopy(r) for r in reqs}
    for req in reqs:
        req["scope_id"] = scopes_by_area[
            "FRONTEND" if req["source_requirement_id"] in source_form_codes
            else "BACKEND"]
    derived = []
    for front in front_rows:
        area = front["execution_area"]
        sid = scopes_by_area[area]
        front["scope_ids"] = [sid]
        linked = []
        sources = {}
        for original_id in front["requirement_ids"]:
            parent = originals[original_id]
            if next(r for r in reqs if r["requirement_id"] == original_id)["scope_id"] == sid:
                bound_id = original_id
            else:
                bound_id = original_id + "-" + area
                alias = deepcopy(parent)
                alias["requirement_id"] = bound_id
                alias["scope_id"] = sid
                alias["derived_from_requirement_id"] = original_id
                alias["execution_area"] = area
                alias["area_binding_evidence_refs"] = deepcopy(front["evidence_refs"])
                derived.append(alias)
            linked.append(bound_id)
            sources[bound_id] = deepcopy(parent["evidence_refs"])
        front["requirement_ids"] = sorted(linked)
        front["obligation_refs"] = sorted(linked)
        front["requirement_source_refs"] = sources
    reqs.extend(derived)
    has_blocked = any(f["closure"] == "BLOCKED" for f in front_rows)
    readiness = ("BLOCKED" if a8.get("decision") == "BLOCKED"
                 else "REQUIRES_DECISION" if a8.get("decision") == "REQUIRES_DECISION"
                 else "READY_CANDIDATE" if a8.get("decision") == "STOP" and not has_blocked
                 else "NEED_MORE_EVIDENCE")
    scopes = [{"scope_id": scopes_by_area[area], "scope_kind": "SCREEN",
               "material_front_refs": [next(f["front_id"] for f in front_rows
                                            if f["execution_area"] == area)],
               "readiness_candidate": readiness, "simulation_mode": MODE}
              for area in ("BACKEND", "FRONTEND")]
    snapshot = _snapshot(result, reqs, front_rows, scopes, classification)
    receipt = {
        "schema_version": "A9_SIMULATED_PACKAGE_RECEIPT_V1",
        "simulation_mode": MODE, "source_attested": False,
        "request_sha256": hashlib.sha256(intake.normalized_request_bytes(request_raw)).hexdigest(),
        "source_snapshot_sha256": snapshot["source_snapshot_sha256"],
        "a8_digest": digest(a8), "a7_digest": digest(a7),
        "requirements_sha256": digest(reqs),
        "scope_readiness": readiness, "status": "SIMULATED_PACKAGE_CANDIDATE",
    }
    package = {
        "schema_version": "ANALYSIS_IMPLEMENTATION_PACKAGE_V1",
        "candidate_only": True, "analysis_mode": "SIMULATED_ANALYSIS",
        "simulation_mode": MODE, "attestation_mode": MODE,
        "request_sha256": receipt["request_sha256"],
        "request_context": context,
        "classification": classification,
        "stage_trace": _stage_trace(result, receipt),
        "requirements": reqs, "material_fronts": front_rows,
        "non_atomized_fronts": non_atomized,
        "scope_proposals": scopes,
        "research_stop": deepcopy(a8),
        "package_readiness_candidate": _readiness(scopes),
        # Still unresolved as an *authority* fact despite simulated A8 STOP.
        "material_unknowns": deepcopy(a6.get("unresolved_material_items", [])),
        "decisions_pending": deepcopy(a5.get("pending_owner_decisions", [])),
        "programming_context_snapshot": snapshot,
        "applicable_rules": deepcopy(snapshot["applicable_rules"]),
        "applicable_invariants": deepcopy(snapshot["applicable_invariants"]),
        "authority_bindings": deepcopy(snapshot["authority_bindings"]),
        "currentness_refs": deepcopy(snapshot["currentness_refs"]),
        "snapshot_schema_digest_sha256": snapshot["snapshot_schema_digest_sha256"],
        "authority_fingerprint_sha256": snapshot["authority_fingerprint_sha256"],
        "source_snapshot_sha256": snapshot["source_snapshot_sha256"],
        "source_attested": False,
        **{k: False for k in AUTHORITY_FALSE},
    }
    validate(package, request_raw, result=result)
    return package


def validate(package, request_raw, *, result=None):
    """Intake-compatible and stricter A9 checks before any file is written."""
    if not isinstance(package, dict):
        fail("F4_A9_PACKAGE_INVALID")
    required = ("schema_version", "candidate_only", "analysis_mode",
                "request_sha256", "stage_trace", "requirements",
                "material_fronts", "scope_proposals", "research_stop",
                "package_readiness_candidate", "programming_context_snapshot",
                "snapshot_schema_digest_sha256", "authority_fingerprint_sha256",
                "source_snapshot_sha256", "simulation_mode")
    if any(k not in package for k in required):
        fail("F4_A9_FIELD_MISSING")
    if package["simulation_mode"] != MODE:
        fail("F4_A9_SIMULATION_MARK_MISSING")
    if (package["request_sha256"] != hashlib.sha256(
            intake.normalized_request_bytes(request_raw)).hexdigest()):
        fail("F4_A9_REQUEST_SHA_MISMATCH")
    if any(package.get(k) is not False for k in AUTHORITY_FALSE):
        fail("F4_A9_AUTHORITY_FORBIDDEN")
    if (not isinstance(package.get("stage_trace"), list)
            or [s.get("stage") for s in package["stage_trace"]] != STAGES
            or any(not isinstance(s.get("output_sha256"), str) or
                   len(s["output_sha256"]) != 64 for s in package["stage_trace"])):
        fail("F4_A9_STAGE_TRACE_INVALID")
    for req in package.get("requirements", []):
        if (not isinstance(req.get("acceptance_signal"), str)
                or not req["acceptance_signal"]
                or not isinstance(req.get("acceptance_checks"), list)
                or not req["acceptance_checks"]):
            fail("F4_A9_ACCEPTANCE_SIGNAL_MISSING")
    snapshot = package["programming_context_snapshot"]
    if not isinstance(snapshot, dict):
        fail("F4_A9_SNAPSHOT_INVALID")
    _, schema = _contracts()
    if package["snapshot_schema_digest_sha256"] != digest(schema) or snapshot.get("snapshot_schema_digest_sha256") != digest(schema):
        fail("F4_A9_SCHEMA_DIGEST_MISMATCH")
    if package["source_snapshot_sha256"] != snapshot.get("source_snapshot_sha256"):
        fail("F4_A9_SOURCE_SNAPSHOT_MISMATCH")
    if package["authority_fingerprint_sha256"] != snapshot.get("authority_fingerprint_sha256"):
        fail("F4_A9_AUTHORITY_FINGERPRINT_MISMATCH")
    if (snapshot.get("source_snapshot_sha256") != digest(snapshot.get("source_snapshot_inputs"))
            or snapshot.get("authority_fingerprint_sha256") != digest({
                "authority_binding_refs": snapshot.get("authority_bindings"),
                "authority_state": snapshot.get("authority_state"),
                "source_attested": False,
                "currentness_refs": snapshot.get("currentness_refs"),
            })):
        fail("F4_A9_SNAPSHOT_DIGEST_MISMATCH")
    if any(snapshot.get(k) is not False for k in AUTHORITY_FALSE):
        fail("F4_A9_AUTHORITY_FORBIDDEN")
    scope_ids = {x["scope_id"] for x in package["scope_proposals"]}
    for front in package["material_fronts"]:
        if set(front["scope_ids"]) - scope_ids:
            fail("F4_A9_FRONT_UNKNOWN_SCOPE")
    for scope in package["scope_proposals"]:
        members = {x["front_id"] for x in package["material_fronts"]
                   if scope["scope_id"] in x["scope_ids"]}
        if set(scope["material_front_refs"]) != members:
            fail("F4_A9_SCOPE_FRONT_MISMATCH")
        if (scope["readiness_candidate"] == "READY_CANDIDATE"
                and any(f["closure"] == "BLOCKED" for f in package["material_fronts"]
                        if scope["scope_id"] in f["scope_ids"])):
            fail("F4_A9_READY_WITH_BLOCKED_FRONT")
    if result is not None:
        a3 = result["stages"]["A3"]
        _guard_invariants(a3)
        expected_rules = _typed_rules(result,
            a3.get("policy_scope_clear_rule_candidates", []), package["requirements"])
        if (package.get("applicable_rules") != expected_rules
                or snapshot.get("applicable_rules") != expected_rules
                or snapshot.get("applicable_invariants") != []
                or package.get("applicable_invariants") != []):
            fail("F4_A9_RULE_PARITY_MISMATCH")
        expected_trace = _stage_trace(result, {
            "schema_version": "A9_SIMULATED_PACKAGE_RECEIPT_V1",
            "simulation_mode": MODE, "source_attested": False,
            "request_sha256": package["request_sha256"],
            "source_snapshot_sha256": snapshot["source_snapshot_sha256"],
            "a8_digest": digest(result["a8"]),
            "a7_digest": digest(result["a7"]),
            "requirements_sha256": digest(package["requirements"]),
            "scope_readiness": package["package_readiness_candidate"],
            "status": "SIMULATED_PACKAGE_CANDIDATE",
        })
        if package["stage_trace"] != expected_trace:
            fail("F4_A9_UPSTREAM_STAGE_DIGEST_MISMATCH")
    # The actual unchanged intake is the compatibility oracle.
    intake.validate(package, request_raw)
    return True
