"""PG-03_C6: fail-closed sufficiency assessment; candidate only.

No human decision, approval, dispatch or ledger closure is manufactured here.
All input provenance is caller-supplied and remains untrusted.
"""
from collections.abc import Mapping, Sequence

class SufficiencyBlocked(ValueError):
    pass

def _refs(rows, label):
    if not isinstance(rows, list):
        raise SufficiencyBlocked(label + "_INVALID")
    refs = []
    for item in rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str) or not item["id"].strip() or not isinstance(item.get("source_ref"), str) or not item["source_ref"].strip():
            raise SufficiencyBlocked(label + "_PROVENANCE_MISSING")
        refs.append(item["id"])
    if len(refs) != len(set(refs)):
        raise SufficiencyBlocked(label + "_DUPLICATE")
    return set(refs)

def assess_sufficiency(*, strategy, pg01_questions, requirement_evidence, acceptance_evidence, blocking_findings):
    """Check explicit required IDs and unresolved PG-01 questions; never authorizes handoff.

    pg01_questions: list of {id, source_ref, status}, with status RESOLVED,
    REQUIRES_DECISION, OPEN or BLOCKED. A resolved question also needs evidence_ref.
    requirement_evidence / acceptance_evidence: list of {id, source_ref}.
    blocking_findings: list of {id, source_ref, status}, status OPEN or RESOLVED;
    RESOLVED requires evidence_ref.
    """
    if not isinstance(strategy, Mapping) or strategy.get("status") != "CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False or strategy.get("handoff_allowed") is not False:
        raise SufficiencyBlocked("STRATEGY_AUTHORITY_INVALID")
    required = {}
    for key in ("requirement_ids", "acceptance_ids"):
        values = strategy.get(key)
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(values):
            raise SufficiencyBlocked("STRATEGY_" + key.upper() + "_INVALID")
        required[key] = set(values)
    requirements = _refs(requirement_evidence, "REQUIREMENT")
    acceptance = _refs(acceptance_evidence, "ACCEPTANCE")
    questions = _refs(pg01_questions, "PG01_QUESTION")
    findings = _refs(blocking_findings, "BLOCKING_FINDING")
    if not questions.issubset(set(x["id"] for x in pg01_questions)) or not findings.issubset(set(x["id"] for x in blocking_findings)):
        raise SufficiencyBlocked("INVALID_INPUT")
    gaps = []
    for identifier in sorted(required["requirement_ids"] - requirements):
        gaps.append({"code": "REQUIREMENT_EVIDENCE_MISSING", "id": identifier, "route": "ANALYSIS"})
    for identifier in sorted(required["acceptance_ids"] - acceptance):
        gaps.append({"code": "ACCEPTANCE_EVIDENCE_MISSING", "id": identifier, "route": "ANALYSIS"})
    for question in pg01_questions:
        status = question.get("status")
        if status not in ("RESOLVED", "OPEN", "REQUIRES_DECISION", "BLOCKED"):
            raise SufficiencyBlocked("PG01_QUESTION_STATUS_INVALID")
        if status == "RESOLVED" and (not isinstance(question.get("evidence_ref"), str) or not question["evidence_ref"].strip()):
            raise SufficiencyBlocked("PG01_RESOLUTION_EVIDENCE_MISSING")
        if status != "RESOLVED":
            gaps.append({"code": "PG01_UNRESOLVED_QUESTION", "id": question["id"], "route": "DECISION" if status == "REQUIRES_DECISION" else "ANALYSIS"})
    for finding in blocking_findings:
        if finding.get("status") not in ("OPEN", "RESOLVED"):
            raise SufficiencyBlocked("FINDING_STATUS_INVALID")
        if finding["status"] == "RESOLVED" and (not isinstance(finding.get("evidence_ref"), str) or not finding["evidence_ref"].strip()):
            raise SufficiencyBlocked("FINDING_RESOLUTION_EVIDENCE_MISSING")
        if finding["status"] == "OPEN":
            gaps.append({"code": "UNRESOLVED_FINDING", "id": finding["id"], "route": "ANALYSIS"})
    return {
        "schema_version": "PG03_C6_SUFFICIENCY_CANDIDATE_V1",
        "status": "REQUIRES_DECISION" if any(g["route"] == "DECISION" for g in gaps) else ("BLOCKED" if gaps else "CANDIDATE_SUFFICIENT_NOT_ADMITTED"),
        "production_authority": False,
        "handoff_allowed": False,
        "source_strategy_sha256": strategy.get("candidate_sha256"),
        "gaps": sorted(gaps, key=lambda x: (x["code"], x["id"])),
        "reason": "SOURCE_AUTHORITY_AND_MATERIAL_SUFFICIENCY_NOT_ATTESTED" if not gaps else "EXPLICIT_INSUFFICIENCY",
    }
