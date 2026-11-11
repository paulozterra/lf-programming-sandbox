"""A5 synthetic decision/ADR tests. No owner approvals or native runtime receipts."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("a5_decision_consumer", ROOT / "validators/run.py")
a5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a5)

T = "B2B-AUTH-001"
S = "supabase://lf_ops.pantallas/B2B-AUTH-001"
FLAGS = [
    "canonical_authority_or_owner_changes",
    "transversal_capability_created_extended_or_retired",
    "cross_stage_or_multi_consumer_contract_changes",
    "canonical_state_authority_or_lifecycle_changes",
    "material_migration_cutover_or_long_lived_compatibility_changes",
    "security_or_privacy_boundary_changes",
    "runtime_or_production_topology_changes",
]


def inputs():
    return {
        "REQUEST_CONTEXT_V1": {
            "schema_version": "REQUEST_CONTEXT_V1", "target_hints": ["Login B2B"],
            "source_refs": ["user://request"], "constraints": ["No pending rules"],
            "objective": {"problem_statement": "Implementar Login B2B"}},
        "ANALYSIS_CHANGE_CLASSIFICATION_V1": {
            "schema_version": "ANALYSIS_CHANGE_CLASSIFICATION_V1",
            "target_ref": "Login B2B", "change_type": "CREATE"},
        "TARGETED_EVIDENCE_SET_V1": {
            "schema_version": "TARGETED_EVIDENCE_SET_V1",
            "business": "LF", "status": "SOURCE_READBACK_PROCESSED_UNATTESTED",
            "target_ref": T, "declared_target_hint": "Login B2B",
            "source_refs": [S],
            "excluded_rule_items": [{"rule_code": "PENDING", "rule_status": "CANDIDATO"}],
        },
        "SHARED_CHANGE_IMPACT_ANALYSIS": {
            "schema_version": "SHARED_CHANGE_IMPACT_ANALYSIS",
            "status": "PLANNED_BUILD_IMPACT_UNATTESTED",
            "business": "LF", "target_ref": T, "evidence_refs": [S],
            "target_change_action": "CREATE",
            "unresolved_material_impacts": [
                {"code": "A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED",
                 "target_ref": T, "source_id": "S3_INV_OBJECT"}],
        },
    }


def packet(flags=None):
    return {
        "schema_version": "A5_GOVERNED_DECISION_READBACK_V1",
        "business": "LF", "target_ref": T, "source_attested": False,
        "adr_trigger_review": {
            "flags": {f: False for f in FLAGS} if flags is None else flags,
            "evidence_ref": S, "source_attested": False,
        },
    }


class A5DecisionTests(unittest.TestCase):
    def test_no_sidecar_no_human_escalation(self):
        result = a5.run(inputs())
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["decision_context"]["adr_disposition"], "ADR_BLOCKED")
        self.assertFalse(result["a6_allowed"])

    def test_reviewed_local_build_not_new_adr(self):
        data = inputs(); before = deepcopy(data)
        out = a5.run(data, packet())
        self.assertEqual(out["decision_context"]["adr_disposition"], "NOT_REQUIRED")
        self.assertEqual(out["status"], "UNRESOLVED")
        self.assertEqual(out["material_adr_triggers_true"], [])
        self.assertFalse(out["excluded_pending_definitions_are_decisions"])
        self.assertNotIn("A5_NEW_ARCHITECTURE_DECISION_REQUIRES_OWNER", out["unresolved_material_questions"])
        self.assertEqual(data, before)

    def test_pending_rules_alone_never_human_decision(self):
        data = inputs()
        data["TARGETED_EVIDENCE_SET_V1"]["excluded_rule_items"].extend([
            {"rule_code": f"WAIT_{i}", "rule_status": "CANDIDATO"} for i in range(40)])
        out = a5.run(data, packet())
        self.assertEqual(out["status"], "UNRESOLVED")
        self.assertEqual(out["decision_context"]["adr_disposition"], "NOT_REQUIRED")

    def test_unknown_material_trigger_not_assumed_false(self):
        flags = {f: False for f in FLAGS}
        flags["security_or_privacy_boundary_changes"] = "UNKNOWN"
        out = a5.run(inputs(), packet(flags))
        self.assertEqual(out["status"], "UNRESOLVED")
        self.assertEqual(out["decision_context"]["adr_disposition"], "ADR_BLOCKED")
        self.assertIn("A5_MATERIAL_ADR_CLASSIFICATION_UNVERIFIED",out["unresolved_material_questions"])

    def test_material_owner_change_without_adrs_search_is_unresolved(self):
        flags = {f: False for f in FLAGS}
        flags["canonical_authority_or_owner_changes"] = True
        out = a5.run(inputs(), packet(flags))
        self.assertEqual(out["status"], "UNRESOLVED")
        self.assertEqual(out["decision_context"]["adr_disposition"], "ADR_BLOCKED")
        self.assertIn("A5_CURRENT_ADR_ASSERTION_OR_NEGATIVE_LOOKUP_REQUIRED",
                      out["unresolved_material_questions"])

    def test_material_new_adr_is_human_decision_only_after_bound_negative(self):
        flags = {f: False for f in FLAGS}
        flags["cross_stage_or_multi_consumer_contract_changes"] = True
        p = packet(flags)
        p["adr_search"] = {
            "state": "NO_CURRENT_ADR", "source_function": "transversal.decision_log",
            "target_ref": T, "source_attested": False, "evidence_ref": S,
        }
        out = a5.run(inputs(), p)
        self.assertEqual(out["status"], "REQUIRES_DECISION")
        self.assertEqual(out["decision_context"]["adr_disposition"], "NEW_ADR_REQUIRED")
        self.assertIsNone(out["decision_context"]["selected_option_ref"])
        self.assertIsNone(out["decision_context"]["persistence_ref"])
        self.assertFalse(out["a6_allowed"])

    def test_reuse_current_adr_requires_exact_assertion(self):
        flags = {f: False for f in FLAGS}
        flags["security_or_privacy_boundary_changes"] = True
        p=packet(flags)
        p["existing_adr_ref"]="ADR-LF-CURRENT-1"
        p["adr_assertion"]={
            "schema_version":"ENGINEERING_CURRENT_ADR_ASSERT_V1",
            "status":"PASS","adr":"ADR-LF-CURRENT-1","estado":"vigente",
            "created_at":"2026-10-20T00:00:00+00:00"}
        out=a5.run(inputs(),p)
        self.assertEqual(out["decision_context"]["adr_disposition"],"REUSE_CURRENT_ADR")
        self.assertEqual(out["decision_context"]["adr_ref"],"ADR-LF-CURRENT-1")
        self.assertEqual(out["status"],"UNRESOLVED")
        self.assertFalse(out["source_attested"])

    def test_stale_adr_assertion_blocks(self):
        flags = {f: False for f in FLAGS}
        flags["security_or_privacy_boundary_changes"]=True
        p=packet(flags);p["existing_adr_ref"]="ADR-STALE"
        p["adr_assertion"]={
            "schema_version":"ENGINEERING_CURRENT_ADR_ASSERT_V1",
            "status":"PASS","adr":"ADR-STALE","estado":"superado",
            "created_at":"2026-10-20T00:00:00+00:00"}
        out=a5.run(inputs(),p)
        self.assertEqual(out["status"],"BLOCKED")
        self.assertIn("A5_EXISTING_ADR_CURRENT_ASSERTION_INVALID",out["blocking_codes"])

    def test_historical_asof_not_current_approval(self):
        p=packet()
        p["asof_resolution"]={
            "schema_version":"LF_DECISION_CONTEXT_ASOF_RESOLUTION_V1",
            "state":"RESOLVED","resolution_basis":"IMMUTABLE_RECORDED_CONTEXT",
            "latest_reinterpreted":False,"subject_ref":T,
            "context_id":"historical_1"}
        out=a5.run(inputs(),p)
        self.assertEqual(out["status"],"UNRESOLVED")
        self.assertIn("A5_HISTORICAL_ASOF_NOT_CURRENT_DECISION",
                      out["unresolved_material_questions"])
        self.assertFalse(out["a6_allowed"])

    def test_mismatched_or_forged_asof_blocks(self):
        p=packet()
        p["asof_resolution"]={
            "schema_version":"LF_DECISION_CONTEXT_ASOF_RESOLUTION_V1",
            "state":"RESOLVED","resolution_basis":"IMMUTABLE_RECORDED_CONTEXT",
            "latest_reinterpreted":True,"subject_ref":T,"context_id":"historical"}
        self.assertEqual(a5.run(inputs(),p)["status"],"BLOCKED")

    def test_exact_four_inputs_and_business_guard(self):
        data=inputs();del data["REQUEST_CONTEXT_V1"]
        self.assertIn("A5_EXACT_FOUR_CANONICAL_INPUTS_REQUIRED",
                      a5.run(data)["blocking_codes"])
        self.assertIn("A5_BUSINESS_NOT_ENABLED_FOR_LF_SKILL",
                      a5.run(inputs(),packet(),business="SALY")["blocking_codes"])

    def test_cross_target_and_source_provenance_blocks(self):
        data=inputs()
        data["SHARED_CHANGE_IMPACT_ANALYSIS"]["target_ref"]="DIFFERENT"
        self.assertEqual(a5.run(data,packet())["status"],"BLOCKED")
        p=packet();p["adr_trigger_review"]["evidence_ref"]="unbound://fake"
        self.assertEqual(a5.run(inputs(),p)["status"],"BLOCKED")

    def test_incomplete_or_malformed_trigger_set_blocks(self):
        p=packet();del p["adr_trigger_review"]["flags"][FLAGS[0]]
        self.assertIn("A5_ADR_TRIGGER_SET_INCOMPLETE",a5.run(inputs(),p)["blocking_codes"])
        p=packet();p["adr_trigger_review"]["flags"][FLAGS[0]]=1
        self.assertIn("A5_ADR_TRIGGER_VALUE_INVALID",a5.run(inputs(),p)["blocking_codes"])

    def test_fingerprint_deterministic_and_sensitive_to_material_change(self):
        a=a5.run(inputs(),packet())
        b=a5.run(deepcopy(inputs()),deepcopy(packet()))
        f=a["decision_context"]["decision_fingerprint_sha256"]
        self.assertEqual(f,b["decision_context"]["decision_fingerprint_sha256"])
        self.assertRegex(f,r"^[0-9a-f]{64}$")
        flags={k:False for k in FLAGS}
        flags["canonical_authority_or_owner_changes"]=True
        c=a5.run(inputs(),packet(flags))
        self.assertNotEqual(f,c["decision_context"]["decision_fingerprint_sha256"])

    def test_technical_detail_not_selected_by_a5(self):
        a=a5.run(inputs(),packet())
        d=a["decision_context"]
        self.assertEqual(d["options_considered"],[])
        self.assertIsNone(d["selected_option_ref"])
        self.assertIsNone(d["persistence_ref"])
        self.assertFalse(a["a6_allowed"])


if __name__ == "__main__":
    unittest.main()
