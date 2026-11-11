"""Original EX6 source truth / true v1 producer attempts, no foreign fixtures."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import ex6_source_truth_v1 as source
import ex6_real_chain_v1 as chain


class EX6ChainV1Tests(unittest.TestCase):
    def test_real_public_source_and_three_hunks(self):
        truth = source.source_truth()
        self.assertEqual(truth["holdout_sha256"], source.EXPECTED_HOLDOUT)
        self.assertEqual(truth["holdout_result"], "PASS")
        self.assertEqual(truth["api_calls"], 0)
        self.assertEqual(truth["incremental_api_cost"], "0")
        self.assertEqual(sorted(x["path"] for x in truth["hunks"]), truth["write_paths"])
        self.assertEqual(len(truth["hunks"]), 3)
        self.assertFalse(truth["production_authority"])

    def test_authorization_is_exact_single_batch_and_scope_per_file(self):
        truth = source.source_truth()
        changed, authorization, traces = chain.authorize_from_real_hunks(truth)
        self.assertEqual(len(changed), len(authorization))
        self.assertEqual(len(traces), 3)
        for row in authorization:
            self.assertEqual(row["change_type"], "ADDED")
            self.assertEqual(len({a["batch_ref"] for a in row["authorized_links"]}), 1)
            self.assertEqual(len({a["scope_ref"] for a in row["authorized_links"]}), 1)
        self.assertEqual(sum(len(r["authorized_links"]) for r in authorization), 4)

    def test_no_foreign_exercise_data_or_references(self):
        data = json.dumps(source.source_truth(), sort_keys=True).lower()
        self.assertNotIn("ex5c", data)
        self.assertNotIn("lote-c", data)
        self.assertFalse(source.source_truth()["production_authority"])

    def test_install_uninstall_has_no_synthetic_pollution(self):
        before = sys.path[:]
        chain.install()
        self.assertNotEqual(before, sys.path)
        chain.uninstall()
        self.assertEqual(before, sys.path)

    def test_pg01_fixture_binding_is_official_and_sole_exception(self):
        chain.install()
        try:
            from test_pg06_c1_c5_chain_v1 import pg01
            official = pg01()
            imported = chain.official_pg01_fixture()
            self.assertEqual(imported, official)
            self.assertEqual(imported["pg01_decision_ref"], "fixture://pg01/currentness")
            self.assertEqual(imported["pg01_decision_sha256"], official["pg01_decision_sha256"])
            self.assertEqual(imported["authority_fingerprint_sha256"],
                             official["authority_fingerprint_sha256"])
            self.assertEqual(imported["source_snapshot_sha256"],
                             official["source_snapshot_sha256"])
            # The only non-EX6 provenance in downstream EX6 inputs is the
            # exact official PG01 fixture, not any copied synthetic setup.
            truth = source.source_truth()
            self.assertNotIn("fixture://", json.dumps(truth, sort_keys=True))
            self.assertNotIn("ex5c", json.dumps(truth, sort_keys=True).lower())
            self.assertNotIn("lote-c", json.dumps(truth, sort_keys=True).lower())
            pg05 = chain.make_pg05(chain.make_pg04(truth), truth)
            pg06 = chain.make_pg06(pg05)
            self.assertEqual(pg06["pg01_binding"], official)
            self.assertEqual(pg06["pg01_status"], "FIXTURE_UNATTESTED")
            self.assertFalse(pg06["production_authority"])
        finally:
            chain.uninstall()

    def test_pg06_c2_real_java21_pom_and_ci_log_not_synthetic(self):
        from ex6_pg06_evidence_v1 import source_evidence, c2_inputs
        facts = source_evidence()
        self.assertEqual(facts["java_version"], "21")
        self.assertEqual(facts["spring_boot_version"], "4.1.1")
        self.assertEqual(facts["temurin_version"], "21.0.13+9")
        self.assertEqual(facts["base_tree_sha"], facts["pr_head_tree_sha"])
        self.assertEqual(facts["pr_head_tree_sha"], facts["pr_merge_tree_sha"])
        chain.install()
        try:
            from pg06_c2_toolchain_environment_candidate_v1 import prepare_pg06_c2
            pg05 = chain.make_pg05()
            binding = chain.make_pg06(pg05)
            cat, obs = c2_inputs(pg05["handoff"])
            self.assertEqual(cat["requirements"][0]["version_exact"], "21")
            self.assertEqual(cat["profile_ref"], "stack://java21-maven-spring-boot")
            self.assertIn(facts["native_log_excerpt_sha256"],
                          obs["observations"][0]["evidence_ref"])
            result = prepare_pg06_c2(pg05_exit=pg05["handoff"],
                      pg06_c1=binding["c1"], toolchain_catalog=cat,
                      environment_observations=obs)
            self.assertEqual(result["status"], "CANDIDATE_NOT_ADMITTED")
            self.assertEqual(result["required_toolchains"][0]["diagnostic_status"],
                             "MATCH_REPORTED_UNVERIFIED")
            self.assertFalse(result["production_authority"])
        finally:
            chain.uninstall()

    def test_pg06_c4_baseline_is_partial_not_fabricated(self):
        from ex6_pg06_evidence_v1 import source_evidence, c4_partial_baseline
        facts = source_evidence()
        chain.install()
        try:
            pg05 = chain.make_pg05()
            partial = c4_partial_baseline(pg05["handoff"])
            self.assertEqual(partial["base_head_sha"],
                             "53ab6b1a85da95f3e2a38d7f3298af731c6698ab")
            self.assertEqual(partial["proven_build"]["check"], "backend (Maven verify)")
            self.assertEqual(partial["proven_build"]["tree_sha"],
                             facts["base_tree_sha"])
            self.assertEqual(partial["lint_status"], "pending-execution")
            self.assertEqual(partial["command_results"], [])
            self.assertNotIn("ex5c", json.dumps(partial).lower())
            self.assertNotIn("lote-c", json.dumps(partial).lower())
        finally:
            chain.uninstall()

    def test_one_pass_all_stages_real_producer_codes_and_fixture_ledger(self):
        import ex6_one_pass_v1 as unified
        result=unified.run_all()
        stages=result["stages"]
        self.assertEqual([x["stage"] for x in stages],
                         [f"PG-{n:02d}" for n in range(4,15)])
        by={x["stage"]:x for x in stages}
        self.assertEqual(by["PG-04"]["outcome"],"PASS_SOURCE_ONLY")
        self.assertEqual(by["PG-05"]["outcome"],"PASS_SOURCE_ONLY")
        self.assertEqual(by["PG-06"]["outcome"],"PASS_FIXTURE_UNATTESTED")
        self.assertEqual(by["PG-07"]["outcome"],"PASS_FIXTURE_UNATTESTED")
        self.assertEqual(by["PG-08"]["outcome"],"PASS_FIXTURE_UNATTESTED")
        self.assertEqual(result["evidence"]["pg08_c1_reported_outcome"],"REPORTED_PASS_UNVERIFIED")
        self.assertEqual(result["evidence"]["pg08_c2_format_aosp_exit_code"],1)
        self.assertEqual(by["PG-09"]["after_v2"],
                         "REPORTED_WITHIN_BUDGET_UNVERIFIED")
        self.assertEqual(by["PG-12"]["outcome"],"PASS_SOURCE_ONLY")
        self.assertEqual(result["evidence"]["pg12_c2_status"],"CANDIDATE_NOT_ADMITTED")
        self.assertEqual(by["PG-13"]["code"],"C1_UPSTREAM_SCHEMA")
        self.assertEqual(by["PG-14"]["code"],"C1_UPSTREAM_SCHEMA")
        self.assertEqual(result["evidence"]["pg06_c4_real_code"],
                         "PASS_SOURCE_ONLY")
        self.assertEqual(result["evidence"]["rem_d4_process"]["reason"],
                         "FORMAT_AOSP_EXIT_1")
        local_v2=result["evidence"]["local_v2"]
        self.assertEqual(local_v2["pg11_actual_link_count"],4)
        self.assertEqual(local_v2["pg12_c4"],"CANDIDATE_NOT_ADMITTED")
        self.assertEqual(local_v2["pg13_local_mutations_blocked"],5)
        self.assertEqual(local_v2["pg14_local_verdict"],
                         "LOCAL_FIXTURE_SHAPE_ACCEPTED_ONLY")
        self.assertEqual(local_v2["pg14_tampered_verdict"],"BLOCK")
        self.assertFalse(local_v2["real_analysis_ready"])
        self.assertFalse(local_v2["real_testing_invoked"])
        self.assertFalse(local_v2["production_authority"])
        self.assertEqual(by["PG-13"]["after_existing_v2"],
                         "PASS_LOCAL_SOURCE_ONLY_FIVE_ATTACKS_BLOCKED")
        self.assertEqual(by["PG-14"]["after_existing_v2"],
                         "PASS_LOCAL_TESTING_FIXTURE_ONLY_NOT_REAL_ADMISSION")
        self.assertEqual(result["evidence"]["pg09_c1_request_diagnostic"],
                         "REQUIRES_DECISION")
        self.assertEqual(result["evidence"]["pg09_v2_subscription_cost"],
                         "NOT_EVALUATED")
        self.assertEqual(result["evidence"]["ex6_reversibility_plan"]["operation"],
                         "DELETE_ADDED_FILES")
        self.assertEqual(len(result["evidence"]["ex6_reversibility_plan"]["paths"]),3)
        self.assertTrue(all(x["production_authority"] is False for x in stages))
        for x in stages:
            for item in x["fixture_status"]:
                self.assertIn(item.removeprefix("FIXTURE_UNATTESTED:"),
                              unified.FIXTURES)
        text=json.dumps(result,sort_keys=True).lower()
        self.assertNotIn("ex5c",text)
        self.assertNotIn("lote-c",text)

    def test_a7_and_c4_fixture_unchanged_by_one_pass(self):
        import ex6_one_pass_v1 as unified
        chain.install()
        try:
            from test_pg06_c1_c5_chain_v1 import a7_and_plans, baseline
            pg05=chain.make_pg05()
            official_a7,official_plans=a7_and_plans(pg05["handoff"])
            official_baseline=baseline(pg05["handoff"])
            v=unified.stage06(pg05)
            self.assertEqual(v["a7"],official_a7)
            self.assertEqual(v["a7_plans"],official_plans)
            self.assertEqual(v["fixture_facts"]["fixture_a7"]["sha256"],
                             unified.digest(official_a7))
            self.assertEqual(v["fixture_facts"]["fixture_a7"]["plans_sha256"],
                             unified.digest(official_plans))
            self.assertEqual(v["fixture_facts"]["fixture_lint"]["sha256"],
                             unified.digest(official_baseline))
            self.assertFalse(v["fixture_facts"]["fixture_lint"]["used_as_ex6_c4"])
            self.assertEqual(v["c4"]["observation_ref"],
                             "ex6://sandbox/actions/runs/42707967927/artifacts/13715275651#baseline")
        finally:
            chain.uninstall()

    def test_pg04_to_pg14_does_not_claim_unrun_stages(self):
        result = chain.run_v1()
        self.assertEqual(len(result), 11)
        self.assertEqual([r["stage"] for r in result], list(chain.STAGE_ORDER))
        self.assertTrue(all(r["before_v2"] in ("PASS_SOURCE_ONLY", "BLOCK", "NOT_RUN_UPSTREAM_BLOCKED") for r in result))
        self.assertTrue(all(not r["producer_invoked"] for r in result
                            if r["code"] and r["code"].startswith("UPSTREAM_BLOCKED:")))
        self.assertFalse(any(r.get("production_authority", False) for r in result))


if __name__ == "__main__":
    unittest.main()
