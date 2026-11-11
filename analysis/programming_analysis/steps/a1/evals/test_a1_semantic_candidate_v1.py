"""Candidate tests: mocked semantic producer/reviewer; NOT real model attestation."""
import copy
import importlib.util
import json
import unittest
from hashlib import sha256
from pathlib import Path

STEP = Path(__file__).resolve().parents[1]
SKILL = STEP.parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A1 = load(STEP / "validators/run.py", "a1_candidate_runner")
SEM = load(STEP / "semantic_intake_candidate_v1.py", "a1_candidate_semantic")
BRIDGE = load(SKILL / "adapters/a1_a2_candidate_bridge_v1.py", "a1_a2_candidate_bridge")
A2 = load(SKILL / "steps/a2/validators/run.py", "a2_candidate_runner")
D4CONSUMER = load(
    SKILL / "adapters/a1_d4_inventory_consumer_candidate_v1.py",
    "a1_d4_inventory_consumer_candidate",
)


LOGIN = "Implementa por primera vez el login B2B o también llamado inicio de sesión"
IMPLICIT = "Necesito una vista para que las empresas entren al portal"
NEGATED = "No crees otra pantalla; usa la existente"
GRID = "Necesito un listado de operaciones con filtros"


def span(raw, needle, dimension):
    start = raw.index(needle)
    return {"dimension": dimension, "quote": needle,
            "start": start, "end": start + len(needle)}


def semantic_candidate(raw):
    if raw == LOGIN:
        op, assumption, assumed_phrase = "Implementa", "CLAIMED_GREENFIELD", "por primera vez"
        artifact, capability, domain, mentions = "login B2B", "login B2B", "B2B", [
            "login B2B", "inicio de sesión"
        ]
    elif raw == IMPLICIT:
        op, assumption, assumed_phrase = "Necesito una vista", "UNSPECIFIED", None
        artifact, capability, domain, mentions = "vista", "empresas entren al portal", "empresas", [
            "vista para que las empresas entren al portal"
        ]
    elif raw == GRID:
        op, assumption, assumed_phrase = "Necesito", "UNSPECIFIED", None
        artifact, capability, domain, mentions = "listado de operaciones", "listado de operaciones", None, ["listado de operaciones"]
    else:
        op, assumption, assumed_phrase = "crees", "CLAIMED_EXISTING", "existente"
        artifact, capability, domain, mentions = "pantalla", "pantalla", None, ["pantalla"]
    spans = [span(raw, op, "OPERATION"),
             span(raw, artifact, "ARTIFACT"),
             span(raw, capability, "CAPABILITY")]
    if domain:
        spans.append(span(raw, domain, "ACTOR_SCOPE"))
    if assumed_phrase:
        spans.append(span(raw, assumed_phrase, "ASSUMPTION"))
    proposal = {
        "schema_version": "A1_INTENT_ANALYSIS_CANDIDATE_V1",
        "operation": {
            "kind": "IMPLEMENT",
            "user_assumed_state": assumption,
            "repo_verification_state": "PENDING_INVENTORY"
        },
        "target": {
            "artifact_kind": "SCREEN",
            "functional_archetype": "DATA_GRID_VIEW" if raw == GRID else "AUTH_FLOW",
            "canonical_capability": "DATA_EXPLORATION" if raw == GRID else "IDENTITY_AND_ACCESS",
            "actor_scope": "B2B" if domain else "UNSPECIFIED",
            "raw_mentions": mentions
        },
        "desired_outcome": "Mostrar operaciones con filtros" if raw == GRID else "Permitir el acceso de empresas al portal",
        "analysis_hints": (["DATA_ACCESS_REVIEW", "PAGINATION_REVIEW"] if raw == GRID
                           else ["SECURITY_REVIEW", "SESSION_REVIEW", "ROUTING_REVIEW"]),
        "dimensions_to_investigate": (["FILTER_CRITERIA", "PAGINATION_STRATEGY"] if raw == GRID
                                     else ["AUTH_MECHANISM", "SESSION_POLICY", "POST_LOGIN_ROUTING",
                                           "ACCOUNT_RECOVERY", "ERROR_HANDLING"]),
        "evidence_spans": spans,
        "explicit_constraints": [],
        "material_ambiguities": []
    }
    if raw == IMPLICIT:
        proposal["target"]["functional_archetype"] = "PORTAL_ENTRY_VIEW"
        proposal["target"]["canonical_capability"] = "ENTERPRISE_PORTAL_ACCESS"
        proposal["dimensions_to_investigate"] = [
            "PORTAL_ENTRY_MODE", "AUTHENTICATION_IF_APPLICABLE",
            "EXISTING_PORTAL_ENTRY",
        ]
        proposal["material_ambiguities"] = [{
            "code": "PORTAL_ENTRY_MODE_UNRESOLVED",
            "statement": "La solicitud no diferencia autenticación de navegación al portal.",
            "materiality": "MATERIAL",
        }]
    return proposal


