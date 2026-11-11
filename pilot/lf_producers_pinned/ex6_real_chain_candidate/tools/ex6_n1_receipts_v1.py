"""Fail-closed, exact-byte N and N+1 ZIP receipts; never repackage source artifacts."""
from __future__ import annotations
import base64
import hashlib
import json
import re
import zipfile
from pathlib import Path

EVIDENCE=Path(__file__).resolve().parents[1]/"evidence"
BASE="53ab6b1a85da95f3e2a38d7f3298af731c6698ab"
N="912c4ad9ea71f48edbd1ac58089441f9ed2c3449"
N1="8e57b84c8a79de1abee1de057a8fcb9075de406c"
EXPECTED={
"N":{"name":"ex6-build-lint-aosp-two-snapshots-v1.zip",
     "zip":"2e8950a77ee9707df3cc7ab77e52e592a96f317fb4cc0736b3c28e8044671769",
     "json":"5008714c29f55c2813792d6da98002393febdc5adbe5070ae194970742ff9fbd",
     "candidate":N,"aosp":1,"run":42707967927},
"N1":{"name":"ex6-build-lint-aosp-n1-run-42718885627.zip",
      "zip":"b84de2eb9f577d8c43dad98b313b51c6924bd28d43a9e3b57d5c06125f30a946",
      "json":"cdba0f6ebebd5790fb95321f81ff9807004eed0797d8f8281c8a0078f74cef79",
      "candidate":N1,"aosp":0,"run":42718885627}}
MEMBERS={"ex6-build-lint-bundle-v1.json","ex6-build-lint-bundle-v1.sha256"}
COMMANDS_BASE={"build","format_aosp","classpath_resolution","javac_lint"}
THREE={"ReminderStats.java","ReminderStatsService.java","ReminderStatsController.java"}
class ReceiptIntegrityError(ValueError):
    pass
def sha(b):
    return hashlib.sha256(b).hexdigest()
def load(label, path=None):
    if label not in EXPECTED:
        raise ReceiptIntegrityError("EX6_UNKNOWN_SNAPSHOT")
    e=EXPECTED[label]
    path=Path(path) if path is not None else EVIDENCE/e["name"]
    if sha(path.read_bytes())!=e["zip"]:
        raise ReceiptIntegrityError("EX6_ZIP_SHA_DRIFT:"+label)
    with zipfile.ZipFile(path) as z:
        if set(z.namelist())!=MEMBERS or len(z.namelist())!=2:
            raise ReceiptIntegrityError("EX6_ZIP_MEMBERS_DRIFT")
        raw=z.read("ex6-build-lint-bundle-v1.json")
        side=z.read("ex6-build-lint-bundle-v1.sha256")
    if sha(raw)!=e["json"]:
        raise ReceiptIntegrityError("EX6_JSON_SHA_DRIFT:"+label)
    if side!=(e["json"]+"  ex6-build-lint-bundle-v1.json\n").encode("ascii"):
        raise ReceiptIntegrityError("EX6_SIDECAR_DRIFT")
    obj=json.loads(raw)
    if obj.get("schema_version")!="LF_EX6_BUILD_LINT_AOSP_EVIDENCE_V1":
        raise ReceiptIntegrityError("EX6_SCHEMA_DRIFT")
    if obj.get("base_commit")!=BASE or obj.get("candidate_commit")!=e["candidate"]:
        raise ReceiptIntegrityError("EX6_COMMIT_DRIFT")
    if (obj.get("formatter_version")!="1.30.0" or
        obj.get("formatter_sha256")!="f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a" or
        obj.get("formatter_flags")!=["--aosp","--dry-run","--set-exit-if-changed"]):
        raise ReceiptIntegrityError("EX6_FORMATTER_DRIFT")
    if (obj.get("production_authority") is not False or
        obj.get("receipt_authenticated") is not False or
        obj.get("worker_invoked") is not False or
        obj.get("holdout_accessed") is not False or obj.get("api_calls")!=0):
        raise ReceiptIntegrityError("EX6_AUTHORITY_DRIFT")
    snaps=obj.get("snapshots")
    if not isinstance(snaps,list) or len(snaps)!=2 or [v.get("label") for v in snaps]!=["baseline","candidate"]:
        raise ReceiptIntegrityError("EX6_SNAPSHOT_DRIFT")
    for index,snap in enumerate(snaps):
        if snap.get("commit")!=(BASE if index==0 else e["candidate"]):
            raise ReceiptIntegrityError("EX6_SNAPSHOT_COMMIT_DRIFT")
        commands=snap.get("commands",{})
        if set(commands)!=(COMMANDS_BASE|({"visible_ex6"} if index else set())):
            raise ReceiptIntegrityError("EX6_COMMAND_COVERAGE")
        for name,row in commands.items():
            if not isinstance(row.get("argv"),list) or type(row.get("exit_code")) is not int:
                raise ReceiptIntegrityError("EX6_COMMAND_TYPE")
            if name=="format_aosp" and "--aosp" not in row["argv"]:
                raise ReceiptIntegrityError("EX6_AOSP_FLAG")
            for stream in ("stdout","stderr"):
                val=row.get(stream)
                if not isinstance(val,dict) or set(val)!={"sha256","base64","bytes"}:
                    raise ReceiptIntegrityError("EX6_STREAM_TYPE")
                data=base64.b64decode(val["base64"],validate=True)
                if sha(data)!=val["sha256"] or len(data)!=val["bytes"]:
                    raise ReceiptIntegrityError("EX6_STREAM_SHA")
        if any(row["exit_code"]!=0 for name,row in commands.items()
               if name!="format_aosp") or commands["format_aosp"]["exit_code"]!=(0 if index==0 else e["aosp"]):
            raise ReceiptIntegrityError("EX6_RESULT_DRIFT")
    if len(obj.get("write_paths",[]))!=3 or {Path(x).name for x in obj["write_paths"]}!=THREE:
        raise ReceiptIntegrityError("EX6_SCOPE_DRIFT")
    if label=="N":
        finding=base64.b64decode(snaps[1]["commands"]["format_aosp"]["stdout"]["base64"]).decode().splitlines()
        if len(finding)!=3 or {Path(x).name for x in finding}!=THREE:
            raise ReceiptIntegrityError("EX6_N_FINDINGS_DRIFT")
    else:
        finding=base64.b64decode(snaps[1]["commands"]["format_aosp"]["stdout"]["base64"])
        if finding.strip():
            raise ReceiptIntegrityError("EX6_N1_UNEXPECTED_FORMAT_FINDINGS")
    return obj
def verify_both():
    original=load("N")
    remediated=load("N1")
    if (original["base_time_service_tree_oid"]!=remediated["base_time_service_tree_oid"] or
        original["write_paths"]!=remediated["write_paths"]):
        raise ReceiptIntegrityError("EX6_LINEAGE_BASE_DRIFT")
    return {"N":original,"N1":remediated}
if __name__=="__main__":
    verify_both()
    for label,row in EXPECTED.items():
        print(f"EX6_{label}_ZIP_SHA256_PASS={row['zip']} JSON_SHA256_PASS={row['json']}")
