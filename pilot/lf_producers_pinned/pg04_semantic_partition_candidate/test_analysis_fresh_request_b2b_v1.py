"""Source-only A1-A9 trial: execute the existing profile validator on fresh B2B request."""
import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
PROFILE=ROOT/"profiles/programming_analysis_lf"

def load_validator(name,relative):
    spec=importlib.util.spec_from_file_location(name,PROFILE/relative)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

V=load_validator("a9_existing_contract","validators/runtime_validate.py")
U=load_validator("a9_existing_utility","validators/runtime_semantic_utility.py")
PATH=HERE/"analysis_trial_b2b_app_shell_unadmitted_v1.json"

class FreshRequestBlockedTrial(unittest.TestCase):
    def get(self):
        return json.loads(PATH.read_text(encoding="utf-8"))

    def test_01_existing_a9_validator_accepts_explicit_blocked_candidate_shape(self):
        result=V.validate(self.get())
        self.assertEqual(result["status"],"PASS",result)
        self.assertFalse(result["downstream_authorized"])
        self.assertEqual(result["independent_semantic_judge"],"NOT_EXECUTED")

    def test_02_existing_deterministic_utility_does_not_grant_authority(self):
        p=self.get()
        gate=V.validate(p)
        utility=U.evaluate(p,gate)
        self.assertEqual(utility["status"],"PASS",utility)
        self.assertFalse(utility["downstream_authorized"])
        self.assertEqual(utility["independent_semantic_judge"],"NOT_EXECUTED")

    def test_03_no_ready_scopes_or_typed_requirements_fabricated(self):
        p=self.get()
        self.assertEqual(p["package_readiness_candidate"],"NEED_MORE_EVIDENCE")
        self.assertEqual(p["requirements"],[])
        self.assertEqual(len(p["scope_proposals"]),1)
        self.assertEqual(p["scope_proposals"][0]["readiness_candidate"],"NEED_MORE_EVIDENCE")
        self.assertEqual(p["material_fronts"][0]["closure"],"BLOCKED")

    def test_04_false_ready_from_historic_scope_is_rejected(self):
        p=self.get()
        p["scope_proposals"][0]["readiness_candidate"]="READY_CANDIDATE"
        p["package_readiness_candidate"]="READY_CANDIDATE"
        result=V.validate(p)
        codes={x["code"] for x in result["errors"]}
        self.assertIn("ANALYSIS_UNKNOWN_TARGET_STATE_FALSE_READY",codes)
        self.assertIn("ANALYSIS_UNKNOWN_MATERIAL_FALSE_READY",codes)
        self.assertIn("ANALYSIS_FALSE_READY_SCOPE",codes)

    def test_05_missing_front_reference_is_rejected(self):
        p=self.get()
        p["scope_proposals"][0]["material_front_refs"]=[]
        errors={e["code"] for e in V.validate(p)["errors"]}
        self.assertIn("ANALYSIS_SCOPE_FRONT_BIDIRECTIONAL_MISMATCH",errors)

    def test_06_unjustified_stop_is_rejected(self):
        p=self.get()
        p["research_stop"]["decision"]="STOP"
        errors={e["code"] for e in V.validate(p)["errors"]}
        self.assertIn("ANALYSIS_STOP_WITH_UNRESOLVED_MATERIAL",errors)

if __name__=="__main__":
    unittest.main()
