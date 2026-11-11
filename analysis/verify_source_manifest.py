#!/usr/bin/env python3
"""Offline byte-exact provenance verification for the Analysis F0 sandbox copy."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "analysis/source_manifest.json").read_text(encoding="utf-8"))
assert manifest["schema_version"] == "ANALYSIS_F0_SOURCE_MANIFEST_V1"
seen = set()
failed = []
for entry in manifest["files"]:
    rel = entry["path"]
    if rel in seen or Path(rel).is_absolute() or ".." in Path(rel).parts:
        failed.append(f"INVALID_PATH: {rel}")
        continue
    seen.add(rel)
    path = ROOT / rel
    if not path.is_file():
        failed.append(f"MISSING: {rel}")
        continue
    actual = subprocess.check_output(["git", "hash-object", "--", str(path)], text=True).strip()
    if actual != entry["blob_sha"]:
        failed.append(f"BLOB_MISMATCH: {rel}: expected {entry['blob_sha']} actual {actual}")
print(f"Analysis F0 source provenance: {len(seen)} files, {len(failed)} errors")
for failure in failed:
    print(failure, file=sys.stderr)
sys.exit(1 if failed else 0)
