"""PG-09 source-only tests. C1-C4 use real upstream PG07 producers.

C5 matrix is separately exercised with synthetic, correctly digested one-solution
scenario envelopes (does not claim nine runtime executions).
"""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
             "pg06_preflight_candidate","pg07_worker_candidate",
             "pg08_build_candidate","pg09_iteration_candidate"):
    for sub in ("tests","tools"):
        folder=ROOT/name/sub
        if folder.is_dir():sys.path.insert(0,str(folder))

from test_pg08_full_chain_v1 import make_chain as pg08_chain
from pg07_c5_iteration_guard_candidate_v1 import prepare_pg07_c5
from pg09_c1_iteration_cost_governor_candidate_v1 import prepare_pg09_c1,PG09C1Blocked
from pg09_c2_convergence_guard_candidate_v1 import prepare_pg09_c2,PG09C2Blocked
from pg09_c3_quality_bypass_guard_candidate_v1 import prepare_pg09_c3,PG09C3Blocked
from pg09_c4_typed_escalation_candidate_v1 import prepare_pg09_c4,PG09C4Blocked
from pg09_c5_adversarial_assurance_candidate_v1 import prepare_pg09_c5,PG09C5Blocked,EXPECTED

def sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def resign(obj):
    obj["candidate_sha256"]=sha({k:v for k,v in obj.items() if k!="candidate_sha256"})
def policy():
    return {"policy_ref":"fixture://budget/policy","currency":"USD",
            "request_budget":"100.00","batch_budget":"100.00",
            "max_attempts_per_solution":3,
            "existing_worker_limit_ref":"fixture://existing-worker-v08/attempt-limit"}
def cost_observations(x,cost="79.99",mode="WORKER_API",attempts=1):
    rows=[]
    for i,sol in enumerate(x["tasks"]):
        sid=sol["solution_id"]
        rows.append({"solution_id":sid,"executor_mode":mode,"batch_id":"batch-1",
            "attempts_used":attempts,"attempt_limit_source_ref":"fixture://worker/attempts",
            "calls":[{"call_ref":"call-"+sid,"usage_receipt_ref":"fixture://usage/"+sid,
                "usage_authentication_ref":None,
                "provider":"fixture-model-provider","model_id":"fixture-model",
                "reported_cost":cost if i==0 else "0",
                "currency":"USD","input_tokens":50,"output_tokens":10,
                "cached_input_tokens":0}]})
    return rows
def snapshots(source):
    return [{"solution_id":r["solution_id"],"iterations":[]} for r in source["solutions"]]
def context(c1):
    return [{"solution_id":r["solution_id"],"run_ref":c1["run_ref"],
             "owner_decision_ref":"fixture://owner/decision",
             "diagnostic_evidence_refs":["fixture://diag/"+r["solution_id"]]}
            for r in c1["solutions"]]

def make_chain(cost="79.99"):
    pg08=pg08_chain()
    pg07=pg08["upstream"]
    c1=prepare_pg09_c1(pg07_c1=pg07["c1"],pg07_c5=pg07["c5"],
                       budget_policy=policy(),usage_observations=cost_observations(pg07,cost))
    c2=prepare_pg09_c2(pg07_c5=pg07["c5"],pg09_c1=c1,
        iteration_observations=snapshots(pg07["c5"]))
    observations=snapshots(pg07["c5"])
    c3=prepare_pg09_c3(pg07_c5=pg07["c5"],pg09_c2=c2,
                       quality_change_observations=observations)
    c4=prepare_pg09_c4(pg09_c1=c1,pg09_c2=c2,pg09_c3=c3,
                       escalation_context=context(c1))
    return locals()

