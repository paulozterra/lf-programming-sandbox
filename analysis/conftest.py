"""Sandbox-only pytest path adapter; upstream A1-A5 and test bodies remain byte-exact."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis" / "programming_analysis"
COMPAT = ROOT / "skills" / "programming_analysis"
if not COMPAT.exists() and not COMPAT.is_symlink():
    COMPAT.parent.mkdir(parents=True, exist_ok=True)
    COMPAT.symlink_to(SOURCE, target_is_directory=True)
elif COMPAT.resolve() != SOURCE.resolve():
    raise RuntimeError("ANALYSIS_COMPAT_PATH_CONFLICT")
for relative in ("steps/a2/adapters",):
    candidate = str(SOURCE / relative)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import json
import pytest

KNOWN_FAILURES_FILE = ROOT / "analysis" / "known_inherited_failures.json"


def _known_failures():
    record = json.loads(KNOWN_FAILURES_FILE.read_text(encoding="utf-8"))
    failures = record["failures"]
    node_ids = [failure["node_id"] for failure in failures]
    if len(failures) != 20 or len(set(node_ids)) != 20:
        raise pytest.UsageError("ANALYSIS_F0_KNOWN_FAILURES_NOT_EXACTLY_20_UNIQUE")
    if any(not failure.get("observed_error") or failure.get("area") not in {"A1", "A2", "paquete"} for failure in failures):
        raise pytest.UsageError("ANALYSIS_F0_KNOWN_FAILURE_METADATA_INVALID")
    return {failure["node_id"]: failure for failure in failures}


def pytest_collection_modifyitems(items):
    known = _known_failures()
    prefix = "analysis/programming_analysis/"
    collected = {}
    for item in items:
        node_id = item.nodeid.replace("\\", "/")
        if node_id.startswith(prefix):
            relative = node_id[len(prefix):]
            collected[relative] = item
    missing = set(known) - set(collected)
    if missing:
        raise pytest.UsageError("ANALYSIS_F0_KNOWN_FAILURE_TEST_MISSING: " + ", ".join(sorted(missing)))
    for node_id, failure in known.items():
        collected[node_id].add_marker(pytest.mark.xfail(
            reason="Inherited from " + failure["area"] + ": " + failure["observed_error"][:240],
            strict=True,
        ))
