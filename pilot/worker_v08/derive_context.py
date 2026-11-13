#!/usr/bin/env python3
"""Deterministic, bounded, offline context derivation for Worker tasks.

Never reads denied files, secrets or hidden oracles. The returned record
contains selected paths, the single winning reason, bytes, and rejected paths.
No AI and no recursive Java traversal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
from pathlib import Path, PurePosixPath

MAX_BYTES = 240_000
MAX_CONTEXT = 12
MAX_WRITE = 6
REASONS = ("WRITE_TARGET", "IMPORT", "SAME_PACKAGE_REF", "BUILD", "SPEC", "VISIBLE_TEST")
EX5C_WRITES = (
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderRepository.java",
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/InMemoryReminderRepository.java",
    "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderController.java",
)
EX5C_SPEC = "apps/time-service/REMINDERS_SPEC.md"


class ContextBlocked(ValueError):
    pass


def _safe_name(value: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ContextBlocked("CONTEXT_PATH_INVALID")
    p = PurePosixPath(value)
    if ".." in p.parts or "." in p.parts or str(p) != value:
        raise ContextBlocked("CONTEXT_PATH_INVALID")
    return value


def denial(name: str, is_spec: bool = False) -> str | None:
    parts = PurePosixPath(name).parts
    if any(p.startswith(".env") for p in parts):
        return "DENIED_ENV"
    if parts and parts[0] == "vendor":
        return "DENIED_VENDOR"
    if ".github" in parts:
        return "DENIED_GITHUB"
    if "target" in parts:
        return "DENIED_TARGET"
    if name.endswith(".jar"):
        return "DENIED_JAR"
    if name.endswith(".pem"):
        return "DENIED_PEM"
    if name.endswith(".key"):
        return "DENIED_KEY"
    if any(term in name.lower() for term in ("holdout", "secret", "oracle")):
        return "DENIED_SENSITIVE_NAME"
    contract_write = bool(re.fullmatch(r"contracts/[a-z][a-z0-9-]*[.]openapi[.]yaml", name))
    if not is_spec and not contract_write and (
            not parts or parts[0] not in ("apps", "frontend", "db")
            and not name.startswith("supabase/migrations/")):
        return "DENIED_OUTSIDE_APPS"
    return None


def _file(root: Path, name: str) -> Path | None:
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        return None
    return path


def _files(root: Path, start: Path):
    """Deterministic metadata-only scan (no denied file bytes read)."""
    if not start.is_dir() or start.is_symlink():
        return []
    return sorted((p.relative_to(root).as_posix() for p in start.rglob("*")
                   if p.is_file() or p.is_symlink()))


def _source_root(name: str) -> str:
    prefix, sep, _ = name.partition("/src/main/java/")
    return prefix + "/src/main/java" if sep else ""


def _package(source: str) -> str:
    m = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", source)
    return m.group(1) if m else ""


def _imports(source: str) -> list[str]:
    return sorted(set(re.findall(r"(?m)^\s*import\s+(?:static\s+)?(lf\.sandbox\.[\w.]+)\s*;", source)))


def derive(root: Path, write_scope: list[str], spec_paths: list[str]) -> dict:
    root = root.resolve()
    if not isinstance(write_scope, list) or not isinstance(spec_paths, list):
        raise ContextBlocked("CONTEXT_SCOPE_INVALID")
    if not write_scope or len(write_scope) > MAX_WRITE or len(set(write_scope)) != len(write_scope):
        raise ContextBlocked("LOTE_DEMASIADO_GRANDE" if len(write_scope) > MAX_WRITE else "CONTEXT_SCOPE_INVALID")
    if len(set(spec_paths)) != len(spec_paths):
        raise ContextBlocked("CONTEXT_SCOPE_INVALID")
    writes = [_safe_name(n) for n in write_scope]
    specs = [_safe_name(n) for n in spec_paths]
    reasons: dict[str, str] = {}
    denied: dict[str, str] = {}

    def add(name: str, reason: str, *, spec: bool = False):
        name = _safe_name(name)
        forbidden = denial(name, is_spec=spec)
        if forbidden:
            denied[name] = forbidden
            return
        if _file(root, name) is not None and name not in reasons:
            reasons[name] = reason

    # WRITE_TARGET has priority over any nonrecursive neighbor source.
    for name in writes:
        add(name, "WRITE_TARGET")
    for name in writes:
        if not name.endswith(".java"):
            continue
        source_file = _file(root, name)
        if source_file is None or denial(name):
            continue
        source = source_file.read_text(encoding="utf-8")
        src_root = _source_root(name)
        if not src_root:
            continue
        pkg = _package(source)
        package_dir = (root / name).parent
        sibling_names = _files(root, package_dir)
        for imported in _imports(source):
            imported_path = src_root + "/" + imported.replace(".", "/") + ".java"
            if _file(root, imported_path):
                add(imported_path, "IMPORT")
            else:
                # Imports from explicitly disallowed vendor trees are recorded,
                # never opened or added to the model context.
                vendor_candidate = "vendor/" + imported.split(".")[-1] + ".java"
                if _file(root, vendor_candidate):
                    add(vendor_candidate, "IMPORT")
        for sibling in sibling_names:
            if sibling == name or not sibling.endswith(".java"):
                continue
            class_name = PurePosixPath(sibling).stem
            if re.search(r"\b" + re.escape(class_name) + r"\b", source):
                add(sibling, "SAME_PACKAGE_REF")
        # Collect sensitive local candidates by filename only; do not open.
        for candidate in _files(root, root / src_root.split("/src/main/java")[0]):
            if denial(candidate) and (".env" in candidate or
                                      any(t in candidate.lower() for t in
                                          ("holdout", "secret", "oracle"))):
                denied[candidate] = denial(candidate)  # type: ignore[assignment]
        parent = (root / name).parent
        while parent != root and parent.is_relative_to(root):
            pom = parent / "pom.xml"
            if pom.is_file() or pom.is_symlink():
                add(pom.relative_to(root).as_posix(), "BUILD")
                break
            parent = parent.parent

    # TS/TSX: relative imports plus project manifests; no recursive traversal.
    for name in writes:
        if not name.endswith((".ts", ".tsx")) or denial(name):
            continue
        source_file = _file(root, name)
        if source_file is None:
            continue
        source = source_file.read_text(encoding="utf-8")
        imports = sorted(set(re.findall(
            r"""(?:import\s+(?:[^;]*?\s+from\s+)?|require\s*\(|import\s*\()\s*['"]([.][^'"]+)['"]""",
            source)))
        for module in imports:
            # Normalize ../ locally, then apply the strict path policy.
            relative = posixpath.normpath(str(PurePosixPath(name).parent / module))
            try:
                _safe_name(relative)
            except ContextBlocked:
                continue
            for candidate in (relative + ext for ext in
                              (".ts", ".tsx", "/index.ts", "/index.tsx")):
                if _file(root, candidate):
                    add(candidate, "IMPORT")
                    break
        parent = (root / name).parent
        while parent != root and parent.is_relative_to(root):
            for manifest in ("package.json", "tsconfig.json"):
                candidate = parent / manifest
                if candidate.is_file() or candidate.is_symlink():
                    add(candidate.relative_to(root).as_posix(), "BUILD")
            parent = parent.parent

    # Flyway: only earlier versioned migrations within the same directory.
    for name in writes:
        if not name.lower().endswith(".sql") or denial(name):
            continue
        target = PurePosixPath(name)
        version = re.fullmatch(r"V([0-9]+)__[^/]+\.sql", target.name)
        if version is None:
            continue
        for other in _files(root, root / target.parent):
            if other == name or denial(other):
                continue
            m = re.fullmatch(r"V([0-9]+)__[^/]+\.sql", PurePosixPath(other).name)
            if m and PurePosixPath(other).parent == target.parent and int(m[1]) < int(version[1]):
                add(other, "IMPORT")

    for spec in specs:
        add(spec, "SPEC", spec=True)

    # Visible tests: exact class-name substring, only under src/test.
    class_names = tuple(PurePosixPath(n).stem for n in writes if n.endswith(".java"))
    for name in writes:
        prefix, sep, _ = name.partition("/src/main/java/")
        if not sep:
            continue
        for test in _files(root, root / prefix / "src/test"):
            if test.endswith(".java") and any(c in PurePosixPath(test).stem for c in class_names):
                add(test, "VISIBLE_TEST")

    selected = [{"path": name, "reason": reasons[name],
                 "bytes": (root / name).stat().st_size}
                for name in sorted(reasons)]
    total = sum(item["bytes"] for item in selected)
    excluded = [{"path": name, "reason": denied[name]} for name in sorted(denied)]
    if len(selected) > MAX_CONTEXT or total > MAX_BYTES:
        raise ContextBlocked("LOTE_DEMASIADO_GRANDE")
    return {"schema_version": "LF_DERIVED_CONTEXT_V1", "context_paths": [x["path"] for x in selected],
            "files": selected, "excluded": excluded, "bytes": total,
            "write_files": len(writes)}


def canonical(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def expected_ex5c(result: dict, root: Path) -> None:
    """Fail closed on real-repo routing drift, independent from runtime model."""
    names = {row["path"]: row["reason"] for row in result["files"]}
    src = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
    desired = {p: "WRITE_TARGET" for p in EX5C_WRITES}
    desired[src + "Reminder.java"] = "SAME_PACKAGE_REF"
    desired["apps/time-service/pom.xml"] = "BUILD"
    desired[EX5C_SPEC] = "SPEC"
    for name in _files(root, root / "apps/time-service/src/test"):
        if name.endswith(".java") and any(stem in PurePosixPath(name).stem for stem in
                                           ("ReminderRepository", "InMemoryReminderRepository", "ReminderController")):
            desired[name] = "VISIBLE_TEST"
    if names != desired:
        raise ContextBlocked("CONTEXT_DERIVATION_MISMATCH")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--task", help="Legacy task (ex5c retains its exact output)")
    parser.add_argument("--task-file", type=Path, help="Generic task specification JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from task_selector import select
    try:
        if bool(args.task) == bool(args.task_file):
            raise ContextBlocked("CONTEXT_TASK_INPUT_INVALID")
        if args.task_file:
            registration = json.loads(args.task_file.read_text(encoding="utf-8"))
            task = registration.get("task_spec", registration)
        else:
            task = select(args.task, require_holdout=True)
        spec_paths = task.get("spec_paths")
        if spec_paths is None:
            spec_paths = [task["spec_path"]] if task.get("spec_path") else []
        result = derive(args.root, task["write_path_patterns"], spec_paths)
        if args.task == "ex5c":
            expected_ex5c(result, args.root)
        payload = canonical(result)
        result["sha256"] = hashlib.sha256(payload).hexdigest()
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.is_symlink():
            raise ContextBlocked("CONTEXT_OUTPUT_SYMLINK")
        output.write_bytes(canonical(result))
        # The internal hash pins the canonical record without its own SHA field;
        # this independent sidecar hashes the *entire* emitted JSON file.
        sidecar = output.with_suffix(".sha256")
        if sidecar.is_symlink() or sidecar.exists():
            raise ContextBlocked("CONTEXT_OUTPUT_ALREADY_EXISTS")
        sidecar.write_text(hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n", encoding="utf-8")
        print("DERIVED_CONTEXT_PASS sha256=" + result["sha256"] +
              " files=" + str(len(result["files"])) + " bytes=" + str(result["bytes"]))
        return 0
    except (ContextBlocked, OSError, UnicodeError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
