"""Offline adversarial qualification gate tests. No Supabase, network or model."""
import copy
import hashlib
import json
import unittest
from context_gate_v1 import gate, CONTRACT, CATALOG_REF


def raw(o):
    return (json.dumps(o, sort_keys=True, ensure_ascii=False) + "\n").encode()


class GateTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"catalog_version": "0.7.0",
                        "status": "BORRADOR_EN_REPO_DE_CALIFICACION",
                        "rules": [{"id": "STD-BE-01", "domain": "STD-BE", "status": "APROBADO"},
                                  {"id": "STD-BE-02", "domain": "STD-BE", "status": "VALIDAR_CON_LEGAL"}]}
        self.skill = {"skill_version": "0.3.0", "catalog_compat": "0.7",
                      "exclude_rule_ids": []}
        self.text = b"validated demo context"
        self.receipt = {"schema_version": CONTRACT, "run_id": "E-RUN-1",
                        "catalog_version": "0.7.0", "catalog_sha256": hashlib.sha256(raw(self.catalog)).hexdigest(),
                        "skills": [{"skill": "spring-boot", "skill_version": "0.3.0",
                                    "skill_json_sha256": hashlib.sha256(raw(self.skill)).hexdigest()}],
                        "active_domains": ["STD-BE"], "rule_ids": ["STD-BE-01", "STD-BE-02"],
                        "pending_rule_ids": ["STD-BE-02"], "bytes": len(self.text),
                        "approx_tokens": (len(self.text.decode()) + 3)//4,
                        "assembled_sha256": hashlib.sha256(self.text).hexdigest(), "warnings": []}
        self.kw = {"text": self.text, "receipt": self.receipt,
                   "source_catalog": raw(self.catalog), "source_skills": {"spring-boot": raw(self.skill)},
                   "approved_budget": {"status": "APPROVED", "max_estimated_tokens": 4000,
                                       "decision_ref": "APPROVED-QUALIFICATION-TEST"},
                   "trusted_source": {"commit": CATALOG_REF, "qualification_approved": True},
                   "expected_run_id": "E-RUN-1", "expected_domains": ["STD-BE"],
                   "expected_required_ids": ["STD-BE-01"]}
    def check(self, code, **changes):
        x = copy.deepcopy(self.kw)
        x.update(changes)
        result = gate(**x)
        self.assertEqual(result["code"], code, result)
    def test_positive_qualification(self):
        self.check("QUALIFICATION_CONTEXT_VALIDATED_NOT_RUNTIME_AUTHORIZED")
    def test_production_always_blocked(self):
        self.check("PRODUCTION_RELEASE_NOT_ATTESTED", qualification_only=False)
    def test_untrusted_source(self):
        self.check("SOURCE_PROVENANCE_UNVERIFIED", trusted_source=None)
    def test_wrong_run(self):
        r=copy.deepcopy(self.receipt);r["run_id"]="other"
        self.check("RECEIPT_RUN_BINDING_MISMATCH", receipt=r)
    def test_tampered_context(self):
        self.check("ASSEMBLED_CONTEXT_TAMPERED", text=b"modified")
    def test_tampered_digest(self):
        r=copy.deepcopy(self.receipt);r["catalog_sha256"]="0"*64
        self.check("CATALOG_PIN_MISMATCH", receipt=r)
    def test_wrong_version(self):
        r=copy.deepcopy(self.receipt);r["catalog_version"]="0.6.1"
        self.check("CATALOG_PIN_MISMATCH", receipt=r)
    def test_unknown_skill(self):
        r=copy.deepcopy(self.receipt);r["skills"][0]["skill"]="unknown"
        self.check("UNKNOWN_SKILL", receipt=r)
    def test_excluded_rule(self):
        s=copy.deepcopy(self.skill);s["exclude_rule_ids"]=[{"rule_id":"STD-BE-01","reason":"bypass"}]
        r=copy.deepcopy(self.receipt);r["skills"][0]["skill_json_sha256"]=hashlib.sha256(raw(s)).hexdigest()
        self.check("SKILL_EXCLUSIONS_REQUIRE_REVIEW", receipt=r, source_skills={"spring-boot":raw(s)})
    def test_mandatory_rule_deleted(self):
        r=copy.deepcopy(self.receipt);r["rule_ids"].remove("STD-BE-01")
        self.check("REQUIRED_RULE_OMITTED", receipt=r)
    def test_caller_omits_mandatory(self):
        self.check("REQUIRED_RULE_SET_INVALID", expected_required_ids=[])
    def test_pending_rule_propagated(self):
        r=copy.deepcopy(self.receipt);r["pending_rule_ids"]=[]
        self.check("PENDING_RULE_MISMATCH", receipt=r)
    def test_unapproved_budget(self):
        self.check("CONTEXT_BUDGET_NOT_APPROVED", approved_budget=None)
    def test_exceeded_budget(self):
        self.check("CONTEXT_BUDGET_EXCEEDED", approved_budget={"status":"APPROVED","max_estimated_tokens":1,"decision_ref":"D"})
    def test_spring_warning_3358(self):
        txt=b"a"*13432
        r=copy.deepcopy(self.receipt);r.update(bytes=len(txt),approx_tokens=3358,
                assembled_sha256=hashlib.sha256(txt).hexdigest(), warnings=["CONTEXT_SIZE_WARNING"])
        self.check("CONTEXT_BUDGET_EXCEEDED", text=txt, receipt=r,
                   approved_budget={"status":"APPROVED","max_estimated_tokens":3000,"decision_ref":"D"})
        self.check("QUALIFICATION_CONTEXT_VALIDATED_NOT_RUNTIME_AUTHORIZED",text=txt,receipt=r)
    def test_warning_omitted(self):
        txt=b"a"*13432
        r=copy.deepcopy(self.receipt);r.update(bytes=len(txt),approx_tokens=3358,
                assembled_sha256=hashlib.sha256(txt).hexdigest())
        self.check("CONTEXT_WARNING_OMITTED",text=txt,receipt=r)


if __name__=="__main__":
    unittest.main()
