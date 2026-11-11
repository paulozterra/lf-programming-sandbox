"""PG04_C5 deterministic DoD plans: scoped standards, tests and fail-closed negatives."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pg04_definition_of_done_candidate_v1 import prepare_dod,DoDBlocked
from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome
from test_pg04_semantic_partition_candidate_v1 import args

def fixtures():
    partition=partition_by_semantic_outcome(**args())
    standards=[
      {"standard_code":"STD-API","source_ref":"git://std/api",
       "source_sha256":"a"*64,"applies_to_write_scopes":["backend/api"]},
      {"standard_code":"STD-DB","source_ref":"git://std/db",
       "source_sha256":"b"*64,"applies_to_write_scopes":["database/migration"]},
      {"standard_code":"STD-UI","source_ref":"git://std/ui",
       "source_sha256":"c"*64,"applies_to_write_scopes":["frontend/ui"]}]
    def check(cid,kind,req=None,acc=None,std=None,deps=None):
        row={"check_id":cid,"kind":kind,"validation_code":"PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
             "input_ref":"fixture://"+cid,"requirement_ids":req or [],
             "acceptance_ids":acc or []}
        if std:row["standard_code"]=std
        if deps is not None:row["dependency_ids"]=deps
        return row
    plans=[
      {"solution_id":"SOL-001","standard_codes":["STD-API","STD-DB"],
       "checks":[check("S-API","STANDARD",std="STD-API"),
                 check("S-DB","STANDARD",std="STD-DB"),
                 check("R1","REQUIREMENT",req=["R1"]),
                 check("R2","REQUIREMENT",req=["R2"]),
                 check("A1","ACCEPTANCE",acc=["A1"]),
                 check("A2","ACCEPTANCE",acc=["A2"])]},
      {"solution_id":"SOL-002","standard_codes":["STD-UI"],
       "checks":[check("S-UI","STANDARD",std="STD-UI"),
                 check("R3","REQUIREMENT",req=["R3"]),
                 check("A3","ACCEPTANCE",acc=["A3"]),
                 check("D1","DEPENDENCY",deps=["SOL-001"])]}]
    return {"partition":partition,"standards_catalog_version":"TEST-CATALOG-01",
            "standards":standards,
            "validation_registry":[{"validation_code":"PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
                                    "status":"ACTIVE","source_ref":"fixture://registry/current"}],
            "solution_plans":plans}

class Tests(unittest.TestCase):
    def denied(self,code,mutate):
        a=fixtures();mutate(a)
        with self.assertRaisesRegex(DoDBlocked,"^"+code+"$"):
            prepare_dod(**a)

    def test_positive_scoped_checks_no_authority(self):
        x=prepare_dod(**fixtures())
        self.assertEqual(x["status"],"CANDIDATE_NOT_ADMITTED")
        self.assertEqual(x["standard_resolution_mode"],"WRITE_SCOPE_FILTERED")
        self.assertEqual(x["solutions"][0]["standard_codes"],["STD-API","STD-DB"])
        self.assertEqual(x["solutions"][1]["standard_codes"],["STD-UI"])
        self.assertEqual(x["solutions"][0]["check_count"],6)
        self.assertEqual(x["solutions"][1]["check_count"],4)
        self.assertFalse(x["checks_executed"])
        self.assertFalse(x["handoff_allowed"])
        for sol in x["solutions"]:
            self.assertEqual(sol["status"],"PLANNED_NOT_EXECUTED")
            self.assertFalse(sol["done"])
            for c in sol["checks"]:
                self.assertEqual(c["status"],"NOT_EXECUTED")
                self.assertIsNone(c["receipt_id"])

    def test_deterministic(self):
        self.assertEqual(prepare_dod(**fixtures()),prepare_dod(**fixtures()))

    def test_order_invariance_of_plans(self):
        a=fixtures();a["solution_plans"].reverse()
        self.assertEqual(prepare_dod(**a),prepare_dod(**fixtures()))

    def test_candidate_digest_drift(self):
        self.denied("PARTITION_SHA_DRIFT",lambda a:a["partition"]["solutions"][0].update(id="FORGED"))

    def test_prevent_authority_escalation(self):
        self.denied("PARTITION_NOT_UNTRUSTED_CANDIDATE",lambda a:a["partition"].update(production_authority=True))

    def test_missing_catalog_version(self):
        self.denied("STANDARDS_CATALOG_VERSION_REQUIRED",lambda a:a.update(standards_catalog_version=""))

    def test_missing_standard_source_digest(self):
        self.denied("STANDARD_SCOPE_SOURCE_INVALID",lambda a:a["standards"][0].update(source_sha256="bad"))

    def test_duplicate_standard_code(self):
        self.denied("STANDARD_DUPLICATE",lambda a:a["standards"].append(copy.deepcopy(a["standards"][0])))

    def test_only_backend_standard_must_not_read_other_std(self):
        def bad(a):
            a["solution_plans"][0]["standard_codes"].append("STD-UI")
        self.denied("DOD_SCOPE_STANDARD_COVERAGE_MISMATCH",bad)

    def test_missing_applicable_standard_fails(self):
        self.denied("DOD_SCOPE_STANDARD_COVERAGE_MISMATCH",
                    lambda a:a["solution_plans"][0]["standard_codes"].remove("STD-DB"))

    def test_unregistered_standard_fails(self):
        self.denied("DOD_STANDARD_UNDECLARED",
                    lambda a:a["solution_plans"][0]["standard_codes"].append("STD-FAKE"))

    def test_missing_standard_check_fails(self):
        self.denied("DOD_STANDARD_WITHOUT_CHECK",
                    lambda a:a["solution_plans"][0]["checks"].pop(0))

    def test_missing_acceptance_check_fails(self):
        self.denied("DOD_OBLIGATION_CHECK_COVERAGE_MISMATCH",
                    lambda a:a["solution_plans"][1]["checks"].pop(2))

    def test_missing_requirement_check_fails(self):
        self.denied("DOD_OBLIGATION_CHECK_COVERAGE_MISMATCH",
                    lambda a:a["solution_plans"][0]["checks"].pop(2))

    def test_missing_dependency_check_fails(self):
        self.denied("DOD_DEPENDENCY_CHECK_MISSING",
                    lambda a:a["solution_plans"][1]["checks"].pop(3))

    def test_dependency_check_must_be_bound(self):
        self.denied("DOD_DEPENDENCY_CHECK_UNBOUND",
                    lambda a:a["solution_plans"][1]["checks"][3].pop("dependency_ids"))

    def test_foreign_dependency_rejected(self):
        self.denied("DOD_DEPENDENCY_CHECK_FOREIGN",
                    lambda a:a["solution_plans"][1]["checks"][3].update(dependency_ids=["SOL-999"]))

    def test_dependency_binding_for_other_check_forbidden(self):
        self.denied("DOD_NONDEPENDENCY_BINDING_FORBIDDEN",
                    lambda a:a["solution_plans"][0]["checks"][0].update(dependency_ids=["SOL-001"]))

    def test_foreign_acceptance_not_allowed(self):
        self.denied("DOD_CHECK_FOREIGN_OBLIGATION",
                    lambda a:a["solution_plans"][1]["checks"][2].update(acceptance_ids=["A1"]))

    def test_duplicate_check_id_fails(self):
        self.denied("DOD_CHECK_DUPLICATE",
                    lambda a:a["solution_plans"][0]["checks"].append(copy.deepcopy(a["solution_plans"][0]["checks"][0])))

    def test_solution_plan_missing_fails(self):
        self.denied("DOD_SOLUTION_PLAN_MISMATCH",lambda a:a["solution_plans"].pop())

    def test_unauthorized_standard_on_acceptance_fails(self):
        self.denied("DOD_CHECK_NONSTANDARD_CODE_FORBIDDEN",
                    lambda a:a["solution_plans"][0]["checks"][4].update(standard_code="STD-API"))

    def test_fake_pass_field_rejected(self):
        self.denied("DOD_CHECK_FIELDS_INVALID",
                    lambda a:a["solution_plans"][0]["checks"][0].update(status="PASS",receipt_id="invented"))

    def test_fake_done_plan_rejected(self):
        self.denied("DOD_PLAN_FIELDS_INVALID",
                    lambda a:a["solution_plans"][0].update(done=True))

    def test_fake_standard_authority_rejected(self):
        self.denied("STANDARD_FIELDS_INVALID",
                    lambda a:a["standards"][0].update(current_release_verified=True))

    def test_malformed_standard_scope_list_blocked(self):
        self.denied("STANDARD_SCOPE_SOURCE_INVALID",
                    lambda a:a["standards"][0].update(applies_to_write_scopes=[{"scope":"backend/api"}]))

    def test_unknown_validator_blocked(self):
        self.denied("DOD_VALIDATOR_NOT_ACTIVE_OR_UNDECLARED",
                    lambda a:a["solution_plans"][0]["checks"][0].update(validation_code="INVENTED_VALIDATOR"))

    def test_inactive_validator_blocked(self):
        self.denied("DOD_VALIDATOR_REGISTRY_INVALID",
                    lambda a:a["validation_registry"][0].update(status="PROPOSED"))

    def test_duplicate_validator_declaration_blocked(self):
        self.denied("DOD_VALIDATOR_DUPLICATE",
                    lambda a:a["validation_registry"].append(copy.deepcopy(a["validation_registry"][0])))

    def test_empty_requirement_binding_in_check_fails(self):
        self.denied("DOD_REQUIREMENT_CHECK_UNBOUND",
                    lambda a:a["solution_plans"][0]["checks"][2].update(requirement_ids=[]))

if __name__=="__main__":
    unittest.main()
