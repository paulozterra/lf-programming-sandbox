"""Contract checks only. NO operational credential access, model invocation, or DB write."""
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "adapters/governed_step_homology_v1.json").read_text(encoding="utf-8"))
CONSUMER = json.loads((ROOT / "adapters/consumer_binding_v1.json").read_text(encoding="utf-8"))
OPERATION = json.loads((ROOT / "adapters/existing_skill_operation_binding_v1.json").read_text(encoding="utf-8"))

def check(candidate):
    problems = []
    if candidate.get("status") != "CANDIDATE_SOURCE_ONLY_NOT_WIRED":
        problems.append("FALSE_OPERATIONAL_CLAIM")
    if candidate.get("authority_principle") != "AUTHORIZED_EXECUTOR_WRITES; READ_ONLY_CONSUMER_OBSERVES":
        problems.append("AUTHORITY_BOUNDARY_CHANGED")
    identities = candidate["identity_separation"]
    if any(not identities[k]["must_not_mutate"] for k in (
        "historical_analysis_unit", "historical_qualification_unit"
    )):
        problems.append("HISTORICAL_DONE_REPLAY")
    asset = identities["new_skill"]
    if (asset["runtime_activation_allowed"] or asset.get("runtime_binding_enabled") is not False
            or asset.get("approval_status") != "NOT_APPROVED"):
        problems.append("FALSE_SKILL_RELEASE")
    registered = candidate["source_basis"].get("registration_readback", {})
    if (asset.get("observed_asset_count") != 1 or asset.get("registered_asset_id") != 414
            or registered.get("asset_count") != 1 or registered.get("asset_id") != 414
            or registered.get("runtime_binding_enabled") is not False):
        problems.append("ASSET_REGISTRATION_READBACK_DRIFT")
    if (registered.get("main_blob_parity_verified") is not True
            or registered.get("registered_main_skill_blob_sha1")
                 != registered.get("github_main_skill_blob_sha1")
            or not registered.get("registered_main_skill_blob_sha1")):
        problems.append("MAIN_SOURCE_PARITY_DRIFT")
    required_names = {x["name"]:x for x in candidate["observed_paths"]}
    if len(required_names) != len(candidate["observed_paths"]) or set(required_names) != {
        "INPUT_GOVERNANCE", "PROFILE_UPDATER", "PROFILE_CREATOR", "SKILL_CREATOR", "ANALYSIS_SKILL_EXECUTION"
    }:
        problems.append("EXISTING_OPERATIONS_NOT_MATCHED")
    if required_names["ANALYSIS_SKILL_EXECUTION"]["step_writer"] is not None:
        problems.append("UNVERIFIED_SKILL_RECORDER")
    if any(required_names[k]["can_reuse_for_A1"] for k in (
        "INPUT_GOVERNANCE", "PROFILE_UPDATER", "PROFILE_CREATOR", "SKILL_CREATOR"
    )):
        problems.append("CROSS_OPERATION_RECORDER_BYPASS")
    if required_names["ANALYSIS_SKILL_EXECUTION"]["core_available"] != "public.lf_record_operation_step_core_v1":
        problems.append("WRONG_CORE")
    permission = candidate["permission_path"]
    if any(permission[k] for k in (
        "existing_profile_workflow_is_skill_authorized",
        "existing_ig_queue_is_skill_authorized",
        "router_may_hold_service_role", "access_grants_to_readonly_allowed",
        "direct_rpc_from_readonly_allowed", "new_parallel_runtime_allowed"
    )):
        problems.append("UNAUTHORIZED_TRANSPORT")
    if not all(candidate["common_step_request"]["required"]):
        problems.append("INCOMPLETE_STEP_PACKET")
    if candidate["common_step_result"]["success_claim_allowed_before_readback"]:
        problems.append("SELF_ATTESTED_PERSISTENCE")
    if candidate["asset_registration_out_of_scope"]["this_document_is_not_asset_registration"] is not True:
        problems.append("FALSE_ASSET_REGISTRATION")
    return problems

