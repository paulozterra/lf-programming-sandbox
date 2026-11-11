"""PG-05 source-only positive, adversarial, PG-04 -> PG-05 -> PG-06 chain.

Imports real PG-04 candidate producers from the parent PR (#3534).
No branch/lock/write/review execution or production authority.
"""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PG04 = ROOT / "pg04_semantic_partition_candidate"
PG05 = ROOT / "pg05_target_binding_candidate"
for folder in (PG04 / "tools", PG04 / "tests", PG05 / "tools"):
    sys.path.insert(0, str(folder))

from test_pg04_remaining_edges_v1 import exit_fixture
from pg04_pg05_exit_candidate_v1 import assemble_pg04_exit_candidate
from pg05_c1_target_binding_preflight_v1 import prepare_pg05_c1, PG05BindingBlocked
from pg05_c2_write_scope_candidate_v1 import prepare_pg05_c2, ScopeResolutionBlocked
from pg05_c3_collision_lock_plan_candidate_v1 import prepare_pg05_c3, CollisionPlanBlocked
from pg05_c4_write_boundary_preflight_v1 import prepare_pg05_c4, WriteBoundaryBlocked
from pg05_c5_independent_assurance_request_v1 import prepare_pg05_assurance_request, PG05AssuranceBlocked
from pg05_pg06_exit_candidate_v1 import assemble_pg05_pg06_candidate, PG05ExitBlocked


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def refreeze(obj, digest_key="candidate_sha256"):
    obj[digest_key] = digest({k: v for k, v in obj.items() if k != digest_key})


def pg04_real_exit():
    """Not a forged PG-04 exit: call the existing PG-04 producers."""
    inputs = exit_fixture()
    inputs["target_binding"] = {
        "repo_full_name": "lf-synthetic/pilot",
        "base_head_sha": "a" * 40,
        "target_binding_ref": "fixture://analysis-target-binding",
    }
    return assemble_pg04_exit_candidate(**inputs)


def resources(exit_obj):
    result = []
    for sol in exit_obj["solutions"]:
        sid = sol["solution_id"]
        groups = []
        for token in sol["write_scope_candidates"]:
            unique = token.replace("/", "_").replace(".", "_")
            groups.append({
                "scope_token": token,
                "derivation_ref": "fixture://l3/derive/" + sid + "/" + unique,
                "resources": [{
                    "kind": "REPO_PATH",
                    "identity": "src/" + sid + "/" + unique + ".py",
                    "source_ref": "fixture://l3/resource/" + sid + "/" + unique,
                }],
            })
        shared = []
        for contract in sol["shared_contract_refs"]:
            shared.append({
                "contract_ref": contract,
                "derivation_ref": "fixture://shared/derivation",
                "resource": {
                    "kind": "REPO_PATH",
                    "identity": "contracts/payment-v1.json",
                    "source_ref": "fixture://shared/read",
                },
            })
        result.append({
            "solution_id": sid,
            "resolved_scopes": groups,
            "shared_read_refs": shared,
            "l3_structure_ref": "fixture://l3/structure",
        })
    return result


def changes(c1, c2):
    out = []
    for sol in c2["solution_scopes"]:
        sid = sol["solution_id"]
        entry = sol["write_resource_keys"][0]
        out.append({
            "solution_id": sid,
            "source_head_sha": c1["target_binding"]["base_head_sha"],
            "proposal_ref": "fixture://diff/" + sid,
            "changes": [{
                "operation": "MODIFY",
                "resource": copy.deepcopy(entry),
                "change_ref": "fixture://change/" + sid,
            }],
        })
    return out


def manifest(exit_obj, c1, c2, c3, c4):
    parts = dict(pg04_exit=exit_obj, pg05_c1=c1, pg05_c2=c2, pg05_c3=c3, pg05_c4=c4)
    return dict(
        source_head_sha="a" * 40,
        **{key: {"ref": "fixture://source/" + key, "sha256": value["candidate_sha256"]}
           for key, value in parts.items()},
    )


