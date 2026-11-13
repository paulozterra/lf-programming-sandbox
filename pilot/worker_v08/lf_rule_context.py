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
        # Contract-only lots have no independent L2 stack manifest; the
        # API domain is provided by a unique manifest only if unambiguous.
        possibilities = [name for name, item in options.items()
                         if "STD-API" in item.get("domains", [])]
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
    pinfile = STD / "pins.json"
    pins = json.loads(pinfile.read_text("utf-8"))
    # Resolve catalog compatibility from standard pins, never synthesize SHA.
    pin = {"catalog_sha256": hashlib.sha256((STD / "catalog.json").read_bytes()).hexdigest(),
           "catalog_version": catalog["catalog_version"]}
    known_pins = json.dumps(pins, sort_keys=True)
    if pin["catalog_sha256"] not in known_pins:
        raise RuleContextBlocked("LF_CATALOG_PIN_UNATTESTED")
    resolver = _resolver()
    try:
        content, receipt = resolver.assemble(pin, [selected], active)
    except (ValueError, KeyError, TypeError) as exc:
        raise RuleContextBlocked("LF_SKILL_ASSEMBLY_BLOCKED") from exc
    receipt["area"] = area
    receipt["selected_stack"] = selected
    receipt["selected_domains"] = active
    return content.encode("utf-8"), receipt
