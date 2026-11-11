"""PG-06 C1-C5 positive synthetic chain, negative gates and real PG-05 exit.

No execution/authority: toolchain versions, A7 and build/lint are caller-supplied.
"""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
for folder in (ROOT/"pg04_semantic_partition_candidate"/"tools",
               ROOT/"pg04_semantic_partition_candidate"/"tests",
               ROOT/"pg05_target_binding_candidate"/"tools",
               ROOT/"pg05_target_binding_candidate"/"tests",
               ROOT/"pg06_preflight_candidate"/"tools"):
    sys.path.insert(0,str(folder))

from test_pg05_chain_c1_c5_v1 import build_chain as build_pg05
from pg05_pg06_exit_candidate_v1 import assemble_pg05_pg06_candidate
from pg06_c1_currentness_reuse_candidate_v1 import prepare_pg06_c1,PG06CurrentnessBlocked
from pg06_c2_toolchain_environment_candidate_v1 import prepare_pg06_c2,ToolchainBlocked
from pg06_c3_reversibility_plan_candidate_v1 import prepare_pg06_c3,ReversibilityBlocked
from pg06_c4_baseline_capture_candidate_v1 import prepare_pg06_c4,BaselineBlocked
from pg06_c5_independent_assurance_request_v1 import prepare_pg06_assurance_request,PG06AssuranceBlocked

SHA="a"*64
BASE="a"*40

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def resign(obj,field="candidate_sha256"):
    obj[field]=digest({k:v for k,v in obj.items() if k!=field})

def pg05_exit():
    upstream=build_pg05()
    return assemble_pg05_pg06_candidate(
        pg04_exit=upstream["pg04_exit"],
        pg05_c1=upstream["c1"],pg05_c2=upstream["c2"],
        pg05_c3=upstream["c3"],pg05_c4=upstream["c4"],
        pg05_c5=upstream["c5"])

def pg01():
    return {
        "pg01_decision_ref":"fixture://pg01/currentness",
        "pg01_decision_sha256":SHA,"context_sha256":"b"*64,
        "snapshot_schema_digest_sha256":"c"*64,
        "authority_fingerprint_sha256":"d"*64,
        "source_snapshot_sha256":"e"*64,
        "decision":"CURRENT",
        "decision_source_capability":"CURRENTNESS_AUTHORITY"}

def toolchain(exit_obj):
    target=exit_obj["target_binding"]
    sol_ids=[s["solution_id"] for s in exit_obj["solutions"]]
    catalog={
        "schema_version":"PG06_TOOLCHAIN_CATALOG_SELECTION_CANDIDATE_V1",
        "catalog_ref":"fixture://catalog/one","catalog_sha256":SHA,
        "profile_ref":"fixture://stack/python",
        "target_repo":target["repo_full_name"],
        "target_base_head_sha":target["base_head_sha"],
        "requirements":[{
            "tool_id":"python","component":"backend",
            "version_exact":"3.12.8","source_ref":"fixture://catalog/tool/python",
            "applies_to_solution_ids":sol_ids}]}
    observed={
        "schema_version":"PG06_TOOLCHAIN_ENVIRONMENT_OBSERVATION_CANDIDATE_V1",
        "environment_ref":"fixture://environment/one",
        "observed_target_repo":target["repo_full_name"],
        "observed_base_head_sha":target["base_head_sha"],
        "observations":[{
            "tool_id":"python","reported_version":"3.12.8",
            "availability":"AVAILABLE","evidence_ref":"fixture://env/python"}]}
    return catalog,observed

def a7_and_plans(exit_obj):
    # Synthetic A7 is not authenticated, modified or inferred from Analysis.
    front={
        "front_id":"A7-ROLLBACK-01",
        "front_kind":"ROLLBACK_RECOVERY","status":"REQUIRED",
        "closure":"CLOSED","scope_refs":["fixture://scope/global"],
        "source_signal_refs":[],"authority_refs":[],
        "evidence_refs":["fixture://a7/rollback"],
        "currentness_refs":["fixture://a7/currentness"],
        "blockers":[],"reason":"synthetic rollback obligations"}
    a7={
        "schema_version":"MATERIAL_FRONT_COVERAGE_V1",
        "artifact_ref":"fixture://a7/artifact",
        "artifact_sha256":SHA,
        "all_material_fronts_accounted":True,
        "material_fronts":[front],
        "source_refs":["fixture://a7/source"],
        "currentness_refs":["fixture://a7/currentness"]}
    plans=[{
        "solution_id":sol["solution_id"],
        "scope_refs":["fixture://scope/global"],
        "front_plans":[{
            "front_id":"A7-ROLLBACK-01",
            "disposition":"PLAN_REQUIRED",
            "technical_steps_ref":"fixture://rollback/steps",
            "rollback_steps_ref":"fixture://rollback/reverse",
            "verification_ref":"fixture://rollback/verify",
            "cutover_or_recovery_strategy_ref":"fixture://rollback/strategy"}]}
        for sol in exit_obj["solutions"]]
    return a7,plans

