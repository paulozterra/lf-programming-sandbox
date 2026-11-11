"""Fail-closed inventory checks for the 20 exactly identified inherited failures."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "analysis/known_inherited_failures.json"
SOURCE = ROOT / "analysis/programming_analysis"


def test_known_inherited_failures_exact_inventory():
    data = json.loads(FILE.read_text(encoding="utf-8"))
    failures = data["failures"]
    assert data["source_commit"] == "20968c79a83b2df182d9fd873c8aa0c6b8b832d4"
    assert data["verified_by"] == "claude 2026-11-11, comparación lado a lado"
    assert len(failures) == 20, "No additional upstream failures may be grandfathered"
    ids = [entry["node_id"] for entry in failures]
    assert len(set(ids)) == len(ids), "Duplicate node_id"
    for entry in failures:
        assert entry["area"] in {"A1", "A2", "paquete"}
        assert entry["observed_error"]
        path, *parts = entry["node_id"].split("::")
        assert len(parts) == 2, entry["node_id"]
        assert path.endswith(".py") and (SOURCE / path).is_file(), entry["node_id"]
        assert all(part.isidentifier() for part in parts), entry["node_id"]
    # pytest_collection_modifyitems additionally checks every complete node ID
    # against actual collected pytest items, rather than only file existence.
