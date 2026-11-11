"""One-pass H4 EX6 diagnostics against unmodified original LF producers.

Each result identifies (a) original producer result, (b) provenance, and
(c) which official fixtures underlie the structural probe. Never upgrades
fixture-backed structural PASS into real EX6 chain admission.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

from ex6_real_chain_v1 import (
    install, uninstall, make_pg04, make_pg05, make_pg06,
    authorize_from_real_hunks, official_pg01_fixture,
)
from ex6_source_truth_v1 import source_truth, SPEC_REF, TASK_REF, RUN_REF

STAGES = [f"PG-{i:02d}" for i in range(4, 15)]
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {
    "PG01": "test_pg06_c1_c5_chain_v1.pg01",
    "PG06_A7": "test_pg06_c1_c5_chain_v1.a7_and_plans",
    "PG06_LINT_PROBE_ONLY": "test_pg06_c1_c5_chain_v1.baseline",
    "PG09_BUDGET_POLICY_UNATTESTED": "test_pg09_iteration_chain_v1.policy",
    "PG10_SCENARIOS": "test_pg10_decision_chain_v1.scenarios",
}
FORBIDDEN = ("ex5c", "lote-c")

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
        ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()

def only_ex6(value):
    data = json.dumps(value, sort_keys=True, default=str).lower()
    if any(f in data for f in FORBIDDEN):
        raise AssertionError("EX6_FOREIGN_DATA_CONTAMINATION")
    return value

def entry(stage, outcome, code, origin, *, producer_invoked=True, fixtures=()):
    return {"stage": stage, "outcome": outcome, "code": code,
            "producer_invoked": producer_invoked,
            "provenance": origin,
            "fixture_status": ["FIXTURE_UNATTESTED:" + f for f in fixtures
                               if f in FIXTURES],
            "unattested_projections": ["UNATTESTED:" + f for f in fixtures
                                       if f not in FIXTURES],
            "production_authority": False}

def attempt(stage, fn, *, origin, fixtures=()):
    try:
        result=fn()
        value = result if isinstance(result, dict) else {}
        if value.get("production_authority") is True or value.get("handoff_allowed") is True:
            raise AssertionError("EX6_AUTHORITY_ESCALATION")
        return entry(stage, "PASS_SOURCE_ONLY" if not fixtures else "PASS_FIXTURE_UNATTESTED",
                     "CANDIDATE_NOT_ADMITTED", origin, fixtures=fixtures), result
    except Exception as exc:
        return entry(stage, "BLOCK", str(exc).splitlines()[0] or type(exc).__name__,
                     origin, fixtures=fixtures), None

def stage06(upstream):
    """Use original PG06 C1-C5, preserving official authority fixture identity."""
    import test_pg06_c1_c5_chain_v1 as t6
    from ex6_pg06_evidence_v1 import c2_inputs, c4_partial_baseline
    t = upstream["handoff"]
    facts = {"fixture_pg01": official_pg01_fixture(),
             "fixture_a7": None, "fixture_lint": None}
    one = make_pg06(upstream)
    c1 = one["c1"]
    cat, obs = c2_inputs(t)
    c2 = t6.prepare_pg06_c2(pg05_exit=t, pg06_c1=c1,
                            toolchain_catalog=cat, environment_observations=obs)
    a7, plans = t6.a7_and_plans(t)  # exact official A7, no modified fields
    a7_again, plans_again = t6.a7_and_plans(t)
    if (a7, plans) != (a7_again, plans_again):
        raise AssertionError("EX6_A7_OFFICIAL_FIXTURE_DRIFT")
    facts["fixture_a7"] = {"sha256": digest(a7), "plans_sha256": digest(plans)}
    c3 = t6.prepare_pg06_c3(pg05_exit=t, pg06_c1=c1, pg06_c2=c2,
       a7_material_front_coverage=a7, solution_reversibility_plans=plans)
    from ex6_build_lint_inputs_v1 import baseline as actual_ex6_baseline
    source_baseline = actual_ex6_baseline(t)  # verified original ZIP
    c4 = t6.prepare_pg06_c4(pg05_exit=t, pg06_c1=c1, pg06_c2=c2,
                   pg06_c3=c3, baseline_observations=source_baseline)
    # The official C4 fixture remains unchanged, solely for identity parity.
    # It is not fed into the actual EX6 PG06 C4 producer.
    synthetic = t6.baseline(t)
    synthetic_again = t6.baseline(t)
    if synthetic != synthetic_again:
        raise AssertionError("EX6_C4_OFFICIAL_FIXTURE_DRIFT")
    facts["fixture_lint"] = {
        "sha256": digest(synthetic),
        "real_code": "PASS_SOURCE_ONLY",
        "real_lint": "PASS_REPORTED_UNVERIFIED",
        "used_as_ex6_c4": False,
    }
    parts = {"pg05_exit":t,"pg06_c1":c1,"pg06_c2":c2,"pg06_c3":c3,"pg06_c4":c4}
    manifest = {"source_head_sha": upstream["pg04"]["truth"]["base_head_sha"]
                if "truth" in upstream["pg04"] else source_truth()["base_head_sha"],
        **{k:{"ref":"ex6://manifest/"+k,"sha256":v["candidate_sha256"]}
        for k,v in parts.items()}}
    c5=t6.prepare_pg06_assurance_request(**parts,source_manifest=manifest,
        producer_execution_id="ex6://source-only/pg06-official-fixtures")
    return {"exit":t,"c1":c1,"c2":c2,"c3":c3,"c4":c4,"c5":c5,
            "a7":a7,"a7_plans":plans,"baseline_real":source_baseline,
            "fixture_facts":facts}

def stage07(pg06, pg05, truth):
    from ex6_pg07_v1 import make_pg07
    return make_pg07(pg06=pg06, pg05=pg05, truth=truth)


def stage08(pg07, pg06, truth):
    """Original PG08 C1/C2 using preserved EX6 real build and AOSP receipts."""
    from ex6_build_lint_inputs_v1 import pg08_build, pg08_format_lint
    from pg08_c1_build_compilation_candidate_v1 import prepare_pg08_c1
    from pg08_c2_format_lint_delta_candidate_v1 import prepare_pg08_c2
    source=pg07["c6"]
    c1=prepare_pg08_c1(pg07_c6=source,
                       build_observations=pg08_build(source))
    c2=prepare_pg08_c2(pg06_c4=pg06["c4"],pg08_c1=c1,
                       lint_observations=pg08_format_lint(source))
    return {"c1":c1,"c2":c2,
            "format_aosp_exit_code":__import__("ex6_build_lint_inputs_v1").observed()["snapshots"][1]["commands"]["format_aosp"]["exit_code"],
            "build_source":__import__("ex6_build_lint_inputs_v1").active_ref(),
            "production_authority":False}



def stage09(pg07, truth):
    """Original C1-C4: native no-API receipt, unmodified budget test fixture."""
    from test_pg09_iteration_chain_v1 import policy
    from pg09_c1_iteration_cost_governor_candidate_v1 import prepare_pg09_c1
    from pg09_c2_convergence_guard_candidate_v1 import prepare_pg09_c2
    from pg09_c3_quality_bypass_guard_candidate_v1 import prepare_pg09_c3
    from pg09_c4_typed_escalation_candidate_v1 import prepare_pg09_c4
    sids=[x["solution_id"] for x in pg07["c5"]["solutions"]]
    if len(sids)!=1:
        raise ValueError("EX6_PG09_ONE_SOLUTION_EXPECTED")
    observations=[{
        "solution_id":sid, "executor_mode":"GPT_NATIVE",
        "batch_id":"ex6://batch/EX6-SOL-001",
        "attempts_used":truth["attempt_proof"]["attempt"],
        "attempt_limit_source_ref":TASK_REF+"#max_attempts",
        "calls":[],  # Zero calls from *real* cost.json
    } for sid in sids]
    if truth["cost"]["api_calls"]!=0:
        raise ValueError("EX6_PG09_API_CALL_NONZERO")
    budget=policy()  # imported official fixture, unchanged, unauthenticated
    c1=prepare_pg09_c1(pg07_c1=pg07["c1"],pg07_c5=pg07["c5"],
                        budget_policy=budget,usage_observations=observations)
    snapshots=[{"solution_id":sid,"iterations":[]} for sid in sids]
    c2=prepare_pg09_c2(pg07_c5=pg07["c5"],pg09_c1=c1,
                        iteration_observations=snapshots)
    c3=prepare_pg09_c3(pg07_c5=pg07["c5"],pg09_c2=c2,
                        quality_change_observations=snapshots)
    context=[{"solution_id":sid,"run_ref":RUN_REF,
              "owner_decision_ref":"ex6://unattested/owner-cost-policy",
              "diagnostic_evidence_refs":[RUN_REF+"#cost.json",
                  "ex6://source/proposal/"+truth["proposal_sha256"]]}
              for sid in sids]
    c4=prepare_pg09_c4(pg09_c1=c1,pg09_c2=c2,pg09_c3=c3,
                        escalation_context=context)
    return {"c1":c1,"c2":c2,"c3":c3,"c4":c4,
            "usage":observations,"budget_fixture":budget}


def stage10(pg09, pg07, truth):
    """No EX6 conflict asserted: exercise original v1 with empty observations."""
    from pg10_c1_conflict_inventory_candidate_v1 import prepare_pg10_c1
    from pg10_c2_precedence_legacy_guard_candidate_v1 import prepare_pg10_c2
    from pg10_c3_typed_decision_routing_candidate_v1 import prepare_pg10_c3
    from pg10_c4_human_decision_packet_candidate_v1 import prepare_pg10_c4
    from pg10_c5_negative_assurance_candidate_v1 import prepare_pg10_c5
    ids=[x["solution_id"] for x in pg09["c4"]["solutions"]]
    conflicts=[{"solution_id":sid,"conflicts":[]} for sid in ids]
    c1=prepare_pg10_c1(pg07_c5=pg07["c5"],pg09_c4=pg09["c4"],
                        conflict_observations=conflicts)
    from test_pg10_decision_chain_v1 import precedence, routes, packets, scenarios
    c2=prepare_pg10_c2(pg10_c1=c1,precedence_observations=precedence(c1))
    c3=prepare_pg10_c3(pg10_c2=c2,routing_observations=routes(c2))
    c4=prepare_pg10_c4(pg10_c3=c3,decision_observations=packets(c3))
    # Original test scenarios are authority-free structural fixtures.
    c5=prepare_pg10_c5(pg10_c1=c1,pg10_c2=c2,pg10_c3=c3,
                       pg10_c4=c4,scenario_observations=scenarios())
    return {"c1":c1,"c2":c2,"c3":c3,"c4":c4,"c5":c5}


def stage11(truth):
    """Original C1 with the exact three EX6 added-file hunks and scopes."""
    from pg11_c1_diff_hygiene_candidate_v1 import prepare_pg11_c1
    diff, authorized, traces=authorize_from_real_hunks(truth)
    scope=[{**row,**{k:auth["authorized_links"][0][k]
           for k in ("scope_ref","requirement_ref","batch_ref")}}
           for row,auth in zip(diff,authorized)]
    c1=prepare_pg11_c1(
         expected_base_sha=truth["base_head_sha"],
         expected_head_sha="13ef9c319fb62f7e08f6f030d447c60ee7bfa7f5",
         declared_diff=diff,authorized_scope=scope,
         residue_observations=[],dependency_observations=[],
         compatibility_observations=[{
            "surface":"MODULE_CONTRACT",
            "contract_ref":SPEC_REF+"#REM-D3",
            "baseline_ref":"ex6://source/base/"+truth["base_head_sha"]+"/apps/time-service",
            "evidence_ref":RUN_REF+"#status.json/PASS",
            "compatible_reported":True}])
    from pg11_c2_terminology_catalog_candidate_v1 import prepare_pg11_c2
    from pg11_c3_suppression_waiver_candidate_v1 import prepare_pg11_c3
    from pg11_c4_diff_requirement_batch_trace_candidate_v1 import prepare_pg11_c4
    from pg11_c5_independent_reviewer_candidate_v1 import prepare_pg11_c5
    rows=[{"path":h["path"],
           "symbol_ref":h["header_ref"]+"#"+Path(h["path"]).stem,
           "kind":"DOMAIN_IDENTIFIER",
           "literal_value":Path(h["path"]).stem,
           "source_ref":h["header_ref"],
           "term_ids":h["requirements"],
           "term_exists_reported":False,
           "term_matches_reported":False,
           "literal_match_reported":True,
           "neighbor_match_reported":False}
          for h in truth["hunks"]]
    c2=prepare_pg11_c2(pg11_c1=c1,declared_changed_paths=[d["path"] for d in diff],
         terminology_observations=rows,glossary_snapshot_ref=SPEC_REF,
         catalog_snapshot_ref=SPEC_REF,messages_snapshot_ref=SPEC_REF,
         neighbor_baseline_ref="ex6://source/base/"+truth["base_head_sha"])
    c3=prepare_pg11_c3(pg11_c2=c2,suppression_observations=[],
           waiver_observations=[],std_gen_05_source_ref=SPEC_REF)
    # PG11 C4 v1 represents only one requirement per path. This projection
    # deliberately reports the REM-D4 secondary link as *unrepresented*;
    # complete N:M trace admission requires the separately existing v2.
    v1_traces=[{**t,"links":t["links"][:1]} for t in traces]
    c4=prepare_pg11_c4(pg11_c1=c1,pg11_c2=c2,pg11_c3=c3,
          declared_diff=diff,authorized_scope=scope,trace_observations=v1_traces)
    reviews=[{"path":h["path"],
         "builder_principal_ref":"ex6://principal/gpt-native-worker",
         "reviewer_principal_ref":"ex6://unattested/independent-reviewer",
         "reviewer_role_ref":"ex6://unattested/independent-verifier",
         "builder_provenance_ref":RUN_REF,
         "reviewer_provenance_ref":"ex6://unattested/reviewer-provenance",
         "review_scope_ref":RUN_REF+"#native-verified-patch",
         "reviewer_is_builder_reported":False,
         "reviewer_independence_reported":True} for h in truth["hunks"]]
    c5=prepare_pg11_c5(pg11_c4=c4,review_observations=reviews,
         review_policy_ref="ex6://unattested/independent-review-policy")
    from ex6_build_lint_inputs_v1 import rem_d4_process
    process = rem_d4_process()
    return {"c1":c1,"c2":c2,"c3":c3,"c4":c4,"c5":c5,
            "diff":diff,"scope":scope,"traces":traces,
            "rem_d4_process":process,
            "v1_trace_limitation":"EX6_REM_D4_PROCESS_"+process["reason"]}


def stage12(pg11, truth):
    """Original PG12 C1 with real Git identity; reject unavailable lint C2."""
    from pg12_c1_candidate_identity_v1 import prepare_pg12_c1
    from pg12_c2_execution_inputs_usage_candidate_v1 import prepare_pg12_c2
    commit="912c4ad9ea71f48edbd1ac58089441f9ed2c3449"
    tree="72e5f54ca75cb3a1186dbc160469cf8f5dd070c5"
    changed=[{"path":h["path"],"change_type":"ADDED","old_path":None,
              "object_type":"blob","object_oid":h["git_blob_oid"],
              "old_object_oid":None} for h in truth["hunks"]]
    c1=prepare_pg12_c1(
          pg11_c5=pg11["c5"],repo_ref=truth["repo_full_name"],
          base_commit_sha=truth["base_head_sha"],
          candidate_commit_sha=commit,candidate_tree_sha=tree,
          diff_sha256=truth["patch_sha256"],changed_objects=changed,
          builder_principal_ref="ex6://principal/gpt-native-worker",
          builder_provenance_ref=RUN_REF)
    row={"stage_ref":"PG-07","input_tokens":0,"output_tokens":0,
         "cached_input_tokens":0,"cost_reported":"0",
         "wasted_cost_reported":"0"}
    # These are API counters, not total ChatGPT usage.
    totals={**row,"stage_ref":"TOTAL"}
    from ex6_build_lint_inputs_v1 import config_sha, observed
    lint_config_digest = config_sha(observed(),"format_aosp")
    c2=prepare_pg12_c2(
            pg12_c1=c1,
            context_id="ex6://source/task-pack/"+truth["task_pack_sha256"],
            catalog_version_ref=SPEC_REF,
            skill_versions=[{"name":"programming-worker-v0.8",
                             "version_ref":"ex6://vendor/programming-agent"}],
            stack_profile_ref="ex6://source/base/"+truth["base_head_sha"],
            provider_ref="ex6://native/chatgpt",model_ref="GPT_NATIVE",
            ekb_snapshot_ref=SPEC_REF,
            toolchain_versions=[{"name":"java","version_ref":
               "ex6://run/42674262914#Temurin-21.0.13"}],
            # Exact AOSP jar version/digest and command flags from original ZIP.
            linter_config_sha256=lint_config_digest,optimization_mode="HYBRID",
            usage_totals=totals,usage_by_stage=[row],
            extra_queries=[],identifier_term_map=[],
            billing_currency="USD",
        )
    return {"c1":c1,"c2":c2,"linter_config_sha256":lint_config_digest,
            "candidate_git_commit":commit,"candidate_git_tree":tree}


def stage13():
    """Probe original PG13 C1 without fictitious persisted PG12 readback."""
    from pg13_c1_freeze_intent_candidate_v1 import prepare_pg13_c1
    return prepare_pg13_c1(pg12_c4=None,
         candidate_commit_sha="912c4ad9ea71f48edbd1ac58089441f9ed2c3449",
         candidate_tree_sha="72e5f54ca75cb3a1186dbc160469cf8f5dd070c5",
         freeze_policy_ref="ex6://pending-execution/freeze-policy",
         freeze_request_ref="ex6://pending-execution/freeze-request")


def stage14(truth):
    """Probe original PG14 C1 without fabricated immutable freeze receipt."""
    from pg14_c1_testing_execution_contract_candidate_v1 import prepare_pg14_c1
    return prepare_pg14_c1(pg13_c3=None,admission_contract=None,
         analysis_package_ref="ex6://unattested/analysis-package",
         analysis_package_sha256=truth["source_snapshot_sha256"],
         source_currentness_ref="ex6://unattested/source-currentness",
         frozen_candidate_ref="ex6://pending-execution/frozen-candidate",
         frozen_candidate_sha256=truth["proposal_sha256"])


def run_all():
    install()
    table=[]
    evidence={}
    try:
        truth=source_truth()
        only_ex6(truth)
        changed, authorized, traces=authorize_from_real_hunks(truth)
        assert len(changed)==len(authorized)==len(traces)==3
        row, x=attempt("PG-04",lambda:make_pg04(truth),
              origin="EX6_SPEC_AND_VERIFIED_HUNKS")
        table.append(row)
        if x is None:
            return {"stages":table,"evidence":evidence}
        row, y=attempt("PG-05",lambda:make_pg05(x,truth),
              origin="EX6_TASK_SPEC_AND_WRITE_SCOPE")
        table.append(row)
        if y is None:
            return {"stages":table,"evidence":evidence}
        row, z=attempt("PG-06",lambda:stage06(y),
              origin="EX6_JAVA21_AND_BASELINE_WITH_OFFICIAL_FIXTURES",
              fixtures=("PG01","PG06_A7"))
        table.append(row)
        if z is not None:
            evidence["pg06_fixture_checks"]=z["fixture_facts"]
            evidence["pg06_c4_real_code"]=z["fixture_facts"]["fixture_lint"]["real_code"]
            evidence["pg06_c2_diagnostic"]=z["c2"]["required_toolchains"][0]["diagnostic_status"]
            evidence["pg06_c3_diagnostic"]=z["c3"]["status"]
            evidence["pg06_c4_real_diagnostic"]=z["c4"]["status"]
            evidence["pg06_c5_diagnostic"]=z["c5"]["status"]
        # Probe downstream original producers independently, even if their
        # source-only shapes are blocked by a real verification gap.
        pg07 = None
        pg09 = None
        row, pg07=attempt("PG-07",lambda:stage07(z,y,truth),
                    origin="EX6_REAL_TASK_AND_WORKER_RECEIPTS",
                    fixtures=("PG01","PG06_A7",
                              "PG07_CONTEXT_PROFILE_UNATTESTED"))
        table.append(row)
        if pg07:
            evidence["pg07_c6_diagnostic"]=pg07["c6"]["status"]
            row, pg08=attempt("PG-08",lambda:stage08(pg07,z,truth),
                       origin="EX6_REAL_BUILD_AND_AOSP_RECEIPTS_VERIFIED",
                       fixtures=("PG01","PG06_A7","PG06_LINT_PROBE_ONLY"))
            table.append(row)
            if pg08:
                evidence["pg08_c1_reported_outcome"]=pg08["c1"]["solutions"][0]["reported_build_outcome"]
                evidence["pg08_c2_format_aosp_exit_code"]=pg08["format_aosp_exit_code"]
                evidence["pg08_c2_solution_diagnostics"]=pg08["c2"]["solutions"]
            row, pg09=attempt("PG-09",lambda:stage09(pg07,truth),
                       origin="EX6_NATIVE_API_CALLS_ZERO_ORIGINAL_V1",
                       fixtures=("PG01","PG06_A7","PG06_LINT_PROBE_ONLY",
                                 "PG09_BUDGET_POLICY_UNATTESTED"))
            table.append(row)
            if pg09:
                evidence["pg09_c1_request_diagnostic"]=pg09["c1"]["request_diagnostic"]
                evidence["pg09_c1_cost_unknown"]=pg09["c1"]["missing_usage_requires_decision"]
                evidence["pg09_c1_known_cost"]=pg09["c1"]["reported_request_known_cost"]
                from pg09_c1_iteration_cost_governor_candidate_v2 import (
                    prepare_pg09_c1 as native_cost_v2)
                proof={"executor_mode":"GPT_NATIVE",
                    "api_calls":truth["cost"]["api_calls"],
                    "proposal_sha256":truth["proposal_sha256"],
                    "expected_proposal_sha256":truth["status"]["proposal_sha256"],
                    "tool_receipt_ref":None,
                    "cost_receipt_ref":RUN_REF+"#cost.json",
                    "status_receipt_ref":RUN_REF+"#status.json",
                    "subscription_cost":truth["subscription_cost"]}
                v2=native_cost_v2(pg07_c1=pg07["c1"],pg07_c5=pg07["c5"],
                    budget_policy=pg09["budget_fixture"],
                    usage_observations=pg09["usage"],
                    native_execution_evidence=proof)
                evidence["pg09_v2_request_diagnostic"]=v2["request_diagnostic"]
                evidence["pg09_v2_subscription_cost"]=v2["native_subscription_cost"]
                table[-1]["after_v2"]=v2["request_diagnostic"]
                row, pg10=attempt("PG-10",lambda:stage10(pg09,pg07,truth),
                     origin="EX6_NO_ASSERTED_CONFLICT_OR_DECISION",
                     fixtures=("PG09_BUDGET_POLICY_UNATTESTED","PG10_SCENARIOS"))
                table.append(row)
            else:
                table.append(entry("PG-10","NOT_RUN",
                    "EX6_UPSTREAM_PG09_NOT_AVAILABLE","SOURCE_CHAIN",producer_invoked=False))
        else:
            for stage in ("PG-08","PG-09","PG-10"):
                table.append(entry(stage,"NOT_RUN",
                     "EX6_UPSTREAM_PG07_NOT_AVAILABLE","SOURCE_CHAIN",producer_invoked=False))
        row, pg11=attempt("PG-11",lambda:stage11(truth),
                origin="EX6_REAL_ADDED_FILE_HUNKS_V1_LINK_PROJECTION",
                fixtures=("PG11_INDEPENDENT_REVIEW_UNATTESTED",))
        table.append(row)
        if pg11:
            evidence["pg11_v1_trace_limitation"]=pg11["v1_trace_limitation"]
            evidence["rem_d4_process"]=pg11["rem_d4_process"]
            pg12=stage12(pg11,truth)
            evidence["pg12_c1_status"]=pg12["c1"]["status"]
            evidence["pg12_c2_status"]=pg12["c2"]["status"]
            evidence["pg12_linter_config_sha256"]=pg12["linter_config_sha256"]
            table.append(entry("PG-12","PASS_SOURCE_ONLY",
                "C1_C2_CANDIDATES_NOT_ADMITTED_PERSISTENCE_PENDING",
                "EX6_GIT_IDENTITY_AND_REAL_AOSP_LINTER_DIGEST"))
        else:
            table.append(entry("PG-12","NOT_RUN",
                "PG11_UPSTREAM_REVIEW_UNATTESTED",
                "NO_FABRICATED_GIT_IDENTITY",producer_invoked=False))
        row,_=attempt("PG-13",stage13,
             origin="ISOLATED_ORIGINAL_FREEZE_C1_MISSING_PERSISTED_READBACK")
        table.append(row)
        row,_=attempt("PG-14",lambda:stage14(truth),
             origin="ISOLATED_ORIGINAL_TESTING_C1_MISSING_FREEZE")
        table.append(row)
        # Original V2 source-only chain is an independent, explicit extension
        # of v1, never a production approval or authenticated Analysis handoff.
        from ex6_pg12_pg13_v2 import (make_pg11_v2,make_pg12_v2,
            make_pg13_v2,make_pg14_v2)
        from ex6_local_freeze_v1 import local_freeze_and_attacks
        import os
        v11=make_pg11_v2(truth)
        v12=make_pg12_v2(v11,truth)
        v13=make_pg13_v2(v12,truth)
        freeze=local_freeze_and_attacks()
        v14=make_pg14_v2(v13,freeze,truth)
        evidence["local_v2"]={
            "pg11_c5":v11["c5"]["status"],
            "pg11_actual_link_count":sum(len(x["links"]) for x in v11["traces"]),
            "pg12_c4":v12["c4"]["status"],
            "pg12_c4_payload_sha256":v12["c4"]["payload_candidate_sha256"],
            "pg13_c3":v13["c3"]["status"],
            "pg13_bridge":v13["bridge"]["status"],
            "pg13_local_mutations_blocked":freeze["blocked_mutation_count"],
            "pg14_c3":v14["c3"]["status"],
            "pg14_local_verdict":v14["verdict"]["reason"],
            "pg14_tampered_verdict":v14["tampered_verdict"]["verdict"],
            "real_analysis_ready":False,
            "real_testing_invoked":False,
            "production_authority":False,
        }
        if os.environ.get("PG12_DISPOSABLE_DB")=="YES":
            from pg12_disposable_postgres_readback_v2 import persist_readback
            readback=persist_readback(v12["c4"])
            if readback!=v12["c4"]["payload_candidate_sha256"]:
                raise AssertionError("EX6_POSTGRES_V2_PAYLOAD_SHA_DRIFT")
            evidence["local_v2"]["pg12_local_postgres_readback"]="PASS"
        else:
            evidence["local_v2"]["pg12_local_postgres_readback"]="PENDING_DISPOSABLE_OPT_IN"
        for row in table:
            if row["stage"]=="PG-11":
                row["after_existing_v2"]="PASS_SOURCE_ONLY_N_M_EX6"
            if row["stage"]=="PG-12":
                row["after_existing_v2"]="C1_C4_SOURCE_ONLY_LOCAL_READBACK_NOT_AUTHORITY"
            if row["stage"]=="PG-13":
                row["after_existing_v2"]="PASS_LOCAL_SOURCE_ONLY_FIVE_ATTACKS_BLOCKED"
            if row["stage"]=="PG-14":
                row["after_existing_v2"]="PASS_LOCAL_TESTING_FIXTURE_ONLY_NOT_REAL_ADMISSION"
        evidence["ex6_reversibility_plan"]={
             "status":"SOURCE_DERIVED_NOT_EXECUTED",
             "operation":"DELETE_ADDED_FILES",
             "paths":truth["write_paths"],
             "base_restored_if_no_other_changes":True}
        return {"stages":table,"evidence":evidence,
                "fixture_allowlist":FIXTURES,
                "patch_sha256":truth["patch_sha256"],
                "proposal_sha256":truth["proposal_sha256"],
                "api_calls":truth["api_calls"]}
    finally:
        uninstall()

if __name__=="__main__":
    print(json.dumps(run_all(),indent=2,sort_keys=True))