def baseline(exit_obj):
    target=exit_obj["target_binding"]
    rows=[]
    for sol in exit_obj["solutions"]:
        for kind in ("BUILD","LINT"):
            sid=sol["solution_id"]
            rows.append({
                "command_id":sid+"-"+kind,
                "solution_id":sid,"kind":kind,
                "command_ref":"fixture://cmd/"+kind.lower(),
                "command_sha256":SHA,
                "result":"PASS","exit_code":0,
                "stdout_sha256":"b"*64,
                "stderr_sha256":"c"*64,
                "violation_refs":[],
                "execution_receipt_ref":"fixture://receipt/"+sid+"/"+kind})
    return {
        "schema_version":"PG06_UNCHANGED_TARGET_BASELINE_OBSERVATION_CANDIDATE_V1",
        "target_repo":target["repo_full_name"],
        "base_head_sha":target["base_head_sha"],
        "observation_ref":"fixture://baseline/one",
        "execution_environment_ref":"fixture://baseline/environment",
        "unchanged_target_claim":True,
        "command_results":rows}

def make_chain():
    exit_obj=pg05_exit()
    currentness=pg01()
    c1=prepare_pg06_c1(pg05_exit=exit_obj,pg01_currentness_binding=currentness)
    catalog,env=toolchain(exit_obj)
    c2=prepare_pg06_c2(pg05_exit=exit_obj,pg06_c1=c1,
                       toolchain_catalog=catalog,environment_observations=env)
    a7,plans=a7_and_plans(exit_obj)
    c3=prepare_pg06_c3(pg05_exit=exit_obj,pg06_c1=c1,pg06_c2=c2,
                       a7_material_front_coverage=a7,solution_reversibility_plans=plans)
    observed=baseline(exit_obj)
    c4=prepare_pg06_c4(pg05_exit=exit_obj,pg06_c1=c1,pg06_c2=c2,
                       pg06_c3=c3,baseline_observations=observed)
    parts=dict(pg05_exit=exit_obj,pg06_c1=c1,pg06_c2=c2,pg06_c3=c3,pg06_c4=c4)
    manifest={
        "source_head_sha":BASE,
        **{name:{"ref":"fixture://source/"+name,"sha256":obj["candidate_sha256"]}
           for name,obj in parts.items()}}
    c5=prepare_pg06_assurance_request(
        **parts,source_manifest=manifest,
        producer_execution_id="fixture://producer/pg06")
    return dict(exit=exit_obj,c1=c1,c2=c2,c3=c3,c4=c4,c5=c5,
                currentness=currentness,catalog=catalog,env=env,
                a7=a7,plans=plans,baseline=observed,manifest=manifest)

