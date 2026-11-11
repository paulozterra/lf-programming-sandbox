"""Unit tests for candidate only; no DB writes or genuine receipts."""
import copy
import hashlib
import unittest

from pathlib import Path
import sys
test_location = Path(__file__).resolve()
package_adapters = test_location.parents[3] / "adapters" if len(test_location.parents) > 3 else test_location.parent
for candidate_root in (package_adapters, test_location.parent):
    if (candidate_root / "native_readonly_run_plan_v1.py").is_file():
        sys.path.insert(0, str(candidate_root))
        break
from native_readonly_run_plan_v1 import plan, verify_readback, SKILL, OP, REPO, PATH

H1, H2 = "a" * 64, "b" * 64
S1, S2 = "c" * 40, "d" * 40


def fixture():
    parent = dict(execution_id="EXEC-PROFILE-ORIGINAL", operation_code="EJECUCION_PERFIL_LF", status="IN_PROGRESS", target_type="PERFIL",
                  target_code="PERFIL-PROGRAMADOR-LF", request_sha256=H1,
                  manifest={"business": "LF", "router_profile_handoff": {
                      "business": "LF", "profile_code": "PERFIL-PROGRAMADOR-LF", "request_sha256": H1,
                      "router_authorization_receipt": {
                          "schema_version": "LF_ROUTER_PROFILE_AUTHORIZATION_RECEIPT_V1", "router": "ACT-0001",
                          "operation_code": "EJECUCION_PERFIL_LF", "action_code": "PROFILE_EXECUTION", "asset_type": "PERFIL",
                          "profile_execution_allowed": True, "effect_authority": False,
                          "business": "LF", "profile_code": "PERFIL-PROGRAMADOR-LF", "request_sha256": H1}}})
    catalog = dict(skill_code=SKILL, required_operation=OP, effect="READ_ONLY", status="READY")
    asset = dict(codigo_activo=SKILL, tipo_activo="SKILL", archived_at=None,
                 estado_operativo="READ_ONLY", metadata={"runtime_binding_enabled": True})
    authority = dict(profile_code="PERFIL-PROGRAMADOR-LF", operation_code=OP, status="ACTIVE")
    router = dict(asset_type="SKILL", action_code="SKILL_EXECUTION", operation_code=OP,
                  write_allowed=False, status="ACTIVE")
    source = dict(repository=REPO, path=PATH, ref="refs/heads/main", commit_sha=S1, blob_sha=S2)
    caller = dict(repository=REPO, method="GITHUB_ACTIONS_OIDC_EXACT_SKILL_V1",
                  workflow_ref=REPO + "/.github/workflows/authorized-skill-caller.yml@refs/heads/main")
    return [parent, catalog, asset, authority, router, source, caller, H2, parent["execution_id"]]


def make_receipts(candidate, *, replay=False):
    a = candidate["reservation_args"]
    reserve = dict(result="REPLAY_EXISTING_EXECUTION" if replay else "RESERVED_NEW_EXECUTION",
                   execution_id=a["p_execution_id"], operation_code=OP,
                   idempotency_key=a["p_idempotency_key"], request_sha256=a["p_request_sha256"],
                   dispatch_permitted=not replay)
    child = dict(execution_id=a["p_execution_id"], operation_code=OP,
                 target_type="SKILL", target_code=SKILL, target_repo=REPO, target_path=PATH,
                 created_by_execution_id=a["p_actor_execution_id"], request_sha256=a["p_request_sha256"],
                 idempotency_key=a["p_idempotency_key"], status="IN_PROGRESS",
                 manifest=copy.deepcopy(a["p_manifest"]))
    step = dict(execution_id=a["p_execution_id"], step_order=0, step_id="init_execution",
                status="STEP_PASS_WITH_EVIDENCE", evidence_ref="supabase://public.lf_operation_execution_steps/real-source",
                evidence_payload=dict(execution_id_created=True, step_result="STEP_PASS_WITH_EVIDENCE",
                                      mini_judge_code="JUDGE-EJECUCION-SKILL-LF-v0.1",
                                      mini_judge_result="STEP_PASS_WITH_EVIDENCE"))
    return reserve, child, step


