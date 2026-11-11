"""Synthetic tests only: no authorization, model or database execution."""
import copy
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("a1_step_preflight", HERE/"adapters/governed_skill_step_preflight_v1.py")
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def envelope(step="input_validate"):
    by_step={
        "init_execution":{"execution_id_created":True},
        "router":{"router_read":{"status":"READY"},"action":"SKILL_EXECUTION"},
        "skill_resolve":{"exact_skill_resolved":True,"codigo_activo":M.SKILL,"skill_identity":{"code":M.SKILL}},
        "skill_source_read":{"skill_source_ref":"github://a1","source_revision":"a"*40,"source_authority":"SOURCE_GITHUB"},
        "input_validate":{"input_scope":"literal user request","activation_trigger_match":True},
        "execute_skill":{"skill_output":{"status":"CANDIDATE"},"source_refs":["user://r"]},
        "output_validate":{"output_contract_result":"PENDING_REVIEW","deterministic_validation":"PASS"},
        "semantic_judge":{"semantic_judge_result":"PASS","unsupported_claims":[]},
        "report_output":{"result":"CANDIDATE","skill_code":M.SKILL,"execution_id":"EXEC-A1-SYNTHETIC-000001","no_write_performed":True},
    }
    return {"schema_version":"A1_GOVERNED_STEP_REQUEST_V1","operation_code":M.OPERATION,
        "target_type":"SKILL","target_code":M.SKILL,
        "execution_id":"EXEC-A1-SYNTHETIC-000001","actor_execution_id":"EXEC-A1-SYNTHETIC-000001",
        "step_id":step,"evidence_ref":"fixture://untrusted-local-evidence","evidence_payload":by_step[step]}


