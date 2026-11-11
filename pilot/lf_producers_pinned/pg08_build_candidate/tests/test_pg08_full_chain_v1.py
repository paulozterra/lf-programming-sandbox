"""PG-08 C1-C8 source-only chain from actual PG07 C6 producer.

The observed command data is SYNTHETIC. Never a CI PASS or real receipt.
"""
import copy,hashlib,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for dirname in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
                "pg06_preflight_candidate","pg07_worker_candidate","pg08_build_candidate"):
    for sub in ("tests","tools"):
        folder=ROOT/dirname/sub
        if folder.is_dir():sys.path.insert(0,str(folder))
from test_pg07_c1_c6_chain_v1 import make_chain as pg07_chain
from pg08_c1_build_compilation_candidate_v1 import prepare_pg08_c1,PG08C1Blocked
from pg08_c2_format_lint_delta_candidate_v1 import prepare_pg08_c2,PG08C2Blocked
from pg08_c3_typecheck_candidate_v1 import prepare_pg08_c3,PG08C3Blocked
from pg08_c4_test_flyway_candidate_v1 import prepare_pg08_c4,PG08C4Blocked
from pg08_c5_contract_lint_candidate_v1 import prepare_pg08_c5,PG08C5Blocked
from pg08_c6_check_receipts_candidate_v1 import prepare_pg08_c6,PG08C6Blocked
from pg08_c7_arch_boundary_candidate_v1 import prepare_pg08_c7,PG08C7Blocked
from pg08_c8_iac_container_candidate_v1 import prepare_pg08_c8,PG08C8Blocked
from pg08_c6_final_receipts_candidate_v1 import (
    consolidate_pg08_c6_c7_c8,reject_falsified_pass_fingerprint,PG08FinalReceiptBlocked)

