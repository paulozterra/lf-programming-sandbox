#!/usr/bin/env python3
"""Generate deterministic EX5C N+1 formatting remediation, without a model.

Run only on checked-out sandbox main after the AOSP rule is merged. Original
code is pinned to e76b213. Before applying any Git change, compile both
original and formatted sources with javac -g:none; every class path and
every class byte must match, otherwise BLOCK and no commit.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_ROOT = pathlib.Path("apps/time-service/src/main/java")
POM = "apps/time-service/pom.xml"
ORIGINAL = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
GJF_VERSION = "1.30.0"
GJF_SHA256 = "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"
GJF_URL = ("https://github.com/google/google-java-format/releases/download/v1.30.0/"
           "google-java-format-1.30.0-all-deps.jar")


def require(test: bool, reason: str) -> None:
    if not test:
        raise RuntimeError("FORMAT_REMEDIATION_BLOCK:" + reason)


def run(argv: list[str], cwd: pathlib.Path = ROOT) -> bytes:
    result = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=360)
    if result.returncode != 0:
        raise RuntimeError("FORMAT_REMEDIATION_BLOCK:COMMAND_FAILED:" +
                           argv[0] + ":" + str(result.returncode) + "\n" +
                           result.stderr.decode("utf-8", errors="replace")[-1000:])
    return result.stdout


def git(*argv: str) -> bytes:
    return run(["git", *argv])


def checked_source_inventory(root: pathlib.Path) -> list[pathlib.Path]:
    paths = sorted((root / SRC_ROOT).rglob("*.java"))
    require(bool(paths), "NO_JAVA_FILES")
    return paths


def classes(root: pathlib.Path, destination: pathlib.Path, classpath: str) -> dict[str, str]:
    destination.mkdir(parents=True)
    files = checked_source_inventory(root)
    argv = ["javac", "--release", "21", "-g:none", "-encoding", "UTF-8",
            "-cp", classpath, "-d", str(destination)] + [str(x) for x in files]
    run(argv, cwd=root)
    output = {}
    for p in destination.rglob("*.class"):
        key = p.relative_to(destination).as_posix()
        output[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    require(bool(output), "NO_COMPILED_CLASSES")
    return output


def main() -> None:
    require(git("rev-parse", "--abbrev-ref", "HEAD").strip() != b"HEAD",
            "DETACHED_WORKTREE")
    require(not git("status", "--porcelain"), "DIRTY_WORKTREE")
    require(git("rev-parse", ORIGINAL + "^{commit}").decode().strip() == ORIGINAL,
            "ORIGINAL_COMMIT_UNAVAILABLE")
    # Same Java bytes as original N; policy, evidence and workflow files may differ.
    result = subprocess.run(["git", "diff", "--quiet", ORIGINAL, "--",
                             SRC_ROOT.as_posix()], cwd=ROOT)
    require(result.returncode == 0, "JAVA_DRIFT_FROM_ORIGINAL_N")
    head = git("rev-parse", "HEAD").decode().strip()
    require(head != ORIGINAL, "AOSP_POLICY_NOT_YET_MERGED")
    spec = (ROOT / "apps/time-service/REMINDERS_SPEC.md").read_text(encoding="utf-8")
    require("google-java-format 1.30.0" in spec and "`--aosp`" in spec,
            "AOSP_POLICY_MISSING")

    with tempfile.TemporaryDirectory(prefix="lf_ex5c_format_n1_") as temp:
        area = pathlib.Path(temp)
        jar = area / "google-java-format-1.30.0-all-deps.jar"
        req = urllib.request.Request(GJF_URL, headers={"User-Agent": "LF-EX5C-AOSP"})
        with urllib.request.urlopen(req, timeout=90) as stream:
            raw = stream.read(8_000_000)
        require(hashlib.sha256(raw).hexdigest() == GJF_SHA256, "FORMATTER_SHA_MISMATCH")
        jar.write_bytes(raw)

        baseline = area / "original"
        candidate = area / "candidate"
        for dest in (baseline, candidate):
            shutil.copytree(ROOT / "apps/time-service", dest / "apps/time-service",
                            ignore=shutil.ignore_patterns("target", ".git"))
        old_java = checked_source_inventory(baseline)
        new_java = checked_source_inventory(candidate)
        require([p.relative_to(baseline) for p in old_java] ==
                [p.relative_to(candidate) for p in new_java], "JAVA_INVENTORY_DRIFT")
        format_args = ["java", "-jar", str(jar), "--aosp", "--replace"] + [
            str(p) for p in new_java]
        run(format_args, cwd=candidate)
        # Must be fully clean under the same pinned formatter.
        dry = ["java", "-jar", str(jar), "--aosp", "--dry-run",
               "--set-exit-if-changed"] + [str(p) for p in new_java]
        run(dry, cwd=candidate)

        cp_file = area / "classpath.txt"
        run(["mvn", "-B", "-q", "-f", POM, "dependency:build-classpath",
             "-Dmdep.outputFile=" + str(cp_file)], cwd=ROOT)
        require(cp_file.is_file(), "DEPENDENCY_CLASSPATH_MISSING")
        classpath = cp_file.read_text(encoding="utf-8").strip()
        before = classes(baseline, area / "base-classes", classpath)
        after = classes(candidate, area / "formatted-classes", classpath)
        require(before == after, "CLASS_BYTES_DIFFER:" +
                str(sorted(set(before.items()) ^ set(after.items()))[:4]))
        print("EX5C_FORMAT_JAVAC_G_NONE_CLASS_BYTES_IDENTICAL_PASS")
        print("EX5C_FORMAT_CLASS_COUNT=" + str(len(before)))
        print("EX5C_FORMAT_GOOGLE_JAVA_FORMAT_VERSION=" + GJF_VERSION)
        print("EX5C_FORMAT_GOOGLE_JAVA_FORMAT_SHA256=" + GJF_SHA256)
        print("EX5C_FORMAT_SOURCE_COMMIT=" + ORIGINAL)

        # Only after equivalence: apply the already-verified formatted bytes.
        changed = []
        for source in new_java:
            rel = source.relative_to(candidate)
            original = ROOT / rel
            new_bytes = source.read_bytes()
            if original.read_bytes() != new_bytes:
                original.write_bytes(new_bytes)
                changed.append(rel.as_posix())
        require(bool(changed), "NO_FORMAT_DELTA")
        actual = git("diff", "--name-only").decode().splitlines()
        require(sorted(actual) == sorted(changed), "CHANGED_PATHS_OUTSIDE_FORMAT")
        require(all(name.startswith(SRC_ROOT.as_posix() + "/") and
                    name.endswith(".java") for name in actual),
                "NON_JAVA_FILE_MODIFIED")
        print("EX5C_FORMAT_ONLY_JAVA_PATHS=" + str(len(changed)))
        print("EX5C_FORMAT_NO_MODEL=true")
        print("EX5C_FORMAT_PRODUCTION_AUTHORITY=false")


if __name__ == "__main__":
    main()