class A1PreflightTests(unittest.TestCase):
    def test_01_all_except_judge_are_only_preflight(self):
        for step in M.STEPS:
            with self.subTest(step=step):
                result=M.preflight(envelope(step))
                expected=("REQUIRES_SERVER_SIDE_INDEPENDENT_JUDGE"
                          if step=="semantic_judge" else
                          "REQUIRES_CANONICAL_BEGIN" if step=="init_execution" else
                          "PREFLIGHT_ONLY")
                self.assertEqual(result["status"],expected)
                self.assertFalse(result["authority_verified"])
                self.assertFalse(result["readback_verified"])

    def test_02_missing_evidence(self):
        e=envelope();del e["evidence_payload"]["input_scope"]
        self.assertEqual(M.preflight(e)["code"],"CANONICAL_EVIDENCE_MISSING")

    def test_03_other_operation(self):
        e=envelope();e["operation_code"]="CREACION_SKILL_LF"
        self.assertEqual(M.preflight(e)["code"],"OPERATION_TARGET_MISMATCH")

    def test_04_other_target_type(self):
        e=envelope();e["target_type"]="PERFIL"
        self.assertEqual(M.preflight(e)["code"],"OPERATION_TARGET_MISMATCH")

    def test_05_skill_code_mismatch(self):
        e=envelope();e["target_code"]="OTHER_SKILL"
        self.assertEqual(M.preflight(e)["code"],"SKILL_TARGET_MISMATCH")

    def test_06_actor_different_execution(self):
        e=envelope();e["actor_execution_id"]="EXEC-STOLEN"
        self.assertEqual(M.preflight(e)["code"],"ACTOR_EXECUTION_BINDING_MISMATCH")

    def test_07_step_not_canonical(self):
        e=envelope();e["step_id"]="github_write"
        self.assertEqual(M.preflight(e)["code"],"STEP_NOT_IN_CANONICAL_OPERATION")

    def test_08_forbidden_service_role_in_payload(self):
        e=envelope();e["evidence_payload"]["service_role_key"]="dont"
        self.assertEqual(M.preflight(e)["code"],"UNTRUSTED_AUTHORITY_FIELDS")

    def test_09_untrusted_judge_pass_cannot_authorize(self):
        e=envelope("semantic_judge");r=M.preflight(e)
        self.assertEqual(r["status"],"REQUIRES_SERVER_SIDE_INDEPENDENT_JUDGE")
        self.assertFalse(r["writes_performed"])

    def test_10_judge_unsupported_claims_blocks(self):
        e=envelope("semantic_judge");e["evidence_payload"]["unsupported_claims"]=["source not verified"]
        self.assertEqual(M.preflight(e)["code"],"UNSUPPORTED_CLAIMS_PRESENT")

    def test_11_malformed_claims_blocks(self):
        e=envelope("semantic_judge");e["evidence_payload"]["unsupported_claims"]="no"
        self.assertEqual(M.preflight(e)["code"],"UNSUPPORTED_CLAIMS_INVALID")

    def test_12_failed_source_revision(self):
        e=envelope("skill_source_read");e["evidence_payload"]["source_revision"]="main"
        self.assertEqual(M.preflight(e)["code"],"SOURCE_REVISION_INVALID")

    def test_13_empty_source_refs(self):
        e=envelope("execute_skill");e["evidence_payload"]["source_refs"]=[]
        self.assertEqual(M.preflight(e)["code"],"SOURCE_REFS_REQUIRED")

    def test_14_report_mismatched_id(self):
        e=envelope("report_output");e["evidence_payload"]["execution_id"]="EXEC-OTHER-12345"
        self.assertEqual(M.preflight(e)["code"],"REPORT_IDENTITY_MISMATCH")

    def test_15_report_cannot_admit_skill_mutation(self):
        e=envelope("report_output");e["evidence_payload"]["no_write_performed"]=False
        self.assertEqual(M.preflight(e)["code"],"REPORT_EXPECTS_READ_ONLY_SKILL")

    def test_16_readback_row_must_match_exact_run(self):
        e=envelope()
        row={"execution_id":"EXEC-OTHER","step_id":e["step_id"],"status":"STEP_PASS_WITH_EVIDENCE",
             "evidence_ref":e["evidence_ref"],"evidence_payload":e["evidence_payload"]}
        self.assertEqual(M.compare_readback(e,row)["code"],"PERSISTED_IDENTITY_MISMATCH")

    def test_17_readback_row_fails_on_mismatched_evidence(self):
        e=envelope()
        row={"execution_id":e["execution_id"],"step_id":e["step_id"],"status":"STEP_PASS_WITH_EVIDENCE",
             "evidence_ref":e["evidence_ref"],"evidence_payload":{"input_scope":"altered","activation_trigger_match":True}}
        self.assertEqual(M.compare_readback(e,row)["code"],"PERSISTED_EVIDENCE_MISMATCH")

    def test_18_matching_row_is_not_authority_proof(self):
        e=envelope()
        row={"execution_id":e["execution_id"],"step_id":e["step_id"],"status":"STEP_PASS_WITH_EVIDENCE",
             "evidence_ref":e["evidence_ref"],"evidence_payload":copy.deepcopy(e["evidence_payload"])}
        result=M.compare_readback(e,row)
        self.assertEqual(result["status"],"READBACK_SHAPE_MATCH_ONLY")
        self.assertFalse(result["readback_verified"])
        self.assertFalse(result["authority_verified"])

    def test_19_readback_fail_status(self):
        e=envelope()
        row={"execution_id":e["execution_id"],"step_id":e["step_id"],"status":"BLOCKED_STEP_NOT_CLEAN",
             "evidence_ref":e["evidence_ref"],"evidence_payload":e["evidence_payload"]}
        self.assertEqual(M.compare_readback(e,row)["code"],"PERSISTED_STATUS_NOT_CLEAN")

    def test_20_no_extra_authority_flags(self):
        e=envelope();e["caller_oidc_verified"]=True
        self.assertEqual(M.preflight(e)["code"],"REQUEST_CONTRACT_INVALID")

    def test_21_declared_blocking_codes_blocks(self):
        e=envelope();e["evidence_payload"]["blocking_codes"]=["MISSING_SOURCE"]
        self.assertEqual(M.preflight(e)["code"],"DECLARED_BLOCKING_CODES")

    def test_22_malformed_request_blocks(self):
        self.assertEqual(M.preflight([])["code"],"REQUEST_CONTRACT_INVALID")

    def test_23_skill_resolve_code_mismatch(self):
        e=envelope("skill_resolve");e["evidence_payload"]["codigo_activo"]="FAKE"
        self.assertEqual(M.preflight(e)["code"],"SKILL_RESOLVE_CODE_MISMATCH")

    def test_24_readback_absent(self):
        e=envelope()
        self.assertEqual(M.compare_readback(e,None)["code"],"PERSISTED_ROW_MISSING")

    def test_25_report_same_run_exact(self):
        e=envelope("report_output")
        self.assertEqual(M.preflight(e)["status"],"PREFLIGHT_ONLY")

    def test_26_init_is_reserved_for_canonical_operation_begin(self):
        e=envelope("init_execution")
        result=M.preflight(e)
        self.assertEqual(result["status"],"REQUIRES_CANONICAL_BEGIN")
        self.assertFalse(result["writes_performed"])

if __name__=="__main__":
    unittest.main()
