#!/usr/bin/env python3
"""T7 verified implementation ledger: reconstructed from Train ancestry only.

The trusted CP3.6 consumer is the only writer of implemented.json. Historical
backfill uses the same routine; never infer missing lot, rule or contract data.
No external model, manual mapping, or private oracle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

SHA40 = re.compile(r"[a-f0-9]{40}\Z")
MERGE = re.compile(r"Merge PR #([1-9][0-9]*) via sandbox-train\Z")
BRANCH = re.compile(r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-([1-9][0-9]*)\Z")
ROOT = Path(__file__).resolve().parents[2]
REPO = "paulozterra/lf-programming-sandbox"


class RegistryBlocked(ValueError):
    pass


def command(root: Path, *argv: str) -> str:
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True,
                            timeout=120, check=False)
    if result.returncode:
        raise RegistryBlocked("REGISTRY_GIT_UNAVAILABLE")
    return result.stdout.strip()


def git_file(root: Path, commit: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", commit + ":" + path], cwd=root,
                            capture_output=True, timeout=45, check=False)
    return result.stdout if result.returncode == 0 else None


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_at(root: Path, commit: str, path: str) -> dict | None:
    raw = git_file(root, commit, path)
    if raw is None:
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _plans(root: Path, commit: str) -> list[tuple[str, dict, dict]]:
    """Enumerate pinned lot files at the merge being examined."""
    paths = command(root, "git", "ls-tree", "-r", "--name-only", commit,
                    "pilot/runs").splitlines()
    results = []
    for path in sorted(p for p in paths if p.endswith("/lots.json")):
        slug = path.split("/")[2]
        lots = json_at(root, commit, path)
        package = json_at(root, commit, f"pilot/runs/{slug}/analysis.json")
        if lots and package and isinstance(lots.get("lots"), list):
            results.append((slug, lots, package))
    return results


def _rules(package: dict, ids: list[str]) -> list[str] | None:
    selected = [r for r in package.get("applicable_rules", [])
                if isinstance(r, dict) and r.get("requirement_id") in ids]
    codes = {r.get("rule_code") for r in selected}
    if (not isinstance(package.get("applicable_rules"), list)
            or any(not isinstance(v, str) or not v for v in codes)):
        return None
    # Don't silently mark an obligation with absent rule evidence as complete.
    if not set(ids).issubset({r.get("requirement_id") for r in selected}):
        return None
    return sorted(codes)


def _contract_endpoints(root: Path, commit: str, lot: dict) -> list[str] | None:
    """Only contract-declared operations; never reverse-engineer a contract."""
    proposed = [lot.get("contract_context_ref")] + [
        p for p in lot.get("write_paths", []) if isinstance(p, str)
        and p.endswith((".openapi.yaml", ".openapi.yml", ".openapi.json"))]
    refs = sorted(set(p for p in proposed if isinstance(p, str) and p))
    if not refs:
        return None
    endpoints = []
    for path in refs:
        raw = git_file(root, commit, path)
        if raw is None:
            return None
        try:
            if path.endswith(".json"):
                contract = json.loads(raw)
            else:
                import yaml
                contract = yaml.safe_load(raw)
        except (ValueError, UnicodeError, ImportError):
            return None
        if not isinstance(contract, dict) or not isinstance(contract.get("paths"), dict):
            return None
        for route, methods in sorted(contract["paths"].items()):
            if not isinstance(methods, dict):
                return None
            for method in sorted(methods):
                if method.lower() in ("get", "post", "patch", "put", "delete"):
                    endpoints.append(method.upper() + " " + route)
    return sorted(set(endpoints))


def record_merge(root: Path, merge_sha: str, pr: dict, *,
                 current_sha: str) -> dict:
    branch = pr.get("head", {}).get("ref", "")
    matched = BRANCH.fullmatch(branch)
    if (not matched or pr.get("merged") is not True
            or pr.get("merge_commit_sha") != merge_sha
            or pr.get("base", {}).get("ref") != "main"):
        raise RegistryBlocked("REGISTRY_MERGE_UNTRUSTED")
    task = matched.group(1)
    parents = command(root, "git", "rev-list", "--parents", "-n", "1", merge_sha).split()
    if len(parents) != 3:
        raise RegistryBlocked("REGISTRY_NOT_TRAIN_MERGE")
    changed = set(command(root, "git", "diff", "--name-only", parents[1], merge_sha).splitlines())
    entries = []
    for slug, lots, package in _plans(root, merge_sha):
        for lot in lots["lots"]:
            paths = lot.get("write_paths")
            if not isinstance(paths, list) or not paths:
                continue
            # Task is pinned either by CP3.6 binding or by the native task
            # registration and a UNIQUE exact write-path set.
            plan = json_at(root, merge_sha, f"pilot/orchestrator/chain_plans/{slug}.json")
            binding = [b for b in (plan or {}).get("bindings", [])
                       if b.get("lot_id") == lot.get("id")]
            bound = bool(binding and any(re.fullmatch(
                re.escape(b["task_name"]) + r"(?:[2-9]|[1-9][0-9]+)?", task)
                for b in binding))
            reg = json_at(root, merge_sha, f"pilot/worker_v08/native_tasks/{task}.json")
            registered_paths = (reg or {}).get("task_spec", {}).get("write_path_patterns", [])
            if not bound and set(paths) != set(registered_paths):
                continue
            if not set(paths).issubset(changed):
                continue
            ids = lot.get("requirement_ids", [])
            rule_codes = _rules(package, ids)
            endpoints = _contract_endpoints(root, merge_sha, lot)
            files = []
            for path in sorted(paths):
                raw = git_file(root, merge_sha, path)
                if raw is not None:
                    files.append({"path": path, "sha256": sha(raw)})
            reasons = []
            if not ids or not isinstance(ids, list):
                reasons.append("REQUIREMENT_IDS_MISSING")
            if rule_codes is None:
                reasons.append("RULE_BINDING_MISSING")
            if endpoints is None:
                reasons.append("CONTRACT_ENDPOINTS_NOT_DERIVABLE")
            if len(files) != len(paths):
                reasons.append("INTEGRATED_FILES_MISSING")
            entries.append({
                "request": slug, "lot": lot.get("id"), "area": lot.get("area"),
                "requirement_ids": ids, "rule_codes": rule_codes or [],
                "endpoints": endpoints or [], "files": files,
                "merge_sha": merge_sha,
                "status": "NO_DERIVABLE" if reasons else "ATTESTED",
                "reasons": reasons,
            })
    if len(entries) != 1:
        return {"request": None, "lot": None, "area": None,
                "requirement_ids": [], "rule_codes": [], "endpoints": [],
                "files": [], "merge_sha": merge_sha,
                "status": "NO_DERIVABLE",
                "reasons": ["LOT_MAPPING_NOT_UNIQUE" if entries else "LOT_MAPPING_MISSING"]}
    return entries[0]


def reconstruct(root: Path, current_sha: str, pr_reader) -> dict:
    if not SHA40.fullmatch(current_sha):
        raise RegistryBlocked("REGISTRY_BASE_INVALID")
    history = command(root, "git", "log", "--first-parent", "--format=%H%x09%s", current_sha).splitlines()
    entries = []
    for line in reversed(history):
        commit, _, subject = line.partition("\t")
        match = MERGE.fullmatch(subject)
        if not match:
            continue
        # Query metadata only for verified Train merge integration branches.
        # No manually inferred PR/head authority.
        try:
            pr = pr_reader(int(match.group(1)))
        except (ValueError, KeyError):
            raise RegistryBlocked("REGISTRY_PR_UNAVAILABLE")
        if not BRANCH.fullmatch(pr.get("head", {}).get("ref", "")):
            continue
        entries.append(record_merge(root, commit, pr, current_sha=current_sha))
    return {"schema_version": "T7_IMPLEMENTED_REGISTRY_V1",
            "source_main_sha": current_sha, "entries": entries}


def save(root: Path, value: dict) -> bool:
    target = root / "pilot/registry/implemented.json"
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if target.is_symlink():
        raise RegistryBlocked("REGISTRY_PATH_INVALID")
    if target.exists() and target.read_bytes() == raw:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--main-sha", required=True)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    def reader(number):
        return json.loads(command(ROOT, "gh", "api", f"repos/{REPO}/pulls/{number}"))
    try:
        result = reconstruct(ROOT, args.main_sha, reader)
        if args.write:
            save(ROOT, result)
        print(json.dumps({"entries": len(result["entries"]),
                          "derivable": sum(x["status"] == "ATTESTED"
                                           for x in result["entries"])}))
        return 0
    except (RegistryBlocked, OSError, ValueError):
        print("REGISTRY_BUILD_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
