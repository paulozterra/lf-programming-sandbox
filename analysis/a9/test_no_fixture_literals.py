"""CI fail-closed guard: fixture-specific IDs never occur in Analysis production Python."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (ROOT / "analysis", ROOT / "pilot/orchestrator", ROOT / "pilot/worker_v08")
FIXTURE_CODES = re.compile(r"\b(?:SBX|DEMO)-[A-Za-z0-9_-]+|\bREQ-[A-Z][A-Z0-9]{2,}-[A-Z0-9_-]+|\bf5-login\b|/(?:login|notes)(?:/|\\.)")


def test_no_fixture_codes_outside_tests():
    violations = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if (path.name.startswith("test_") or path.name.endswith("_test.py")
                    or "tests" in path.parts):
                continue
            body = path.read_text(encoding="utf-8")
            for match in FIXTURE_CODES.finditer(body):
                line = body.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line}:{match.group()}")
    assert not violations, "FIXTURE_CODE_IN_PRODUCTION:" + ", ".join(violations)


def test_guard_does_not_allow_names_in_docstrings():
    assert FIXTURE_CODES.search('"""Implement SBX-NOT-ALLOWED here"""')
    assert FIXTURE_CODES.search('constant = "DEMO-REQUIRED"')