def producer(raw):
    return semantic_candidate(raw)


def reviewer(raw, candidate):
    # Fixture evaluator, NOT a genuine semantic judge / authority receipt.
    return {"verdict": "FAIL" if raw == NEGATED else "PASS",
            "candidate_sha256": SEM._hash(candidate), "reviewer_ref": "fixture://reviewer",
            "issues": ["NEGATION_NOT_PRESERVED"] if raw == NEGATED else []}


def reuse_candidate(raw):
    assert raw == NEGATED
    return {
        "schema_version": "A1_INTENT_ANALYSIS_CANDIDATE_V1",
        "operation": {
            "kind": "REUSE", "user_assumed_state": "CLAIMED_EXISTING",
            "repo_verification_state": "PENDING_INVENTORY",
        },
        "target": {
            "artifact_kind": "SCREEN",
            "functional_archetype": "EXISTING_SCREEN",
            "canonical_capability": "UNKNOWN",
            "actor_scope": "UNSPECIFIED",
            "raw_mentions": ["pantalla"],
        },
        "desired_outcome": "Reutilizar la pantalla existente sin crear otra",
        "analysis_hints": ["EXISTING_ARTIFACT_INVENTORY"],
        "dimensions_to_investigate": [
            "EXISTING_SCREEN_LOOKUP", "FUNCTIONAL_CAPABILITY_RESOLUTION",
        ],
        "evidence_spans": [
            span(raw, "usa la existente", "OPERATION"),
            span(raw, "pantalla", "ARTIFACT"),
            span(raw, "existente", "ASSUMPTION"),
            span(raw, "No crees otra pantalla", "NEGATION"),
        ],
        "explicit_constraints": [{"text": "No crees otra pantalla"}],
        "material_ambiguities": [{
            "code": "FUNCTIONAL_CAPABILITY_UNSPECIFIED",
            "statement": "La capacidad funcional de la pantalla existente no se especifica.",
            "materiality": "MATERIAL",
        }],
    }


def accepting_fixture_reviewer(raw, candidate):
    return {
        "verdict": "PASS", "candidate_sha256": SEM._hash(candidate),
        "reviewer_ref": "fixture://reviewer", "issues": [],
    }


def unknown_signals():
    # Externally supplied synthetic UNKNOWN inputs, not A1-generated facts.
    return {
        "materiality_level": "UNKNOWN", "scope_bounded": "UNKNOWN",
        "authority_state": "UNKNOWN", "reversibility_state": "UNKNOWN",
        "currentness_decision": "UNKNOWN_FAIL_CLOSED",
        "material_contradiction": False, "known_cross_scope_impact": "UNKNOWN",
        "unresolved_material_signal_count": 1, "required_specialist_count": 0,
    }