def build_chain():
    exit_obj = pg04_real_exit()
    c1 = prepare_pg05_c1(pg04_exit=exit_obj, work_code="LF-TEST", slug="synthetic-pilot")
    resolutions = resources(exit_obj)
    c2 = prepare_pg05_c2(pg04_exit=exit_obj, pg05_c1=c1, scope_resolutions=resolutions)
    c3 = prepare_pg05_c3(pg04_exit=exit_obj, pg05_c2=c2)
    proposals = changes(c1, c2)
    c4 = prepare_pg05_c4(pg04_exit=exit_obj, pg05_c2=c2, pg05_c3=c3, change_proposals=proposals)
    m = manifest(exit_obj, c1, c2, c3, c4)
    c5 = prepare_pg05_assurance_request(
        pg04_exit=exit_obj, pg05_c1=c1, pg05_c2=c2, pg05_c3=c3,
        pg05_c4=c4, source_manifest=m, producer_execution_id="fixture:builder",
    )
    handoff = assemble_pg05_pg06_candidate(
        pg04_exit=exit_obj, pg05_c1=c1, pg05_c2=c2, pg05_c3=c3,
        pg05_c4=c4, pg05_c5=c5,
    )
    return dict(pg04_exit=exit_obj, c1=c1, c2=c2, c3=c3, c4=c4, c5=c5,
                handoff=handoff, resolutions=resolutions, proposals=proposals, manifest=m)


