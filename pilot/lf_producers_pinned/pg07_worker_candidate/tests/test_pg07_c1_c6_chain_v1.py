"""PG07 source-only chain using actual PG06 C5 output; no Worker invocation."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
             "pg06_preflight_candidate","pg07_worker_candidate"):
    for sub in ("tests","tools"):
        folder=ROOT/name/sub
        if folder.is_dir():sys.path.insert(0,str(folder))

from test_pg06_c1_c5_chain_v1 import make_chain as pg06_chain
from pg07_c1_worker_dispatch_plan_v1 import prepare_pg07_c1, PG07WorkerPlanBlocked
from pg07_c2_task_batch_projection_v1 import prepare_pg07_c2, TaskProjectionBlocked
from pg07_c3_context_budget_projection_v1 import prepare_pg07_c3, ContextProjectionBlocked
from pg07_c4_contract_first_standards_candidate_v1 import prepare_pg07_c4, StandardsPlanBlocked
from pg07_c5_iteration_guard_candidate_v1 import prepare_pg07_c5, IterationGuardBlocked
from pg07_c6_worker_batch_evidence_candidate_v1 import prepare_pg07_c6, BatchEvidenceBlocked

SHA="a"*64
def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def resign(obj):
    obj["candidate_sha256"]=sha({k:v for k,v in obj.items() if k!="candidate_sha256"})

def make_c1():
    upstream=pg06_chain()
    exit_obj=upstream["exit"]
    sid=[s["solution_id"] for s in exit_obj["solutions"]]
    run={"run_ref":"fixture://run/07","provider":"fixture-model-provider","model_id":"fixture-model",
         "model_profile_ref":"fixture://profile/model","pricing_ref":"fixture://pricing/not-live",
         "pricing_currency":"USD","input_price_per_million":"0.1",
         "output_price_per_million":"0.2","cached_input_price_per_million":"0.01",
         "lane_executor_ref":"fixture://existing-lane-executor","worker_contract_ref":"fixture://worker-v08",
         "worker_version":"0.8"}
    tasks=[{"solution_id":s,"agent_task_id":i+1,"task_binding_ref":"fixture://task/"+s,
            "base_head_sha":exit_obj["target_binding"]["base_head_sha"],
            "source_snapshot_sha256":"b"*64,
            "worker_spec_ref":"fixture://spec/"+s,"task_execution_authority_ref":"fixture://authority/unverified"}
           for i,s in enumerate(sid)]
    c1=prepare_pg07_c1(pg05_exit=exit_obj,pg06_c5=upstream["c5"],
                       run_binding=run,worker_task_bindings=tasks)
    return upstream,run,tasks,c1

def worker_spec(task,base):
    return {"schema_version":2,"task_id":"T-"+str(task["agent_task_id"]),
        "objective":"Implement one scoped requirement","expected_change":"small patch",
        "human_story":"synthetic story","functional_contract":{"acceptance_criteria":["fixture acceptance"]},
        "scope":{"in_scope":["src"],"out_of_scope":["secrets"],"must_not_change":["policy"]},
        "cases":[],"dependency_resolution":{},"dependency_task_ids":[],"required_tests":["unit"],
        "required_evidence":["diff"],"blocked_if":["unauthorized"],
        "base_head_sha":base,"source_snapshot_sha256":task["source_snapshot_sha256"],
        "context_path_patterns":["src/**"],"write_path_patterns":["src/**"],
        "protected_path_patterns":[".github/**"],"files_expected":["src/file.py"],
        "platform_refs":[],"interface_refs":[],"acceptance_commands":["python -m unittest"],
        "max_attempts":2,"max_patch_bytes":10000,"max_changed_files":3,
        "max_context_bytes":100000,"allow_deletions":False}

def make_chain():
    upstream,run,tasks,c1=make_c1()
    base=upstream["exit"]["target_binding"]["base_head_sha"]
    specs=[{"solution_id":t["solution_id"],"function_result_ref":"fixture://worker/spec/result",
            "worker_spec":worker_spec(t,base),"source_snapshot_sha256":t["source_snapshot_sha256"]}
           for t in tasks]
    oracle=[{"solution_id":t["solution_id"],"verifier_only_ref":"fixture://verifier/"+t["solution_id"],
             "oracle_subject_sha256":"c"*64,"access_policy":"VERIFIER_ONLY"} for t in tasks]
    c2=prepare_pg07_c2(pg07_c1=c1,worker_spec_projections=specs,verifier_oracle_bindings=oracle)
    profile={"profile_ref":run["model_profile_ref"],"provider":run["provider"],"model_id":run["model_id"],
             "context_window_tokens":8192,"reserved_output_tokens":1000,
             "reserved_system_tokens":500,"safety_margin_tokens":500,
             "token_estimator_ref":"fixture://estimator","budget_policy_ref":"fixture://context-policy",
             "budget_capability":"CONTEXT_BUDGET_GOVERNANCE"}
    selections=[]
    for t in tasks:
        sid=t["solution_id"]
        selections.append({"solution_id":sid,"mandatory_ref_ids":["STD-API-06"],
            "reference_catalog":[{"ref_id":"STD-API-06","source_ref":"fixture://rule/STD-API-06",
                "source_sha256":"d"*64,"kind":"STD","material":True,"delivery":"EAGER",
                "estimated_tokens":100,"estimated_bytes":400,"role":"REQUIRED"}],
            "stable_cache_refs":[],"token_estimate_ref":"fixture://estimate/"+sid,
            "estimated_static_tokens":100,"estimated_dynamic_tokens":0,
            "estimated_jit_tokens":0,"estimated_context_bytes":400})
    c3=prepare_pg07_c3(pg07_c1=c1,pg07_c2=c2,
                       model_context_profile=profile,task_context_selections=selections)
    catalog={"catalog_ref":"fixture://c6/catalog","catalog_sha256":"e"*64,
             "catalog_version":"fixture-v1","selection_ref":"fixture://c6/selection",
             "entries":[{"rule_id":"STD-API-06","kind":"STD",
                "source_ref":"fixture://rule/STD-API-06","source_sha256":"d"*64,
                "version":"fixture-v1","ok_example_ref":"fixture://rule/ok",
                "no_example_ref":"fixture://rule/no",
                "applies_to_solution_ids":[t["solution_id"] for t in tasks]}]}
    plans=[{"solution_id":t["solution_id"],"required_rule_ids":["STD-API-06"],
            "contract_first_ref":"fixture://contract/first","contract_first_rule_id":"STD-API-06",
            "formatter_commands":[{"command_id":"fmt-"+t["solution_id"],
                "formatter_tool_ref":"fixture://formatter","command_ref":"fixture://formatter/cmd",
                "scope_ref":"fixture://formatter/scope","expected_artifact_ref":"fixture://formatter/result"}],
            "formatter_plan_ref":"fixture://formatter/plan"} for t in tasks]
    c4=prepare_pg07_c4(pg07_c1=c1,pg07_c2=c2,pg07_c3=c3,
                       standards_catalog_selection=catalog,solution_policy_plans=plans)
    c5=prepare_pg07_c5(pg07_c2=c2,pg07_c3=c3,pg07_c4=c4,iteration_proposals=[])
    evidence=[{"solution_id":t["solution_id"],"batch_id":"fixture-batch-"+t["solution_id"],
        "execution_ref":"fixture://execution/claimed","context_pack_ref":"fixture://context",
        "candidate_head_sha":"b"*40,"diff_ref":"fixture://diff","diff_sha256":"f"*64,
        "changed_paths":["src/"+t["solution_id"]+"/file.py"],"input_refs":["fixture://requirement"],
        "applied_rule_ids":["STD-API-06"],"formatter_receipt_refs":["fixture://formatter/claimed"],
        "worker_receipt_ref":"fixture://worker/claimed","worker_receipt_sha256":"9"*64,
        "provider_usage_receipt_refs":["fixture://usage/claimed"]} for t in tasks]
    c6=prepare_pg07_c6(pg07_c1=c1,pg07_c2=c2,pg07_c3=c3,pg07_c4=c4,
                       pg07_c5=c5,worker_batch_evidence=evidence)
    return locals()

class PG07ChainTests(unittest.TestCase):
    def test_positive_real_pg06_output_through_all_six(self):
        x=make_chain()
        self.assertEqual(x["c1"]["source_pg06_review_request_sha256"],x["upstream"]["c5"]["request_sha256"])
        self.assertEqual(x["c2"]["source_pg07_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg07_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["c4"]["source_pg07_c3_sha256"],x["c3"]["candidate_sha256"])
        self.assertEqual(x["c5"]["source_pg07_c4_sha256"],x["c4"]["candidate_sha256"])
        self.assertEqual(x["c6"]["upstream_source_digests"]["pg07_c5"],x["c5"]["candidate_sha256"])
        for name in ("c1","c2","c3","c4","c5","c6"):
            self.assertIs(x[name]["production_authority"],False)
            self.assertIs(x[name]["handoff_allowed"],False)
            self.assertIs(x[name]["worker_invoked"],False)
        self.assertIs(x["c6"]["receipt_sealed"],False)
        self.assertIs(x["c6"]["receipt_digest_authenticated"],False)
        self.assertIs(x["c1"]["usage_receipt_schema"]["usage_receipts_verified"],False)
        self.assertIs(x["c1"]["usage_receipt_schema"]["cost_calculated"],False)
        self.assertEqual(len(x["c6"]["batches"]),len(x["tasks"]))
    def test_c1_not_cost_executed_claim(self):
        upstream,run,tasks,c1=make_c1()
        fake=copy.deepcopy(run);fake["cost_calculated"]=True
        with self.assertRaises(PG07WorkerPlanBlocked):
            prepare_pg07_c1(pg05_exit=upstream["exit"],pg06_c5=upstream["c5"],
                            run_binding=fake,worker_task_bindings=tasks)
    def test_c1_worker_invoked_claim(self):
        upstream,run,tasks,c1=make_c1()
        forged=copy.deepcopy(upstream["c5"]);forged["worker_invoked"]=True
        forged["request_sha256"]=sha({k:v for k,v in forged.items() if k!="request_sha256"})
        with self.assertRaises(PG07WorkerPlanBlocked):
            prepare_pg07_c1(pg05_exit=upstream["exit"],pg06_c5=forged,
                            run_binding=run,worker_task_bindings=tasks)
    def test_c1_injected_authority(self):
        upstream,run,tasks,c1=make_c1()
        forged=copy.deepcopy(upstream["c5"]);forged["production_authority"]=True
        forged["request_sha256"]=sha({k:v for k,v in forged.items() if k!="request_sha256"})
        with self.assertRaises(PG07WorkerPlanBlocked):
            prepare_pg07_c1(pg05_exit=upstream["exit"],pg06_c5=forged,
                            run_binding=run,worker_task_bindings=tasks)
    def test_c2_hidden_oracle_in_worker_payload(self):
        x=make_chain();bad=copy.deepcopy(x["specs"])
        bad[0]["worker_spec"]["hidden_oracle_ref"]="leak"
        with self.assertRaises(TaskProjectionBlocked):
            prepare_pg07_c2(pg07_c1=x["c1"],worker_spec_projections=bad,
                            verifier_oracle_bindings=x["oracle"])
    def test_c2_injected_authority(self):
        x=make_chain();bad=copy.deepcopy(x["c1"]);bad["production_authority"]=True;resign(bad)
        with self.assertRaises(TaskProjectionBlocked):
            prepare_pg07_c2(pg07_c1=bad,worker_spec_projections=x["specs"],
                            verifier_oracle_bindings=x["oracle"])
    def test_c3_budget_overflow_fails_closed(self):
        x=make_chain();profile=copy.deepcopy(x["profile"]);profile["context_window_tokens"]=2099
        r=prepare_pg07_c3(pg07_c1=x["c1"],pg07_c2=x["c2"],model_context_profile=profile,
                          task_context_selections=x["selections"])
        self.assertTrue(all(s["diagnostic_status"]=="BLOCK_CONTEXT_BUDGET" for s in r["solutions"]))
        self.assertFalse(r["material_truncation_allowed"])
    def test_c3_injected_authority(self):
        x=make_chain();bad=copy.deepcopy(x["c2"]);bad["production_authority"]=True;resign(bad)
        with self.assertRaises(ContextProjectionBlocked):
            prepare_pg07_c3(pg07_c1=x["c1"],pg07_c2=bad,
                            model_context_profile=x["profile"],task_context_selections=x["selections"])
    def test_c4_missing_material_rule(self):
        x=make_chain();bad=copy.deepcopy(x["plans"]);bad[0]["required_rule_ids"]=[]
        with self.assertRaises(StandardsPlanBlocked):
            prepare_pg07_c4(pg07_c1=x["c1"],pg07_c2=x["c2"],pg07_c3=x["c3"],
                standards_catalog_selection=x["catalog"],solution_policy_plans=bad)
    def test_c4_injected_authority(self):
        x=make_chain();bad=copy.deepcopy(x["c3"]);bad["production_authority"]=True;resign(bad)
        with self.assertRaises(StandardsPlanBlocked):
            prepare_pg07_c4(pg07_c1=x["c1"],pg07_c2=x["c2"],pg07_c3=bad,
                standards_catalog_selection=x["catalog"],solution_policy_plans=x["plans"])
    def test_c5_undeclared_iteration_change(self):
        x=make_chain();spec=x["specs"][0]["worker_spec"]
        canonical={"objective":sha(spec["objective"]),
            "acceptance":sha(spec["functional_contract"].get("acceptance_criteria")),
            "write_scope":sha({"scope":spec["scope"],"write_path_patterns":spec["write_path_patterns"],
                "protected_path_patterns":spec["protected_path_patterns"],
                "allow_deletions":spec["allow_deletions"]})}
        proposed=copy.deepcopy(canonical);proposed["objective"]="b"*64
        row={"iteration_id":"iter-1","solution_id":x["tasks"][0]["solution_id"],
            "previous_iteration_ref":None,"objective_ref":"fixture://objective",
            "change_reason":"fixture drift","proposed_diff_ref":"fixture://diff",
            "proposed_diff_sha256":"c"*64,"baseline_bindings":canonical,
            "proposed_bindings":proposed,"declared_changed_fields":[],
            "evidence_refs":["fixture://evidence"]}
        with self.assertRaises(IterationGuardBlocked):
            prepare_pg07_c5(pg07_c2=x["c2"],pg07_c3=x["c3"],pg07_c4=x["c4"],
                             iteration_proposals=[row])
    def test_c5_injected_authority(self):
        x=make_chain();bad=copy.deepcopy(x["c4"]);bad["production_authority"]=True;resign(bad)
        with self.assertRaises(IterationGuardBlocked):
            prepare_pg07_c5(pg07_c2=x["c2"],pg07_c3=x["c3"],pg07_c4=bad,
                             iteration_proposals=[])
    def test_c6_worker_execution_claim_is_not_receipt(self):
        x=make_chain();bad=copy.deepcopy(x["evidence"])
        bad[0]["worker_invoked"]=True
        with self.assertRaises(BatchEvidenceBlocked):
            prepare_pg07_c6(pg07_c1=x["c1"],pg07_c2=x["c2"],pg07_c3=x["c3"],
                             pg07_c4=x["c4"],pg07_c5=x["c5"],worker_batch_evidence=bad)
    def test_c6_cost_execution_claim_is_not_receipt(self):
        x=make_chain();bad=copy.deepcopy(x["evidence"])
        bad[0]["cost_calculated"]=True
        with self.assertRaises(BatchEvidenceBlocked):
            prepare_pg07_c6(pg07_c1=x["c1"],pg07_c2=x["c2"],pg07_c3=x["c3"],
                             pg07_c4=x["c4"],pg07_c5=x["c5"],worker_batch_evidence=bad)
    def test_c6_injected_authority(self):
        x=make_chain();bad=copy.deepcopy(x["c5"]);bad["production_authority"]=True;resign(bad)
        with self.assertRaises(BatchEvidenceBlocked):
            prepare_pg07_c6(pg07_c1=x["c1"],pg07_c2=x["c2"],pg07_c3=x["c3"],
                             pg07_c4=x["c4"],pg07_c5=bad,worker_batch_evidence=x["evidence"])

if __name__=="__main__":unittest.main()
