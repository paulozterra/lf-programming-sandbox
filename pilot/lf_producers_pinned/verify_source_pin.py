#!/usr/bin/env python3
"""Fail-closed SHA-256 and byte-for-byte LF producer source-pin validation."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

PIN_ROOT = Path(__file__).resolve().parent
ORIGIN_PREFIX = "sandbox/lf_contract_gate_test/programming_agent_four_stage/"
TARGET_PREFIX = "pilot/lf_producers_pinned/"
PIN_COMMIT = "882c7213f83887952a99ad0793174d535eb91233"
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


def check(root: Path, source: Path | None = None) -> dict:
    root = root.resolve()
    pin = root / "pilot/lf_producers_pinned/SOURCE_PIN.json"
    raw = json.loads(pin.read_text(encoding="utf-8"))
    if (raw.get("schema_version") != "LF_PRODUCER_SOURCE_PIN_V1"
            or raw.get("source_repository") != "cristhianlujan/claude-persona-lf-patch"
            or raw.get("source_commit_sha") != PIN_COMMIT):
        raise ValueError("SOURCE_PIN_HEADER_DRIFT")
    entries = raw.get("files")
    if not isinstance(entries, list) or len(entries) != 252:
        raise ValueError("SOURCE_PIN_COUNT_INVALID")
    if source is not None:
        head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True).strip()
        if head != PIN_COMMIT:
            raise ValueError("SOURCE_PIN_LF_COMMIT_DRIFT")
    seen = set()
    for entry in entries:
        origin, dest, expected = (entry.get("origin_path"),
                                  entry.get("destination_path"), entry.get("sha256"))
        if not all(isinstance(x, str) for x in (origin, dest, expected)):
            raise ValueError("SOURCE_PIN_ENTRY_INVALID")
        if (not origin.startswith(ORIGIN_PREFIX) or not dest.startswith(TARGET_PREFIX)
                or dest != TARGET_PREFIX + origin.removeprefix(ORIGIN_PREFIX)
                or ".." in PurePosixPath(dest).parts or chr(92) in dest
                or dest in seen or not SHA64.fullmatch(expected)
                or any(x in PurePosixPath(dest).parts for x in ("profiles", "vendor"))):
            raise ValueError("SOURCE_PIN_SCOPE_INVALID")
        seen.add(dest)
        file = root / dest
        if not file.is_file() or file.is_symlink():
            raise ValueError("SOURCE_PIN_FILE_MISSING")
        content = file.read_bytes()
        if len(content) != entry.get("size_bytes"):
            raise ValueError("SOURCE_PIN_SIZE_DRIFT")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("SOURCE_PIN_SHA256_DRIFT")
        if source is not None:
            source_file = source / origin
            if not source_file.is_file() or source_file.is_symlink():
                raise ValueError("SOURCE_PIN_ORIGINAL_MISSING")
            if source_file.read_bytes() != content:
                raise ValueError("SOURCE_PIN_SOURCE_BYTES_DIFFER")
    stage_files = {
        f.relative_to(root).as_posix()
        for folder in (root / TARGET_PREFIX).iterdir()
        if folder.is_dir() and not folder.is_symlink()
        for f in folder.rglob("*") if f.is_file() or f.is_symlink()
    }
    if stage_files != seen:
        raise ValueError("SOURCE_PIN_EXTRA_OR_MISSING_FILES")
    return {"status": "PASS", "files": len(seen), "source_commit_sha": PIN_COMMIT,
            "byte_equal_with_lf": source is not None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PIN_ROOT.parents[1])
    parser.add_argument("--lf-source", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    outcome = check(args.root, args.lf_source)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(outcome, sort_keys=True) + "\n")
    print("LF_PRODUCERS_SOURCE_PIN_PASS files=" + str(outcome["files"]))


if __name__ == "__main__":
    main()
