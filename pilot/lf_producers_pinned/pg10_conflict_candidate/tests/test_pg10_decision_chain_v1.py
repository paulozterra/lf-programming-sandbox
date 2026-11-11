"""PG-10 source-only positive chain and authority, precedence, repeat-question negatives.

The upstream PG09 C4 and PG08 final are produced by actual source modules
from preceding stacked PRs; all source observations are synthetic.
"""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
             "pg06_preflight_candidate","pg07_worker_candidate","pg08_build_candidate",
             "pg09_iteration_candidate","pg10_conflict_candidate"):
    for sub in ("tests","tools"):
        p=ROOT/name/sub
        if p.is_dir():sys.path.insert(0,str(p))

from test_pg09_iteration_chain_v1 import make_chain as pg09_chain
from pg10_c1_conflict_inventory_candidate_v1 import prepare_pg10_c1,PG10C1Blocked
from pg10_c2_precedence_legacy_guard_candidate_v1 import prepare_pg10_c2,PG10C2Blocked
from pg10_c3_typed_decision_routing_candidate_v1 import prepare_pg10_c3,PG10C3Blocked
from pg10_c4_human_decision_packet_candidate_v1 import prepare_pg10_c4,PG10C4Blocked
from pg10_c5_negative_assurance_candidate_v1 import prepare_pg10_c5,PG10C5Blocked,EXPECTED
from pg10_decision_lineage_dedup_candidate_v1 import (
    prepare_pg10_decision_lineage,PG10LineageBlocked)

