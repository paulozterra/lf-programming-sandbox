#!/usr/bin/env python3
"""EX5C v2 additive evidence: pinned formatter and javac -Xlint:all at TWO Git revisions.

Only reads the existing history and independently fetched, SHA-pinned formatting
binary. Never invokes model, accesses hidden tests, rewrites v1 or claims
production authority. Nonzero check exit is evidence, not silently converted
into PASS. Fatal preflight errors fail closed.
"""
from __future__ import annotations
import base64
import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("LF_EVIDENCE_SOURCE_ROOT", Path(__file__).resolve().parents[2])).resolve()
HERE = Path(__file__).resolve().parent
BASE = "28de535acd4a76be038013cc6241c59a08102155"
HEAD = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
V1_SHA = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"
VERSION = "1.30.0"
GJF_SHA256 = "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"
GJF_URL = ("https://github.com/google/google-java-format/releases/download/v"
           + VERSION + "/google-java-format-" + VERSION + "-all-deps.jar")
EXPECTED_JAVA = {"apps/time-service/src/main/java/lf/sandbox/time/TimeServiceApplication.java",
                 "apps/time-service/src/main/java/lf/sandbox/time/TimeController.java",
                 "apps/time-service/src/main/java/lf/sandbox/time/TimeConfig.java"}
EXPECTED_DIFF_SHA = "bfba0329bcac92dbde06a1319a16acd535acd718f224df6121dae3c70fe307c6"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def block(why: str):
    raise RuntimeError(why)


def run(argv: list[str], cwd: Path, *, timeout: int = 240) -> dict:
    start = time.monotonic_ns()
    result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout)
    duration = (time.monotonic_ns() - start) // 1_000_000
    return {
        "argv": argv, "exit_code": result.returncode, "duration_ms": duration,
        "stdout": {"base64": base64.b64encode(result.stdout).decode(),
                   "bytes": len(result.stdout), "sha256": sha(result.stdout)},
        "stderr": {"base64": base64.b64encode(result.stderr).decode(),
                   "bytes": len(result.stderr), "sha256": sha(result.stderr)}
    }


def checked_git(*args: str) -> bytes:
    x = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=60)
    if x.returncode:
        block("V2_GIT_FAILURE: " + " ".join(args))
    return x.stdout


def download_pinned_jar(output: Path) -> None:
    req = urllib.request.Request(GJF_URL, headers={"User-Agent": "LF-EX5C-v2-pinned-tool"})
    with urllib.request.urlopen(req, timeout=90) as f:
        content = f.read(10_000_000)
    if sha(content) != GJF_SHA256:
        block("V2_GOOGLE_JAVA_FORMAT_SHA_BLOCK")
    output.write_bytes(content)


def java_paths(checkout: Path) -> list[str]:
    main = checkout / "apps/time-service/src/main/java"
    names = sorted(p.relative_to(checkout).as_posix() for p in main.rglob("*.java"))
    if not names or any("holdout" in n.lower() or "secret" in n.lower() or
                        "oracle" in n.lower() for n in names):
        block("V2_JAVA_FILE_INVENTORY_BLOCK")
    return names


def format_findings(checkout: Path, jar: Path, files: list[str]) -> tuple[dict, list[dict]]:
    argv = ["java", "-jar", str(jar), "--dry-run", "--set-exit-if-changed", *files]
    observation = run(argv, checkout)
    if observation["exit_code"] not in (0, 1):
        block("V2_FORMATTER_EXECUTION_ERROR")
    findings = []
    for rel in files:
        original = (checkout / rel).read_bytes()
        fmt = run(["java", "-jar", str(jar), rel], checkout)
        if fmt["exit_code"] != 0:
            block("V2_FORMATTER_PROJECTION_FAILED")
        formatted = base64.b64decode(fmt["stdout"]["base64"])
        if original != formatted:
            old_lines = original.decode("utf-8").splitlines(keepends=True)
            new_lines = formatted.decode("utf-8").splitlines(keepends=True)
            for tag, i, j, k, l in difflib.SequenceMatcher(
                    None, old_lines, new_lines, autojunk=False).get_opcodes():
                if tag != "equal":
                    findings.append({
                        "path": rel, "line_start": i + 1, "line_end": max(i + 1, j),
                        "kind": "FORMAT_DELTA", "change": tag,
                        "old_sha256": sha("".join(old_lines[i:j]).encode()),
                        "formatted_sha256": sha("".join(new_lines[k:l]).encode())
                    })
    # A dry run is expected to return 1 if any files would be reformatted.
    if (observation["exit_code"] == 0) != (len(findings) == 0):
        block("V2_FORMATTER_FINDINGS_STATUS_MISMATCH")
    return observation, findings


