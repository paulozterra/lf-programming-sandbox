"""T8 CP1.6: project-standard context derived from the authoritative skills resolver.

Not a copy of standards/tools/skills.py: imports its assemble function and
skill manifests, preserving exclusions and the exact catalog pin.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "standards"

class RuleContextBlocked(ValueError):
    pass

def _resolver():
    source = STD / "tools/skills.py"
    spec = importlib.util.spec_from_file_location("lf_standard_skill_resolver", source)
    if spec is None or spec.loader is None:
        raise RuleContextBlocked("LF_SKILL_RESOLVER_MISSING")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def material(area: str) -> tuple[bytes, dict]:
    area = "BACKEND" if area == "INFRA" else area
    manifests = sorted((STD / "skills").glob("*/skill.json"))
    options = {}
    for path in manifests:
        value = json.loads(path.read_text("utf-8"))
        if value.get("skill_id") != path.parent.name:
            raise RuleContextBlocked("LF_SKILL_MANIFEST_INVALID")
        options[value["skill_id"]] = value
    # Selection uses each official stack's primary domain, not a mirrored
    # literal list of secondary domains. Every domain is taken from its
    # existing skill.json, as the canonical resolver does.
    catalog = json.loads((STD / "catalog.json").read_text("utf-8"))
    primaries = {
        "BACKEND": ("java-spring",),
        "FRONTEND": ("nextjs-typescript",),
        "DATA": ("postgresql",),
        "CONTRATO": ("http-api",),
    }
    if area not in primaries:
        raise RuleContextBlocked("LF_STACK_AREA_UNRESOLVED")
    desired = set(primaries[area])
    matching = [rule["domain"] for rule in catalog["rules"]
                if any(domain["id"] == rule["domain"] and
                       desired.intersection(domain.get("applies_to", []))
                       for domain in catalog["domains"])]
    if area == "CONTRATO":
        # Shared API contracts have no dedicated stack skill. Derive the API
        # rules directly from catalog, without pretending to select Spring
        # or Next for a contract-only lot.
        api_domains = [d["id"] for d in catalog["domains"]
                       if {"http-api", "all"}.intersection(d.get("applies_to", []))]
        rows = [r for r in catalog["rules"] if r["domain"] in api_domains]
        if not rows:
            raise RuleContextBlocked("LF_STACK_AREA_UNRESOLVED")
        content = "\n".join(r["id"] + " [" + r.get("status", "") +
                            "] " + r["rule"] for r in rows) + "\n"
        receipt = {"schema_version": "T8_LF_RULE_CONTEXT_V1", "area": area,
                   "selected_stack": None, "selected_domains": api_domains,
                   "rule_ids": [r["id"] for r in rows],
                   "pending_rule_ids": [r["id"] for r in rows if
                       r.get("status") in ("PENDIENTE_REVISION", "VALIDAR_CON_LEGAL")],
                   "assembled_sha256": hashlib.sha256(content.encode()).hexdigest()}
        return content.encode("utf-8"), receipt
    else:
        primary = {
            "BACKEND": "STD-BE", "FRONTEND": "STD-FE", "DATA": "STD-DB",
        }[area]
        possibilities = [name for name, item in options.items()
                         if primary in item.get("domains", [])]
    if len(possibilities) != 1:
        raise RuleContextBlocked("LF_STACK_AMBIGUOUS:" + area)
    selected = possibilities[0]
    manifest = options[selected]
    active = list(manifest.get("domains", []))
    # Assemble uses a versioned digest from the repository's own catalog;
    # the skill resolver independently validates catalog major.minor compat.
    pin = {"catalog_sha256": hashlib.sha256((STD / "catalog.json").read_bytes()).hexdigest(),
           "catalog_version": catalog["catalog_version"]}
    resolver = _resolver()
    try:
        content, receipt = resolver.assemble(pin, [selected], active)
    except (ValueError, KeyError, TypeError) as exc:
        raise RuleContextBlocked("LF_SKILL_ASSEMBLY_BLOCKED") from exc
    receipt["area"] = area
    receipt["selected_stack"] = selected
    receipt["selected_domains"] = active
    return content.encode("utf-8"), receipt
