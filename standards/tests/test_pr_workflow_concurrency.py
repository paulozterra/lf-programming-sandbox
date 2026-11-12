"""Offline, exact top-level PR concurrency policy for Analysis F0 only."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_GROUP = "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
EXPECTED_CANCEL = "${{ github.event_name == 'pull_request' }}"


def test_analysis_f0_pr_only_concurrency():
    source = (ROOT / ".github/workflows/analysis-f0.yml").read_text(encoding="utf-8")
    matches = re.findall(r"(?m)^concurrency:\n((?:^  [^\n]*\n)*)", source)
    assert len(matches) == 1, "Missing or duplicate top-level concurrency"
    assert matches[0].splitlines() == [
        "  group: " + EXPECTED_GROUP,
        "  cancel-in-progress: " + EXPECTED_CANCEL,
    ]
    assert "workflow_dispatch:" in source
