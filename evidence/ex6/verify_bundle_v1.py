#!/usr/bin/env python3
"""Offline fail-closed verifier for the EX6 two-snapshot evidence JSON and sidecar."""
from __future__ import annotations
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

from build_bundle_v1 import BASE, CANDIDATE, GJF_SHA256, GJF_VERSION, ADDED

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def verify(raw: bytes, checksum: str) -> dict:
    if sha(raw) != checksum:
        raise ValueError("EX6_BUNDLE_DIGEST_MISMATCH")
    data=json.loads(raw)
    if data.get("schema_version")!="LF_EX6_BUILD_LINT_AOSP_EVIDENCE_V1":
        raise ValueError("EX6_BUNDLE_SCHEMA")
    if (data.get("base_commit")!=BASE or
        data.get("candidate_commit")!=CANDIDATE or
        data.get("formatter_version")!=GJF_VERSION or
        data.get("formatter_sha256")!=GJF_SHA256 or
        data.get("formatter_flags")!=["--aosp","--dry-run","--set-exit-if-changed"] or
        data.get("write_paths")!=list(ADDED)):
        raise ValueError("EX6_BUNDLE_SOURCE_DRIFT")
    if (data.get("production_authority") is not False or
        data.get("receipt_authenticated") is not False or
        data.get("holdout_accessed") is not False or
        data.get("worker_invoked") is not False or
        data.get("api_calls")!=0):
        raise ValueError("EX6_BUNDLE_AUTHORITY_DRIFT")
    snapshots=data.get("snapshots")
    if not isinstance(snapshots,list) or len(snapshots)!=2:
        raise ValueError("EX6_BUNDLE_SNAPSHOT_COUNT")
    for snap,label,commit in zip(snapshots,("baseline","candidate"),(BASE,CANDIDATE)):
        if snap.get("label")!=label or snap.get("commit")!=commit:
            raise ValueError("EX6_BUNDLE_SNAPSHOT_IDENTITY")
        commands=snap.get("commands")
        required={"build","format_aosp","classpath_resolution","javac_lint"}
        if label=="candidate":
            required.add("visible_ex6")
        if set(commands)!=required:
            raise ValueError("EX6_BUNDLE_COMMAND_COVERAGE")
        if not snap.get("java_paths") or snap.get("java_file_count")!=len(snap["java_paths"]):
            raise ValueError("EX6_BUNDLE_JAVA_INVENTORY")
        for name,row in commands.items():
            if row.get("status","").startswith("NOT_RUN_"):
                if row.get("exit_code") is not None or row.get("stdout") is not None:
                    raise ValueError("EX6_BUNDLE_NOT_RUN_CLAIMS_RESULTS")
                continue
            if (not isinstance(row.get("argv"),list) or not row["argv"] or
                type(row.get("exit_code")) is not int):
                raise ValueError("EX6_BUNDLE_COMMAND_IDENTITY:"+name)
            for stream in ("stdout","stderr"):
                obj=row.get(stream)
                if not isinstance(obj,dict) or set(obj)!={"base64","bytes","sha256"}:
                    raise ValueError("EX6_BUNDLE_STREAM_SHAPE")
                raw_stream=base64.b64decode(obj["base64"],validate=True)
                if len(raw_stream)!=obj["bytes"] or sha(raw_stream)!=obj["sha256"]:
                    raise ValueError("EX6_BUNDLE_STREAM_DIGEST_MISMATCH")
        if "--aosp" not in commands["format_aosp"]["argv"]:
            raise ValueError("EX6_BUNDLE_AOSP_NOT_SET")
    return data

def main() -> None:
    if len(sys.argv)!=3:
        raise SystemExit("usage: verify_bundle_v1.py <json> <sha256>")
    path, sidecar=map(Path,sys.argv[1:])
    lines=sidecar.read_text(encoding="ascii").splitlines()
    if len(lines)!=1:
        raise ValueError("EX6_BUNDLE_CHECKSUM_COUNT")
    match=re.fullmatch(r"([a-f0-9]{64})  ([^/\\]+)",lines[0])
    if not match or match.group(2)!=path.name:
        raise ValueError("EX6_BUNDLE_SIDECAR_INVALID")
    data=verify(path.read_bytes(),match.group(1))
    print("EX6_BUNDLE_INTEGRITY_PASS snapshots="+str(len(data["snapshots"])))
    print("EX6_BUNDLE_SHA256="+match.group(1))

if __name__=="__main__":
    main()
