"""EX6-only original V2 PG11→PG13 candidate chain with disposable readbacks.

Every external reference starts ex6://. No EX5C values, no Supabase access.
PG11 process REM-D4 retains visible PASS and AOSP FAIL. The local PostgreSQL
writer and Git hook are test-only, not real LF storage or production freeze.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path

from ex6_source_truth_v1 import source_truth, SPEC_REF, RUN_REF, TASK_REF
from ex6_real_chain_v1 import authorize_from_real_hunks
from ex6_build_lint_inputs_v1 import observed, config_sha, rem_d4_process, active_ref

TREE="72e5f54ca75cb3a1186dbc160469cf8f5dd070c5"
N="912c4ad9ea71f48edbd1ac58089441f9ed2c3449"
BUILDER="ex6://principal/gpt-native-worker"
REVIEWER="ex6://unattested/independent-reviewer"

def h(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,
        separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def make_pg11_v2(truth=None):
    """Source-only N:M original PG11 v2 producers, full three true EX6 hunks."""
    from pg11_c1_diff_hygiene_candidate_v2 import prepare_pg11_c1
    from pg11_c2_terminology_catalog_candidate_v2 import prepare_pg11_c2
    from pg11_c3_suppression_waiver_candidate_v2 import prepare_pg11_c3
    from pg11_c4_diff_requirement_batch_trace_candidate_v2 import prepare_pg11_c4
    from pg11_c5_independent_reviewer_candidate_v2 import prepare_pg11_c5
    truth=truth or source_truth()
    diff,auth,traces=authorize_from_real_hunks(truth)
    assert len(diff)==len(auth)==len(traces)==3
    c1=prepare_pg11_c1(
        expected_base_sha=truth["base_head_sha"],
        expected_head_sha="13ef9c319fb62f7e08f6f030d447c60ee7bfa7f5",
        declared_diff=diff,authorized_scope=auth,
        residue_observations=[],dependency_observations=[],
        compatibility_observations=[{
            "surface":"MODULE_CONTRACT","contract_ref":SPEC_REF+"#REM-D3",
            "baseline_ref":"ex6://source/base/"+truth["base_head_sha"],
            "evidence_ref":active_ref()+"#candidate/commands/build",
            "compatible_reported":True}])
    observed_terms=[{
        "path":x["path"],"symbol_ref":x["header_ref"]+"#"+Path(x["path"]).stem,
        "kind":"DOMAIN_IDENTIFIER","literal_value":Path(x["path"]).stem,
        "source_ref":x["header_ref"],"term_ids":x["requirements"],
        "term_exists_reported":False,"term_matches_reported":False,
        "literal_match_reported":True,"neighbor_match_reported":False
    } for x in truth["hunks"]]
    c2=prepare_pg11_c2(
        pg11_c1=c1,declared_changed_paths=[x["path"] for x in diff],
        terminology_observations=observed_terms,
        glossary_snapshot_ref=SPEC_REF,
        catalog_snapshot_ref=SPEC_REF,
        messages_snapshot_ref=SPEC_REF,
        neighbor_baseline_ref="ex6://source/base/"+truth["base_head_sha"])
    c3=prepare_pg11_c3(
        pg11_c2=c2,suppression_observations=[],waiver_observations=[],
        std_gen_05_source_ref=SPEC_REF+"#CHG-0015")
    # Process-only REM-D4 points to real visible test AND AOSP failure.
    process=rem_d4_process()
    for trace in traces:
        for link in trace["links"]:
            if link["requirement_ref"].endswith("#REM-D4"):
                link["evidence_ref"]=process["visible_test_ref"]
                link["change_reason_ref"]=process["aosp_receipt_ref"]
    c4=prepare_pg11_c4(
        pg11_c1=c1,pg11_c2=c2,pg11_c3=c3,
        declared_diff=diff,authorized_scope=auth,trace_observations=traces)
    reviews=[{
        "path":x["path"],"builder_principal_ref":BUILDER,
        "reviewer_principal_ref":REVIEWER,
        "reviewer_role_ref":"ex6://unattested/independent-review-role",
        "builder_provenance_ref":RUN_REF,
        "reviewer_provenance_ref":"ex6://unattested/independent-review",
        "review_scope_ref":RUN_REF+"#native-verified-patch",
        "reviewer_is_builder_reported":False,
        "reviewer_independence_reported":True,
    } for x in truth["hunks"]]
    c5=prepare_pg11_c5(pg11_c4=c4,review_observations=reviews,
                        review_policy_ref="ex6://unattested/reviewer-policy")
    return {"c1":c1,"c2":c2,"c3":c3,"c4":c4,"c5":c5,
            "diff":diff,"traces":traces,"auth":auth,"rem_d4":process,
            "production_authority":False}

def make_pg12_v2(pg11=None,truth=None):
    """Same V2 stage structure as predecessor, only EX6 source/bundle inputs."""
    from pg12_c1_candidate_identity_v2 import prepare_pg12_c1
    from pg12_c2_execution_inputs_usage_candidate_v2 import prepare_pg12_c2
    from pg12_c3_check_results_link_candidate_v2 import prepare_pg12_c3
    from pg12_c4_persistence_readback_request_candidate_v2 import prepare_pg12_c4
    truth=truth or source_truth()
    pg11=pg11 or make_pg11_v2(truth)
    d=observed()
    changed=[{
        "path":x["path"],"change_type":"ADDED","old_path":None,
        "object_type":"blob","object_oid":x["git_blob_oid"],
        "old_object_oid":None} for x in truth["hunks"]]
    builder_bindings=[{
        "path":x["path"],"builder_principal_ref":BUILDER,
        "builder_provenance_ref":RUN_REF} for x in truth["hunks"]]
    c1=prepare_pg12_c1(
        pg11_c5=pg11["c5"],repo_ref=truth["repo_full_name"],
        base_commit_sha=truth["base_head_sha"],candidate_commit_sha=N,
        candidate_tree_sha=TREE,diff_sha256=truth["patch_sha256"],
        changed_objects=changed,builder_principal_ref=BUILDER,
        builder_provenance_ref=RUN_REF,builder_bindings=builder_bindings)
    row={"stage_ref":"PG-07-EX6-NATIVE-API",
         "input_tokens":0,"output_tokens":0,"cached_input_tokens":0,
         "cost_reported":"0","wasted_cost_reported":"0"}
    # Zero *API* calls only. Subscription and native model tokens NOT_EVALUATED.
    c2=prepare_pg12_c2(
        pg12_c1=c1,context_id="ex6://source/task-pack/"+truth["task_pack_sha256"],
        catalog_version_ref=SPEC_REF,
        skill_versions=[{"name":"programming-worker-v0.8",
                         "version_ref":"ex6://vendor/programming-agent/v0.8"}],
        stack_profile_ref="ex6://stack/java21-maven-spring-boot",
        provider_ref="ex6://provider/chatgpt-native",model_ref="GPT_NATIVE",
        ekb_snapshot_ref=SPEC_REF,
        toolchain_versions=[
            {"name":"java","version_ref":active_ref()+"#java21"},
            {"name":"maven","version_ref":active_ref()+"#candidate/commands/build"},
            {"name":"google-java-format","version_ref":d["formatter_sha256"]}],
        linter_config_sha256=config_sha(d,"format_aosp"),
        optimization_mode="HYBRID",
        usage_totals={**row,"stage_ref":"TOTAL"},usage_by_stage=[row],
        extra_queries=[{
            "query_id":"EX6_NATIVE_SUBSCRIPTION_UNATTESTED",
            "reason_type":"EVIDENCE_GAP",
            "resolver_ref":"ex6://owner/native-cost",
            "exact_query_ref":RUN_REF+"#cost.json/NOT_EVALUATED"}],
        identifier_term_map=[{
            "identifier_ref":x["path"]+"#"+Path(x["path"]).stem,
            "term_ids":x["requirements"],"glossary_source_ref":SPEC_REF}
            for x in truth["hunks"]],
        billing_currency="USD")
    checks=[{
        "checkpoint_code":f"PG-{stage:02d}_C{i}",
        "candidate_identity_sha256":c1["candidate_sha256"],
        "check_contract_ref":("ex6://lf/pg"+str(stage)+"/c"+str(i)),
        "result_ref":None,"result_digest_sha256":None,
        "runner_ref":active_ref(),"observed_outcome":"NOT_RUN",
        "execution_receipt_ref":None,
    } for stage,max_c in ((8,8),(11,5)) for i in range(1,max_c+1)]
    c3=prepare_pg12_c3(pg12_c2=c2,
        candidate_identity_sha256=c1["candidate_sha256"],
        check_observations=checks)
    c4=prepare_pg12_c4(pg12_c3=c3,
        storage_contract_ref="ex6://pg12/disposable-postgres/readback-v2",
        authorized_writer_ref="ex6://pg12/disposable-local-writer",
        readback_contract_ref="ex6://pg12/jsonb-readback-contract-v2",
        record_key_ref="ex6://pg12/N/"+N,
        expected_store_namespace="pg12_test_ex6")
    return {"c1":c1,"c2":c2,"c3":c3,"c4":c4,
            "checks":checks,"pg11":pg11,"production_authority":False}

def make_pg13_v2(pg12=None,truth=None):
    """Original PG13 C1-C3 and exact C4→C1 bridge; no production freeze."""
    from pg13_c1_freeze_intent_candidate_v2 import prepare_pg13_c1
    from pg13_c2_rebuild_comparison_candidate_v2 import prepare_pg13_c2
    from pg13_c3_mutation_block_candidate_v2 import prepare_pg13_c3,SCENARIOS
    from pg13_pg12_exact_freeze_bridge_v2 import bridge_pg12_c4_to_pg13_c1
    truth=truth or source_truth()
    pg12=pg12 or make_pg12_v2(truth=truth)
    d=observed()
    c1=prepare_pg13_c1(
        pg12_c4=pg12["c4"],candidate_commit_sha=N,candidate_tree_sha=TREE,
        freeze_policy_ref="ex6://pg13/immutable-local-only",
        freeze_request_ref="ex6://pg13/format-N-then-N1/"+N)
    bridge=bridge_pg12_c4_to_pg13_c1(
        pg12_c1=pg12["c1"],pg12_c4=pg12["c4"],pg13_c1=c1)
    # An unchanged SHA from one observation is NOT an independent rebuild.
    # We record the same source digest in both sides, but this is a source
    # declaration only; c2.rebuild_execution_verified remains False.
    candidate=d["snapshots"][1]
    reported_sha=candidate["commands"]["build"]["stdout"]["sha256"]
    c2=prepare_pg13_c2(
        pg13_c1=c1,rebuild_observations=[{
            "artifact_ref":active_ref()+"#candidate/maven/stdout-only",
            "baseline_digest_sha256":reported_sha,
            "rebuild_digest_sha256":reported_sha,
            "difference_ref":None}],
        build_recipe_ref=active_ref()+"#candidate/commands/build",
        environment_lock_ref=d["formatter_sha256"])
    scenarios=[{
        "scenario_code":code,
        "attempt_ref":"ex6://pg13/local-mutation/"+code,
        "expected_verdict":"BLOCK",
        "evidence_ref":"ex6://pg13/pending-execution/"+code,
    } for code in sorted(SCENARIOS)]
    c3=prepare_pg13_c3(pg13_c2=c2,mutation_scenarios=scenarios,
        policy_ref="ex6://pg13/local-immutable-refs")
    return {"pg12":pg12,"c1":c1,"c2":c2,"c3":c3,
            "bridge":bridge,"production_authority":False}


def make_pg14_v2(pg13=None,local_freeze=None,truth=None):
    """Original PG14 v2 source-only Testing fixture; real Analysis NOT READY."""
    from pg14_c1_testing_execution_contract_candidate_v2 import prepare_pg14_c1
    from pg14_c2_testing_payload_candidate_v2 import prepare_pg14_c2
    from pg14_c2_completeness_guard_v2 import validate_pg14_c2_completeness
    from pg14_c3_testing_admission_readback_request_candidate_v2 import prepare_pg14_c3
    from pg14_pg13_freeze_bridge_v2 import bridge_pg13_to_pg14
    from pg14_local_testing_receiver_v2 import simulate_testing_receiver
    from ex6_local_freeze_v1 import local_freeze_and_attacks
    truth=truth or source_truth()
    pg13=pg13 or make_pg13_v2(truth=truth)
    if local_freeze is None:
        local_freeze=local_freeze_and_attacks()
    if local_freeze["source_commit"]!=N or local_freeze["blocked_mutation_count"]!=5:
        raise AssertionError("EX6_PG14_LOCAL_GIT_FREEZE_NOT_VERIFIED")
    contract_path=Path(__file__).resolve().parents[2]/"wave1_boundary_contracts"/"testing_admission_contract_v1.json"
    contract=json.loads(contract_path.read_text())
    analysis={
        "package_ref":"ex6://analysis/fixture-unattested/not-ready",
        "package_sha256":h({"status":"NOT_READY","spec":SPEC_REF,"commit":N}),
        "source_currentness_ref":SPEC_REF,
        "ready_verified":False,
    }
    identity=pg13["pg12"]["c1"]
    c1=prepare_pg14_c1(
        pg13_c3=pg13["c3"],admission_contract=contract,
        analysis_package_ref=analysis["package_ref"],
        analysis_package_sha256=analysis["package_sha256"],
        source_currentness_ref=analysis["source_currentness_ref"],
        frozen_candidate_ref="ex6://pg13/local-git-freeze/"+N,
        frozen_candidate_sha256=identity["candidate_sha256"])
    # Original V2 Git bridge mandates literal Git ref syntax. All new source
    # refs remain ex6://; this is the *actual local* refs/tags/frozen namespace.
    bridge=bridge_pg13_to_pg14(
        pg12_c1=identity,pg13_bridge=pg13["bridge"],
        pg13_c1=pg13["c1"],pg13_c2=pg13["c2"],pg13_c3=pg13["c3"],
        pg14_c1=c1,freeze_tag_ref="refs/tags/frozen/"+N,
        freeze_tag_oid=local_freeze["local_tag_oid"],
        analysis_package_observation=analysis)
    obligations=[{
        "obligation_ref":req,
        "spec_ref":SPEC_REF+"#"+req,
        "test_case_ref":active_ref()+"#candidate/commands/visible_ex6" if req=="REM-D4"
                        else RUN_REF+"#visible-tests/ex6",
        "expected_oracle_ref":"ex6://holdout/sha256/"+truth["holdout_sha256"]+"/PASS",
    } for req in truth["requirements"]]
    c2=prepare_pg14_c2(
        pg14_c1=c1,catalog_version_ref=SPEC_REF,
        spec_test_obligations=obligations,
        blind_test_contract_ref="fn_submit_blind_test_contract",
        pending_copy_texts=[],required_obligation_ref="REM-D1",
        copy_applicability_ref="ex6://not-applicable/no-UI-copy-time-service")
    completeness=validate_pg14_c2_completeness(c2)
    c3=prepare_pg14_c3(
        pg14_c2=c2,
        testing_admission_endpoint_ref="ex6://testing/local-only-unattested",
        readback_contract_ref="ex6://pg14/testing-readback-v2-disposable",
        request_key_ref="ex6://pg14/local-request/"+N)
    verdict=simulate_testing_receiver(
        pg14_bridge=bridge,pg14_c1=c1,pg14_c2=c2,pg14_c3=c3,
        request_payload=c3["admission_request"])
    tampered=json.loads(json.dumps(c3["admission_request"]))
    tampered["frozen_candidate_sha256_reported"]="f"*64
    blocked=simulate_testing_receiver(
        pg14_bridge=bridge,pg14_c1=c1,pg14_c2=c2,pg14_c3=c3,
        request_payload=tampered)
    return {"pg13":pg13,"c1":c1,"c2":c2,"c3":c3,
            "bridge":bridge,"completeness":completeness,
            "verdict":verdict,"tampered_verdict":blocked,
            "local_freeze":local_freeze,"production_authority":False}
