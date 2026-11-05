from __future__ import annotations

import re
from typing import Iterable

from .hashutil import sha256_evidence_envelope
from .models import Evidence, GateResult

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def validate_evidence_envelope(head_sha: str, evidence: Iterable[Evidence], gates: Iterable[GateResult]) -> dict:
    items = list(evidence)
    gate_items = list(gates)
    problems: list[str] = []
    evidence_by_code: dict[str, list[Evidence]] = {}
    for item in items:
        evidence_by_code.setdefault(item.code, []).append(item)
        if item.head_sha != head_sha:
            problems.append(f"{item.code}:HEAD_MISMATCH")
        if not HEX64.fullmatch(item.sha256):
            problems.append(f"{item.code}:INVALID_SHA256")
        else:
            expected_sha = sha256_evidence_envelope(
                code=item.code,
                status=item.status,
                source_system=item.source_system,
                source_ref=item.source_ref,
                head_sha=item.head_sha,
                producer=item.producer,
                metadata=item.metadata,
            )
            if item.sha256 != expected_sha:
                problems.append(f"{item.code}:SHA256_MISMATCH")
    for gate in gate_items:
        if gate.status == "PASS" and not gate.evidence_codes:
            problems.append(f"{gate.gate_code}:PASS_WITHOUT_EVIDENCE")
        for code in gate.evidence_codes:
            referenced = evidence_by_code.get(code, [])
            if not referenced:
                problems.append(f"{gate.gate_code}:MISSING_EVIDENCE:{code}")
                continue
            if gate.status == "PASS" and any(item.status != "PASS" for item in referenced):
                problems.append(f"{gate.gate_code}:PASS_WITH_NONPASS_EVIDENCE:{code}")
    return {"status": "FAIL" if problems else "PASS", "problems": problems, "evidence_count": len(items), "gate_count": len(gate_items)}
