"""PG07 original v1 producers supplied with EX6 public task, patch, receipts.

Only the model token estimator/budget and formatting-example declarations lack
native source receipts: they are explicitly UNATTESTED in this candidate.
"""
from __future__ import annotations

import json
from pathlib import Path
from ex6_source_truth_v1 import source_truth, pinned_public_file, SPEC_REF, TASK_REF, RUN_REF
from ex6_pg06_evidence_v1 import source_evidence

def make_pg07(pg06, pg05, truth=None):
    from pg07_c1_worker_dispatch_plan_v1 import prepare_pg07_c1
    from pg07_c2_task_batch_projection_v1 import prepare_pg07_c2
    from pg07_c3_context_budget_projection_v1 import prepare_pg07_c3
    from pg07_c4_contract_first_standards_candidate_v1 import prepare_pg07_c4
    from pg07_c5_iteration_guard_candidate_v1 import prepare_pg07_c5
    from pg07_c6_worker_batch_evidence_candidate_v1 import prepare_pg07_c6
    truth=truth or source_truth()
    task=json.loads(pinned_public_file("ex6_task_registration.json"))["task_spec"]
    sols=pg05["handoff"]["solutions"]
    sids=[x["solution_id"] for x in sols]
    if len(sids)!=1:
        raise ValueError("EX6_PG07_ONE_BATCH_EXPECTED")
    sid=sids[0]
    cost=truth["cost"]
    if cost["api_calls"]!=0:
        raise ValueError("EX6_PG07_NATIVE_API_CALLS_MISMATCH")
    run={
        "run_ref": RUN_REF,
        "provider": "chatgpt-native",
        "model_id": "GPT_NATIVE",
        "model_profile_ref": "ex6://unattested/chatgpt-native-context-window",
        "pricing_ref": RUN_REF+"#cost.json/incremental_api",
        "pricing_currency": "USD",
        # Rate refers to incremental API only, not subscription price.
        # A zero API call does NOT establish model token pricing.
        "input_price_per_million": "0",
        "output_price_per_million": "0",
        "cached_input_price_per_million": "0",
        "lane_executor_ref":"ex6://sandbox/workflows/worker-native.yml",
        "worker_contract_ref":"ex6://vendor/programming-agent/worker-v0.8",
        "worker_version":"0.8",
    }
    tasks=[{
        "solution_id":sid,"agent_task_id":1,
        "task_binding_ref":TASK_REF,
        "base_head_sha":task["base_head_sha"],
        "source_snapshot_sha256":task["source_snapshot_sha256"],
        "worker_spec_ref":TASK_REF+"#task_spec",
        "task_execution_authority_ref":"ex6://unattested/owner-sandbox-only",
    }]
    c1=prepare_pg07_c1(pg05_exit=pg05["handoff"],pg06_c5=pg06["c5"],
                        run_binding=run,worker_task_bindings=tasks)
    projection={
        **task,
        "schema_version":2,
        "expected_change":"three new reminder statistics Java files",
        "human_story":"Read-only reminder statistics from Lote D",
        "functional_contract":{"acceptance_criteria":truth["requirements"]},
        "scope":{"in_scope":task["write_path_patterns"],
                 "out_of_scope":task["protected_path_patterns"],
                 "must_not_change":task["protected_path_patterns"]},
        "cases":[],"dependency_resolution":{},"dependency_task_ids":[],
        "required_tests":[r["name"] for r in task["acceptance_commands"]],
        "required_evidence":["native-verified-patch","status.json","feedback.json"],
        "blocked_if":["write outside allowed scope","modify protected paths"],
        "files_expected":task["write_path_patterns"],
        "platform_refs":[],"interface_refs":[],
        "acceptance_commands":[r["argv"] for r in task["acceptance_commands"]],
        "max_context_bytes":task["max_context_bytes"],
    }
    # Do not mutate the authoritative v1 registered task: this is the PG07
    # projection/envelope schema v2 required by the *original* LF producer.
    spec=[{"solution_id":sid,"function_result_ref":TASK_REF+"#projection-v2",
           "worker_spec":projection,
           "source_snapshot_sha256":task["source_snapshot_sha256"]}]
    oracle=[{"solution_id":sid,
             "verifier_only_ref":"ex6://verifier-only/sha256/"+truth["holdout_sha256"],
             "oracle_subject_sha256":truth["holdout_sha256"],
             "access_policy":"VERIFIER_ONLY"}]
    c2=prepare_pg07_c2(pg07_c1=c1,worker_spec_projections=spec,
                        verifier_oracle_bindings=oracle)
    # The EX6 receipts do not contain a native model context-window size
    # or token estimates. These are shape-only declared bounds, not an
    # authenticated estimate. Never claim C3 budget verified.
    profile={"profile_ref":run["model_profile_ref"],"provider":run["provider"],
          "model_id":run["model_id"],"context_window_tokens":200000,
          "reserved_output_tokens":16000,"reserved_system_tokens":4000,
          "safety_margin_tokens":4000,
          "token_estimator_ref":"ex6://unattested/token-estimator",
          "budget_policy_ref":"ex6://unattested/native-model-context-budget",
          "budget_capability":"CONTEXT_BUDGET_GOVERNANCE"}
    selections=[{"solution_id":sid,"mandatory_ref_ids":["STD-EX6-LOTE-D"],
        "reference_catalog":[{
             "ref_id":"STD-EX6-LOTE-D","source_ref":SPEC_REF,
             "source_sha256":truth["source_snapshot_sha256"],"kind":"STD",
             "material":True,"delivery":"EAGER","estimated_tokens":100,
             "estimated_bytes":400,"role":"REQUIRED"}],
        "stable_cache_refs":[],"token_estimate_ref":"ex6://unattested/token-estimate",
        "estimated_static_tokens":100,"estimated_dynamic_tokens":0,
        "estimated_jit_tokens":0,"estimated_context_bytes":400}]
    c3=prepare_pg07_c3(pg07_c1=c1,pg07_c2=c2,
                        model_context_profile=profile,task_context_selections=selections)
    catalog={"catalog_ref":SPEC_REF,"catalog_sha256":truth["source_snapshot_sha256"],
       "catalog_version":"ex6-source-v1","selection_ref":TASK_REF,
       "entries":[{"rule_id":"STD-EX6-LOTE-D","kind":"STD",
          "source_ref":SPEC_REF,"source_sha256":truth["source_snapshot_sha256"],
          "version":"ex6-base",
          "ok_example_ref":"ex6://unattested/standard-example-ok",
          "no_example_ref":"ex6://unattested/standard-example-no",
          "applies_to_solution_ids":[sid]}]}
    plans=[{"solution_id":sid,"required_rule_ids":["STD-EX6-LOTE-D"],
       "contract_first_ref":SPEC_REF,"contract_first_rule_id":"STD-EX6-LOTE-D",
       "formatter_commands":[{"command_id":"fmt-"+sid,
             "formatter_tool_ref":"ex6://pending-execution/formatter",
             "command_ref":"ex6://pending-execution/formatter-command",
             "scope_ref":"ex6://scope/apps/time-service/src/main/java",
             "expected_artifact_ref":"ex6://pending-execution/formatter-artifact"}],
       "formatter_plan_ref":"ex6://pending-execution/formatter-plan"}]
    c4=prepare_pg07_c4(pg07_c1=c1,pg07_c2=c2,pg07_c3=c3,
                       standards_catalog_selection=catalog,solution_policy_plans=plans)
    c5=prepare_pg07_c5(pg07_c2=c2,pg07_c3=c3,pg07_c4=c4,iteration_proposals=[])
    evidence=[{"solution_id":sid,"batch_id":"ex6://batch/EX6-SOL-001",
       "execution_ref":RUN_REF,
       "context_pack_ref":"ex6://source/task-pack/"+truth["task_pack_sha256"],
       "candidate_head_sha":"13ef9c319fb62f7e08f6f030d447c60ee7bfa7f5",
       "diff_ref":RUN_REF+"#native-verified-patch/worker.patch",
       "diff_sha256":truth["patch_sha256"],
       "changed_paths":truth["write_paths"],
       "input_refs":[TASK_REF,SPEC_REF],
       "applied_rule_ids":["STD-EX6-LOTE-D"],
       "formatter_receipt_refs":["ex6://pending-execution/format-lint"],
       "worker_receipt_ref":RUN_REF+"#status.json",
       "worker_receipt_sha256":
           "c2725691a6f941648becd262ff45a51b3bcb1a883ac0fd81b274019edc0cb6af",
       "provider_usage_receipt_refs":[RUN_REF+"#cost.json"]}]
    c6=prepare_pg07_c6(pg07_c1=c1,pg07_c2=c2,pg07_c3=c3,pg07_c4=c4,
                       pg07_c5=c5,worker_batch_evidence=evidence)
    return locals()
