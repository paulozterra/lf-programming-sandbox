"""Protect PR-only cancellation without touching dispatch / Train.

This test parses the two top-level YAML concurrency scalars, not job-level
concurrency or comment strings. It uses stdlib to avoid external YAML packages.
"""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/analysis-f0.yml")
EXPECTED_GROUP = "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
EXPECTED_CANCEL = "${{ github.event_name == 'pull_request' }}"


@pytest.mark.parametrize("path", WORKFLOWS)
def test_pr_only_concurrency_and_dispatch_isolation(path):
    source = (ROOT / path).read_text(encoding="utf-8")
    matches = re.findall(r"(?m)^concurrency:\n((?:^  [^\n]*\n)*)", source)
    assert len(matches) == 1, "Missing or duplicate top-level concurrency"
    fields = {}
    for line in matches[0].splitlines():
        match = re.fullmatch(r"  (group|cancel-in-progress): (.*)", line)
        assert match, "Unexpected concurrency configuration"
        key, value = match.groups()
        assert key not in fields
        fields[key] = value
    assert fields == {
        "group": EXPECTED_GROUP,
        "cancel-in-progress": EXPECTED_CANCEL,
    }
    assert "workflow_dispatch:" in source, "Train manual runs must remain available"
    assert "github.run_id" in fields["group"], "Manual runs require independent groups"
    assert "github.event_name == 'pull_request'" in fields["cancel-in-progress"]
