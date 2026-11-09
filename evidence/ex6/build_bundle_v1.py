#!/usr/bin/env python3
"""Produce immutable EX6 base/merged build and AOSP-lint observations.

Only works on two explicitly pinned source checkouts. Never reads hidden tests,
uses model/API credentials, writes to source files, or claims LF authority.
Nonzero command exits are recorded, not upgraded to PASS. The JSON SHA is
published in a separate .sha256 (no circular self-hash).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

BASE = "53ab6b1a85da95f3e2a38d7f3298af731c6698ab"
CANDIDATE = "8e57b84c8a79de1abee1de057a8fcb9075de406c"
BASE_APP_TREE = "2c199d6c49b76ea8a23e15149425ece0f29e1410"
GJF_VERSION = "1.30.0"
GJF_SHA256 = "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"
GJF_URL = ("https://github.com/google/google-java-format/releases/download/v"
           + GJF_VERSION + "/google-java-format-" + GJF_VERSION + "-all-deps.jar")
SPEC = "apps/time-service/REMINDERS_SPEC.md"
POM = "apps/time-service/pom.xml"
ROOT_JAVA = "apps/time-service/src/main/java"
EX6_VISIBLE = "apps/time-service/visible-tests/ex6/run_visible.py"
ADDED = (
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderStats.java",
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderStatsService.java",
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderStatsController.java",
)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def block(message: str) -> None:
    raise RuntimeError("EX6_EVIDENCE_" + message)

def git(path: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(path), *args], capture_output=True, timeout=90)
    if p.returncode:
        block("GIT_FAILED:" + " ".join(args))
    return p.stdout.decode().strip()

def verify_checkout(path: Path, expected: str) -> dict:
    if git(path, "rev-parse", "HEAD") != expected:
        block("CHECKOUT_COMMIT_MISMATCH")
    if git(path, "status", "--porcelain"):
        block("DIRTY_SOURCE_CHECKOUT")
    if not (path / POM).is_file():
        block("POM_NOT_FOUND")
    tree = git(path, "rev-parse", "HEAD:apps/time-service")
    paths = sorted(p.relative_to(path).as_posix() for p in
                   (path / ROOT_JAVA).rglob("*.java"))
    if not paths or any(re.search("holdout|secret|oracle", v, re.I) for v in paths):
        block("JAVA_SCOPE_INVALID")
    return {"commit": expected, "time_service_tree_oid": tree,
            "java_paths": paths, "java_file_count": len(paths)}

def record(argv: list[str], cwd: Path, timeout: int = 600) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        block("COMMAND_TIMED_OUT:" + argv[0])
    # Capture complete stdout/stderr bytes for verifying downstream observations.
    return {"argv": argv, "exit_code": proc.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "stdout": {"sha256": sha(proc.stdout), "bytes": len(proc.stdout),
                       "base64": base64.b64encode(proc.stdout).decode("ascii")},
            "stderr": {"sha256": sha(proc.stderr), "bytes": len(proc.stderr),
                       "base64": base64.b64encode(proc.stderr).decode("ascii")}}

def download_formatter(out: Path) -> None:
    req = urllib.request.Request(GJF_URL, headers={"User-Agent": "LF-EX6-evidence/1"})
    with urllib.request.urlopen(req, timeout=90) as stream:
        jar = stream.read(12_000_000)
    if sha(jar) != GJF_SHA256:
        block("FORMATTER_SHA256_MISMATCH")
    out.write_bytes(jar)

def make_snapshot(root: Path, label: str, jar: Path, work: Path) -> dict:
    meta = verify_checkout(root, BASE if label == "baseline" else CANDIDATE)
    files = meta["java_paths"]
    # AOSP --dry-run is non-mutating. Exit 1 is retained as format finding.
    commands = {
        "build": record(["mvn", "-B", "-q", "-f", POM, "package"], root),
        "format_aosp": record(["java", "-jar", str(jar), "--aosp", "--dry-run",
                                "--set-exit-if-changed", *files], root),
    }
    for key in ("build", "format_aosp"):
        if commands[key]["exit_code"] not in (0, 1):
            # Real errors are retained in JSON and reported; they are NOT PASS.
            pass
    # Independent javac lint observation using exactly the snapshot's sources
    # and Maven-resolved dependencies; isolate generated class files in temp.
    work.mkdir(parents=True, exist_ok=True)
    classpath = work / "classpath.txt"
    dep = record(["mvn", "-B", "-q", "-f", POM, "dependency:build-classpath",
                  "-Dmdep.outputFile=" + str(classpath)], root)
    commands["classpath_resolution"] = dep
    if dep["exit_code"] == 0 and classpath.is_file():
        classes = work / "classes"
        classes.mkdir()
        cp = classpath.read_text(encoding="utf-8").strip()
        commands["javac_lint"] = record(
            ["javac", "--release", "21", "-Xlint:all", "-encoding", "UTF-8",
             "-cp", cp, "-d", str(classes), *files], root)
    else:
        commands["javac_lint"] = {"status": "NOT_RUN_DEPENDENCY_RESOLUTION_FAILED",
                                 "argv": None, "exit_code": None,
                                 "stdout": None, "stderr": None}
    if label == "candidate":
        if (root / EX6_VISIBLE).is_file():
            commands["visible_ex6"] = record(["python3", EX6_VISIBLE], root, timeout=150)
        else:
            commands["visible_ex6"] = {"status": "NOT_RUN_VISIBLE_SCRIPT_MISSING",
                                       "argv": None, "exit_code": None,
                                       "stdout": None, "stderr": None}
    return {"label": label, **meta, "commands": commands,
            "formatting_standard": "google-java-format 1.30.0 --aosp",
            "source_authenticated": False, "production_authority": False}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base, candidate = args.base.resolve(), args.candidate.resolve()
    if base == candidate or args.out.exists():
        block("PATH_COLLISION_OR_OVERWRITE")
    base_meta = verify_checkout(base, BASE)
    cand_meta = verify_checkout(candidate, CANDIDATE)
    if base_meta["time_service_tree_oid"] != BASE_APP_TREE:
        block("BASE_TIME_SERVICE_TREE_DRIFT")
    base_files, cand_files = set(base_meta["java_paths"]), set(cand_meta["java_paths"])
    if cand_files - base_files != set(ADDED) or base_files - cand_files:
        block("EX6_JAVA_SET_DRIFT")
    for path in sorted(base_files):
        if (base/path).read_bytes() != (candidate/path).read_bytes():
            block("EX6_EXISTING_JAVA_CHANGED:" + path)
    if (base/POM).read_bytes() != (candidate/POM).read_bytes():
        block("EX6_POM_CHANGED")
    if (base/SPEC).read_bytes() != (candidate/SPEC).read_bytes():
        block("EX6_SPEC_CHANGED")
    with tempfile.TemporaryDirectory(prefix="ex6_evidence_") as td:
        tmp = Path(td)
        jar = tmp / "google-java-format-1.30.0-all-deps.jar"
        download_formatter(jar)
        snaps = [
            make_snapshot(base, "baseline", jar, tmp/"lint-base"),
            make_snapshot(candidate, "candidate", jar, tmp/"lint-candidate"),
        ]
    bundle = {
        "schema_version": "LF_EX6_BUILD_LINT_AOSP_EVIDENCE_V1",
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "base_commit": BASE, "candidate_commit": CANDIDATE,
        "base_time_service_tree_oid": BASE_APP_TREE,
        "formatter_version": GJF_VERSION, "formatter_sha256": GJF_SHA256,
        "formatter_flags": ["--aosp", "--dry-run", "--set-exit-if-changed"],
        "write_paths": list(ADDED),
        "snapshots": snaps,
        "worker_invoked": False, "api_calls": 0,
        "holdout_accessed": False, "production_authority": False,
        "receipt_authenticated": False,
    }
    data = (json.dumps(bundle, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")) + "\n").encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Fail closed; do not replace an existing bundle, even on rerun.
    with args.out.open("xb") as fp:
        fp.write(data)
    sidecar = args.out.with_suffix(".sha256")
    sidecar.write_text(sha(data)+"  "+args.out.name+"\n", encoding="ascii")
    print("EX6_EVIDENCE_BUNDLE_SHA256="+sha(data))
    for snap in snaps:
        for name, record_ in snap["commands"].items():
            print("EX6_"+snap["label"].upper()+"_"+name.upper()+
                  "_EXIT="+str(record_["exit_code"]))
    print("EX6_EVIDENCE_PUBLISHED_AUTHORITY_FALSE=true")

if __name__ == "__main__":
    main()
