"""PG12 C1-C4 actual source modules + actual PG10->11 bridge output.

Tests operate in source-only mode. Database persistence runs in separate
pg12_postgres_disposable_readback_v1.py and must NOT be counted here.
"""
import copy,hashlib,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ("pg04_semantic_partition_candidate","pg05_target_binding_candidate",
             "pg06_preflight_candidate","pg07_worker_candidate",
             "pg08_build_candidate","pg09_iteration_candidate",
             "pg10_conflict_candidate","pg11_integrity_candidate","pg12_identity_candidate"):
    for sub in ("tests","tools"):
        p=ROOT/name/sub
        if p.is_dir():sys.path.insert(0,str(p))
from test_pg10_pg11_bridge_and_waiver_time_v1 import inputs as pg11_bridge_inputs
from pg11_pg10_handoff_bridge_candidate_v1 import bridge_pg10_c5_to_pg11_c1
from pg12_c1_candidate_identity_v1 import prepare_pg12_c1, PG12C1Blocked
from pg12_c2_execution_inputs_usage_candidate_v1 import prepare_pg12_c2,PG12C2Blocked
from pg12_c3_check_results_link_candidate_v1 import prepare_pg12_c3,PG12C3Blocked
from pg12_c4_persistence_readback_request_candidate_v1 import prepare_pg12_c4,PG12C4Blocked
from pg12_git_identity_and_pg11_bridge_v1 import (
    bridge_pg11_to_pg12_identity,verify_git_object,PG12IdentityBlocked)


def oid(kind,content):
    return hashlib.sha1((kind+" "+str(len(content))+"\0").encode()+content).hexdigest()

def raw_git_objects():
    tree=b"100644 file.txt\0"+bytes.fromhex("b"*40)
    tree_oid=oid("tree",tree)
    base=(f"tree {tree_oid}\nauthor Test <test@example.org> 1000000000 +0000\n"
          "committer Test <test@example.org> 1000000000 +0000\n\nbase\n").encode()
    head=(f"tree {tree_oid}\nparent {oid('commit',base)}\n"
          "author Test <test@example.org> 1000000001 +0000\n"
          "committer Test <test@example.org> 1000000001 +0000\n\ncandidate\n").encode()
    return base,head,tree

def cost(stage,cost,waste="0"):
    return {"stage_ref":stage,"input_tokens":10,"output_tokens":5,
            "cached_input_tokens":2,"cost_reported":cost,"wasted_cost_reported":waste}

def inputs():
    connection,upstream,pg11=pg11_bridge_inputs()
    prior=bridge_pg10_c5_to_pg11_c1(**connection)
    review=pg11["c5"]
    row=review["reviews"][0]
    c1=prepare_pg12_c1(
        pg11_c5=review,repo_ref=connection["run_binding"]["target_repo"],
        base_commit_sha=connection["run_binding"]["base_head_sha"],
        candidate_commit_sha=connection["run_binding"]["expected_head_sha"],
        candidate_tree_sha="c"*40,diff_sha256="d"*64,
        changed_objects=[{"path":row["path"],"change_type":"MODIFIED","old_path":None,
            "object_type":"blob","object_oid":"e"*40,"old_object_oid":"f"*40}],
        builder_principal_ref=row["builder_principal_ref_reported"],
        builder_provenance_ref=row["builder_provenance_ref_reported"])
    bridge=bridge_pg11_to_pg12_identity(
        pg10_pg11_bridge=prior,pg11_c5=review,pg12_c1=c1,
        repo_ref=connection["run_binding"]["target_repo"])
    stages=[cost("PG-07","0.10","0.01"),cost("PG-08","0.20","0.02")]
    totals={"stage_ref":"TOTAL","input_tokens":20,"output_tokens":10,
        "cached_input_tokens":4,"cost_reported":"0.30","wasted_cost_reported":"0.03"}
    c2args=dict(pg12_c1=c1,context_id="fixture://context/1",
        catalog_version_ref="fixture://catalog/v1",
        skill_versions=[{"name":"review","version_ref":"fixture://skills/v1"}],
        stack_profile_ref="fixture://stack/python",
        provider_ref="fixture://provider",model_ref="fixture://model",
        ekb_snapshot_ref="fixture://ekb/sha",
        toolchain_versions=[{"name":"python","version_ref":"3.12"}],
        linter_config_sha256="a"*64,optimization_mode="HYBRID",
        usage_totals=totals,usage_by_stage=stages,
        extra_queries=[],identifier_term_map=[{"identifier_ref":"fixture://feature",
            "term_ids":["TERM-001"],"glossary_source_ref":"fixture://glossary"}],
        billing_currency="USD")
    c2=prepare_pg12_c2(**c2args)
    checks=[{"checkpoint_code":f"PG-{stage:02d}_C{i}",
        "candidate_identity_sha256":c1["candidate_sha256"],
        "check_contract_ref":"fixture://check/contract",
        "result_ref":None,"result_digest_sha256":None,
        "runner_ref":"fixture://runner/unverified",
        "observed_outcome":"NOT_RUN","execution_receipt_ref":None}
        for stage,count in ((8,8),(11,5)) for i in range(1,count+1)]
    c3=prepare_pg12_c3(pg12_c2=c2,candidate_identity_sha256=c1["candidate_sha256"],
                        check_observations=checks)
    c4=prepare_pg12_c4(pg12_c3=c3,storage_contract_ref="fixture://storage/contract",
        authorized_writer_ref="fixture://governed/writer",
        readback_contract_ref="fixture://readback/contract",
        record_key_ref="fixture://candidate/record-key",
        expected_store_namespace="pg12_test_disposable")
    return locals()

