import unittest
from copy import deepcopy
try:
    from .pg03_architecture_d15_v1 import assess_architecture, ArchitectureBlocked
except ImportError:
    from pg03_architecture_d15_v1 import assess_architecture, ArchitectureBlocked

S={"status":"CANDIDATE_NOT_ADMITTED","production_authority":False,"handoff_allowed":False,"scope_ids":["S1"]}
P={"repository":"repo/example","source_ref":"git:d15","commit_sha":"a"*40,"sha256":"b"*64,"deployment_units":[{"id":"api","modules":["backend"],"allowed_resources":["postgres"]}]}
ROWS=[{"piece_id":"P1","scope_id":"S1","deployment_unit":"api","module":"backend","resources":["postgres"]}]
def run(**kwargs):
    return assess_architecture(strategy=kwargs.get("strategy",deepcopy(S)),profile=kwargs.get("profile",deepcopy(P)),pieces=kwargs.get("pieces",deepcopy(ROWS)))
class ArchitectureTests(unittest.TestCase):
    def test_conformant_candidate_never_deploys(self):
        x=run()
        self.assertEqual(x["status"],"CANDIDATE_CONFORMANT_NOT_ADMITTED")
        self.assertFalse(x["deployment_allowed"])
        self.assertEqual(x["source_authenticity"],"UNVERIFIED")
    def test_empty_resources_are_explicit_d14_none(self):
        rows=deepcopy(ROWS);rows[0]["resources"]=[]
        self.assertEqual(run(pieces=rows)["status"],"CANDIDATE_CONFORMANT_NOT_ADMITTED")
    def test_unknown_unit_requires_adr(self):
        rows=deepcopy(ROWS);rows[0]["deployment_unit"]="unapproved"
        self.assertEqual(run(pieces=rows)["status"],"REQUIRES_DECISION")
    def test_unknown_module_requires_adr(self):
        rows=deepcopy(ROWS);rows[0]["module"]="other"
        self.assertEqual(run(pieces=rows)["deviations"][0]["route"],"REQUIRES_DECISION_ADR_PROPOSAL")
    def test_extra_resource_requires_adr(self):
        rows=deepcopy(ROWS);rows[0]["resources"]=["redis"]
        self.assertEqual(run(pieces=rows)["status"],"REQUIRES_DECISION")
    def test_missing_resource_declaration_blocks(self):
        rows=deepcopy(ROWS);del rows[0]["resources"]
        with self.assertRaises(ArchitectureBlocked):run(pieces=rows)
    def test_unknown_scope_blocks(self):
        rows=deepcopy(ROWS);rows[0]["scope_id"]="S2"
        with self.assertRaises(ArchitectureBlocked):run(pieces=rows)
    def test_missing_profile_blocks(self):
        with self.assertRaises(ArchitectureBlocked):run(profile=None)
    def test_invalid_exact_sha_blocks(self):
        with self.assertRaises(ArchitectureBlocked):run(profile=dict(P,commit_sha="main"))
    def test_duplicated_pieces_block(self):
        with self.assertRaises(ArchitectureBlocked):run(pieces=ROWS+ROWS)
    def test_duplicated_units_block(self):
        with self.assertRaises(ArchitectureBlocked):run(profile=dict(P,deployment_units=P["deployment_units"]*2))
    def test_authority_escalation_blocks(self):
        with self.assertRaises(ArchitectureBlocked):run(strategy=dict(S,production_authority=True))
if __name__=="__main__":unittest.main()
