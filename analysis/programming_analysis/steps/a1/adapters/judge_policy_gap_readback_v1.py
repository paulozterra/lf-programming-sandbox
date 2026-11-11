"""Source-only A1 judge-policy gap detector for existing EJECUCION_SKILL_LF.

No SQL, network, model calls, or admission. The live provider readback must
remain external. Even a structurally complete candidate is not proof of an
independent reviewer, trusted worker, runtime enforcement, or persisted receipt.
"""
from __future__ import annotations
from typing import Any

OPERATION = "EJECUCION_SKILL_LF"
SKILL = "PROGRAMMING_ANALYSIS_LF"
JUDGE = "JUDGE-EJECUCION-SKILL-LF-v0.1"
REQUIRED_KEYS = {"semantic_judge_result", "unsupported_claims"}


def blocked(code: str) -> dict:
    return {"status": "BLOCKED", "blocking_codes": [code],
            "runtime_qualified": False, "independent_judge_verified": False,
            "a3_allowed": False, "source_attested": False}


def inspect(snapshot: Any) -> dict:
    if not isinstance(snapshot, dict):
        return blocked("JUDGE_SOURCE_READBACK_REQUIRED")
    if (snapshot.get("operation_code") != OPERATION
            or snapshot.get("skill_code") != SKILL
            or snapshot.get("step_id") != "semantic_judge"):
        return blocked("JUDGE_OPERATION_OR_STEP_MISMATCH")
    judge, binding = snapshot.get("judge"), snapshot.get("binding")
    if not isinstance(judge, dict) or not isinstance(binding, dict):
        return blocked("JUDGE_POLICY_OR_BINDING_MISSING")
    if (judge.get("judge_code") != JUDGE
            or binding.get("judge_code") != JUDGE
            or judge.get("status") != "ACTIVE_ENFORCEMENT"
            or binding.get("status") != "ACTIVE_ENFORCEMENT"):
        return blocked("JUDGE_IDENTITY_OR_STATE_MISMATCH")
    keys = binding.get("required_evidence_keys")
    if not isinstance(keys, list) or not REQUIRED_KEYS.issubset(set(
            x for x in keys if isinstance(x, str))):
        return blocked("JUDGE_REQUIRED_EVIDENCE_INCOMPLETE")
    if (binding.get("clean_result_value") != "STEP_PASS_WITH_EVIDENCE"
            or binding.get("blocked_result_value") != "BLOCKED_STEP_NOT_CLEAN"):
        return blocked("JUDGE_RESULT_BINDING_MISMATCH")
    pos, neg = judge.get("pass_if"), judge.get("fail_if")
    if (not isinstance(pos, list) or not isinstance(neg, list)
            or any(not isinstance(x, str) or not x.strip() for x in pos + neg)
            or len(pos) != len(set(pos)) or len(neg) != len(set(neg))):
        return blocked("JUDGE_PREDICATE_SCHEMA_INVALID")
    if not pos or not neg:
        return blocked("SEMANTIC_JUDGE_POSITIVE_AND_NEGATIVE_RULES_MISSING")
    if set(pos).intersection(neg):
        return blocked("JUDGE_PASS_FAIL_PREDICATE_OVERLAP")
    return {"status": "POLICY_STRUCTURE_ONLY_UNATTESTED",
            "blocking_codes": ["NATIVE_INDEPENDENT_JUDGE_AND_RUN_UNVERIFIED"],
            "positive_predicate_count": len(pos),
            "negative_predicate_count": len(neg),
            "runtime_qualified": False, "independent_judge_verified": False,
            "a3_allowed": False, "source_attested": False}