class CandidatePlan(unittest.TestCase):
    def test_01_positive_simulated_never_authorizes(self):
        x = plan(*fixture()); self.assertEqual(x["status"], "CANDIDATE_PRECONDITIONS_CONSISTENT")
        self.assertFalse(x["host_attested"]); self.assertFalse(x["a3_allowed"])
        self.assertFalse(x["reservation_executed"])

    def test_02_idempotence_same_request(self):
        self.assertEqual(plan(*fixture())["reservation_args"], plan(*fixture())["reservation_args"])

    def test_03_different_input_not_same_idempotency(self):
        a, b = fixture(), fixture(); b[-2] = "f" * 64
        self.assertNotEqual(plan(*a)["reservation_args"]["p_idempotency_key"],plan(*b)["reservation_args"]["p_idempotency_key"])

    def test_04_changed_source_keeps_key_for_replay_drift_detection(self):
        a, b = fixture(), fixture(); b[5]["commit_sha"] = "e" * 40
        pa,pb = plan(*a),plan(*b)
        self.assertEqual(pa["reservation_args"]["p_idempotency_key"],pb["reservation_args"]["p_idempotency_key"])
        self.assertNotEqual(pa["reservation_args"]["p_manifest"],pb["reservation_args"]["p_manifest"])

    def test_05_real_candidate_not_admitted(self):
        x=fixture();x[2]["metadata"]["runtime_binding_enabled"]=False
        self.assertEqual(plan(*x)["blocking_codes"],["SKILL_ASSET_NOT_ADMITTED"])

    def test_06_no_authority(self):self.failcase(3,"status","DISABLED","PROFILE_SKILL_OPERATION_AUTHORITY_MISSING")
    def test_07_wrong_profile_authority(self):self.failcase(3,"profile_code","OTHER","PROFILE_SKILL_OPERATION_AUTHORITY_MISSING")
    def test_08_wrong_actor(self):self.failcase(8,None,"EXEC-FOREIGN","PARENT_SCOPE_NOT_AUTHORIZED")
    def test_09_root_business_missing(self):
        x=fixture();x[0]["manifest"].pop("business");self.assertEqual(plan(*x)["blocking_codes"],["PARENT_BUSINESS_MISSING"])
    def test_10_cross_business(self):
        x=fixture();x[0]["manifest"]["business"]="SALY";self.assertEqual(plan(*x)["blocking_codes"],["PARENT_ROUTER_SCOPE_CONFLICT"])
    def test_11_router_bad_code(self):self.failcase(4,"action_code","PROFILE_EXECUTION","SKILL_ROUTER_ROUTE_INVALID")
    def test_12_router_write_allowed(self):self.failcase(4,"write_allowed",True,"SKILL_ROUTER_ROUTE_INVALID")
    def test_13_catalog_wrong_effect(self):self.failcase(1,"effect","WRITE_GOVERNED","SKILL_CATALOG_NOT_ADMITTED_READONLY")
    def test_14_catalog_not_ready(self):self.failcase(1,"status","DRAFT","SKILL_CATALOG_NOT_ADMITTED_READONLY")
    def test_15_wrong_target(self):self.failcase(2,"codigo_activo","OTHER","SKILL_ASSET_NOT_ADMITTED")
    def test_16_source_not_main(self):self.failcase(5,"ref","refs/heads/feature","SKILL_MAIN_SOURCE_NOT_ATTESTED")
    def test_17_source_bad_sha(self):self.failcase(5,"blob_sha","invalid","SKILL_MAIN_SOURCE_NOT_ATTESTED")
    def test_18_caller_fake_workflow(self):self.failcase(6,"workflow_ref",REPO+"/.github/workflows/evil.yml@refs/heads/feature","CALLER_OIDC_IDENTITY_INVALID")
    def test_19_invalid_digest(self):self.failcase(7,None,"fake-digest","SKILL_INPUT_DIGEST_INVALID")
    def test_20_receipt_false_authority(self):
        x=fixture();x[0]["manifest"]["router_profile_handoff"]["router_authorization_receipt"]["effect_authority"]=True
        self.assertEqual(plan(*x)["blocking_codes"],["PARENT_ROUTER_AUTHORIZATION_INVALID"])
    def test_21_missing_router_receipt(self):
        x=fixture();x[0]["manifest"]["router_profile_handoff"].pop("router_authorization_receipt")
        self.assertEqual(plan(*x)["blocking_codes"],["PARENT_ROUTER_RECEIPT_MISSING"])

    def failcase(self, slot, field, value, expected):
        x=fixture()
        if field is None:x[slot]=value
        else:x[slot][field]=value
        result=plan(*x)
        self.assertEqual(result["blocking_codes"],[expected])
        self.assertFalse(result["a3_allowed"])