def sha(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def resign(obj):
    obj["candidate_sha256"]=sha({k:v for k,v in obj.items() if k!="candidate_sha256"})

def conflicts(pg09):
    ids=[x["solution_id"] for x in pg09["c4"]["solutions"]]
    first=ids[0]
    return ([{"solution_id":sid,"conflicts":([{
        "conflict_id":"CONFLICT-001",
        "classification":"REQUIREMENT_VS_STANDARD","issue_kind":"CONFLICT",
        "requirement_ref":"fixture://analysis/req/R1",
        "standard_ref":"fixture://standards/STD-API-06",
        "existing_contract_ref":None,"reuse_as_is_ref":None,
        "evidence_refs":["fixture://req/R1","fixture://std/STD-API-06"],
        "diagnosis_ref":"fixture://diagnosis/001"}] if sid==first else [])}
        for sid in ids],first)

def precedence(c1):
    rows=[]
    for sol in c1["solutions"]:
        rows.append({"solution_id":sol["solution_id"],
            "conflict_actions":[{"conflict_id":x["conflict_id"],
                "action":"PRESERVE_EXISTING"} for x in sol["conflicts"]],
            "legacy_changes":[]})
    return rows

def routes(c2,prior=False):
    rows=[]
    for sol in c2["solutions"]:
        issues=[]
        for a in sol["conflict_actions"]:
            issues.append({"conflict_id":a["conflict_id"],
                "issue_class":"HUMAN_DECISION","exact_query_ref":"fixture://query/exact",
                "resolver_ref":"fixture://owner/decider",
                "prior_decision_ref":"fixture://decision/resolved" if prior else None,
                "prior_decision_current_verified":False})
        rows.append({"solution_id":sol["solution_id"],"issues":issues})
    return rows

def packets(c3,include=True):
    rows=[]
    for sol in c3["solutions"]:
        entries=[]
        for r in sol["routes"]:
            if include and r["route_candidate"]=="HUMAN_DECISION_PACKET_CANDIDATE":
                entries.append({
                    "conflict_id":r["conflict_id"],
                    "question":"Which contract behavior is authorized?",
                    "options":[
                        {"option_id":"KEEP","description":"Keep existing semantics",
                         "consequence":"Legacy behavior maintained"},
                        {"option_id":"CHANGE","description":"Request governed change",
                         "consequence":"Requires contract migration"}],
                    "recommended_option_id":"KEEP",
                    "recommendation_reason":"Respect higher-priority existing contract",
                    "risk_if_undecided":"Affected scope remains blocked",
                    "source_refs":["fixture://analysis/req","fixture://standards/current"],
                    "affected_scope_refs":["fixture://scope/affected"],
                    "resume_condition":"Authorized, current, signed decision readback",
                    "ready_unaffected_scope_refs":["fixture://scope/ready"]})
        rows.append({"solution_id":sol["solution_id"],"packets":entries})
    return rows

def scenarios():
    return [{"scenario_id":k,"fixture_ref":"fixture://pg10/"+k,
        "fixture_sha256":sha(k),"target_conflict_ref":"fixture://conflict/001",
        "expected_result":v[0],"expected_reason":v[1],
        "execution_receipt_ref":None} for k,v in EXPECTED.items()]

def build(prior=False):
    upstream=pg09_chain()
    observation,sid=conflicts(upstream)
    c1=prepare_pg10_c1(pg07_c5=upstream["pg07"]["c5"],
                       pg09_c4=upstream["c4"],conflict_observations=observation)
    p=precedence(c1)
    c2=prepare_pg10_c2(pg10_c1=c1,precedence_observations=p)
    r=routes(c2,prior=prior)
    c3=prepare_pg10_c3(pg10_c2=c2,routing_observations=r)
    c4=prepare_pg10_c4(pg10_c3=c3,decision_observations=packets(c3))
    c5=prepare_pg10_c5(pg10_c1=c1,pg10_c2=c2,pg10_c3=c3,
                        pg10_c4=c4,scenario_observations=scenarios())
    return locals()

def ledger_for(x,state="RESOLVED"):
    return [{"solution_id":x["sid"],"conflict_id":"CONFLICT-001",
        "decision_ref":"fixture://decision/resolved",
        "decision_state":state,
        "decision_question_key":"REQ-R1-STD-API-06",
        "currentness_ref":"fixture://decision/currentness"}]
def question(x):
    return [{"solution_id":x["sid"],"conflict_id":"CONFLICT-001",
             "decision_question_key":"REQ-R1-STD-API-06"}]
def lineage(x,ledger=None,questions=None):
    return prepare_pg10_decision_lineage(
        pg08_final=x["upstream"]["pg08"]["final"],
        pg09_c4=x["upstream"]["c4"],pg10_c3=x["c3"],
        ledger_observations=[] if ledger is None else ledger,
        proposed_human_questions=[] if questions is None else questions)

class PG10Tests(unittest.TestCase):
    def test_real_upstream_pg09_and_pg08_through_c1_c5(self):
        x=build()
        self.assertEqual(x["c1"]["source_pg09_c4_sha256"],x["upstream"]["c4"]["candidate_sha256"])
        self.assertEqual(x["c2"]["source_pg10_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg10_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["c4"]["source_pg10_c3_sha256"],x["c3"]["candidate_sha256"])
        self.assertEqual(x["c5"]["source_candidate_sha256"]["pg10_c4"],x["c4"]["candidate_sha256"])
        self.assertEqual(x["c5"]["executed_case_count"],0)
        self.assertFalse(x["c4"]["human_questions_sent"])
        for stage in ("c1","c2","c3","c4","c5"):
            self.assertIs(x[stage]["production_authority"],False)
            self.assertIs(x[stage]["handoff_allowed"],False)
        y=lineage(x,questions=question(x))
        self.assertEqual(y["source_pg08_final_sha256"],x["upstream"]["pg08"]["final"]["candidate_sha256"])
        self.assertEqual(y["source_pg09_c4_sha256"],x["upstream"]["c4"]["candidate_sha256"])
        self.assertFalse(y["question_sent"])

    def test_c1_missing_other_conflict_side_blocks(self):
        x=build();ob=copy.deepcopy(x["observation"])
        ob[0]["conflicts"][0]["standard_ref"]=None
        with self.assertRaises(PG10C1Blocked):
            prepare_pg10_c1(pg07_c5=x["upstream"]["pg07"]["c5"],
                pg09_c4=x["upstream"]["c4"],conflict_observations=ob)

    def test_c1_authority_injected_rehash_blocks(self):
        x=build();bad=copy.deepcopy(x["upstream"]["c4"])
        bad["production_authority"]=True;resign(bad)
        with self.assertRaises(PG10C1Blocked):
            prepare_pg10_c1(pg07_c5=x["upstream"]["pg07"]["c5"],
                pg09_c4=bad,conflict_observations=x["observation"])

    def test_c2_lower_priority_override_higher_priority_rejected(self):
        x=build();obs=copy.deepcopy(x["p"])
        obs[0]["conflict_actions"][0]["action"]="OVERRIDE_HIGHER_PRIORITY"
        with self.assertRaisesRegex(PG10C2Blocked,"ACTION_INVALID"):
            prepare_pg10_c2(pg10_c1=x["c1"],precedence_observations=obs)

    def test_c2_unapproved_legacy_rename_not_allowed(self):
        x=build();obs=copy.deepcopy(x["p"])
        obs[0]["legacy_changes"]=[{
            "change_id":"rename-001","kind":"RENAME",
            "legacy_ref":"fixture://legacy/billing",
            "target_ref":"fixture://new/billing",
            "migration_approval_ref":None,"migration_approval_authenticated":False}]
        r=prepare_pg10_c2(pg10_c1=x["c1"],precedence_observations=obs)
        self.assertFalse(r["solutions"][0]["legacy_changes"][0]["rename_allowed"])
        self.assertFalse(r["legacy_rename_executed"])

    def test_c2_forged_migration_approval_blocks(self):
        x=build();obs=copy.deepcopy(x["p"])
        obs[0]["legacy_changes"]=[{
            "change_id":"rename-001","kind":"RENAME",
            "legacy_ref":"fixture://legacy/billing",
            "target_ref":"fixture://new/billing",
            "migration_approval_ref":"fixture://approval","migration_approval_authenticated":True}]
        with self.assertRaisesRegex(PG10C2Blocked,"UNVERIFIED_APPROVAL_CLAIM"):
            prepare_pg10_c2(pg10_c1=x["c1"],precedence_observations=obs)

    def test_c3_prior_answered_question_cannot_be_repeated(self):
        x=build(prior=True)
        with self.assertRaisesRegex(PG10LineageBlocked,"DUPLICATE_ANSWERED_QUESTION"):
            lineage(x,ledger=ledger_for(x),questions=question(x))
        self.assertFalse(x["c3"]["human_questions_sent"])
        self.assertFalse(x["c3"]["duplicate_questions_checked_against_ledger"])

    def test_c3_stale_prior_must_be_checked_before_question(self):
        x=build(prior=True)
        with self.assertRaisesRegex(PG10LineageBlocked,"PRIOR_DECISION_REQUIRES_CURRENTNESS_CHECK"):
            lineage(x,ledger=ledger_for(x,"STALE"),questions=question(x))

    def test_c3_resolved_prior_reuse_candidate_no_question_sent(self):
        x=build(prior=True)
        y=lineage(x,ledger=ledger_for(x))
        self.assertTrue(y["rows"][0]["reuse_decision_candidate"] or
            any(r["reuse_decision_candidate"] for r in y["rows"]))
        self.assertFalse(y["decision_ledger_authenticated"])

    def test_c3_existing_prior_cannot_generate_human_packet(self):
        x=build(prior=True)
        bad=packets(build()["c3"])
        with self.assertRaises(PG10C4Blocked):
            prepare_pg10_c4(pg10_c3=x["c3"],decision_observations=bad)

    def test_c3_question_for_nonhuman_route_blocks(self):
        x=build();bad=copy.deepcopy(x["r"])
        bad[0]["issues"][0]["issue_class"]="TECHNICAL_DECISION"
        c3=prepare_pg10_c3(pg10_c2=x["c2"],routing_observations=bad)
        with self.assertRaisesRegex(PG10LineageBlocked,"NOT_A_NEW_HUMAN_QUESTION"):
            prepare_pg10_decision_lineage(
                pg08_final=x["upstream"]["pg08"]["final"],
                pg09_c4=x["upstream"]["c4"],pg10_c3=c3,
                ledger_observations=[],proposed_human_questions=question(x))

    def test_c4_resume_overlaps_ready_scope_blocks(self):
        x=build();obs=packets(x["c3"])
        obs[0]["packets"][0]["ready_unaffected_scope_refs"]=["fixture://scope/affected"]
        with self.assertRaisesRegex(PG10C4Blocked,"SCOPE_OVERLAP"):
            prepare_pg10_c4(pg10_c3=x["c3"],decision_observations=obs)

    def test_c5_full_negative_matrix_source_only(self):
        x=build()
        self.assertEqual(x["c5"]["required_case_count"],12)
        self.assertFalse(x["c5"]["independent_verdict_issued"])
        self.assertEqual(x["c5"]["executed_case_count"],0)

    def test_c5_fake_test_receipt_rejected(self):
        x=build();bad=scenarios();bad[0]["execution_receipt_ref"]="fake://receipt"
        with self.assertRaisesRegex(PG10C5Blocked,"UNVERIFIED_EXECUTION_RECEIPT"):
            prepare_pg10_c5(pg10_c1=x["c1"],pg10_c2=x["c2"],
                pg10_c3=x["c3"],pg10_c4=x["c4"],scenario_observations=bad)

    def test_c5_missing_scenario_blocks(self):
        x=build()
        with self.assertRaises(PG10C5Blocked):
            prepare_pg10_c5(pg10_c1=x["c1"],pg10_c2=x["c2"],
                pg10_c3=x["c3"],pg10_c4=x["c4"],scenario_observations=scenarios()[:-1])

if __name__=="__main__":unittest.main()