def javac_findings(checkout: Path, files: list[str], output: Path) -> tuple[dict, list[dict], dict]:
    pom = "apps/time-service/pom.xml"
    output.mkdir(parents=True, exist_ok=True)
    cp_file = output / "dependencies-classpath.txt"
    dependency = run(["mvn", "-B", "-q", "-f", pom,
                      "dependency:build-classpath",
                      "-Dmdep.outputFile=" + str(cp_file)], checkout, timeout=240)
    if dependency["exit_code"] != 0 or not cp_file.exists():
        block("V2_JAVAC_DEPENDENCIES_BLOCK")
    # Separate isolated output per checkout, no writes to historical source.
    classes = output / "classes"
    classes.mkdir()
    classpath = cp_file.read_text(encoding="utf-8").strip()
    command = ["javac", "--release", "21", "-Xlint:all", "-encoding", "UTF-8",
               "-cp", classpath, "-d", str(classes), *files]
    observed = run(command, checkout, timeout=240)
    if observed["exit_code"] != 0:
        block("V2_JAVAC_COMPILE_BLOCK")
    combined = base64.b64decode(observed["stderr"]["base64"]).decode("utf-8", "replace")
    findings = []
    pattern = re.compile(r"(?m)^(.+?\.java):(\d+):\s*(warning|error):\s*(.*)$")
    for match in pattern.finditer(combined):
        rel = match.group(1)
        if rel.startswith(str(checkout)):
            rel = Path(rel).relative_to(checkout).as_posix()
        if rel not in files:
            block("V2_JAVAC_FINDING_OUTSIDE_SCOPE")
        findings.append({"path": rel, "line": int(match.group(2)),
                         "kind": match.group(3), "message": match.group(4)})
    return observed, findings, dependency


def commit_observation(checkout: Path, jar: Path, commit: str, output: Path) -> dict:
    files = java_paths(checkout)
    fmt, fmt_findings = format_findings(checkout, jar, files)
    javac, lint_findings, deps = javac_findings(checkout, files, output)
    return {
        "commit": commit, "files": [{"path": name,
                                    "blob_sha256": sha((checkout / name).read_bytes())}
                                   for name in files],
        "formatter": {"version": VERSION, "jar_sha256": GJF_SHA256,
                      "execution": fmt, "findings": fmt_findings},
        "javac": {"version_output": run(["javac", "-version"], checkout),
                  "execution": javac, "findings": lint_findings,
                  "classpath_resolver": deps},
        "candidate_source": "EXACT_GIT_CHECKOUT", "authority_authenticated": False
    }


def main():
    if checked_git("rev-parse", "HEAD").strip().decode() != HEAD:
        block("V2_WRONG_GIT_CHECKOUT")
    if sha(checked_git("diff", BASE, HEAD, "--", "apps/time-service/src/main")) != EXPECTED_DIFF_SHA:
        block("V2_REAL_DIFF_DRIFT")
    if not (HERE / "lf-evidence-bundle-v1.json").is_file() or sha(
            (HERE / "lf-evidence-bundle-v1.json").read_bytes()) != V1_SHA:
        block("V2_V1_PIN_INVALID")
    target = HERE / "v2"
    target.mkdir(parents=True, exist_ok=True)
    name = target / "lf-evidence-bundle-v2.json"
    if name.exists():
        block("V2_OVERWRITE_FORBIDDEN")
    with tempfile.TemporaryDirectory(prefix="ex5c_v2_offline_") as temp:
        tmp = Path(temp)
        jar = tmp / ("google-java-format-" + VERSION + ".jar")
        download_pinned_jar(jar)
        base_checkout = tmp / "base"
        final_checkout = tmp / "candidate"
        for path, commit in ((base_checkout, BASE), (final_checkout, HEAD)):
            x = run(["git", "clone", "--no-checkout", "--local", str(ROOT), str(path)], tmp)
            if x["exit_code"] != 0:
                block("V2_CLONE_BLOCK")
            x = run(["git", "checkout", "--detach", commit], path)
            if x["exit_code"] != 0:
                block("V2_HISTORICAL_CHECKOUT_BLOCK")
        results = []
        for checkout, commit, label in ((base_checkout, BASE, "baseline"),
                                        (final_checkout, HEAD, "candidate")):
            result = commit_observation(checkout, jar, commit, tmp / label)
            result["label"] = label
            results.append(result)
    bundle = {
        "schema_version": "LF_EX5C_REAL_EVIDENCE_BUNDLE_V2",
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "base_commit": BASE, "candidate_commit": HEAD,
        "v1_bundle_sha256": V1_SHA, "diff_sha256": EXPECTED_DIFF_SHA,
        "formatter_version": VERSION, "formatter_sha256": GJF_SHA256,
        "snapshots": results,
        "production_authority": False, "tool_execution_verified": False,
        "receipt_authenticated": False, "worker_invoked": False
    }
    name.write_bytes((json.dumps(bundle, ensure_ascii=True, sort_keys=True,
                                 separators=(",", ":")) + "\n").encode())
    checksum = sha(name.read_bytes())
    name.with_suffix(".sha256").write_text(checksum + "  " + name.name + "\n")
    print("EX5C_EVIDENCE_V2_CREATED sha256=" + checksum)
    for snap in results:
        print("EX5C_V2_" + snap["label"].upper() + "_FORMAT_EXIT=" +
              str(snap["formatter"]["execution"]["exit_code"]))
        print("EX5C_V2_" + snap["label"].upper() + "_JAVAC_EXIT=" +
              str(snap["javac"]["execution"]["exit_code"]))
    print("V1_UNCHANGED=true MODEL_NOT_INVOKED=true AUTHORITY_FALSE=true")


if __name__ == "__main__":
    main()
