#!/usr/bin/env python3
"""CHG-0029: byte-for-byte class equivalence under pinned Palantir/Spotless.

Only sandbox time-service, NO model, NO secrets, no historical evidence changes.
Uses the original main tree as N and the current worktree as N+1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = Path("apps/time-service")
SOURCE = APP / "src/main/java"
BASE = "f18b2d96b7e1a8263749d35a7afcc9c043521cb8"
SPOTLESS = "3.10.4"
PALANTIR = "2.102.0"


def run(*args: str) -> bytes:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, check=False, timeout=360)
    if result.returncode:
        raise RuntimeError(
            "PALANTIR_2A_COMMAND_FAILED:" + args[0]
            + ":exit=" + str(result.returncode)
            + ":STDOUT=" + result.stdout.decode("utf-8", errors="replace")[-3500:]
            + ":STDERR=" + result.stderr.decode("utf-8", errors="replace")[-3500:]
        )
    return result.stdout


def source_paths() -> list[str]:
    data = run("git", "ls-tree", "-r", "--name-only", BASE, "--", str(SOURCE)).decode()
    paths = sorted(path for path in data.splitlines() if path.endswith(".java"))
    if not paths:
        raise RuntimeError("PALANTIR_2A_BASE_JAVA_MISSING")
    current = sorted(str(p.relative_to(ROOT)) for p in (ROOT / SOURCE).rglob("*.java"))
    if paths != current:
        raise RuntimeError("PALANTIR_2A_JAVA_PATHS_DRIFT")
    return paths


def compile_classes(sources: list[Path], out: Path, classpath: str) -> dict[str, str]:
    out.mkdir(parents=True)
    run(
        "javac", "--release", "21", "-g:none", "-encoding", "UTF-8",
        "-cp", classpath, "-d", str(out), *map(str, sources)
    )
    classes = {
        str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob("*.class"))
    }
    if not classes:
        raise RuntimeError("PALANTIR_2A_CLASSES_MISSING")
    return classes


def verify(apply: bool, receipt_path: Path) -> None:
    paths = source_paths()
    with tempfile.TemporaryDirectory(prefix="lf_palantir_2a_") as folder:
        tmp = Path(folder)
        cp_file = tmp / "dependencies.txt"
        run(
            "mvn", "-B", "-q", "-f", str(APP / "pom.xml"),
            "dependency:build-classpath", "-Dmdep.outputFile=" + str(cp_file)
        )
        cp = cp_file.read_text(encoding="utf-8").strip()
        if not cp:
            raise RuntimeError("PALANTIR_2A_CLASSPATH_MISSING")
        old_root = tmp / "old_sources"
        for path in paths:
            dest = old_root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(run("git", "show", BASE + ":" + path))
        before = compile_classes([old_root / p for p in paths], tmp / "before", cp)
        if apply:
            run("mvn", "-B", "-f", str(APP / "pom.xml"), "spotless:apply")
        run("mvn", "-B", "-q", "-f", str(APP / "pom.xml"), "spotless:check")
        after = compile_classes([ROOT / p for p in paths], tmp / "after", cp)
        if before != after:
            differences = sorted(set(before) ^ set(after) |
                                 {p for p in before.keys() & after.keys() if before[p] != after[p]})
            raise RuntimeError("PALANTIR_2A_CLASS_BYTES_DIFFER:" + ",".join(differences))
        changed = [
            p for p in paths
            if run("git", "show", BASE + ":" + p) != (ROOT / p).read_bytes()
        ]
        if not changed:
            raise RuntimeError("PALANTIR_2A_NO_FORMAT_CHANGES")
        report = {
            "schema_version": "LF_PALANTIR_2A_CLASS_EQUIVALENCE_V1",
            "baseline_commit": BASE,
            "formatter": "spotless-maven-plugin",
            "spotless_version": SPOTLESS,
            "palantir_java_format_version": PALANTIR,
            "command": "mvn -B -f apps/time-service/pom.xml spotless:apply",
            "compiler": ["javac", "--release", "21", "-g:none"],
            "source_paths": paths,
            "changed_java_paths": changed,
            "class_count": len(before),
            "class_sha256_before": before,
            "class_sha256_after": after,
            "class_bytes_identical": True,
            "candidate_sandbox_only": True,
            "model_calls": 0,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("PALANTIR_2A_CLASS_BYTES_IDENTICAL_PASS")
        print("PALANTIR_2A_CLASS_COUNT=" + str(len(before)))
        print("PALANTIR_2A_FORMATTED_JAVA_COUNT=" + str(len(changed)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path, required=True)
    options = parser.parse_args()
    verify(options.apply, options.receipt)
