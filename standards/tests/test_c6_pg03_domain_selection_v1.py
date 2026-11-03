"""PG-03_C2 independently sampled regression of the ORIGINAL C6 selector."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
import skills

class C6PG03ActiveDomainSelectionTests(unittest.TestCase):
    def test_be_only_ignores_detected_next(self):
        evidence={"spring_boot":True,"next":True}
        self.assertEqual(skills.select(evidence,["STD-BE"]),["spring-boot"])

    def test_fe_only_ignores_detected_spring(self):
        evidence={"spring_boot":True,"next":True}
        self.assertEqual(skills.select(evidence,["STD-FE"]),["nextjs"])

    def test_fe_without_next_must_not_fall_back_to_spring(self):
        with self.assertRaisesRegex(ValueError,"STACK_UNRECOGNIZED.*REQUIRES_DECISION"):
            skills.select({"spring_boot":True},["STD-FE"])

    def test_be_without_spring_must_not_fall_back_to_next(self):
        with self.assertRaisesRegex(ValueError,"STACK_UNRECOGNIZED.*REQUIRES_DECISION"):
            skills.select({"next":True},["STD-BE"])

    def test_db_dependency_keeps_spring_plus_flyway(self):
        evidence={"spring_boot":True,"flyway":True,"migration":True,"next":True}
        self.assertEqual(skills.select(evidence,["STD-DB"]),["spring-boot","postgres-flyway"])

    def test_db_without_spring_uses_flyway(self):
        self.assertEqual(skills.select({"flyway":True,"migration":True},["STD-DB"]),
                         ["postgres-flyway"])

    def test_mixed_specialized_domains_select_exact_matching_stacks(self):
        evidence={"spring_boot":True,"next":True,"flyway":True,"migration":True}
        self.assertEqual(skills.select(evidence,["STD-BE","STD-FE","STD-DB"]),
                         ["spring-boot","nextjs","postgres-flyway"])

    def test_shared_domain_chooses_only_present_compatible_stack(self):
        self.assertEqual(skills.select({"spring_boot":True},["STD-API"]),["spring-boot"])
        self.assertEqual(skills.select({"next":True},["STD-API"]),["nextjs"])

    def test_reject_uncovered_active_domain(self):
        with self.assertRaisesRegex(skills.StackDecisionError,"active domains not covered"):
            skills.select({"spring_boot":True},["STD-BE","STD-PY"])

    def test_incomplete_flyway_keeps_original_selected_skills(self):
        with self.assertRaisesRegex(skills.StackDecisionError,"Flyway declaration") as ctx:
            skills.select({"spring_boot":True,"flyway":True,"migration":False},["STD-DB"])
        self.assertEqual(ctx.exception.selected_skills,["spring-boot"])

    def test_empty_duplicate_or_invalid_active_domains_fail_closed(self):
        for active in ([],["STD-BE","STD-BE"],["STD-BE",None],"STD-BE"):
            with self.subTest(active=active), self.assertRaisesRegex(ValueError,"REQUIRES_DECISION"):
                skills.select({"spring_boot":True},active)

if __name__=="__main__":
    unittest.main()