def with_iteration(kind="NORMAL_CHANGE"):
    """Real PG07 C5 producer with one no-scope-change iteration, not a forged C5."""
    pg08=pg08_chain();pg07=pg08["upstream"]
    sid=pg07["tasks"][0]["solution_id"]
    spec=pg07["specs"][0]["worker_spec"]
    baseline={
        "objective":sha(spec["objective"]),
        "acceptance":sha(spec["functional_contract"].get("acceptance_criteria")),
        "write_scope":sha({"scope":spec["scope"],
            "write_path_patterns":spec["write_path_patterns"],
            "protected_path_patterns":spec["protected_path_patterns"],
            "allow_deletions":spec["allow_deletions"]})}
    proposal={"iteration_id":"iter-1","solution_id":sid,"previous_iteration_ref":None,
        "objective_ref":"fixture://objective","change_reason":"improve quality",
        "proposed_diff_ref":"fixture://diff/iter1","proposed_diff_sha256":"a"*64,
        "baseline_bindings":baseline,"proposed_bindings":copy.deepcopy(baseline),
        "declared_changed_fields":[],"evidence_refs":["fixture://evidence/iteration"]}
    pg07c5=prepare_pg07_c5(pg07_c2=pg07["c2"],pg07_c3=pg07["c3"],
                           pg07_c4=pg07["c4"],iteration_proposals=[proposal])
    c1=prepare_pg09_c1(pg07_c1=pg07["c1"],pg07_c5=pg07c5,
                       budget_policy=policy(),usage_observations=cost_observations(pg07,"1"))
    snaps=snapshots(pg07c5)
    item={"iteration_id":"iter-1","previous_iteration_ref":None,
          "before_finding_refs":["finding-1"],"after_finding_refs":[],
          "before_evidence_refs":["evidence-1"],"after_evidence_refs":["evidence-1","evidence-2"],
          "comparison_receipt_ref":"fixture://comparison","comparison_tool_ref":"fixture://tool"}
    next(r for r in snaps if r["solution_id"]==sid)["iterations"]=[item]
    c2=prepare_pg09_c2(pg07_c5=pg07c5,pg09_c1=c1,iteration_observations=snaps)
    change={"change_id":"chg-1","classification":kind,
            "path":"tests/test_feature.py" if kind=="TEST_DELETE" else "rules/lint.yml",
            "evidence_ref":"fixture://change","before_sha256":"b"*64,
            "after_sha256":None if kind=="TEST_DELETE" else "c"*64,
            "waiver_ref":None,"waiver_decision_ref":None}
    changes=snapshots(pg07c5)
    next(r for r in changes if r["solution_id"]==sid)["iterations"]=[{
        "iteration_id":"iter-1","diff_ref":proposal["proposed_diff_ref"],
        "diff_sha256":proposal["proposed_diff_sha256"],"changes":[change]}]
    c3=prepare_pg09_c3(pg07_c5=pg07c5,pg09_c2=c2,quality_change_observations=changes)
    c4=prepare_pg09_c4(pg09_c1=c1,pg09_c2=c2,pg09_c3=c3,escalation_context=context(c1))
    return locals()

def matrix():
    """Separately synthetic C5 intake fixtures; no claims of executed adversarial runs."""
    x=make_chain("1")
    result=[]
    for case,(typ,reason) in EXPECTED.items():
        c1=copy.deepcopy(x["c1"])
        c4=copy.deepcopy(x["c4"])
        c1["solutions"]=c1["solutions"][:1]
        c4["solutions"]=c4["solutions"][:1]
        c4["solutions"][0]["escalation_type"]=typ
        c4["solutions"][0]["reason_codes"]=[reason]
        if case=="BUDGET_80_WARNING":
            c1["request_diagnostic"]="WARN_80_PERCENT"
            c1["eighty_percent_warning_reported"]=True
            c1["requires_decision_reported"]=False
        elif case=="BUDGET_100_EXHAUSTED":
            c1["request_diagnostic"]="REQUIRES_DECISION"
            c1["requires_decision_reported"]=True
        elif case=="BUDGET_USAGE_UNAVAILABLE":
            c1["missing_usage_requires_decision"]=True
        elif case=="WORKER_ATTEMPTS_EXHAUSTED":
            c1["iteration_limit_reached_reported"]=True
        resign(c1)
        c4["source_pg09_c1_sha256"]=c1["candidate_sha256"]
        resign(c4)
        result.append({"scenario_id":case,"fixture_ref":"fixture://pg09/"+case,
            "fixture_sha256":sha(case),"tool_execution_receipt_ref":None,
            "observed_pg09_c1":c1,"observed_pg09_c4":c4})
    return result

