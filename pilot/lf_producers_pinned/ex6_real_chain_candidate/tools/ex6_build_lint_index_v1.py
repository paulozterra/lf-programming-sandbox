"""EX6 run 42707967927: original ZIP readback and provenance-gated summary.

The original two-snapshot ZIP is preserved as an exact Git blob. The index is
derived from original download and MUST NOT replace raw ZIP validation
in a production judge. In particular AOSP candidate exit=1 is a real negative.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
INDEX = EVIDENCE / "ex6_run_42707967927_receipt_index.json"
ORIGINAL_SHA = "5008714c29f55c2813792d6da98002393febdc5adbe5070ae194970742ff9fbd"
ZIP_SHA = "2e8950a77ee9707df3cc7ab77e52e592a96f317fb4cc0736b3c28e8044671769"
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
THREE_NEW = {"ReminderStats.java","ReminderStatsService.java","ReminderStatsController.java"}

class EX6EvidenceBlocked(ValueError):
    pass

def summary():
    obj=json.loads(INDEX.read_bytes())
    src=obj["source"]
    if (src["workflow_run_id"]!=42707967927 or
        src["bundle_json_sha256"]!=ORIGINAL_SHA or
        src["artifact_zip_sha256"]!=ZIP_SHA or
        src["run_conclusion"]!="success"):
        raise EX6EvidenceBlocked("EX6_EVIDENCE_PROVENANCE_DRIFT")
    snaps=obj["snapshots"]
    if [s["label"] for s in snaps]!=["baseline","candidate"]:
        raise EX6EvidenceBlocked("EX6_EVIDENCE_SNAPSHOT_DRIFT")
    if ([s["commands"]["build"]["exit_code"] for s in snaps]!=[0,0] or
        [s["commands"]["javac_lint"]["exit_code"] for s in snaps]!=[0,0] or
        [s["commands"]["format_aosp"]["exit_code"] for s in snaps]!=[0,1] or
        snaps[1]["commands"]["visible_ex6"]["exit_code"]!=0):
        raise EX6EvidenceBlocked("EX6_EVIDENCE_COMMAND_STATUS_DRIFT")
    for snap in snaps:
        for cmd in snap["commands"].values():
            for key in ("stdout_sha256","stderr_sha256"):
                v=cmd.get(key)
                if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
                    raise EX6EvidenceBlocked("EX6_EVIDENCE_STREAM_SHA_INVALID")
    paths=snaps[1]["commands"]["format_aosp"]["finding_paths"]
    if set(Path(p).name for p in paths)!=THREE_NEW or len(paths)!=3:
        raise EX6EvidenceBlocked("EX6_EVIDENCE_AOSP_SCOPE_DRIFT")
    if (obj["authority"]["production_authority"] is not False or
        obj["authority"]["super_admin"] is not False or
        obj["authority"]["receipt_authenticated"] is not False):
        raise EX6EvidenceBlocked("EX6_EVIDENCE_AUTHORITY_DRIFT")
    return obj

def original_zip_integrity(archive_path: Path | None = None):
    """Actual original downloaded artifact must be byte-identical; no synthesis."""
    import zipfile
    archive_path = archive_path or (EVIDENCE / "ex6-build-lint-aosp-two-snapshots-v1.zip")
    raw=archive_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ZIP_SHA:
        raise EX6EvidenceBlocked("EX6_EVIDENCE_ORIGINAL_ZIP_SHA_MISMATCH")
    with zipfile.ZipFile(archive_path) as z:
        if set(z.namelist())!={"ex6-build-lint-bundle-v1.json",
                               "ex6-build-lint-bundle-v1.sha256"}:
            raise EX6EvidenceBlocked("EX6_EVIDENCE_ZIP_MEMBERS_DRIFT")
        json_bytes=z.read("ex6-build-lint-bundle-v1.json")
        sidecar=z.read("ex6-build-lint-bundle-v1.sha256")
        if hashlib.sha256(json_bytes).hexdigest()!=ORIGINAL_SHA:
            raise EX6EvidenceBlocked("EX6_EVIDENCE_JSON_SHA_MISMATCH")
        if sidecar!=((ORIGINAL_SHA+"  ex6-build-lint-bundle-v1.json\n").encode()):
            raise EX6EvidenceBlocked("EX6_EVIDENCE_SIDECAR_MISMATCH")
        data=json.loads(json_bytes)
    source=summary()
    if [x["commit"] for x in data["snapshots"]] != [x["commit"] for x in source["snapshots"]]:
        raise EX6EvidenceBlocked("EX6_EVIDENCE_COMMIT_DRIFT")
    for snap,idx in zip(data["snapshots"],source["snapshots"]):
        for name,expected in idx["commands"].items():
            observation=snap["commands"][name]
            if observation["exit_code"]!=expected["exit_code"]:
                raise EX6EvidenceBlocked("EX6_EVIDENCE_EXIT_CODE_DRIFT")
            for stream in ("stdout","stderr"):
                if observation[stream]["sha256"]!=expected[stream+"_sha256"]:
                    raise EX6EvidenceBlocked("EX6_EVIDENCE_STREAM_SHA_DRIFT")
    return data
