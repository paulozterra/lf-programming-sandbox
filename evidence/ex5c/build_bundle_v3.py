#!/usr/bin/env python3
"""EX5C v3 after owner-merged N+1: SHA-pinned real AOSP-only remediation evidence.

Requires source checkout at the *current sandbox main merge commit*, with
full Git history. Rebuilds Git objects, verifies exact N->N+1 formatter
transform, compares every compiled Java class with javac -g:none, captures
Maven and HTTP smoke, and emits a distinct v3 JSON/sha256. V1/V2 immutable.
No model, no hidden oracle, no LF writes/authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.request

from build_bundle import smoke
from format_remediation import (
    ORIGINAL, POM, SRC_ROOT, GJF_SHA256, GJF_URL,
    require, run, classes, checked_source_inventory,
)

ROOT = pathlib.Path(os.environ.get("LF_EVIDENCE_SOURCE_ROOT",
                                    pathlib.Path(__file__).resolve().parents[2])).resolve()
HERE = pathlib.Path(__file__).resolve().parent
V1_SHA = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"
V2_SHA = "0988de2e39f5139596d05c3cbfcbe8c8998c753cdb009414e5b38da65172217b"
EXPECTED_BASE_TREE = "4ba97b68310e913795d7ae1ac35d5912e2fe6551"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def oid(kind: str, raw: bytes) -> str:
    return hashlib.sha1((kind + " " + str(len(raw)) + "\0").encode() + raw).hexdigest()


def git(*args: str, inp: bytes | None = None) -> bytes:
    p = subprocess.run(["git", "-C", str(ROOT), *args], input=inp,
                       capture_output=True, timeout=90)
    require(p.returncode == 0, "GIT:" + " ".join(args[:3]))
    return p.stdout


def record(argv: list[str], cwd: pathlib.Path = ROOT, timeout: int = 600) -> dict:
    import time
    start = time.monotonic_ns()
    p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout)
    return {"argv": argv, "exit_code": p.returncode,
            "duration_ms": (time.monotonic_ns() - start) // 1_000_000,
            "stdout": {"base64": base64.b64encode(p.stdout).decode(),
                       "bytes": len(p.stdout), "sha256": sha(p.stdout)},
            "stderr": {"base64": base64.b64encode(p.stderr).decode(),
                       "bytes": len(p.stderr), "sha256": sha(p.stderr)}}


def prepare_sources(tmp: pathlib.Path, head: str) -> tuple[pathlib.Path, pathlib.Path, list[str]]:
    old, candidate = tmp / "original", tmp / "candidate"
    old.mkdir()
    candidate.mkdir()
    old_files = git("ls-tree", "-r", "--name-only", ORIGINAL, "--",
                    SRC_ROOT.as_posix()).decode().splitlines()
    new_files = git("ls-tree", "-r", "--name-only", head, "--",
                    SRC_ROOT.as_posix()).decode().splitlines()
    require(old_files == new_files and bool(old_files),
            "N_N1_JAVA_FILE_SET_MISMATCH")
    for name in old_files:
        base = git("show", ORIGINAL + ":" + name)
        current = git("show", head + ":" + name)
        for root, raw in ((old, base), (candidate, current)):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    return old, candidate, old_files


def raw_git(head: str) -> dict:
    raw = git("cat-file", "commit", head)
    tree = git("rev-parse", head + "^{tree}").decode().strip()
    sub = git("rev-parse", head + ":apps/time-service").decode().strip()
    base_sub = git("rev-parse", ORIGINAL + ":apps/time-service").decode().strip()
    require(oid("commit", raw) == head and base_sub == EXPECTED_BASE_TREE,
            "RAW_COMMIT_OR_BASE_TREE_BLOCK")
    require(("tree " + tree + "\n").encode() in raw[:100], "COMMIT_TREE_MISMATCH")
    parent_ids = [line[7:] for line in raw.decode("utf-8", errors="replace").splitlines()
                  if line.startswith("parent ")]
    require(bool(parent_ids) and ORIGINAL != head, "N1_COMMIT_OR_PARENTS_INVALID")
    rows = git("ls-tree", "-r", "-z", head, "--", "apps/time-service").split(b"\0")
    files = []
    for row in rows:
        if not row:
            continue
        meta, p = row.split(b"\t", 1)
        mode, typ, git_blob = meta.decode().split()
        require(typ == "blob" and mode == "100644", "N1_NON_BLOB_OR_MODE")
        name = p.decode()
        rawfile = git("show", head + ":" + name)
        require(oid("blob", rawfile) == git_blob, "N1_BLOB_OID_BLOCK")
        files.append({"path": name, "mode": mode, "oid": git_blob,
                      "bytes": len(rawfile), "content_base64": base64.b64encode(rawfile).decode()})
    require(len(files) >= 18, "N1_FILE_INVENTORY_MISSING")
    return {"commit": head, "tree": tree, "subtree": sub,
            "base_commit": ORIGINAL, "base_subtree": base_sub,
            "parents": parent_ids, "raw_commit_base64": base64.b64encode(raw).decode(),
            "raw_commit_sha256": sha(raw), "files": files}


def main() -> None:
    head = git("rev-parse", "HEAD").decode().strip()
    branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    require(branch == "main" and head != ORIGINAL, "MUST_RUN_ON_NEW_MAIN")
    require(git("merge-base", "--is-ancestor", ORIGINAL, head) == b"", "N_NOT_ANCESTOR")
    # The last command's successful empty stdout is not itself an ancestry
    # assertion; git() already requires exit 0.
    for path, expected in (("lf-evidence-bundle-v1.json", V1_SHA),
                           ("v2/lf-evidence-bundle-v2.json", V2_SHA)):
        x = HERE / path
        require(x.is_file() and sha(x.read_bytes()) == expected,
                "HISTORICAL_BUNDLE_PIN_DRIFT:" + path)

    with tempfile.TemporaryDirectory(prefix="lf_ex5c_v3_") as td:
        tmp = pathlib.Path(td)
        jar = tmp / "google-java-format-1.30.0-all-deps.jar"
        request = urllib.request.Request(GJF_URL, headers={"User-Agent": "LF-ex5c-v3-aosp"})
        with urllib.request.urlopen(request, timeout=90) as stream:
            binary = stream.read(8_000_000)
        require(sha(binary) == GJF_SHA256, "FORMATTER_PIN_MISMATCH")
        jar.write_bytes(binary)
        original, candidate, paths = prepare_sources(tmp, head)
        projected = tmp / "expected"
        shutil.copytree(original, projected)
        run(["java", "-jar", str(jar), "--aosp", "--replace"] +
            [str(projected / path) for path in paths], cwd=projected)
        for path in paths:
            require((projected / path).read_bytes() == (candidate / path).read_bytes(),
                    "N1_NOT_EXACT_AOSP_TRANSFORM:" + path)
        verify = record(["java", "-jar", str(jar), "--aosp", "--dry-run",
                         "--set-exit-if-changed"] +
                        [str(candidate / path) for path in paths], cwd=candidate)
        require(verify["exit_code"] == 0, "N1_FORMAT_DRY_RUN_FAILED")

        cp_path = tmp / "classpath.txt"
        dep = record(["mvn", "-B", "-q", "-f", POM, "dependency:build-classpath",
                      "-Dmdep.outputFile=" + str(cp_path)], cwd=ROOT)
        require(dep["exit_code"] == 0 and cp_path.is_file(), "N1_DEPENDENCY_RESOLUTION_BLOCK")
        cp = cp_path.read_text(encoding="utf-8").strip()
        before = classes(original, tmp / "before-classes", cp)
        after = classes(candidate, tmp / "after-classes", cp)
        require(before == after, "N1_CLASS_BYTES_CHANGED")
        git_proof = raw_git(head)
        changed = git("diff", "--name-only", ORIGINAL, head, "--",
                      SRC_ROOT.as_posix()).decode().splitlines()
        require(bool(changed) and all(p.endswith(".java") for p in changed),
                "N1_NOT_FORMAT_REMINDER_CHANGE")
        patch = git("diff", ORIGINAL, head, "--", SRC_ROOT.as_posix())
        require(bool(patch), "N1_PATCH_MISSING")

        mvn = record(["mvn", "-B", "-f", POM, "verify"], cwd=ROOT)
        require(mvn["exit_code"] == 0, "N1_MAVEN_VERIFY_BLOCK")
        http = smoke()
        evidence = {
            "schema_version": "LF_EX5C_REAL_EVIDENCE_BUNDLE_V3",
            "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
            "lineage_reason": "FORMAT_REMEDIATION",
            "iteration": "N_PLUS_1", "production_authority": False,
            "tool_execution_verified": False, "receipt_authenticated": False,
            "worker_invoked": False, "testing_real_invoked": False,
            "v1_bundle_sha256": V1_SHA, "v2_bundle_sha256": V2_SHA,
            "formatter_version": "1.30.0", "formatter_mode": "--aosp",
            "formatter_sha256": GJF_SHA256,
            "git": git_proof,
            "changed_java_paths": changed,
            "diff": {"base_commit": ORIGINAL, "candidate_commit": head,
                     "sha256": sha(patch), "bytes": len(patch),
                     "content_base64": base64.b64encode(patch).decode()},
            "class_equivalence": {"javac_flags": ["--release", "21", "-g:none"],
                                  "baseline": before, "candidate": after,
                                  "class_count": len(after), "identical": True,
                                  "dependency_resolution": dep},
            "execution": {"format_check": verify, "maven_verify": mvn, "smoke": http},
            "decision_ref": "LF-OWNER-EX5C-FORMAT-REMEDIATION-20261106"
        }
        outdir = HERE / "v3"
        outdir.mkdir(parents=True, exist_ok=True)
        target = outdir / "lf-evidence-bundle-v3.json"
        require(not target.exists(), "V3_OVERWRITE_BLOCK")
        target.write_bytes((json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True) + "\n").encode("utf-8"))
        target.with_suffix(".sha256").write_text(
            sha(target.read_bytes()) + "  " + target.name + "\n")
        print("EX5C_V3_COMMIT=" + head)
        print("EX5C_V3_BUNDLE_SHA256=" + sha(target.read_bytes()))
        print("EX5C_V3_AOSP_FORMAT_PASS=true")
        print("EX5C_V3_JAVAC_G_NONE_BYTE_IDENTICAL_PASS=true")
        print("EX5C_V3_MAVEN_VERIFY_PASS=true")
        print("EX5C_V3_HTTP_SMOKE_PASS=true")
        print("EX5C_V3_PRODUCTION_AUTHORITY=false")
        print("EX5C_V3_MODEL_NOT_INVOKED=true")


if __name__ == "__main__":
    main()