class GovernedStepHomologyTests(unittest.TestCase):
    def test_01_current_contract_has_no_bypass(self):
        self.assertEqual(check(CONTRACT), [])

    def test_02_readonly_cannot_become_writer(self):
        tampered = copy.deepcopy(CONTRACT)
        tampered["permission_path"]["direct_rpc_from_readonly_allowed"] = True
        self.assertIn("UNAUTHORIZED_TRANSPORT", check(tampered))

    def test_03_no_grant_upgrade(self):
        tampered = copy.deepcopy(CONTRACT)
        tampered["permission_path"]["access_grants_to_readonly_allowed"] = True
        self.assertIn("UNAUTHORIZED_TRANSPORT", check(tampered))

    def test_04_existing_profile_workflow_not_assumed_to_authorize_skill(self):
        tampered = copy.deepcopy(CONTRACT)
        tampered["permission_path"]["existing_profile_workflow_is_skill_authorized"] = True
        self.assertIn("UNAUTHORIZED_TRANSPORT", check(tampered))

    def test_05_ig_does_not_own_skill_writes(self):
        tampered = copy.deepcopy(CONTRACT)
        next(r for r in tampered["observed_paths"] if r["name"]=="INPUT_GOVERNANCE")["can_reuse_for_A1"] = True
        self.assertIn("CROSS_OPERATION_RECORDER_BYPASS", check(tampered))

    def test_06_skill_creation_is_not_execution(self):
        tampered = copy.deepcopy(CONTRACT)
        next(r for r in tampered["observed_paths"] if r["name"]=="SKILL_CREATOR")["can_reuse_for_A1"] = True
        self.assertIn("CROSS_OPERATION_RECORDER_BYPASS", check(tampered))

    def test_07_no_fabricated_skill_recorder(self):
        tampered = copy.deepcopy(CONTRACT)
        next(r for r in tampered["observed_paths"] if r["name"]=="ANALYSIS_SKILL_EXECUTION")["step_writer"]="lf_fake_record_step"
        self.assertIn("UNVERIFIED_SKILL_RECORDER",check(tampered))

    def test_08_old_A1_done_cannot_be_rewritten(self):
        tampered = copy.deepcopy(CONTRACT)
        tampered["identity_separation"]["historical_analysis_unit"]["must_not_mutate"] = False
        self.assertIn("HISTORICAL_DONE_REPLAY",check(tampered))

    def test_09_no_runtime_activation(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["identity_separation"]["new_skill"]["runtime_activation_allowed"] = True
        self.assertIn("FALSE_SKILL_RELEASE",check(tampered))

    def test_09b_registered_does_not_mean_released(self):
        self.assertEqual(CONTRACT["identity_separation"]["new_skill"]["observed_asset_count"], 1)
        self.assertEqual(CONTRACT["identity_separation"]["new_skill"]["registered_asset_id"], 414)
        self.assertFalse(CONTRACT["identity_separation"]["new_skill"]["runtime_binding_enabled"])
        self.assertFalse(OPERATION["asset_readback"]["runtime_binding_enabled"])
        self.assertFalse(OPERATION["release_approved"])

    def test_09c_old_zero_count_is_stale_not_a_pass(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["identity_separation"]["new_skill"]["observed_asset_count"] = 0
        self.assertIn("ASSET_REGISTRATION_READBACK_DRIFT",check(tampered))

    def test_09d_duplicate_asset_count_detected(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["source_basis"]["registration_readback"]["asset_count"] = 2
        self.assertIn("ASSET_REGISTRATION_READBACK_DRIFT",check(tampered))

    def test_09e_runtime_binding_true_is_not_authority(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["identity_separation"]["new_skill"]["runtime_binding_enabled"] = True
        self.assertIn("FALSE_SKILL_RELEASE",check(tampered))

    def test_09f_main_source_blob_drift_detected(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["source_basis"]["registration_readback"]["registered_main_skill_blob_sha1"] = "0"*40
        self.assertIn("MAIN_SOURCE_PARITY_DRIFT",check(tampered))

    def test_09g_registered_asset_identity_drift_detected(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["identity_separation"]["new_skill"]["registered_asset_id"] = 999
        self.assertIn("ASSET_REGISTRATION_READBACK_DRIFT",check(tampered))

    def test_10_no_completed_claim_without_readback(self):
        tampered=copy.deepcopy(CONTRACT)
        tampered["common_step_result"]["success_claim_allowed_before_readback"]=True
        self.assertIn("SELF_ATTESTED_PERSISTENCE",check(tampered))

    def test_11_consumer_points_to_one_contract(self):
        self.assertEqual(CONSUMER["step_homologation_contract"],"adapters/governed_step_homology_v1.json")
        self.assertEqual(OPERATION["step_homologation_contract"],CONSUMER["step_homologation_contract"])
        self.assertFalse(CONSUMER["step_recording_from_read_only_connector"])

    def test_12_step_sequence_matches_existing_operation(self):
        self.assertEqual(CONTRACT["A1_canonical_step_ids"],
                         [x["canonical_step"] for x in OPERATION["step_binding"]])
        self.assertEqual(len(CONTRACT["A1_canonical_step_ids"]),9)

    def test_13_transport_is_not_integrated(self):
        self.assertFalse(OPERATION["independent_execution_verified"])
        self.assertEqual(CONSUMER["existing_skill_execution_recorder"],"NOT_FOUND_IN_LIVE_PUBLIC_PG_PROC")
        self.assertEqual(CONTRACT["status"],"CANDIDATE_SOURCE_ONLY_NOT_WIRED")

    def test_14_profile_skill_invoker_not_a1_execution_recorder(self):
        existing = CONTRACT["existing_profile_skill_invoker"]
        self.assertEqual(existing["function"], "public.lf_skill_invoke_v1(text,text,jsonb)")
        self.assertEqual(existing["profile_parent_operation"], "EJECUCION_PERFIL_LF")
        self.assertFalse(existing["A1_catalog_entry_found"])
        self.assertFalse(existing["approved_as_A1_EJECUCION_SKILL_LF_registrar"])

if __name__=="__main__":
    unittest.main()
