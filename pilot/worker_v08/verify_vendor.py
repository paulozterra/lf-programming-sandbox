#!/usr/bin/env python3
"""Verify EXACT vendored Worker 298307e before any installation or import.

No network access. Detect changed, missing, extra files, symlinks, permissions
not relevant for ordinary source, and mismatched Git blob identity and SHA-256.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

PIN="298307e2f9cac72abfde2b181f3554b0e28bad24"
REPO="cristhianlujan/programming-agent"
VERSION="LF_VENDOR_PROGRAMMING_AGENT_PROVENANCE_V1"

class VendorIntegrityError(RuntimeError):
    pass

def refuse(code):
    raise VendorIntegrityError(code)

def verify(root:Path):
    root=root.absolute()
    if not root.is_dir() or root.is_symlink():
        refuse("VENDOR_ROOT_INVALID")
    provenance_path=root/"PROVENANCE.json"
    if not provenance_path.is_file() or provenance_path.is_symlink():
        refuse("VENDOR_PROVENANCE_MISSING")
    try:
        evidence=json.loads(provenance_path.read_text(encoding="utf-8"))
    except (ValueError,OSError):
        refuse("VENDOR_PROVENANCE_INVALID")
    required={"schema_version","source_repository","source_commit",
              "copied_on_date_utc","copy_scope","file_count","total_bytes",
              "files","immutable_source"}
    if not isinstance(evidence,dict) or set(evidence)!=required:
        refuse("VENDOR_PROVENANCE_SCHEMA_INVALID")
    if (evidence["schema_version"]!=VERSION or evidence["source_repository"]!=REPO
        or evidence["source_commit"]!=PIN or evidence["immutable_source"] is not True
        or evidence["copy_scope"]!=["pyproject.toml","src/**"]):
        refuse("VENDOR_SOURCE_PIN_INVALID")
    records=evidence["files"]
    if not isinstance(records,dict) or not records:
        refuse("VENDOR_FILES_EMPTY")
    if evidence["file_count"]!=len(records) or len(records)!=72:
        refuse("VENDOR_FILE_COUNT_MISMATCH")
    allowed=set(records)|{"PROVENANCE.json"}
    if any(not isinstance(k,str) or (k!="pyproject.toml" and
            (not k.startswith("src/") or k.endswith("/"))) for k in records):
        refuse("VENDOR_PATH_OUT_OF_SCOPE")
    observed=set()
    for item in root.rglob("*"):
        if item.is_symlink():
            refuse("VENDOR_SYMLINK:"+item.relative_to(root).as_posix())
        if item.is_dir():
            continue
        if not item.is_file():
            refuse("VENDOR_NONFILE")
        observed.add(item.relative_to(root).as_posix())
    if observed!=allowed:
        missing=sorted(allowed-observed)
        extra=sorted(observed-allowed)
        refuse("VENDOR_FILE_SET_DRIFT missing="+repr(missing)+" extra="+repr(extra))
    total=0
    for name in sorted(records):
        row=records[name]
        if not isinstance(row,dict) or set(row)!={"sha256","bytes","source_git_blob_sha1"}:
            refuse("VENDOR_ROW_INVALID:"+name)
        content=(root/name).read_bytes()
        count=len(content)
        total+=count
        digest=hashlib.sha256(content).hexdigest()
        blob=hashlib.sha1(b"blob "+str(count).encode("ascii")+b"\0"+content).hexdigest()
        if (count!=row["bytes"] or digest!=row["sha256"] or
            blob!=row["source_git_blob_sha1"]):
            refuse("VENDOR_HASH_MISMATCH:"+name)
    if total!=evidence["total_bytes"] or total!=675415:
        refuse("VENDOR_TOTAL_BYTES_DRIFT")
    return {"status":"PASS_VENDOR_EXACT","source_commit":PIN,"files":len(records),
            "total_bytes":total}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[2]/"vendor/programming-agent")
    a=p.parse_args()
    try:
        result=verify(a.root)
    except VendorIntegrityError as exc:
        print("BLOCK "+str(exc),file=sys.stderr)
        return 1
    print("PASS_VENDOR_EXACT files="+str(result["files"])+" bytes="+str(result["total_bytes"]))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
