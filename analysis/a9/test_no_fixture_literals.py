"""CI fail-closed guard: fixture-specific IDs never occur in Analysis production Python."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CODES = re.compile(r"\b(?:SBX|DEMO)-[A-Za-z0-9_-]+")


def test_no_fixture_codes_outside_tests():
    violations = []
    for path in sorted(ROOT.rglob("*.py")):
        if (path.name.startswith("test_") or path.name.endswith("_test.py")
                or "tests" in path.parts or "evals" in path.parts
                and path.name.startswith("test_")):
            continue
        text = path.read_text(encoding="utf-8")
        for match in FIXTURE_CODES.finditer(text):
            violations.append(f"{path.relative_to(ROOT)}:{text.count(chr(10),0,match.start())+1}:{match.group()}")
    assert not violations, "FIXTURE_CODE_IN_PRODUCTION:" + ", ".join(violations)


def test_guard_does_not_allow_names_in_docstrings():
    assert FIXTURE_CODES.search('"""Implement SBX-NOT-ALLOWED here"""')
    assert FIXTURE_CODES.search('constant = "DEMO-REQUIRED"')