class PG06Tests(unittest.TestCase):
    def test_chain_positive_exact_upstream_hashes_and_zero_authority(self):
        x=make_chain()
        self.assertEqual(x["exit"]["schema_version"],"PG05_TO_PG06_EXIT_CANDIDATE_V1")
        self.assertEqual(x["c1"]["source_pg05_exit_sha256"],x["exit"]["candidate_sha256"])
        self.assertEqual(x["c2"]["source_pg06_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg06_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["c4"]["source_pg06_c3_sha256"],x["c3"]["candidate_sha256"])
        self.assertEqual(x["c5"]["subject"]["upstream_digests"]["pg06_c4"],x["c4"]["candidate_sha256"])
        self.assertEqual(x["c4"]["solutions"][0]["diagnostic_status"],"REPORTED_BASELINE_PASS_UNVERIFIED")
        self.assertEqual(x["c2"]["blocking_tool_ids"],[])
        self.assertEqual(x["c3"]["blocked_front_ids"],[])
        self.assertFalse(x["c4"]["build_lint_executed_by_this_component"])
        self.assertFalse(x["c5"]["independent_review_executed"])
        for key in ("exit","c1","c2","c3","c4","c5"):
            self.assertIs(x[key]["production_authority"],False)
            self.assertIs(x[key]["handoff_allowed"],False)

    def test_c1_mid_execution_rebind_rejected(self):
        x=make_chain()
        with self.assertRaises(PG06CurrentnessBlocked):
            prepare_pg06_c1(pg05_exit=x["exit"],pg01_currentness_binding=x["currentness"],
                            execution_started=True)

    def test_c1_authority_forged_with_rehash_rejected(self):
        x=make_chain();fake=copy.deepcopy(x["exit"])
        fake["production_authority"]=True;resign(fake)
        with self.assertRaises(PG06CurrentnessBlocked):
            prepare_pg06_c1(pg05_exit=fake,pg01_currentness_binding=x["currentness"])

    def test_c1_stale_decision_blocks_without_fresh_approval(self):
        x=make_chain();binding=copy.deepcopy(x["currentness"]);binding["decision"]="STALE_AFFECTED"
        r=prepare_pg06_c1(pg05_exit=x["exit"],pg01_currentness_binding=binding)
        self.assertEqual(r["status"],"BLOCKED")
        self.assertFalse(r["execution_allowed"])

    def test_c2_version_mismatch_blocks_toolchain(self):
        x=make_chain();obs=copy.deepcopy(x["env"])
        obs["observations"][0]["reported_version"]="3.11.0"
        r=prepare_pg06_c2(pg05_exit=x["exit"],pg06_c1=x["c1"],
                          toolchain_catalog=x["catalog"],environment_observations=obs)
        self.assertEqual(r["status"],"BLOCKED_TOOL_UNAVAILABLE")
        self.assertFalse(r["pg06_ready"])

    def test_c2_injected_authority_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["c1"])
        fake["production_authority"]=True;resign(fake)
        with self.assertRaises(ToolchainBlocked):
            prepare_pg06_c2(pg05_exit=x["exit"],pg06_c1=fake,
                            toolchain_catalog=x["catalog"],environment_observations=x["env"])

    def test_c3_missing_a7_front_is_not_not_applicable(self):
        x=make_chain();a7=copy.deepcopy(x["a7"]);a7["material_fronts"]=[]
        with self.assertRaises(ReversibilityBlocked):
            prepare_pg06_c3(pg05_exit=x["exit"],pg06_c1=x["c1"],pg06_c2=x["c2"],
                            a7_material_front_coverage=a7,solution_reversibility_plans=x["plans"])

    def test_c3_authority_injected_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["c2"])
        fake["production_authority"]=True;resign(fake)
        with self.assertRaises(ReversibilityBlocked):
            prepare_pg06_c3(pg05_exit=x["exit"],pg06_c1=x["c1"],pg06_c2=fake,
                            a7_material_front_coverage=x["a7"],solution_reversibility_plans=x["plans"])

    def test_c4_valid_observation_preserves_no_execution(self):
        x=make_chain()
        self.assertEqual(len(x["c4"]["command_reports"]),2*len(x["exit"]["solutions"]))
        self.assertFalse(x["c4"]["unchanged_target_verified"])
        self.assertFalse(x["c4"]["receipts_authenticated"])
        self.assertFalse(x["c4"]["write_allowed"])
        self.assertFalse(x["c4"]["pg06_ready"])

    def test_c4_pass_report_with_nonzero_exit_rejected(self):
        x=make_chain();obs=copy.deepcopy(x["baseline"])
        obs["command_results"][0]["exit_code"]=1
        with self.assertRaises(BaselineBlocked):
            prepare_pg06_c4(pg05_exit=x["exit"],pg06_c1=x["c1"],pg06_c2=x["c2"],
                            pg06_c3=x["c3"],baseline_observations=obs)

    def test_c4_missing_lint_coverage_rejected(self):
        x=make_chain();obs=copy.deepcopy(x["baseline"])
        obs["command_results"]=[v for v in obs["command_results"] if v["kind"]!="LINT"]
        with self.assertRaises(BaselineBlocked):
            prepare_pg06_c4(pg05_exit=x["exit"],pg06_c1=x["c1"],pg06_c2=x["c2"],
                            pg06_c3=x["c3"],baseline_observations=obs)

    def test_c4_authority_injected_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["c3"])
        fake["production_authority"]=True;resign(fake)
        with self.assertRaises(BaselineBlocked):
            prepare_pg06_c4(pg05_exit=x["exit"],pg06_c1=x["c1"],pg06_c2=x["c2"],
                            pg06_c3=fake,baseline_observations=x["baseline"])

    def test_c5_fake_manifest_digest_rejected(self):
        x=make_chain();manifest=copy.deepcopy(x["manifest"])
        manifest["pg06_c4"]["sha256"]="f"*64
        with self.assertRaises(PG06AssuranceBlocked):
            prepare_pg06_assurance_request(pg05_exit=x["exit"],pg06_c1=x["c1"],
                pg06_c2=x["c2"],pg06_c3=x["c3"],pg06_c4=x["c4"],
                source_manifest=manifest,producer_execution_id="fixture://producer/pg06")

    def test_c5_authority_injected_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["c4"])
        fake["production_authority"]=True;resign(fake)
        with self.assertRaises(PG06AssuranceBlocked):
            prepare_pg06_assurance_request(pg05_exit=x["exit"],pg06_c1=x["c1"],
                pg06_c2=x["c2"],pg06_c3=x["c3"],pg06_c4=fake,
                source_manifest=x["manifest"],producer_execution_id="fixture://producer/pg06")

    def test_c5_fake_review_receipt_cannot_be_injected(self):
        x=make_chain();self.assertIsNone(x["c5"]["subject_receipt_id"])
        self.assertFalse(x["c5"]["pg07_dispatch_allowed"])
        self.assertFalse(x["c5"]["review_execution_allowed"])

if __name__=="__main__":
    unittest.main()
