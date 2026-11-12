"""A7 MATERIAL_FRONT_COVERAGE_V1. Offline, source-driven, fail-closed.

Each material candidate is emitted once. Unknown shared dependencies are
explicit BLOCKED fronts, not an assumed absence of impact. A7 hints are not
A5 decisions, permissions, or verified implementation areas.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from analysis.host.simulated_admission_gate import (
    MODE, AdmissionBlocked, digest, verify,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_material_front_coverage_contract_v1.json"
SECTION_KIND = {
    "fields": "DATA_CONTRACT",
    "errors": "STATE_ERROR",
    "visual": "UI_VISUAL",
    "context": "OTHER",
    "metadata": "OTHER",
    "profiles": "OTHER",
    "analytics": "ANALYTICS",
    "evidence": "OTHER",
    "rules": "OTHER",
    "policies": "PERMISSION",
}
# Only typed front_kind is used; NEVER classify from outcome or free text.
# Multi-area STATE_ERROR has UNKNOWN primary hint and explicit candidates.
AREA_HINTS = {
    "UI_VISUAL": ("FRONTEND", ("FRONTEND",)),
    "RESPONSIVE": ("FRONTEND", ("FRONTEND",)),
    "ACCESSIBILITY": ("FRONTEND", ("FRONTEND",)),
    "STATE_ERROR": ("UNKNOWN", ("BACKEND", "FRONTEND")),
    "DATA_CONTRACT": ("DATA", ("DATA",)),
    "API_CONTRACT": ("BACKEND", ("BACKEND",)),
    "PERMISSION": ("BACKEND", ("BACKEND",)),
    "SECURITY_PRIVACY": ("BACKEND", ("BACKEND",)),
    "OBSERVABILITY": ("BACKEND", ("BACKEND",)),
    "ANALYTICS": ("UNKNOWN", ()),
    "SIDE_EFFECT": ("UNKNOWN", ()),
    "PERFORMANCE": ("UNKNOWN", ()),
    "MIGRATION_CUTOVER": ("UNKNOWN", ()),
    "ROLLBACK_RECOVERY": ("UNKNOWN", ()),
    "CONSUMER_HANDOFF": ("UNKNOWN", ()),
    "OTHER": ("UNKNOWN", ()),
}

# Source category comes only from the SHA-pinned fixture read by the F1 host.
# Never classify title/description free text.
CATEGORY_KIND = {
    "seguridad": "SECURITY_PRIVACY", "security": "SECURITY_PRIVACY",
    "ataques": "SECURITY_PRIVACY", "rate_limiting": "SECURITY_PRIVACY",
    "ux": "UI_VISUAL", "estados_ui": "UI_VISUAL", "copy": "UI_VISUAL",
    "error_states": "STATE_ERROR", "datos": "DATA_CONTRACT",
    "api": "API_CONTRACT", "analytics": "ANALYTICS",
}


def category_kind(value):
    if not isinstance(value, str):
        return "OTHER"
    return CATEGORY_KIND.get(value.strip().casefold(), "OTHER")


def _checked_categories(categories, a3):
    if not isinstance(categories, dict) or set(categories) != {
        "direct", "effective", "fixture_provenance"
    }:
        fail("F3_A7_CATEGORY_SOURCE_REQUIRED")
    proof = categories["fixture_provenance"]
    if (not isinstance(proof, dict)
            or any(not isinstance(proof.get(k), str)
                   or not proof[k].startswith("fixture://sbx_auth_login/" + k + "@")
                   or len(proof[k].split("@")[-1]) != 64
                   for k in ("direct_rules.json", "effective_rules.json"))):
        fail("F3_A7_CATEGORY_PROVENANCE_INVALID")
    # The F1 host verified these source bytes and SHA256 before constructing
    # this binding. No bare provider text or user description is consulted.
    direct, effective = categories["direct"], categories["effective"]
    if not isinstance(direct, dict) or not isinstance(effective, dict):
        fail("F3_A7_CATEGORY_SOURCE_INVALID")
    for code, row in direct.items():
        if (not isinstance(row, dict) or not isinstance(row.get("source_ref"), str)
                or not isinstance(row.get("categoria"), str)):
            fail("F3_A7_CATEGORY_SOURCE_INVALID")
    for code, row in effective.items():
        if (not isinstance(row, dict) or not isinstance(row.get("source_ref"), str)
                or not isinstance(row.get("categoria"), str)):
            fail("F3_A7_CATEGORY_SOURCE_INVALID")
        if code in direct and direct[code] != row:
            fail("F3_A7_CATEGORY_SOURCE_DISAGREEMENT")
        if row["source_ref"] not in a3.get("source_refs", []) and code in {
            x.get("rule_code") for x in a3.get("policy_scope_clear_rule_candidates", [])
        }:
            fail("F3_A7_CATEGORY_RULE_REF_UNKNOWN")
    return effective


def _kind_for_rule(code, categories, a3):
    if code not in categories:
        fail("F3_A7_CATEGORY_RULE_UNBOUND:" + str(code))
    row = categories[code]
    return category_kind(row["categoria"])


def fail(code):
    raise AdmissionBlocked(code)


def _contract():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    hints = contract["front_discovery"]["front_kind_hints"]
    if (contract["output_contract"] != "MATERIAL_FRONT_COVERAGE_V1"
            or contract["front_discovery"]["front_kind_policy"] != "EVIDENCE_DERIVED_OPEN_CATALOG"
            or set(hints) != set(AREA_HINTS)
            or not all(contract["coverage_guards"].values())):
        fail("F3_A7_PINNED_CONTRACT_DRIFT")
    return contract


def _front(candidate, kind, status, closure, evidence, reason, scope, blocker=None, obligations=()):
    area, candidates = AREA_HINTS[kind]
    if status == "REQUIRED" and not scope:
        fail("F3_A7_REQUIRED_SCOPE_MISSING")
    if status == "REQUIRED" and closure == "CLOSED" and not evidence:
        fail("F3_A7_CLOSED_WITHOUT_MATERIAL_EVIDENCE")
    if status == "REUSE_AS_IS":
        fail("F3_A7_REUSE_REQUIRES_CURRENTNESS")
    if status == "NOT_APPLICABLE" and (not evidence or not reason):
        fail("F3_A7_NA_WITHOUT_SOURCE")
    return {
        "front_id": "F3-" + digest(candidate)[:16],
        "front_kind": kind,
        "status": status, "closure": closure,
        "source_signal_refs": [candidate],
        "scope_refs": [scope] if scope else [],
        "authority_refs": [],
        "evidence_refs": sorted(set(evidence)),
        "currentness_refs": [],
        "currentness": "UNKNOWN",
        "blockers": [blocker] if blocker else [],
        "reason": reason,
        "candidate_ref": candidate,
        "obligation_refs": sorted(obligations),
        "execution_area_hint": area,
        "execution_area_candidates": list(candidates),
        "execution_area_policy": "SANDBOX_HINT",
        "materiality_level": "HIGH",
        "requires_independent_exam": True,
        "simulation_mode": MODE,
    }


def _material_candidates(a3, a4, a6, admission, category_sources):
    categories = _checked_categories(category_sources, a3)
    readback = a3.get("material_contract_readback")
    if not isinstance(readback, dict):
        fail("F3_A7_MATERIAL_READBACK_MISSING")
    sections = readback.get("contract_sections")
    items = readback.get("status_items")
    if not isinstance(sections, dict) or not isinstance(items, list):
        fail("F3_A7_MATERIAL_READBACK_INVALID")
    source = readback.get("source_ref")
    if not isinstance(source, str) or source not in a3.get("source_refs", []):
        fail("F3_A7_SOURCE_REF_MISMATCH")
    included = {x["rule_code"]: x["source_ref"]
                for x in a3.get("policy_scope_clear_rule_candidates", [])}
    excluded = {x["rule_code"]: x.get("exclusion_reason")
                for x in a3.get("excluded_rule_items", [])}
    expected_source = set(a3.get("source_refs", []))
    by_candidate = {}
    status_seen = set()
    for item in items:
        ref, pointer = item.get("source_ref"), item.get("pointer")
        if not isinstance(ref, str) or not isinstance(pointer, str) or ref in status_seen:
            fail("F3_A7_DUPLICATE_OR_INVALID_MATERIAL_SIGNAL")
        status_seen.add(ref)
        section = pointer.split("/")[0]
        if section not in sections or section not in SECTION_KIND:
            fail("F3_A7_UNMAPPED_MATERIAL_SECTION")
        kind = SECTION_KIND[section]
        code = None
        if section == "rules":
            parts = pointer.split("/")
            if len(parts) != 2 or not parts[1].isdigit():
                fail("F3_A7_RULE_POINTER_INVALID")
            try:
                row = sections["rules"][int(parts[1])]
                code = row["code"]
            except (KeyError, IndexError, TypeError):
                fail("F3_A7_RULE_POINTER_INVALID")
            if code not in included and code not in excluded:
                fail("F3_A7_RULE_SCOPE_UNKNOWN")
            kind = _kind_for_rule(code, categories, a3)
        if code in excluded:
            status, closure, reason, blocker = (
                "NOT_APPLICABLE", "CLOSED", "Explicitly excluded from approved A3 scope: " + str(excluded[code]), None)
        elif item.get("source_status") == "VIGENTE":
            status, closure, reason, blocker = (
                "REQUIRED", "CLOSED", "Existing material definition read from A3 (source-only, not attested)", None)
        else:
            status, closure, reason, blocker = (
                "REQUIRED", "BLOCKED", "Material source status not VIGENTE; cannot assume not applicable",
                "F3_A7_MATERIAL_STATUS_UNRESOLVED:" + str(item.get("source_status")))
        by_candidate[ref] = _front(ref, kind, status, closure, [ref], reason,
                                   a3["target_ref"], blocker)
    # The nonempty untyped sections are independently material candidates.
    for key in sorted(sections):
        value = sections[key]
        if key not in SECTION_KIND:
            fail("F3_A7_UNMAPPED_MATERIAL_SECTION")
        if key in ("context", "metadata") and value:
            ref = source + "#contract/" + key
            if ref in by_candidate:
                fail("F3_A7_DUPLICATE_CANDIDATE")
            by_candidate[ref] = _front(
                ref, SECTION_KIND[key], "REQUIRED", "CLOSED", [ref],
                "Typed screen contract section supplied by A3", a3["target_ref"])
    # A4 can reference both A3 screen JSON pointers and canonical rule
    # source refs. These are distinct *evidence signals*, not interchangeable
    # identities: preserve each exact ref, avoid duplicate candidate creation.
    approved_refs = set(included.values())
    excluded_refs = {x.get("source_ref"): x.get("exclusion_reason")
                     for x in a3.get("excluded_rule_items", [])}
    for impact in a4.get("direct_impacts", []):
        ref = impact.get("affected_ref")
        if not isinstance(ref, str) or not ref:
            fail("F3_A7_DIRECT_IMPACT_UNTYPED")
        if ref in by_candidate:
            continue
        if ref in approved_refs and impact.get("source_status") == "VIGENTE":
            by_candidate[ref] = _front(
                ref, _kind_for_rule(next(c for c, v in included.items() if v == ref), categories, a3), "REQUIRED", "CLOSED", [ref],
                "A4 direct impact on A3 approved rule ref (source-only)",
                a3["target_ref"])
        elif ref in excluded_refs:
            by_candidate[ref] = _front(
                ref, "OTHER", "NOT_APPLICABLE", "CLOSED", [ref],
                "A3 rule excluded from approved scope: " +
                str(excluded_refs[ref]), a3["target_ref"])
        else:
            by_candidate[ref] = _front(
                ref, "OTHER", "REQUIRED", "BLOCKED", [],
                "A4 direct impact lacks a verifiable A3 approved binding",
                a3["target_ref"], "F3_A7_DIRECT_IMPACT_UNRESOLVED:" + ref)
    for label in ("indirect_impacts", "consumers", "dependency_paths"):
        for ix, row in enumerate(a4.get(label, [])):
            if not isinstance(row, dict) or not isinstance(row.get("affected_ref"), str):
                fail("F3_A7_UNKNOWN_MATERIAL_SIGNAL_UNTYPED:" + label)
            ref = row["affected_ref"]
            if ref in by_candidate:
                continue
            by_candidate[ref] = _front(
                ref, "OTHER", "REQUIRED", "BLOCKED", [],
                "A4 material signal without attested closure", a3["target_ref"],
                "F3_A7_A4_UNRESOLVED:" + label)
    # Every A6 requirement is an independently accountable candidate.
    obligations = a6.get("requirements")
    if not isinstance(obligations, list) or not obligations:
        fail("F3_A7_A6_OBLIGATIONS_INVALID")
    for req in obligations:
        code, refs = req.get("requirement_id"), req.get("evidence_refs")
        if not isinstance(code, str) or code not in included or refs != [included[code]]:
            fail("F3_A7_A6_OBLIGATION_SOURCE_INVALID")
        candidate = "A6:requirement:" + code + "@" + refs[0]
        if candidate in by_candidate:
            fail("F3_A7_DUPLICATE_CANDIDATE")
        by_candidate[candidate] = _front(
            candidate, _kind_for_rule(code, categories, a3), "REQUIRED", "CLOSED", refs,
            "A6 verifiable WHAT obligation (not a technical implementation choice)",
            a3["target_ref"], obligations=[code])
    gaps = a4.get("unresolved_material_impacts")
    if not isinstance(gaps, list):
        fail("F3_A7_A4_GAPS_INVALID")
    for gap in gaps:
        if not isinstance(gap, dict) or not isinstance(gap.get("code"), str):
            fail("F3_A7_A4_GAPS_INVALID")
        candidate = "A4:unresolved:" + gap["code"] + ":" + str(gap.get("source_id"))
        if candidate in by_candidate:
            fail("F3_A7_DUPLICATE_CANDIDATE")
        by_candidate[candidate] = _front(
            candidate, "OTHER", "REQUIRED", "BLOCKED", [],
            "A4 external shared dependencies lack source attestation",
            a3["target_ref"], gap["code"])
    # Lift *only* fronts whose entire blocking set is the single exact code
    # recorded in the already-verified simulated admission receipt.
    lifts = admission.get("lifted_codes")
    if not isinstance(lifts, list) or len(lifts) != len(set(lifts)):
        fail("F3_A7_ADMISSION_LIFTS_INVALID")
    admission_ref = "sha256:" + digest(admission)
    for front in by_candidate.values():
        blockers = front["blockers"]
        if (front["closure"] == "BLOCKED" and len(blockers) == 1
                and blockers[0] in lifts):
            lifted = blockers[0]
            front["closure"] = "CLOSED"
            front["closure_basis"] = "SIMULATED_ADMISSION_LIFT"
            front["lifted_code"] = lifted
            front["admission_evidence_ref"] = admission_ref
            front["evidence_refs"] = sorted(set(front["evidence_refs"] + [admission_ref]))
            front["blockers"] = []
        else:
            front["closure_basis"] = "SOURCE_ONLY" if front["closure"] == "CLOSED" else "MATERIAL_GAP_UNRESOLVED"
            front["lifted_code"] = None
            front["admission_evidence_ref"] = None
    return by_candidate


def validate_coverage(packet, a3, a4, a6, admission, category_sources):
    if not isinstance(packet, dict) or packet.get("schema_version") != "MATERIAL_FRONT_COVERAGE_V1":
        fail("F3_A7_OUTPUT_INVALID")
    expected = _material_candidates(a3, a4, a6, admission, category_sources)
    candidates = packet.get("front_candidate_refs")
    fronts = packet.get("material_fronts")
    if not isinstance(candidates, list) or not isinstance(fronts, list):
        fail("F3_A7_COVERAGE_LIST_INVALID")
    if len(candidates) != len(set(candidates)) or set(candidates) != set(expected):
        fail("F3_A7_SILENT_OMISSION_OR_DUPLICATE")
    refs = [x.get("candidate_ref") for x in fronts if isinstance(x, dict)]
    if len(refs) != len(fronts) or len(refs) != len(set(refs)) or set(refs) != set(expected):
        fail("F3_A7_SILENT_OMISSION_OR_DUPLICATE")
    for item in fronts:
        candidate = item["candidate_ref"]
        if item != expected[candidate]:
            fail("F3_A7_FRONT_DERIVATION_DRIFT:" + str(candidate))
    ids = [x["front_id"] for x in fronts]
    if len(ids) != len(set(ids)):
        fail("F3_A7_DUPLICATE_FRONT_ID")
    required = {x["requirement_id"] for x in a6["requirements"]}
    linked = {code for f in fronts if f["status"] == "REQUIRED"
              for code in f["obligation_refs"]}
    if linked != required:
        fail("F3_A7_OBLIGATION_WITHOUT_REQUIRED_FRONT")
    if packet.get("unmapped_material_signals") != []:
        fail("F3_A7_UNMAPPED_SIGNALS_UNRECONCILED")
    if packet.get("all_material_fronts_accounted") is not True:
        fail("F3_A7_MATERIAL_ACCOUNTING_INCOMPLETE")
    if packet.get("materiality_level") != "HIGH" or packet.get("requires_independent_exam") is not True:
        fail("F3_A7_HIGH_EXAM_LOST")
    if packet.get("simulation_mode") != MODE:
        fail("F3_A7_SIMULATION_MODE_LOST")
    fingerprint = packet.get("coverage_fingerprint_sha256")
    if fingerprint != digest({k:v for k,v in packet.items() if k != "coverage_fingerprint_sha256"}):
        fail("F3_A7_DIGEST_MISMATCH")
    return True


def run(stages, signals, envelope, admission, a6, category_sources):
    # Gate verifies *all* real upstream A1–A5 digests; A6 binds to same receipt.
    verify(stages, signals, envelope, admission)
    _contract()
    if (a6.get("implementability_fingerprint_sha256") !=
            digest({k:v for k,v in a6.items() if k != "implementability_fingerprint_sha256"})
            or a6.get("stage_sha256") != admission.get("stage_sha256")
            or a6.get("admission_envelope_sha256") != admission.get("envelope_sha256")
            or a6.get("materiality_level") != admission.get("materiality_level")
            or a6.get("simulation_mode") != MODE
            or a6.get("requires_independent_exam") is not True):
        fail("F3_A7_A6_DIGEST_OR_ADMISSION_INVALID")
    a3, a4 = stages["A3"], stages["A4"]
    candidates = _material_candidates(a3, a4, a6, admission, category_sources)
    fronts = [candidates[key] for key in sorted(candidates)]
    out = {
        "schema_version": "MATERIAL_FRONT_COVERAGE_V1",
        "front_kind_policy": "EVIDENCE_DERIVED_OPEN_CATALOG",
        "execution_area_hint_policy": "SANDBOX_HINT",
        "simulation_mode": MODE, "materiality_level": admission["materiality_level"],
        "requires_independent_exam": True,
        "front_candidate_refs": sorted(candidates),
        "material_fronts": fronts,
        "unmapped_material_signals": [],
        "all_material_fronts_accounted": True,
        "source_refs": sorted({ref for f in fronts for ref in f["evidence_refs"]}),
        "currentness_refs": [],
        "admission_envelope_sha256": admission["envelope_sha256"],
        "a6_fingerprint_sha256": a6["implementability_fingerprint_sha256"],
        "category_source_sha256": {k: v.split("@")[-1] for k, v in category_sources["fixture_provenance"].items()},
        "authority_flags": deepcopy(admission["authority_flags"]),
    }
    out["coverage_fingerprint_sha256"] = digest(out)
    validate_coverage(out, a3, a4, a6, admission, category_sources)
    return out