class PG05Chain(unittest.TestCase):
    def test_pg04_real_exit_through_all_five_and_pg06(self):
        c = build_chain()
        self.assertEqual(c["pg04_exit"]["schema_version"], "PG04_TO_PG05_EXIT_CANDIDATE_V1")
        self.assertEqual(c["c1"]["branch_name_candidate"], "lf/prog-LF-TEST/synthetic-pilot")
        self.assertEqual(c["c1"]["source_pg04_exit_sha256"], c["pg04_exit"]["candidate_sha256"])
        self.assertEqual(c["c2"]["source_pg05_c1_sha256"], c["c1"]["candidate_sha256"])
        self.assertEqual(c["c3"]["source_pg05_c2_sha256"], c["c2"]["candidate_sha256"])
        self.assertEqual(c["c4"]["source_pg05_c3_sha256"], c["c3"]["candidate_sha256"])
        self.assertEqual(c["c5"]["subject"]["pg05_c4_sha256"], c["c4"]["candidate_sha256"])
        self.assertEqual(c["handoff"]["source_hashes"]["pg05_c5"], c["c5"]["request_sha256"])
        self.assertEqual(c["handoff"]["schema_version"], "PG05_TO_PG06_EXIT_CANDIDATE_V1")
        self.assertEqual(len(c["handoff"]["solutions"]), len(c["pg04_exit"]["solutions"]))
        for artifact in (c["pg04_exit"], c["c1"], c["c2"], c["c3"], c["c4"], c["c5"], c["handoff"]):
            self.assertIs(artifact["production_authority"], False)
            self.assertIs(artifact["handoff_allowed"], False)
        self.assertIs(c["handoff"]["write_allowed"], False)
        self.assertIs(c["c3"]["locks_acquired"], False)
        self.assertIs(c["c5"]["independent_review_executed"], False)

    def test_c1_missing_target_is_blocked_without_inventing_target(self):
        a=exit_fixture()
        exit_obj=assemble_pg04_exit_candidate(**a)
        result=prepare_pg05_c1(pg04_exit=exit_obj, work_code="LF-TEST", slug="synthetic-pilot")
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIsNone(result["branch_name_candidate"])

    def test_c1_injected_authority_blocks_even_with_rehashed_input(self):
        exit_obj=pg04_real_exit()
        exit_obj["production_authority"]=True
        refreeze(exit_obj)
        with self.assertRaises(PG05BindingBlocked):
            prepare_pg05_c1(pg04_exit=exit_obj, work_code="LF-TEST", slug="synthetic-pilot")

    def test_c2_traversal_path_blocks(self):
        c=build_chain()
        rows=copy.deepcopy(c["resolutions"])
        rows[0]["resolved_scopes"][0]["resources"][0]["identity"]="../escape.py"
        with self.assertRaises(ScopeResolutionBlocked):
            prepare_pg05_c2(pg04_exit=c["pg04_exit"], pg05_c1=c["c1"], scope_resolutions=rows)

    def test_c2_injected_authority_blocks(self):
        c=build_chain()
        forged=copy.deepcopy(c["c1"])
        forged["production_authority"]=True
        refreeze(forged)
        with self.assertRaises(ScopeResolutionBlocked):
            prepare_pg05_c2(pg04_exit=c["pg04_exit"], pg05_c1=forged,
                            scope_resolutions=c["resolutions"])

    def test_c3_injected_authority_blocks(self):
        c=build_chain()
        forged=copy.deepcopy(c["c2"])
        forged["production_authority"]=True
        refreeze(forged)
        with self.assertRaises(CollisionPlanBlocked):
            prepare_pg05_c3(pg04_exit=c["pg04_exit"], pg05_c2=forged)

    def test_c3_detects_same_path_as_material_conflict(self):
        c=build_chain()
        rows=copy.deepcopy(c["resolutions"])
        shared_path=rows[0]["resolved_scopes"][0]["resources"][0]["identity"]
        rows[1]["resolved_scopes"][0]["resources"][0]["identity"]=shared_path
        c2=prepare_pg05_c2(pg04_exit=c["pg04_exit"], pg05_c1=c["c1"], scope_resolutions=rows)
        c3=prepare_pg05_c3(pg04_exit=c["pg04_exit"], pg05_c2=c2)
        self.assertGreater(c3["material_conflict_pair_count"],0)
        self.assertTrue(any("WRITE_WRITE_MATERIAL_OVERLAP" in [why["kind"]
            for why in pair["material_conflicts"]] for pair in c3["solution_pairs"]))
        self.assertFalse(c3["locks_acquired"])

    def test_c4_out_of_scope_blocks_only_one_solution(self):
        c=build_chain()
        proposals=copy.deepcopy(c["proposals"])
        victim=proposals[0]["solution_id"]
        proposals[0]["changes"][0]["resource"]["identity"]="outside/the-scope.py"
        c4=prepare_pg05_c4(pg04_exit=c["pg04_exit"],pg05_c2=c["c2"],
                           pg05_c3=c["c3"],change_proposals=proposals)
        self.assertEqual(c4["affected_solutions"],[victim])
        self.assertEqual(len(c4["unaffected_solutions_not_promoted"]),len(proposals)-1)
        self.assertFalse(c4["write_allowed"])

    def test_c4_injected_authority_blocks(self):
        c=build_chain()
        forged=copy.deepcopy(c["c3"])
        forged["production_authority"]=True
        refreeze(forged)
        with self.assertRaises(WriteBoundaryBlocked):
            prepare_pg05_c4(pg04_exit=c["pg04_exit"],pg05_c2=c["c2"],
                            pg05_c3=forged,change_proposals=c["proposals"])

    def test_c5_foreign_source_manifest_blocks(self):
        c=build_chain()
        m=copy.deepcopy(c["manifest"])
        m["pg05_c3"]["sha256"]="f"*64
        with self.assertRaises(PG05AssuranceBlocked):
            prepare_pg05_assurance_request(
                pg04_exit=c["pg04_exit"],pg05_c1=c["c1"],pg05_c2=c["c2"],
                pg05_c3=c["c3"],pg05_c4=c["c4"],
                source_manifest=m,producer_execution_id="fixture:builder")

    def test_c5_injected_authority_blocks(self):
        c=build_chain()
        forged=copy.deepcopy(c["c4"])
        forged["production_authority"]=True
        refreeze(forged)
        with self.assertRaises(PG05AssuranceBlocked):
            prepare_pg05_assurance_request(
                pg04_exit=c["pg04_exit"],pg05_c1=c["c1"],pg05_c2=c["c2"],
                pg05_c3=c["c3"],pg05_c4=forged,
                source_manifest=c["manifest"],producer_execution_id="fixture:builder")

    def test_exit_forged_review_receipt_blocks(self):
        c=build_chain()
        forged=copy.deepcopy(c["c5"])
        forged["subject_receipt_id"]="fake-uuid"
        refreeze(forged,"request_sha256")
        with self.assertRaises(PG05ExitBlocked):
            assemble_pg05_pg06_candidate(
                pg04_exit=c["pg04_exit"],pg05_c1=c["c1"],pg05_c2=c["c2"],
                pg05_c3=c["c3"],pg05_c4=c["c4"],pg05_c5=forged)

    def test_exit_injected_authority_blocks(self):
        c=build_chain()
        forged=copy.deepcopy(c["c1"])
        forged["production_authority"]=True
        refreeze(forged)
        with self.assertRaises(PG05ExitBlocked):
            assemble_pg05_pg06_candidate(
                pg04_exit=c["pg04_exit"],pg05_c1=forged,pg05_c2=c["c2"],
                pg05_c3=c["c3"],pg05_c4=c["c4"],pg05_c5=c["c5"])

if __name__=="__main__":
    unittest.main()
