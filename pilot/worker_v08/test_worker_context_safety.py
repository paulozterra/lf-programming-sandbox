"""T16 security regression: rule examples cannot bypass vendored secret checks."""
from __future__ import annotations

import pytest

from pilot.worker_v08.worker_context_safety import (
    safe_rule_context, WorkerContextUnsafe,
)
from pilot.worker_v08.lf_rule_context import material
from programming_agent_runner.worker_secrets import secret_text_reason


def test_assignment_examples_are_safely_redacted_without_dropping_rule_text():
    source = (
        '# STD-GEN-03\n'
        'Nunca usar valores reales en ejemplos:\n'
        'password = "0123456789abcdef012345"\n'
        'api_key: "0123456789abcdef012345"\n'
    ).encode()
    assert secret_text_reason(source.decode()) == "ASSIGNMENT_SECRET"
    output, count = safe_rule_context(source)
    assert count == 2
    assert b"STD-GEN-03" in output
    assert b"Nunca usar" in output
    assert b"0123456789abcdef" not in output
    assert b'password = "REDACTED"' in output
    assert secret_text_reason(output.decode()) is None


def test_non_assignment_secrets_never_get_silently_redacted():
    source = b"Conectar con valor sk-proj-" + b"A" * 30
    assert secret_text_reason(source.decode()) == "OPENAI_API_KEY"
    with pytest.raises(WorkerContextUnsafe, match="LF_RULE_CONTEXT_SECRET"):
        safe_rule_context(source)


@pytest.mark.parametrize("area", ["CONTRATO", "INFRA", "DATA", "BACKEND", "FRONTEND"])
def test_real_assigned_lf_rules_are_safe_for_unmodified_vendor_worker(area):
    raw, receipt = material(area)
    safe, count = safe_rule_context(raw)
    assert receipt["rule_ids"]
    assert count >= 0
    assert secret_text_reason(safe.decode()) is None
    assert safe
