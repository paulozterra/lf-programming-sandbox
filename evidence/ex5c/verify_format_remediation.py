#!/usr/bin/env python3
"""CI gate: independent N -> N+1 AOSP-only transform and identical .class bytes.

Triggered for owner-controlled format-only PR. Every candidate Java file MUST
be the exact output of pinned google-java-format --aosp applied to the
historical N Java bytes. No other edits are possible. Compile N and N+1 using
the same dependency classpath, javac -g:none and compare every class byte.
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import tempfile
import urllib.request

from format_remediation import (
    ROOT, ORIGINAL, POM, SRC_ROOT, GJF_SHA256, GJF_URL,
    require, run, git, checked_source_inventory, classes,
)


def main() -> None:
    require(not git("status", "--porcelain"), "CHECK_DIRTY")
    require(git("rev-parse", ORIGINAL + "^{commit}").decode().strip() == ORIGINAL,
            "ORIGINAL_N_MISSING")
    check_pom = subprocess.run(["git", "diff", "--quiet", ORIGINAL, "HEAD",
                                "--", POM], cwd=ROOT)
    require(check_pom.returncode == 0, "POM_CHANGED_FROM_ORIGINAL_N")

    with tempfile.TemporaryDirectory(prefix="lf_ex5c_format_pr_gate_") as temp:
        root = pathlib.Path(temp)
        old = root / "original"
        projected = root / "expected"
        old.mkdir()
        projected.mkdir()

        # Historical Git objects, not the candidate working tree, are the
        # authoritative input to the formatter.
        old_java = git("ls-tree", "-r", "--name-only", ORIGINAL, "--",
                       SRC_ROOT.as_posix()).decode().splitlines()
        require(bool(old_java), "ORIGINAL_N_JAVA_EMPTY")
        candidate_java = [
            p.relative_to(ROOT).as_posix()
            for p in checked_source_inventory(ROOT)
        ]
        require(sorted(old_java) == sorted(candidate_java),
                "ADDED_OR_DELETED_JAVA_SOURCE")

        for path in sorted(old_java):
            blob = git("show", ORIGINAL + ":" + path)
            for target in (old, projected):
                destination = target / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob)

        jar = root / "google-java-format-1.30.0-all-deps.jar"
        req = urllib.request.Request(GJF_URL, headers={"User-Agent": "LF-EX5C-CI"})
        with urllib.request.urlopen(req, timeout=90) as stream:
            data = stream.read(8_000_000)
        require(hashlib.sha256(data).hexdigest() == GJF_SHA256,
                "FORMATTER_PIN_MISMATCH")
        jar.write_bytes(data)
        run(["java", "-jar", str(jar), "--aosp", "--replace"] +
            [str(projected / f) for f in sorted(old_java)], cwd=projected)
        run(["java", "-jar", str(jar), "--aosp", "--dry-run",
             "--set-exit-if-changed"] +
            [str(ROOT / f) for f in sorted(candidate_java)])

        for path in old_java:
            expected = (projected / path).read_bytes()
            actual = (ROOT / path).read_bytes()
            require(expected == actual, "NOT_EXACT_AOSP_FORMAT:" + path)

        cp_file = root / "dependencies-classpath.txt"
        run(["mvn", "-B", "-q", "-f", POM, "dependency:build-classpath",
             "-Dmdep.outputFile=" + str(cp_file)])
        require(cp_file.is_file(), "CLASSPATH_MISSING")
        cp = cp_file.read_text(encoding="utf-8").strip()
        old_hashes = classes(old, root / "old-classes", cp)
        new_hashes = classes(ROOT, root / "new-classes", cp)
        require(old_hashes == new_hashes, "CLASS_BYTE_COMPARISON_BLOCK")
        changed = git("diff", "--name-only", ORIGINAL, "HEAD", "--",
                      SRC_ROOT.as_posix()).decode().splitlines()
        require(bool(changed) and all(p.endswith(".java") for p in changed),
                "NOT_A_FORMAT_REPAIR")

        print("EX5C_AOSP_EXACT_TRANSFORM_PASS")
        print("EX5C_JAVAC_G_NONE_IDENTICAL_CLASSES_PASS")
        print("EX5C_CLASS_FILES_VERIFIED=" + str(len(old_hashes)))
        print("EX5C_NO_FUNCTIONAL_CHANGE_PROVEN=true")
        print("EX5C_FORMAT_PRODUCTION_AUTHORITY=false")


if __name__ == "__main__":
    main()
