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


def _project_requirements(stages, semantic, data, provenance):
    """Use the real A6/A7/A9 partition and area projection, not a new ID guess."""
    from analysis.host.simulated_admission_gate import seal_envelope, admit
    from analysis.a6.implementability import run as a6_run
    from analysis.a7.front_coverage import run as a7_run
    from analysis.a9.front_bindings import partition
    from analysis.a9.area_projection import project

    signal = dict(semantic["a2_signals"])
    signal["evidence_refs"] = [provenance["semantic_signals.json"]]
    envelope = seal_envelope(stages, signal)
    admission = admit(stages, signal, envelope)
    a6 = a6_run(stages, signal, envelope, admission,
                source_obligations=semantic.get("source_obligations"))
    direct = data["direct_rules.json"]["linked_rules"]
    effective = data["effective_rules.json"]["rules"]
    categories = {
        "direct": {r["code"]: {"source_ref": r["source_ref"],
                               "categoria": r["categoria"]} for r in direct},
        "effective": {r["code"]: {"source_ref": r["source_ref"],
                                  "categoria": r["categoria"]} for r in effective},
        "fixture_provenance": {n: provenance[n] for n in
                               ("direct_rules.json", "effective_rules.json")},
    }
    a7 = a7_run(stages, signal, envelope, admission, a6, categories)
    reqs = [{"requirement_id": "REQ-" + r["requirement_id"],
             "source_requirement_id": r["requirement_id"],
             "evidence_refs": r["evidence_refs"]} for r in a6["requirements"]]
    scope = stages["A3"]["target_ref"]
    fronts, _ = partition(
        a7["material_fronts"], reqs, data["screen_contract.json"]["contract"],
        {r["code"]: r for r in effective}, scope=scope,
        create_empty_inventory=True)
    projected, _, _, _ = project(scope, reqs, fronts, readiness="READY_CANDIDATE")
    return projected


def attest(fixtures: Path, inventory: dict, data: dict, provenance: dict, stages: dict) -> dict:
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
        return {"status": "UNVERIFIED:DEPENDENCIA_SIN_REQUISITO", "simulation": True, "entries": []}
    try:
        main_sha = _main_sha(root)
        requirements = _project_requirements(
            stages, data["semantic_signals.json"], data, provenance)
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
            UnicodeError, ValueError, KeyError, TypeError) as exc:
        reason = (str(exc).split(":", 1)[0] if isinstance(exc, DependencyBlocked)
                  else "DEPENDENCIA_SIN_REQUISITO" if isinstance(exc, (KeyError, TypeError))
                  else "DEPENDENCIA_DECLARADA_AUSENTE")
        return {"status": "UNVERIFIED:" + reason, "reason": reason,
                "simulation": True, "entries": [],
                "production_authority": False}
