"""PG-03_C2: direct assembler calls must not bypass skill scope checks."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

STD=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STD/"tools"))
import skills

class AssemblyAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(STD/"catalog.json").read_bytes()
        cls.pin={"catalog_sha256":hashlib.sha256(raw).hexdigest(),
                 "catalog_version":json.loads(raw)["catalog_version"]}

    def test_valid_single_skill_and_db_dependency(self):
        for selected,domains in [
            (["spring-boot"],["STD-BE","STD-API"]),
            (["nextjs"],["STD-FE","STD-API"]),
            (["spring-boot","postgres-flyway"],["STD-DB","STD-GEN"]),
        ]:
            with self.subTest(selected=selected):
                _,receipt=skills.assemble(self.pin,selected,domains)
                self.assertEqual([x["skill"] for x in receipt["skills"]],selected)

    def test_reject_unknown_duplicate_or_empty_selected(self):
        for selected in ([],["unknown"],["spring-boot","spring-boot"],None,"spring-boot"):
            with self.subTest(selected=selected),self.assertRaisesRegex(ValueError,"SELECTED_SKILLS_INVALID"):
                skills.assemble(self.pin,selected,["STD-BE"])

    def test_reject_missing_duplicate_or_invalid_active(self):
        for active in ([],["STD-BE","STD-BE"],["STD-BE",None],None,"STD-BE"):
            with self.subTest(active=active),self.assertRaisesRegex(ValueError,"ACTIVE_DOMAINS_INVALID"):
                skills.assemble(self.pin,["spring-boot"],active)

    def test_reject_missing_domain_coverage(self):
        with self.assertRaisesRegex(ValueError,"SKILL_ACTIVE_DOMAIN_UNCOVERED"):
            skills.assemble(self.pin,["nextjs"],["STD-BE"])

    def test_reject_unrelated_selected_skill(self):
        with self.assertRaisesRegex(ValueError,"SKILL_NOT_IN_ACTIVE_SCOPE"):
            skills.assemble(self.pin,["spring-boot","nextjs"],["STD-BE","STD-API"])

    def test_reject_multiple_skills_when_only_shared_domains(self):
        with self.assertRaisesRegex(ValueError,"SKILL_AMBIGUOUS_SHARED_ONLY"):
            skills.assemble(self.pin,["spring-boot","nextjs"],["STD-API"])

    def test_reject_db_skill_without_db_domain(self):
        with self.assertRaisesRegex(ValueError,"SKILL_NOT_IN_ACTIVE_SCOPE"):
            skills.assemble(self.pin,["spring-boot","postgres-flyway"],["STD-BE","STD-GEN"])

    def test_atomic_selection_assembly_binds_exact_skill_receipt(self):
        content,receipt=skills.select_and_assemble(
            evidence={"spring_boot":True,"next":True},
            active=["STD-BE","STD-API"],pin=self.pin)
        self.assertTrue(content)
        self.assertEqual([s["skill"] for s in receipt["skills"]],["spring-boot"])
        self.assertEqual(receipt["selection_status"],"CANDIDATE_NOT_ADMITTED")
        self.assertFalse(receipt["production_authority"])
        self.assertFalse(receipt["pg02_source_verified"])

    def test_atomic_selection_rejects_ambiguous_shared_stack(self):
        with self.assertRaisesRegex(skills.StackDecisionError,"STACK_AMBIGUOUS"):
            skills.select_and_assemble(
                evidence={"spring_boot":True,"next":True},
                active=["STD-API"],pin=self.pin)

    def test_atomic_selection_rejects_invalid_pin(self):
        with self.assertRaisesRegex(ValueError,"PIN_DIGEST_MISMATCH"):
            skills.select_and_assemble(
                evidence={"spring_boot":True},active=["STD-BE"],
                pin=dict(self.pin,catalog_sha256="0"*64))

    def test_atomic_selection_db_dependency(self):
        _,receipt=skills.select_and_assemble(
            evidence={"spring_boot":True,"flyway":True,"migration":True},
            active=["STD-DB"],pin=self.pin)
        self.assertEqual([s["skill"] for s in receipt["skills"]],
                         ["spring-boot","postgres-flyway"])

if __name__=="__main__":
    unittest.main()
