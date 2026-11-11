"""Hermetic regressions for the new A2 source-only semantic binding guard."""
from __future__ import annotations
import copy
import hashlib
import json
import unittest
from a2_semantic_input_integrity_v1 import check, _digest

RAW = "Programa la pantalla b2b inicio de sesión o login utiliza las reglas aprobadas, no consideres pendientes"
TARGET = "pantalla b2b inicio de sesión o login"
CONSTRAINTS = ["utiliza las reglas aprobadas", "no consideres pendientes"]

def span(needle, dimension):
    start=RAW.index(needle)
    return {"dimension": dimension, "quote": needle, "start": start, "end": start+len(needle)}

def fixture():
    intent={
       "schema_version":"A1_INTENT_ANALYSIS_CANDIDATE_V1",
       "operation":{"kind":"IMPLEMENT"},
       "target":{"artifact_kind":"SCREEN","raw_mentions":[TARGET]},
       "desired_outcome":"Login B2B con reglas aprobadas",
       "explicit_constraints":[{"text":x} for x in CONSTRAINTS],
       "evidence_spans":[span("Programa","OPERATION"),span(TARGET,"ARTIFACT"),span("b2b","ACTOR_SCOPE"),span(CONSTRAINTS[0],"CONSTRAINT"),span(CONSTRAINTS[1],"NEGATION")]
    }
    context={"schema_version":"REQUEST_CONTEXT_V1","objective":{"problem_statement":RAW,"desired_outcome":intent["desired_outcome"]},
             "target_hints":[TARGET],"constraints":CONSTRAINTS[:]}
    sig={"schema_version":"ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1","business":"LF","target_ref":TARGET,"depth_signals":{"materiality_level":"UNKNOWN"}}
    a2={"schema_version":"A2_INTERNAL_STEP_CANDIDATE_RESULT_V1","skill_code":"PROGRAMMING_ANALYSIS_LF","step_code":"A2","business":"LF",
        "status":"NEED_MORE_EVIDENCE","source_attested":False,
        "independent_judge_verified":False,"operationally_integrated":False,"effects_executed":False,"next_step":None,
        "classification":{"schema_version":"ANALYSIS_CHANGE_CLASSIFICATION_V1","target_ref":TARGET,"change_type":"IMPLEMENT","target_granularity":"SCREEN",
                           "signals_sha256":_digest(sig)}}
    a1={"schema_version":"A1_INTERNAL_STEP_CANDIDATE_RESULT_V1","skill_code":"PROGRAMMING_ANALYSIS_LF","step_code":"A1","business":"LF","status":"VALID_OUTPUT",
        "external_authority_verified":False,"operationally_integrated":False,"effects_executed":False,
        "interpretation_state":"SEMANTIC_REVIEWED_CANDIDATE","semantic_review_required":False,
        "next_capability":"A2","semantic_review_identity_verified":False,
        "semantic_reviewer_ref":"fixture://non-independent",
        "original_request_sha256":hashlib.sha256(RAW.encode()).hexdigest(),
        "semantic_candidate_sha256":_digest(intent),"intent_analysis":intent,"payload":context}
    return a1,a2,sig

class GuardRegression(unittest.TestCase):
    def test_valid_source_only(self):
        out=check(*fixture());self.assertEqual(out["status"],"CHECKED_SOURCE_ONLY")
        self.assertFalse(out["a3_allowed"]);self.assertFalse(out["source_attested"])
    def test_reject_saly_even_if_all_agree(self):
        a,b,s=fixture()
        for row in (a,b,s): row["business"]="SALY"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_BUSINESS_INVALID"])
    def test_reject_materially_open_a1(self):
        a,b,s=fixture();a["status"]="REQUIRES_DECISION"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_GATE_INVALID"])
    def test_reject_unreviewed_a1(self):
        a,b,s=fixture();a["semantic_review_required"]=True
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_GATE_INVALID"])
    def test_reject_false_identity_attestation(self):
        a,b,s=fixture();a["semantic_review_identity_verified"]=True
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_GATE_INVALID"])
    def test_reject_loss_of_negation_with_valid_intent_hash(self):
        a,b,s=fixture();a["payload"]["constraints"].pop()
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_CONSTRAINT_DRIFT"])
    def test_reject_unreviewed_intent_mutation(self):
        a,b,s=fixture();a["intent_analysis"]["desired_outcome"]="Forzar nuevo login"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_CONTENT_DIGEST_INVALID"])
    def test_reject_payload_outcome_mutation(self):
        a,b,s=fixture();a["payload"]["objective"]["desired_outcome"]="Otra cosa"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_CONTENT_DIGEST_INVALID"])
    def test_reject_foreign_target(self):
        a,b,s=fixture();b["classification"]["target_ref"]="SALY-LOGIN"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_TARGET_OR_OPERATION_DRIFT"])
    def test_reject_reclassified_operation(self):
        a,b,s=fixture();b["classification"]["change_type"]="CREATE"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_TARGET_OR_OPERATION_DRIFT"])
    def test_reject_broken_span(self):
        a,b,s=fixture();a["intent_analysis"]["evidence_spans"][0]["end"]+=1
        a["semantic_candidate_sha256"]=_digest(a["intent_analysis"])
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_SPAN_DRIFT"])
    def test_reject_missing_constraint_span(self):
        a,b,s=fixture();a["intent_analysis"]["evidence_spans"].pop()
        a["semantic_candidate_sha256"]=_digest(a["intent_analysis"])
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_CONSTRAINT_SPAN_MISSING"])
    def test_reject_signal_mutation(self):
        a,b,s=fixture();s["depth_signals"]["materiality_level"]="HIGH"
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_SIGNAL_DIGEST_INVALID"])
    def test_does_not_mutate_inputs(self):
        x=fixture();before=copy.deepcopy(x);check(*x);self.assertEqual(x,before)
    def test_reject_forged_judge_on_a2(self):
        a,b,s=fixture();b["independent_judge_verified"]=True
        self.assertEqual(check(a,b,s)["blocking_codes"],["SEMANTIC_BINDING_GATE_INVALID"])

if __name__=='__main__':unittest.main(verbosity=2)