class CandidateReadback(unittest.TestCase):
    def test_22_new_readback_not_real_attestation(self):
        p=plan(*fixture());r=verify_readback(p,*make_receipts(p))
        self.assertEqual(r["status"],"CANDIDATE_READBACK_CONSISTENT")
        self.assertFalse(r["host_attested"]);self.assertFalse(r["a3_allowed"])

    def test_23_replay_does_not_dispatch_again(self):
        p=plan(*fixture());r=verify_readback(p,*make_receipts(p,replay=True))
        self.assertTrue(r["replay"]);self.assertFalse(r["a3_allowed"])

    def test_24_replay_forged_dispatch(self):
        p=plan(*fixture());r,c,s=make_receipts(p,replay=True);r["dispatch_permitted"]=True
        self.assertEqual(verify_readback(p,r,c,s)["blocking_codes"],["RESERVATION_REPLAY_DISPATCH_FORBIDDEN"])

    def test_25_request_sha_drift(self):self.failcase(0,"request_sha256",H2,"RESERVATION_RECEIPT_MISMATCH")
    def test_26_idem_drift(self):self.failcase(0,"idempotency_key","OTHER","RESERVATION_RECEIPT_MISMATCH")
    def test_27_wrong_child_profile(self):self.failcase(1,"created_by_execution_id","OTHER","RESERVATION_CHILD_IDENTITY_MISMATCH")
    def test_28_wrong_child_skill(self):self.failcase(1,"target_code","ACT-0057","RESERVATION_CHILD_IDENTITY_MISMATCH")
    def test_29_manifest_drift_business(self):
        p=plan(*fixture());r,c,s=make_receipts(p);c["manifest"]["business"]="SALY"
        self.assertEqual(verify_readback(p,r,c,s)["blocking_codes"],["RESERVATION_MANIFEST_DRIFT"])
    def test_30_manifest_drift_source(self):
        p=plan(*fixture());r,c,s=make_receipts(p);c["manifest"]["skill_source"]["commit_sha"]="f"*40
        self.assertEqual(verify_readback(p,r,c,s)["blocking_codes"],["RESERVATION_MANIFEST_DRIFT"])
    def test_policy_snapshots_legitimate_append_only(self):
        p=plan(*fixture());r,c,s=make_receipts(p)
        c["manifest"]["operation_policy_snapshots"]={"STATE_MODEL":{"policy_sha":"f"*64}}
        self.assertEqual(verify_readback(p,r,c,s)["status"],"CANDIDATE_READBACK_CONSISTENT")

    def test_unexpected_manifest_field_denied(self):
        p=plan(*fixture());r,c,s=make_receipts(p)
        c["manifest"]["override_business"]="SALY"
        self.assertEqual(verify_readback(p,r,c,s)["blocking_codes"],["RESERVATION_MANIFEST_UNEXPECTED_FIELDS"])

    def test_31_step0_missing(self):
        p=plan(*fixture());r,c,s=make_receipts(p)
        self.assertEqual(verify_readback(p,r,c,None)["blocking_codes"],["RESERVATION_READBACK_REQUIRED"])
    def test_32_step0_wrong_status(self):self.failcase(2,"status","BLOCKED_STEP_NOT_CLEAN","RESERVATION_STEP0_NOT_CLEAN")
    def test_33_step0_wrong_judge(self):
        p=plan(*fixture());r,c,s=make_receipts(p);s["evidence_payload"]["mini_judge_code"]="JUDGE-OTHER"
        self.assertEqual(verify_readback(p,r,c,s)["blocking_codes"],["RESERVATION_STEP0_RECEIPT_INVALID"])
    def test_34_null_plan(self):
        self.assertEqual(verify_readback({"status":"BLOCKED"},None,None,None)["blocking_codes"],["RESERVATION_PLAN_NOT_ELIGIBLE"])
    def test_35_closed_child_cannot_pretend_in_progress(self):self.failcase(1,"status","COMPLETED","RESERVATION_CHILD_IDENTITY_MISMATCH")
    def test_36_false_new_dispatch(self):
        p=plan(*fixture());r,c,s=make_receipts(p);r["dispatch_permitted"]=False
        self.assertEqual(verify_readback(p,r,c,s)["blocking_codes"],["RESERVATION_REPLAY_DISPATCH_FORBIDDEN"])
    def test_37_no_reuse_from_different_source_even_with_same_key(self):
        pa=plan(*fixture()); r,c,s=make_receipts(pa,replay=True)
        other=fixture();other[5]["commit_sha"]="e"*40;pb=plan(*other)
        self.assertEqual(pa["reservation_args"]["p_idempotency_key"],pb["reservation_args"]["p_idempotency_key"])
        self.assertEqual(verify_readback(pb,r,c,s)["blocking_codes"],["RESERVATION_MANIFEST_DRIFT"])

    def failcase(self, index, field, value, expected):
        p=plan(*fixture());rows=list(make_receipts(p));rows[index][field]=value
        self.assertEqual(verify_readback(p,*rows)["blocking_codes"],[expected])

if __name__ == '__main__':unittest.main()