def canonical_d4_metadata_response():
    return {
        "schema_version": "LF_SOURCE_INVESTIGATION_PREPARATION_V1",
        "next_action": "SEARCH_OTHER_CANDIDATES_OR_GOVERN_BINDING",
        "planner_stop_is_local_only": True,
        "discovery": {"discovery_state": "CANDIDATES_FOUND"},
        "binding_checks": [],
        "binding_checks_count": 0,
        "d3": {
            "next_action": "SEARCH_OTHER_CANDIDATES_OR_GOVERN_BINDING",
            "final_business_answer_allowed": False,
        },
        "business_data_read_authorized": False,
        "rows_accessed": False,
        "runtime_dispatched": False,
        "final_business_answer_allowed": False,
        "effects_executed": False,
        "global_discovery_exhausted": False,
    }


class GovernedD4FixtureCursor:
    def __init__(self, response=None, error=None):
        self.response = canonical_d4_metadata_response() if response is None else response
        self.error = error
        self.calls = []

    def execute(self, sql, args):
        self.calls.append((sql, args))
        if self.error is not None:
            raise self.error

    def fetchone(self):
        return (self.response,)


class SemanticA1Candidate(unittest.TestCase):
    def test_free_text_requires_real_producer_and_reviewer_interfaces(self):
        out = A1.run(LOGIN, business="LF")
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["blocking_codes"], ["SEMANTIC_PRODUCER_UNAVAILABLE"])
        self.assertIsNone(out["next_capability"])

    def test_raw_envelope_business_drift_fails_closed(self):
        out = A1.run({"raw_prompt": LOGIN, "business": "SALY"},
                     business="LF", semantic_producer=producer,
                     semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["blocking_codes"], ["RAW_ENVELOPE_BUSINESS_CONFLICT"])
        self.assertIsNone(out["next_capability"])

    def test_raw_envelope_same_business_is_allowed(self):
        out = A1.run({"raw_prompt": LOGIN, "business": "LF"},
                     business="LF", semantic_producer=producer,
                     semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "VALID_OUTPUT")
        self.assertEqual(out["business"], "LF")

    def test_raw_text_requires_business_context_not_keyword(self):
        out = A1.run(LOGIN, semantic_producer=producer, semantic_reviewer=reviewer)
        self.assertEqual(out["blocking_codes"], ["BUSINESS_SCOPE_NOT_PROVIDED_OR_NOT_LF"])

    def test_login_semantic_candidate_preserves_implementation_not_new_code_claim(self):
        out = A1.run(LOGIN, business="LF", semantic_producer=producer, semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "VALID_OUTPUT")
        self.assertEqual(out["interpretation_state"], "SEMANTIC_REVIEWED_CANDIDATE")
        self.assertFalse(out["semantic_review_required"])
        self.assertEqual(out["next_capability"], "A2")
        self.assertEqual(out["intent_analysis"]["operation"]["kind"], "IMPLEMENT")
        self.assertEqual(out["intent_analysis"]["operation"]["user_assumed_state"], "CLAIMED_GREENFIELD")
        self.assertEqual(out["intent_analysis"]["operation"]["repo_verification_state"], "PENDING_INVENTORY")
        self.assertEqual(out["intent_analysis"]["target"]["canonical_capability"], "IDENTITY_AND_ACCESS")
        self.assertEqual(out["payload"]["schema_version"], "REQUEST_CONTEXT_V1")
        self.assertEqual(out["payload"]["target_hints"], ["login B2B"])
        self.assertEqual(out["original_request_sha256"], sha256(LOGIN.encode()).hexdigest())
        self.assertFalse(out["semantic_review_identity_verified"])
        self.assertFalse(out["external_authority_verified"])

    def test_implicit_portal_entry_requires_mechanism_decision(self):
        out = A1.run(IMPLICIT, business="LF", semantic_producer=producer, semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "REQUIRES_DECISION")
        self.assertIsNone(out["next_capability"])
        self.assertEqual(out["intent_analysis"]["target"]["functional_archetype"], "PORTAL_ENTRY_VIEW")
        self.assertEqual(out["intent_analysis"]["target"]["canonical_capability"], "ENTERPRISE_PORTAL_ACCESS")
        self.assertEqual(out["intent_analysis"]["operation"]["kind"], "IMPLEMENT")
        self.assertEqual(out["intent_analysis"]["operation"]["user_assumed_state"], "UNSPECIFIED")
        self.assertEqual(out["payload"]["ambiguities"][0]["resolution_state"], "OPEN")
        transport = BRIDGE.prepare_semantic_transport(
            IMPLICIT, business="LF", semantic_producer=producer, semantic_reviewer=reviewer
        )
        self.assertEqual(transport["status"], "HALTED_AT_A1")
        self.assertIsNone(transport["a2_result"])

    def test_open_catalog_not_hardcoded_to_auth_login(self):
        out = A1.run(GRID, business="LF", semantic_producer=producer, semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "VALID_OUTPUT")
        self.assertEqual(out["intent_analysis"]["target"]["functional_archetype"], "DATA_GRID_VIEW")
        self.assertEqual(out["intent_analysis"]["target"]["canonical_capability"], "DATA_EXPLORATION")
        self.assertNotIn("AUTH_MECHANISM", out["intent_analysis"]["dimensions_to_investigate"])

    def test_negation_needs_semantic_review_not_keyword_pass(self):
        out = A1.run(NEGATED, business="LF", semantic_producer=producer, semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "REQUIRES_SEMANTIC_REVIEW")
        self.assertIsNone(out["next_capability"])

    def test_existing_screen_reuse_preserves_negation_and_blocks_a2(self):
        out = A1.run(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        self.assertEqual(out["status"], "REQUIRES_DECISION", out)
        self.assertEqual(out["intent_analysis"]["operation"]["kind"], "REUSE")
        self.assertEqual(out["declared_intent_kind"], "UNKNOWN")
        self.assertEqual(out["payload"]["constraints"], ["No crees otra pantalla"])
        self.assertIsNone(out["next_capability"])
        transport = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        self.assertEqual(transport["status"], "HALTED_AT_A1")
        self.assertIsNone(transport["a2_result"])

    def test_reuse_missing_negation_span_fails_semantic_grounding(self):
        def bad(raw):
            proposal = reuse_candidate(raw)
            proposal["evidence_spans"] = [
                item for item in proposal["evidence_spans"]
                if item["dimension"] != "NEGATION"
            ]
            return proposal
        out = A1.run(
            NEGATED, business="LF", semantic_producer=bad,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        self.assertEqual(out["status"], "REQUIRES_SEMANTIC_REVIEW")
        self.assertIn("EXPLICIT_CONSTRAINT_EVIDENCE_MISSING", out["blocking_codes"])
        self.assertIsNone(out["next_capability"])

    def test_reuse_unknown_capability_without_ambiguity_fails(self):
        def bad(raw):
            proposal = reuse_candidate(raw)
            proposal["material_ambiguities"] = []
            return proposal
        out = A1.run(
            NEGATED, business="LF", semantic_producer=bad,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        self.assertEqual(out["status"], "REQUIRES_SEMANTIC_REVIEW")
        self.assertIn("MATERIAL_INTENT_UNRESOLVED", out["blocking_codes"])
        self.assertIsNone(out["next_capability"])

    def test_inventory_handoff_portal_entry_preserves_open_ambiguity(self):
        transport = BRIDGE.prepare_semantic_transport(
            IMPLICIT, business="LF", semantic_producer=producer,
            semantic_reviewer=reviewer,
        )
        self.assertEqual(transport["status"], "HALTED_AT_A1")
        request = transport["inventory_research_handoff"]
        self.assertEqual(request["schema_version"], "A1_INVENTORY_RESEARCH_HANDOFF_CANDIDATE_V1")
        self.assertEqual(request["business"], "LF")
        self.assertEqual(request["operation_kind"], "IMPLEMENT")
        self.assertEqual(request["functional_capability_proposal"], "ENTERPRISE_PORTAL_ACCESS")
        self.assertEqual(request["original_request"], IMPLICIT)
        self.assertEqual(request["request_sha256"], sha256(IMPLICIT.encode()).hexdigest())
        self.assertEqual(request["open_ambiguities"][0]["code"], "PORTAL_ENTRY_MODE_UNRESOLVED")
        self.assertEqual(request["open_ambiguities"][0]["resolution_state"], "OPEN")
        self.assertFalse(request["allow_a2"])
        self.assertFalse(request["inventory_source_verified"])
        self.assertFalse(request["inventory_lookup_executed"])
        plan = transport["a2_research_preview"]
        self.assertEqual(plan["status"], "RESEARCH_PLAN_ONLY")
        self.assertEqual(plan["research_plan"]["operation_hint"], "IMPLEMENT")
        self.assertEqual(plan["research_plan"]["unresolved_ambiguities"][0]["code"],
                         "PORTAL_ENTRY_MODE_UNRESOLVED")
        self.assertFalse(plan["a3_dispatch_allowed"])
        self.assertIsNone(plan["a2_classification"])
        self.assertIsNone(transport["a2_result"])
        self.assertIsNone(transport["a2_signal_bundle"])
        self.assertTrue(transport["no_run_created"])

    def test_inventory_handoff_reuse_preserves_negation_and_unknown(self):
        transport = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        self.assertEqual(transport["status"], "HALTED_AT_A1")
        request = transport["inventory_research_handoff"]
        self.assertEqual(request["operation_kind"], "REUSE")
        self.assertEqual(request["functional_capability_proposal"], "UNKNOWN")
        self.assertEqual(request["constraints"], ["No crees otra pantalla"])
        self.assertEqual(request["target_hints"], ["pantalla"])
        self.assertEqual(request["open_ambiguities"][0]["code"], "FUNCTIONAL_CAPABILITY_UNSPECIFIED")
        self.assertIn("EXISTING_SCREEN_LOOKUP", request["dimensions_to_investigate"])
        self.assertFalse(request["allow_a2"])
        self.assertFalse(request["inventory_source_verified"])
        plan = transport["a2_research_preview"]
        self.assertEqual(plan["status"], "RESEARCH_PLAN_ONLY")
        self.assertEqual(plan["research_plan"]["operation_hint"], "REUSE")
        self.assertEqual(plan["research_plan"]["constraints"], ["No crees otra pantalla"])
        self.assertEqual(plan["research_plan"]["functional_capability_hint"], "UNKNOWN")
        self.assertFalse(plan["a3_dispatch_allowed"])
        self.assertTrue(transport["no_run_created"])
        self.assertIsNone(transport["a2_result"])

    def test_material_ambiguity_cannot_be_bypassed_with_a2_signals(self):
        transport = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
            depth_signals=unknown_signals(),
            evidence_refs=["fixture://unverified-source"],
        )
        self.assertEqual(transport["status"], "HALTED_AT_A1")
        self.assertEqual(transport["inventory_research_handoff"]["operation_kind"], "REUSE")
        self.assertFalse(transport["inventory_research_handoff"]["allow_a2"])
        self.assertIsNone(transport["a2_signal_bundle"])
        self.assertIsNone(transport["a2_result"])
        self.assertTrue(transport["no_run_created"])

    def test_invalid_semantic_input_cannot_issue_inventory_handoff(self):
        transport = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=producer,
            semantic_reviewer=reviewer,
        )
        self.assertEqual(transport["status"], "HALTED_AT_A1")
        self.assertEqual(transport["a1_result"]["status"], "REQUIRES_SEMANTIC_REVIEW")
        self.assertIsNone(transport["inventory_research_handoff"])
        self.assertIsNone(transport["a2_research_preview"])
        self.assertIsNone(transport["a2_result"])

    def test_ungrounded_evidence_refused_before_reviewer(self):
        def bad(raw):
            c = semantic_candidate(raw)
            c["evidence_spans"][0]["quote"] = "COMANDO INVENTADO"
            return c
        out = A1.run(LOGIN, business="LF", semantic_producer=bad, semantic_reviewer=reviewer)
        self.assertEqual(out["status"], "REQUIRES_SEMANTIC_REVIEW")
        self.assertIn("EVIDENCE_SPAN_MISMATCH", out["blocking_codes"])

    def test_unverified_assumption_span_blocks(self):
        def bad(raw):
            c = semantic_candidate(raw)
            c["evidence_spans"] = [s for s in c["evidence_spans"] if s["dimension"] != "ASSUMPTION"]
            return c
        out = A1.run(LOGIN, business="LF", semantic_producer=bad, semantic_reviewer=reviewer)
        self.assertIn("USER_ASSUMED_STATE_UNGROUNDED", out["blocking_codes"])

    def test_no_intent_authority_injected_into_canonical_payload(self):
        out = A1.run(LOGIN, business="LF", semantic_producer=producer, semantic_reviewer=reviewer)
        self.assertNotIn("intent_analysis", out["payload"])
        self.assertNotIn("runtime_binding_enabled", out)
        self.assertNotIn("execution_id", out)

    def test_a2_transport_requires_real_typed_evidence(self):
        out = BRIDGE.prepare_semantic_transport(
            LOGIN, business="LF", semantic_producer=producer, semantic_reviewer=reviewer
        )
        self.assertEqual(out["status"], "A1_READY_A2_EVIDENCE_REQUIRED")
        self.assertEqual(out["a2_intent_hint"]["change_type"], "IMPLEMENT")
        self.assertIsNone(out["a2_result"])
        self.assertTrue(out["no_run_created"])

    def test_a2_candidate_continuity_with_external_unknown_signals(self):
        out = BRIDGE.prepare_semantic_transport(
            LOGIN, business="LF", semantic_producer=producer, semantic_reviewer=reviewer,
            depth_signals=unknown_signals(), evidence_refs=["fixture://unverified-a2-source"]
        )
        self.assertEqual(out["status"], "A2_CANDIDATE_RETURNED", out)
        self.assertEqual(out["a2_result"]["status"], "NEED_MORE_EVIDENCE")
        self.assertEqual(out["a2_result"]["classification"]["change_type"], "IMPLEMENT")
        self.assertEqual(out["a2_result"]["classification"]["depth_level"], "L2")
        self.assertFalse(out["a2_result"]["source_attested"])
        self.assertIsNone(out["a2_result"]["next_step"])

    def test_a2_detects_intent_drift(self):
        out = BRIDGE.prepare_semantic_transport(
            LOGIN, business="LF", semantic_producer=producer, semantic_reviewer=reviewer,
            depth_signals=unknown_signals(), evidence_refs=["fixture://source"]
        )
        altered = copy.deepcopy(out["a2_signal_bundle"])
        altered["change_type"] = "CREATE"
        bad = A2.run(out["a1_result"], altered)
        self.assertEqual(bad["status"], "BLOCKED")
        self.assertEqual(bad["blocking_codes"], ["A2_SEMANTIC_INTENT_DRIFT"])


    def test_existing_d4_consumes_02_with_metadata_only_no_a2(self):
        from_existing_a1 = BRIDGE.prepare_semantic_transport(
            IMPLICIT, business="LF", semantic_producer=producer,
            semantic_reviewer=reviewer,
        )
        cursor = GovernedD4FixtureCursor()
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(
            from_existing_a1, cursor
        )
        self.assertEqual(out["status"], "METADATA_PREPARED_AMBIGUITIES_OPEN")
        self.assertFalse(out["a2_allowed"])
        self.assertFalse(out["source_attested"])
        self.assertFalse(out["runtime_integrated"])
        self.assertIsNone(out["a2_result"])
        self.assertTrue(out["no_run_created"])
        self.assertEqual(
            out["open_ambiguities"][0]["code"], "PORTAL_ENTRY_MODE_UNRESOLVED"
        )
        self.assertEqual(
            cursor.calls, [(
                "SELECT private.fn_lf_source_investigation_prepare_v1(%s, %s) AS preparation",
                (IMPLICIT, 12),
            )]
        )

    def test_existing_d4_consumes_04_preserving_negation(self):
        from_existing_a1 = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        cursor = GovernedD4FixtureCursor()
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(
            from_existing_a1, cursor
        )
        self.assertEqual(out["status"], "METADATA_PREPARED_AMBIGUITIES_OPEN")
        self.assertEqual(out["operation_kind"], "REUSE")
        self.assertEqual(out["constraints"], ["No crees otra pantalla"])
        self.assertEqual(
            out["open_ambiguities"][0]["code"], "FUNCTIONAL_CAPABILITY_UNSPECIFIED"
        )
        self.assertFalse(out["a2_allowed"])
        self.assertEqual(cursor.calls[0][1], (NEGATED, 12))

    def test_existing_d4_rejects_tampered_input_sha_before_cursor(self):
        handoff = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        handoff = copy.deepcopy(handoff)
        handoff["inventory_research_handoff"]["request_sha256"] = "0" * 64
        cursor = GovernedD4FixtureCursor()
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(handoff, cursor)
        self.assertEqual(out["blocking_code"], "A1_D4_RAW_REQUEST_HASH_DRIFT")
        self.assertEqual(cursor.calls, [])

    def test_existing_d4_rejects_constraint_drift_before_cursor(self):
        handoff = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        handoff = copy.deepcopy(handoff)
        handoff["inventory_research_handoff"]["constraints"] = []
        cursor = GovernedD4FixtureCursor()
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(handoff, cursor)
        self.assertEqual(out["blocking_code"], "A1_D4_RESEARCH_CONTEXT_DRIFT")
        self.assertEqual(cursor.calls, [])

    def test_existing_d4_rejects_a2_bypass(self):
        handoff = BRIDGE.prepare_semantic_transport(
            NEGATED, business="LF", semantic_producer=reuse_candidate,
            semantic_reviewer=accepting_fixture_reviewer,
        )
        handoff = copy.deepcopy(handoff)
        handoff["a2_result"] = {"status": "FORGED_PASS"}
        cursor = GovernedD4FixtureCursor()
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(handoff, cursor)
        self.assertEqual(out["blocking_code"], "A1_D4_A2_GATE_NOT_HALTED")
        self.assertEqual(cursor.calls, [])

    def test_existing_d4_rejects_unauthorized_effect_claim(self):
        handoff = BRIDGE.prepare_semantic_transport(
            IMPLICIT, business="LF", semantic_producer=producer,
            semantic_reviewer=reviewer,
        )
        forged = canonical_d4_metadata_response()
        forged["business_data_read_authorized"] = True
        cursor = GovernedD4FixtureCursor(forged)
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(handoff, cursor)
        self.assertEqual(out["blocking_code"], "A1_D4_CANONICAL_PREPARATION_FAILED")
        self.assertFalse(out["a2_allowed"])

    def test_existing_d4_rejects_canonical_currentness_block(self):
        handoff = BRIDGE.prepare_semantic_transport(
            IMPLICIT, business="LF", semantic_producer=producer,
            semantic_reviewer=reviewer,
        )
        blocked = canonical_d4_metadata_response()
        blocked["next_action"] = "BLOCK_INVENTORY_LOOKUP_CURRENTNESS_UNSTABLE"
        blocked["d3"] = None
        cursor = GovernedD4FixtureCursor(blocked)
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(handoff, cursor)
        self.assertEqual(out["blocking_code"], "A1_D4_CANONICAL_PREPARATION_BLOCKED")
        self.assertFalse(out["a2_allowed"])

    def test_existing_d4_rejects_connection_error_without_leak(self):
        handoff = BRIDGE.prepare_semantic_transport(
            IMPLICIT, business="LF", semantic_producer=producer,
            semantic_reviewer=reviewer,
        )
        cursor = GovernedD4FixtureCursor(error=RuntimeError("secret connection token"))
        out = D4CONSUMER.prepare_a1_research_with_governed_cursor(handoff, cursor)
        self.assertEqual(out["blocking_code"], "A1_D4_CANONICAL_PREPARATION_FAILED")
        self.assertNotIn("secret", str(out))
        self.assertFalse(out["a2_allowed"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