class PG12Tests(unittest.TestCase):
    def test_actual_pg11_and_pg10_source_chain_through_c1_c4(self):
        x=inputs()
        self.assertEqual(x["bridge"]["source_pg11_c5_sha256"],x["c1"]["source_pg11_c5_sha256"])
        self.assertEqual(x["c2"]["source_pg12_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg12_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["c4"]["source_pg12_c3_sha256"],x["c3"]["candidate_sha256"])
        self.assertEqual(len(x["c3"]["check_results"]),13)
        self.assertFalse(x["c4"]["persisted"])
        self.assertFalse(x["c4"]["readback_matched"])
        for c in ("c1","c2","c3","c4","bridge"):
            self.assertFalse(x[c]["production_authority"])
            self.assertFalse(x[c]["handoff_allowed"])

    def test_c1_git_commit_object_oid_mismatch_blocks(self):
        base,_,_=raw_git_objects()
        with self.assertRaisesRegex(PG12IdentityBlocked,"GIT_OBJECT_OID_MISMATCH"):
            verify_git_object(object_kind="commit",object_bytes=base,declared_oid="f"*40)

    def test_c1_git_tree_oid_mismatch_blocks(self):
        _,_,tree=raw_git_objects()
        with self.assertRaisesRegex(PG12IdentityBlocked,"GIT_OBJECT_OID_MISMATCH"):
            verify_git_object(object_kind="tree",object_bytes=tree,declared_oid="f"*40)

    def test_c1_valid_raw_git_commit_and_tree_are_recomputed(self):
        base,head,tree=raw_git_objects()
        for typ,value in (("commit",base),("commit",head),("tree",tree)):
            self.assertEqual(verify_git_object(object_kind=typ,object_bytes=value,
                declared_oid=oid(typ,value)),oid(typ,value))

    def test_c1_git_object_proof_must_be_complete(self):
        x=inputs()
        with self.assertRaisesRegex(PG12IdentityBlocked,"GIT_OBJECT_PROOF_INCOMPLETE"):
            bridge_pg11_to_pg12_identity(
                pg10_pg11_bridge=x["prior"],pg11_c5=x["review"],
                pg12_c1=x["c1"],repo_ref=x["connection"]["run_binding"]["target_repo"],
                base_commit_bytes=b"partial")

    def test_c1_authority_injection_rejected(self):
        x=inputs();bad=copy.deepcopy(x["review"])
        bad["production_authority"]=True
        from pg12_c1_candidate_identity_v1 import digest
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaises(PG12C1Blocked):
            prepare_pg12_c1(pg11_c5=bad,repo_ref=x["c1"]["repository_ref_reported"],
                base_commit_sha=x["c1"]["base_commit_sha_reported"],
                candidate_commit_sha=x["c1"]["candidate_commit_sha_reported"],
                candidate_tree_sha=x["c1"]["candidate_tree_sha_reported"],
                diff_sha256=x["c1"]["diff_sha256_reported"],
                changed_objects=[{k:v for k,v in x["c1"]["changed_objects_reported"][0].items()
                                  if k!="git_object_readback_verified"}],
                builder_principal_ref=x["c1"]["builder_principal_ref_reported"],
                builder_provenance_ref=x["c1"]["builder_provenance_ref_reported"])

    def test_c2_malformed_cost_decimal_blocks(self):
        x=inputs();bad=copy.deepcopy(x["c2args"])
        bad["usage_by_stage"][0]["cost_reported"]="1.2.3"
        with self.assertRaisesRegex(PG12C2Blocked,"USAGE_COST_INVALID"):
            prepare_pg12_c2(**bad)

    def test_c2_nan_cost_blocks(self):
        x=inputs();bad=copy.deepcopy(x["c2args"])
        bad["usage_by_stage"][0]["cost_reported"]="NaN"
        with self.assertRaisesRegex(PG12C2Blocked,"USAGE_COST_INVALID"):
            prepare_pg12_c2(**bad)

    def test_c2_sum_mismatch_blocks(self):
        x=inputs();bad=copy.deepcopy(x["c2args"])
        bad["usage_totals"]["cost_reported"]="0.31"
        with self.assertRaisesRegex(PG12C2Blocked,"USAGE_TOTAL_MISMATCH"):
            prepare_pg12_c2(**bad)

    def test_c2_cache_exceeds_input_blocks(self):
        x=inputs();bad=copy.deepcopy(x["c2args"])
        bad["usage_by_stage"][0]["cached_input_tokens"]=20
        with self.assertRaisesRegex(PG12C2Blocked,"CACHE_EXCEEDS_INPUT"):
            prepare_pg12_c2(**bad)

    def test_c3_declared_pass_without_receipt_blocks(self):
        x=inputs();bad=copy.deepcopy(x["checks"])
        bad[0]["observed_outcome"]="PASS"
        with self.assertRaises(PG12C3Blocked):
            prepare_pg12_c3(pg12_c2=x["c2"],candidate_identity_sha256=x["c1"]["candidate_sha256"],check_observations=bad)

    def test_c4_never_claims_persistence(self):
        x=inputs();self.assertFalse(x["c4"]["write_attempted"])
        self.assertFalse(x["c4"]["storage_readback_attempted"])
        self.assertIsNone(x["c4"]["readback_payload_sha256"])
if __name__=="__main__":unittest.main()
