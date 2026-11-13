"""T7.2: simulation-only evidence of declared dependencies against exact main bytes.

Never accepts a declaration as proof. No network, no production authority.
Both a Git main blob and the checkout file must match the index SHA256.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from pilot.orchestrator.declared_dependencies import select, resolve, DependencyBlocked
from pilot.orchestrator.reuse_assessment import index


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, timeout=10).stdout


def _main_sha(root: Path) -> str:
    for ref in ("refs/remotes/origin/main", "refs/heads/main"):
        try:
            sha = _git(root, "rev-parse", "--verify", ref).decode().strip()
            if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
                return sha
        except (OSError, subprocess.SubprocessError, UnicodeError):
            continue
    raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")


def attest(fixtures: Path, inventory: dict, direct: dict, effective: dict) -> dict:
    """Return a narrow evidence ledger, or no attestation at all.

    A 13-file fiche lives in <root>/analysis/fixtures/<screen>. Registry
    and index are read from exactly that root, never a different checkout.
    """
    dependencies = inventory.get("dependencies")
    if not isinstance(dependencies, list):
        raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")
    if not dependencies:
        return {"status": "NOT_APPLICABLE", "simulation": True, "entries": []}
    root = fixtures.parent.parent.parent
    if fixtures.parent.name != "fixtures" or fixtures.parent.parent.name != "analysis":
        return {"status": "UNVERIFIED", "simulation": True, "entries": []}
    try:
        main_sha = _main_sha(root)
        rules = [r for r in effective.get("rules", [])
                 if r.get("status") == "VIGENTE" and r.get("pending_decision") is False]
        requirements = [{"requirement_id": "REQ-" + row["code"],
                         "source_requirement_id": row["code"]} for row in rules]
        chosen = select(dependencies, requirements)
        registry_file = root / "pilot/registry/implemented.json"
        if registry_file.is_symlink():
            raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")
        registry = (json.loads(registry_file.read_text("utf-8"))
                    if registry_file.is_file()
                    else {"schema_version": "T7_IMPLEMENTED_REGISTRY_V1", "entries": []})
        if registry.get("schema_version") != "T7_IMPLEMENTED_REGISTRY_V1":
            raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")
        indexed = index(root)
        entries = []
        for req_id, dep in sorted(chosen.items()):
            primary, related = resolve(indexed, registry, root, dep)
            sources = [primary, *related]
            evidence = []
            for item in sources:
                path, digest = item["path"], item["sha256"]
                actual = _git(root, "show", main_sha + ":" + path)
                if hashlib.sha256(actual).hexdigest() != digest:
                    raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")
                evidence.append({"path": path, "sha256": digest,
                                 "main_commit_sha": main_sha,
                                 "attestation_mode": "SIMULATED"})
            entries.append({"requirement_id": req_id, "kind": dep["kind"],
                            "key": dep["key"], "evidence": evidence,
                            "attestation_mode": "SIMULATED"})
        if len(entries) != len(dependencies):
            raise DependencyBlocked("DEPENDENCIA_DECLARADA_AUSENTE")
        return {"status": "CONFIRMED", "simulation": True,
                "main_commit_sha": main_sha, "entries": entries,
                "production_authority": False}
    except (DependencyBlocked, OSError, subprocess.SubprocessError,
            UnicodeError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED", "simulation": True, "entries": [],
                "production_authority": False}