class PG09Tests(unittest.TestCase):
    def test_positive_actual_pg08_c1_to_c4(self):
        x=make_chain()
        self.assertEqual(x["pg08"]["final"]["schema_version"],"PG08_C6_C7_C8_FINAL_FEEDBACK_CANDIDATE_V1")
        self.assertEqual(x["c1"]["source_pg07_c5_sha256"],x["pg07"]["c5"]["candidate_sha256"])
        self.assertEqual(x["c2"]["source_pg09_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg09_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["c4"]["source_pg09_c3_sha256"],x["c3"]["candidate_sha256"])
        for key in ("c1","c2","c3","c4"):
            self.assertFalse(x[key]["production_authority"])
            self.assertFalse(x[key]["handoff_allowed"])
        self.assertFalse(x["c4"]["retry_authorized"])
    def test_c1_exact_7999_below_warning(self):
        x=make_chain("79.99")
        self.assertEqual(x["c1"]["request_diagnostic"],"REPORTED_WITHIN_BUDGET_UNVERIFIED")
    def test_c1_exact_80_warns(self):
        x=make_chain("80.00")
        self.assertEqual(x["c1"]["request_diagnostic"],"WARN_80_PERCENT")
        self.assertTrue(x["c1"]["eighty_percent_warning_reported"])
    def test_c1_exact_100_requires_decision(self):
        x=make_chain("100.00")
        self.assertEqual(x["c1"]["request_diagnostic"],"REQUIRES_DECISION")
        self.assertTrue(x["c1"]["requires_decision_reported"])
        self.assertEqual(x["c4"]["solutions"][0]["escalation_type"],"RETURN")
        self.assertIn("BUDGET_DECISION",x["c4"]["solutions"][0]["reason_codes"])
    def test_c1_undeclared_provider_cost_not_free(self):
        x=make_chain("1")
        observed=cost_observations(x["pg07"],"1")
        observed[0]["calls"][0]["reported_cost"]=None
        r=prepare_pg09_c1(pg07_c1=x["pg07"]["c1"],pg07_c5=x["pg07"]["c5"],
            budget_policy=policy(),usage_observations=observed)
        self.assertTrue(r["requires_decision_reported"])
        self.assertTrue(r["missing_usage_requires_decision"])
    def test_c1_authority_injected_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["pg07"]["c5"])
        fake["production_authority"]=True;resign(fake)
        with self.assertRaises(PG09C1Blocked):
            prepare_pg09_c1(pg07_c1=x["pg07"]["c1"],pg07_c5=fake,
                budget_policy=policy(),usage_observations=cost_observations(x["pg07"]))
    def test_c2_cross_stage_digest_change_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["c1"])
        fake["source_pg07_c5_sha256"]="f"*64;resign(fake)
        with self.assertRaises(PG09C2Blocked):
            prepare_pg09_c2(pg07_c5=x["pg07"]["c5"],pg09_c1=fake,
                            iteration_observations=snapshots(x["pg07"]["c5"]))
    def test_c3_deleting_test_is_blocked(self):
        x=with_iteration("TEST_DELETE")
        self.assertEqual(x["c3"]["solutions"][0 if x["c3"]["solutions"][0]["solution_id"]==x["sid"] else 1]["diagnostic"],"BLOCK")
        self.assertIn("QUALITY_BYPASS",next(r for r in x["c4"]["solutions"] if r["solution_id"]==x["sid"])["reason_codes"])
        self.assertFalse(x["c3"]["real_diff_scanned"])
        self.assertFalse(x["c3"]["quality_gate_bypass_allowed"])
    def test_c3_disabling_rule_is_blocked(self):
        x=with_iteration("RULE_DISABLE")
        self.assertEqual(next(r for r in x["c3"]["solutions"] if r["solution_id"]==x["sid"])["diagnostic"],"BLOCK")
        self.assertFalse(x["c3"]["retry_authorized"])
    def test_c3_test_deletion_with_fake_after_sha_rejected(self):
        x=with_iteration("TEST_DELETE");bad=copy.deepcopy(x["changes"])
        next(r for r in bad if r["solution_id"]==x["sid"])["iterations"][0]["changes"][0]["after_sha256"]="e"*64
        with self.assertRaises(PG09C3Blocked):
            prepare_pg09_c3(pg07_c5=x["pg07c5"],pg09_c2=x["c2"],quality_change_observations=bad)
    def test_c4_owner_run_mismatch_blocks(self):
        x=make_chain();bad=context(x["c1"]);bad[0]["run_ref"]="foreign-run"
        with self.assertRaises(PG09C4Blocked):
            prepare_pg09_c4(pg09_c1=x["c1"],pg09_c2=x["c2"],pg09_c3=x["c3"],
                             escalation_context=bad)
    def test_c5_full_matrix_source_only_not_executed(self):
        out=prepare_pg09_c5(scenario_observations=matrix())
        self.assertEqual(out["required_case_count"],9)
        self.assertEqual(out["executed_test_count"],0)
        self.assertFalse(out["adversarial_cases_executed"])
        self.assertFalse(out["independent_verdict_issued"])
        self.assertTrue(out["reported_structure_matches_all_expectations"])
    def test_c5_missing_scenario_blocks(self):
        with self.assertRaises(PG09C5Blocked):
            prepare_pg09_c5(scenario_observations=matrix()[:-1])
    def test_c5_fabricated_runtime_authority_blocks(self):
        items=matrix();items[0]["observed_pg09_c1"]["production_authority"]=True
        resign(items[0]["observed_pg09_c1"])
        with self.assertRaises(PG09C5Blocked):
            prepare_pg09_c5(scenario_observations=items)
if __name__=="__main__":unittest.main()