SHA="a"*64
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def fingerprint(t):return sha(t)
def rehash(obj):
    from json import dumps
    obj["candidate_sha256"]=hashlib.sha256(dumps(
        {k:v for k,v in obj.items() if k!="candidate_sha256"},
        sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def check(kind,extra=None):
    val={"command_id":kind.lower(),"command_ref":"fixture://command/"+kind,
         "tool_name":"fixture-test-runner","tool_version":"1",
         "config_sha256":SHA,"execution_receipt_ref":"fixture://receipt/"+kind,
         "stdout_sha256":"b"*64,"stderr_sha256":"c"*64,
         "result":"PASS","exit_code":0}
    if extra:val.update(extra)
    return val
def identity(pg07):
    return dict(target_repo=pg07["target_repo"],base_head_sha=pg07["base_head_sha"])
def reported_base(pg07,item):
    return dict(solution_id=item["solution_id"],executor_mode="GPT_NATIVE",
        candidate_head_sha=item["candidate_head_sha_reported"],
        diff_sha256=item["diff_sha256_reported"],**identity(pg07))

def make_chain():
    upstream=pg07_chain()
    source=upstream["c6"]  # actual PG07 producer (not a fabricated C6)
    build=[{**reported_base(source,s),"executor_result_ref":"fixture://gpt-native/result",
            "commands":[check("BUILD")]} for s in source["batches"]]
    c1=prepare_pg08_c1(pg07_c6=source,build_observations=build)
    lint=[{**reported_base(source,s),"checks":[check(kind,{"kind":kind,"findings":[]})
          for kind in ("FORMAT","LINT")]} for s in source["batches"]]
    baseline=upstream["upstream"]["c4"] # actual PG06 C4 positive baseline
    c2=prepare_pg08_c2(pg06_c4=baseline,pg08_c1=c1,lint_observations=lint)
    types=[{**reported_base(source,s),"required_profiles":["MYPY"],
            "checks":[check("MYPY",{"profile":"MYPY","diagnostic_refs":[]})]}
           for s in source["batches"]]
    c3=prepare_pg08_c3(pg08_c1=c1,pg08_c2=c2,typecheck_observations=types)
    tests=[{**reported_base(source,s),"flyway_applicability":"NOT_APPLICABLE",
            "flyway_applicability_ref":"fixture://scope/no-migration",
            "local_pg_isolation_ref":None,
            "checks":[check(kind,{"kind":kind,"diagnostic_refs":[],
                       "runtime_target_ref":"fixture://local/sandbox"})
                      for kind in ("UNIT_FOCAL","SMOKE")]} for s in source["batches"]]
    c4=prepare_pg08_c4(pg08_c1=c1,pg08_c3=c3,test_observations=tests)
    contract_kinds=("SPECTRAL_OPENAPI","OASDIFF_BREAKING","MIGRATED_DB_CATALOG")
    contracts=[{**reported_base(source,s),"checks":[{
        "kind":k,"applicability":"NOT_APPLICABLE",
        "applicability_ref":"fixture://contracts/no-"+k,
        "command_id":None,"command_ref":None,"tool_name":None,"tool_version":None,
        "config_sha256":None,"baseline_contract_sha256":None,
        "candidate_contract_sha256":None,"execution_receipt_ref":None,
        "stdout_sha256":None,"stderr_sha256":None,"result":None,
        "exit_code":None,"findings":[]} for k in contract_kinds]} for s in source["batches"]]
    c5=prepare_pg08_c5(pg08_c1=c1,pg08_c4=c4,contract_observations=contracts)
    c6=prepare_pg08_c6(pg08_c1=c1,pg08_c2=c2,pg08_c3=c3,pg08_c4=c4,pg08_c5=c5)
    arch=[{**reported_base(source,s),"architecture_profile_ref":"fixture://architecture/profile",
        "checks":[{"kind":kind,"applicability":"NOT_APPLICABLE",
           "applicability_ref":"fixture://architecture/na/"+kind,
           "command_id":None,"command_ref":None,"tool_name":None,
           "tool_version":None,"config_sha256":None,
           "execution_receipt_ref":None,"stdout_sha256":None,"stderr_sha256":None,
           "result":None,"exit_code":None,"findings":[]}
           for kind in ("SPRING_MODULITH_VERIFY","ARCHUNIT")]}
         for s in source["batches"]]
    c7=prepare_pg08_c7(pg08_c1=c1,pg08_c6=c6,architecture_observations=arch)
    kinds=("TERRAFORM_FMT","TERRAFORM_VALIDATE","IAC_LINT","FLOCI_PLAN",
           "FLOCI_APPLY","CONTAINER_BUILD","DOCKER_COMPOSE_UP","CONTAINER_HEALTHCHECK")
    iac=[{**reported_base(source,s),"iac_profile_ref":"fixture://iac/profile",
        "isolation_policy_ref":"fixture://isolation/policy","checks":[{
           "kind":kind,"applicability":"NOT_APPLICABLE",
           "applicability_ref":"fixture://iac/na/"+kind,
           "command_id":None,"command_ref":None,"tool_name":None,
           "tool_version":None,"config_sha256":None,"stdout_sha256":None,
           "stderr_sha256":None,"execution_receipt_ref":None,
           "result":None,"exit_code":None,"execution_target_type":None,
           "execution_target_ref":None,"finding_refs":[]}
           for kind in kinds]} for s in source["batches"]]
    c8=prepare_pg08_c8(pg08_c1=c1,pg08_c7=c7,infrastructure_observations=iac)
    final=consolidate_pg08_c6_c7_c8(pg08_c6=c6,pg08_c7=c7,pg08_c8=c8)
    return locals()

class PG08ChainTests(unittest.TestCase):
    def test_real_pg07_c6_full_chain_c1_to_c8_and_final_feedback(self):
        x=make_chain()
        self.assertEqual(x["c1"]["source_pg07_c6_sha256"],x["source"]["candidate_sha256"])
        self.assertEqual(x["c8"]["source_pg08_c7_sha256"],x["c7"]["candidate_sha256"])
        self.assertEqual(x["final"]["source_pg08_c8_sha256"],x["c8"]["candidate_sha256"])
        self.assertTrue(all(len(s["feedback_checks"])>=7 for s in x["final"]["solutions"]))
        self.assertTrue(all({"PG-08_C7","PG-08_C8"}.issubset(
            {c["checkpoint"] for c in s["feedback_checks"]}) for s in x["final"]["solutions"]))
        for stage in ("c1","c2","c3","c4","c5","c6","c7","c8","final"):
            self.assertIs(x[stage]["production_authority"],False)
            self.assertIs(x[stage]["handoff_allowed"],False)
        self.assertFalse(x["final"]["final_verdict_issued"])
        self.assertFalse(x["final"]["receipt_completeness_verified"])
    def test_c1_forged_pg07_worker_authority_blocks(self):
        x=make_chain();fake=copy.deepcopy(x["source"]);fake["production_authority"]=True;rehash(fake)
        with self.assertRaises(PG08C1Blocked):
            prepare_pg08_c1(pg07_c6=fake,build_observations=x["build"])
    def test_c2_build_identity_drift_blocks(self):
        x=make_chain();bad=copy.deepcopy(x["lint"]);bad[0]["candidate_head_sha"]="f"*40
        with self.assertRaises(PG08C2Blocked):
            prepare_pg08_c2(pg06_c4=x["baseline"],pg08_c1=x["c1"],lint_observations=bad)
    def test_c3_injected_authority_blocks(self):
        x=make_chain();bad=copy.deepcopy(x["c2"]);bad["production_authority"]=True;rehash(bad)
        with self.assertRaises(PG08C3Blocked):
            prepare_pg08_c3(pg08_c1=x["c1"],pg08_c2=bad,typecheck_observations=x["types"])
    def test_c4_out_of_order_flyway_blocks(self):
        x=make_chain();bad=copy.deepcopy(x["tests"]);bad[0]["flyway_applicability"]="REQUIRED"
        bad[0]["local_pg_isolation_ref"]="fixture://local/pg"
        flyway=[check(k,{"kind":k,"diagnostic_refs":[],"runtime_target_ref":"fixture://local/pg"})
                for k in ("FLYWAY_APPLY","FLYWAY_ROLLBACK","FLYWAY_REAPPLY")]
        bad[0]["checks"]+=list(reversed(flyway))
        with self.assertRaises(PG08C4Blocked):
            prepare_pg08_c4(pg08_c1=x["c1"],pg08_c3=x["c3"],test_observations=bad)
    def test_c5_not_applicable_with_fake_pass_rejected(self):
        x=make_chain();bad=copy.deepcopy(x["contracts"])
        bad[0]["checks"][0]["result"]="PASS"
        with self.assertRaises(PG08C5Blocked):
            prepare_pg08_c5(pg08_c1=x["c1"],pg08_c4=x["c4"],contract_observations=bad)
    def test_c6_injected_pass_authority_rejected(self):
        x=make_chain();bad=copy.deepcopy(x["c5"]);bad["pg08_c5_pass"]=True;rehash(bad)
        with self.assertRaises(PG08C6Blocked):
            prepare_pg08_c6(pg08_c1=x["c1"],pg08_c2=x["c2"],
                 pg08_c3=x["c3"],pg08_c4=x["c4"],pg08_c5=bad)
    def test_c7_forged_receipt_authority_rejected(self):
        x=make_chain();bad=copy.deepcopy(x["c6"]);bad["receipts_authenticated"]=True;rehash(bad)
        with self.assertRaises(PG08C7Blocked):
            prepare_pg08_c7(pg08_c1=x["c1"],pg08_c6=bad,architecture_observations=x["arch"])
    def test_c8_healthcheck_pass_without_compose_pass_rejected(self):
        x=make_chain();bad=copy.deepcopy(x["iac"]);row=bad[0]["checks"]
        health=next(r for r in row if r["kind"]=="CONTAINER_HEALTHCHECK")
        health.update({"applicability":"REQUIRED",
           "command_id":"health","command_ref":"fixture://health/cmd",
           "tool_name":"docker","tool_version":"fixture-v1",
           "config_sha256":SHA,"stdout_sha256":"b"*64,"stderr_sha256":"c"*64,
           "execution_receipt_ref":"fixture://health/receipt",
           "result":"PASS","exit_code":0,
           "execution_target_type":"LOCAL_ISOLATED",
           "execution_target_ref":"fixture://local/compose"})
        # Compose remains NOT_APPLICABLE -> positive healthcheck is contradictory.
        with self.assertRaisesRegex(PG08C8Blocked,"HEALTHCHECK_WITHOUT_COMPOSE"):
            prepare_pg08_c8(pg08_c1=x["c1"],pg08_c7=x["c7"],infrastructure_observations=bad)
    def test_final_c6_c7_c8_digest_forgery_rejected(self):
        x=make_chain();bad=copy.deepcopy(x["c8"]);bad["source_pg08_c7_sha256"]="f"*64;rehash(bad)
        with self.assertRaisesRegex(PG08FinalReceiptBlocked,"UPSTREAM_DIGEST_LINK_INVALID"):
            consolidate_pg08_c6_c7_c8(pg08_c6=x["c6"],pg08_c7=x["c7"],pg08_c8=bad)
    def test_reported_pass_command_stdout_stderr_fingerprint_mismatch_rejected(self):
        cmd,output,err="python -m unittest","ok",""
        obs={"command_text":cmd,"stdout_text":output,"stderr_text":err,
             "command_sha256":sha(cmd),"stdout_sha256":sha(output),
             "stderr_sha256":sha(err),"exit_code":0}
        reported={"reported_result":"PASS","command_sha256_reported":sha(cmd),
            "stdout_sha256_reported":sha(output),"stderr_sha256_reported":sha(err)}
        result=reject_falsified_pass_fingerprint(reported_check=reported,independent_observation=obs)
        self.assertFalse(result["final_pass"])
        for key in ("command_sha256_reported","stdout_sha256_reported","stderr_sha256_reported"):
            bad=copy.deepcopy(reported);bad[key]="f"*64
            with self.assertRaisesRegex(PG08FinalReceiptBlocked,"REPORTED_PASS_MISMATCH"):
                reject_falsified_pass_fingerprint(reported_check=bad,independent_observation=obs)
    def test_claimed_independent_observation_not_matching_output_rejected(self):
        obs={"command_text":"run","stdout_text":"changed","stderr_text":"",
            "command_sha256":sha("run"),"stdout_sha256":sha("original"),
            "stderr_sha256":sha(""),"exit_code":0}
        check={"reported_result":"PASS","command_sha256_reported":sha("run"),
            "stdout_sha256_reported":sha("original"),"stderr_sha256_reported":sha("")}
        with self.assertRaisesRegex(PG08FinalReceiptBlocked,"INDEPENDENT_OBSERVATION_INCONSISTENT"):
            reject_falsified_pass_fingerprint(reported_check=check,independent_observation=obs)

    def test_required_c7_c8_receipts_are_in_final_c6_feedback(self):
        x=make_chain()
        arch=copy.deepcopy(x["arch"])
        a=next(c for c in arch[0]["checks"] if c["kind"]=="ARCHUNIT")
        a.update({"applicability":"REQUIRED","command_id":"arch",
            "command_ref":"fixture://arch/cmd","tool_name":"archunit","tool_version":"fixture",
            "config_sha256":SHA,"execution_receipt_ref":"fixture://arch/receipt",
            "stdout_sha256":"b"*64,"stderr_sha256":"c"*64,
            "result":"PASS","exit_code":0})
        c7=prepare_pg08_c7(pg08_c1=x["c1"],pg08_c6=x["c6"],architecture_observations=arch)
        iac=copy.deepcopy(x["iac"])
        for k in ("CONTAINER_BUILD","DOCKER_COMPOSE_UP","CONTAINER_HEALTHCHECK"):
            r=next(row for row in iac[0]["checks"] if row["kind"]==k)
            r.update({"applicability":"REQUIRED",
                "command_id":"cmd-"+k,"command_ref":"fixture://iac/"+k,
                "tool_name":"docker","tool_version":"fixture-v1",
                "config_sha256":SHA,"stdout_sha256":"b"*64,"stderr_sha256":"c"*64,
                "execution_receipt_ref":"fixture://iac/receipt/"+k,
                "result":"PASS","exit_code":0,
                "execution_target_type":"LOCAL_ISOLATED",
                "execution_target_ref":"fixture://local/compose"})
        c8=prepare_pg08_c8(pg08_c1=x["c1"],pg08_c7=c7,infrastructure_observations=iac)
        final=consolidate_pg08_c6_c7_c8(pg08_c6=x["c6"],pg08_c7=c7,pg08_c8=c8)
        checks=final["solutions"][0]["feedback_checks"]
        bykind={row["kind"]:row for row in checks if row["checkpoint"] in ("PG-08_C7","PG-08_C8")}
        self.assertEqual(bykind["ARCHUNIT"]["reported_result"],"PASS")
        self.assertEqual(bykind["CONTAINER_HEALTHCHECK"]["reported_result"],"PASS")
        self.assertEqual(bykind["CONTAINER_HEALTHCHECK"]["execution_receipt_ref_reported"],"fixture://iac/receipt/CONTAINER_HEALTHCHECK")
        self.assertFalse(bykind["ARCHUNIT"]["receipt_authenticated"])
        self.assertFalse(bykind["CONTAINER_HEALTHCHECK"]["tool_execution_verified"])
        self.assertFalse(final["final_verdict_issued"])

    def test_healthcheck_pass_when_compose_failed_is_blocked(self):
        x=make_chain()
        bad=copy.deepcopy(x["iac"])
        for k,result,code in (("CONTAINER_HEALTHCHECK","PASS",0),("DOCKER_COMPOSE_UP","FAIL",1)):
            r=next(row for row in bad[0]["checks"] if row["kind"]==k)
            r.update({"applicability":"REQUIRED",
                "command_id":"cmd-"+k,"command_ref":"fixture://iac/"+k,
                "tool_name":"docker","tool_version":"fixture-v1",
                "config_sha256":SHA,"stdout_sha256":"b"*64,"stderr_sha256":"c"*64,
                "execution_receipt_ref":"fixture://iac/receipt/"+k,
                "result":result,"exit_code":code,
                "execution_target_type":"LOCAL_ISOLATED",
                "execution_target_ref":"fixture://local/compose"})
        with self.assertRaisesRegex(PG08C8Blocked,"HEALTHCHECK_PASS_WITHOUT_COMPOSE_PASS"):
            prepare_pg08_c8(pg08_c1=x["c1"],pg08_c7=x["c7"],infrastructure_observations=bad)

if __name__=="__main__":unittest.main()
