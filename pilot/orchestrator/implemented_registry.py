#!/usr/bin/env python3
"""T7 verified implementation ledger: reconstructed from Train ancestry only.

The trusted CP3.6 consumer is the only writer of implemented.json. Historical
backfill uses the same routine; never infer missing lot, rule or contract data.
No external model, manual mapping, or private oracle.
"""
from __future__ import annotations
# Resolve the trusted repository package when executed as a script.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

from pilot.worker_v08.github_network_retry import transport_read

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
                    storage()["requests_root"]).splitlines()
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
    # CP3.6 supports historical legacy plans and T7 request-local plans.
    # Prefer an exact plan binding; path-only matching is a legacy fallback,
    # never allowed to create false ambiguity over an authoritative binding.
    candidates = []
    reg = json_at(root, merge_sha, f"pilot/worker_v08/native_tasks/{task}.json")
    registered_paths = (reg or {}).get("task_spec", {}).get("write_path_patterns", [])
    for slug, lots, package in _plans(root, merge_sha):
        legacy = json_at(root, merge_sha, f"pilot/orchestrator/chain_plans/{slug}.json")
        local = json_at(root, merge_sha, f"pilot/runs/{slug}/chain_plan.json")
        if local is not None and legacy is not None and local != legacy:
            raise RegistryBlocked("REGISTRY_PLAN_AMBIGUOUS")
        plan = local or legacy
        for lot in lots["lots"]:
            paths = lot.get("write_paths")
            if not isinstance(paths, list) or not paths:
                continue
            binding = [row for row in (plan or {}).get("bindings", [])
                       if isinstance(row, dict) and row.get("lot_id") == lot.get("id")]
            bound = any(isinstance(row.get("task_name"), str)
                        and re.fullmatch(re.escape(row["task_name"])
                                         + r"(?:[2-9]|[1-9][0-9]+)?", task)
                        for row in binding)
            fallback = set(paths) == set(registered_paths)
            # Some legitimate verified integrations only change one file;
            # the remaining declared lot files are read and hashed from the
            # authenticated Train merge tree below.
            # An exact task/lot binding authorizes a partial EXTEND;
            # fallback provenance still requires every declared path changed.
            if bound and changed.intersection(paths):
                candidates.append((bound, slug, lot, package, paths))
            elif not bound and fallback and set(paths).issubset(changed):
                candidates.append((False, slug, lot, package, paths))
    authoritative = [row for row in candidates if row[0]]
    selected = authoritative if authoritative else candidates
    for _bound, slug, lot, package, paths in selected:
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
        entry = {
            "request": slug, "lot": lot.get("id"), "area": lot.get("area"),
            "requirement_ids": ids, "rule_codes": rule_codes or [],
            "endpoints": endpoints or [], "files": files,
            "merge_sha": merge_sha,
            "status": "NO_DERIVABLE" if reasons else "ATTESTED",
            "reasons": reasons,
        }
        if _bound and not set(paths).issubset(changed):
            entry["unchanged_paths"] = sorted(set(paths) - changed)
        entries.append(entry)
    if len(entries) != 1:
        return {"request": None, "lot": None, "area": None,
                "requirement_ids": [], "rule_codes": [], "endpoints": [],
                "files": [], "merge_sha": merge_sha,
                "status": "NO_DERIVABLE",
                "reasons": ["LOT_MAPPING_NOT_UNIQUE" if entries else "LOT_MAPPING_MISSING"]}
    return entries[0]


CLOSED_PULLS = "pulls?state=closed&base=main"


def batched_pr_reader(list_closed, read_one):
    """API budget (CHG-0252): one paginated listing of closed PRs replaces one
    GET /pulls/{n} per historical Train merge (~200 calls per rebuild, run in
    every PR CI). The list rows carry the same head/base/merge_commit_sha
    fields; `merged` is derived from merged_at. Any PR absent from the listing
    or not merged falls back to the exact single read, so authority never
    comes from a missing or partial page."""
    cache = None

    def reader(number):
        nonlocal cache
        if cache is None:
            rows = list_closed()
            if not isinstance(rows, list):
                raise RegistryBlocked("REGISTRY_PR_LIST_INVALID")
            cache = {}
            for row in rows:
                if isinstance(row, dict) and type(row.get("number")) is int:
                    cache[row["number"]] = dict(row, merged=row.get("merged_at") is not None)
        row = cache.get(number)
        if row is None or row.get("merged") is not True:
            return read_one(number)
        return row

    return reader


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
    # Preserve the reader error across reconstruct's REGISTRY_PR_UNAVAILABLE
    # conversion without exposing API response bodies or credentials.
    reader_failure = None

    def reader(number):
        nonlocal reader_failure
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        try:
            if not token:
                raise RegistryBlocked("REGISTRY_GITHUB_TOKEN_MISSING")
            request = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/pulls/{number}",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"})
            def read():
                with urllib.request.urlopen(request, timeout=25) as response:
                    return json.loads(response.read(5_000_001))
            return transport_read(read, "REGISTRY_PR")
        except Exception as exc:
            reader_failure = (number, exc)
            raise

    def list_closed():
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise RegistryBlocked("REGISTRY_GITHUB_TOKEN_MISSING")
        rows = []
        for page in range(1, 21):
            request = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/{CLOSED_PULLS}&per_page=100&page={page}",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"})
            def read():
                with urllib.request.urlopen(request, timeout=25) as response:
                    return json.loads(response.read(50_000_001))
            chunk = transport_read(read, "REGISTRY_PR_LIST")
            if not isinstance(chunk, list):
                raise RegistryBlocked("REGISTRY_PR_LIST_INVALID")
            rows.extend(chunk)
            if len(chunk) < 100:
                return rows
        raise RegistryBlocked("REGISTRY_PR_LIST_LIMIT")

    try:
        result = reconstruct(ROOT, args.main_sha, batched_pr_reader(list_closed, reader))
        if args.write:
            save(ROOT, result)
        print(json.dumps({"entries": len(result["entries"]),
                          "derivable": sum(x["status"] == "ATTESTED"
                                           for x in result["entries"])}))
        return 0
    except (RegistryBlocked, OSError, ValueError) as exc:
        if reader_failure is not None:
            number, reason = reader_failure
            code = (str(reason) if isinstance(reason, RegistryBlocked)
                    else str(reason) if isinstance(reason, ValueError)
                    and str(reason).startswith("GITHUB_")
                    else type(reason).__name__)
            print(f"REGISTRY_BUILD_BLOCKED:{code}:PR#{number}")
        else:
            code = str(exc) if isinstance(exc, RegistryBlocked) else type(exc).__name__
            print(f"REGISTRY_BUILD_BLOCKED:{code}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
