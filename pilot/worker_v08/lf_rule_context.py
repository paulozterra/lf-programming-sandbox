"""CP1.6 LF domain context: the assigned stack skill is the only authority.

No maintained domain lists; the already chosen lot skill resolves to a
standards/skills/<stack>/skill.json whose domains drive skills.py. Unknown or
ambiguous selections fail closed with DOMINIOS_NO_RESUELTOS.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
STD = ROOT / "standards"


class RuleContextBlocked(ValueError):
    pass


def _resolver():
    source = STD / "tools/skills.py"
    spec = importlib.util.spec_from_file_location("lf_standard_skill_resolver", source)
    if spec is None or spec.loader is None:
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assigned_codes(area: str, *, root: Path = ROOT) -> list[str]:
    """Obtain the lot's stack identity from pinned profile/skill assignments."""
    role = "BACKEND" if area in ("INFRA", "CONTRATO") else area
    if role == "FRONTEND":
        pin = json.loads((root / "pilot/nextjs_source_pin.json").read_text("utf-8"))
        manifest = pin.get("manifest_path")
        if (pin.get("area") != role or not isinstance(manifest, str)
                or not manifest.startswith("standards/skills/")
                or not manifest.endswith("/skill.json")):
            raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
        return [pin["skill_id"]]
    bindings = json.loads((root / "pilot/lf_profiles_pinned/stack_skills_exp/"
                           "project_stack_binding_fixtures.json").read_text("utf-8"))
    rows = [x for x in bindings.get("rows", [])
            if x.get("project_ref") == "lf_java" and x.get("area") == role]
    if not rows:
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
    return [x["skill_code"] for x in sorted(rows, key=lambda x: x["priority"])]


def select_stack(codes: list[str], *, standards_root: Path = STD) -> str:
    """Resolve selected pinned skill codes to a unique, installed stack ID."""
    if not isinstance(codes, list) or not codes:
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
    candidates = {}
    for file in sorted((standards_root / "skills").glob("*/skill.json")):
        manifest = json.loads(file.read_text("utf-8"))
        if manifest.get("skill_id") != file.parent.name:
            raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
        candidates[manifest["skill_id"]] = manifest
    matched = set()
    for code in codes:
        if not isinstance(code, str):
            raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
        token = re.sub(r"[^a-z0-9]", "", code.lower())
        token = token.removesuffix("exp")
        for slug in candidates:
            normalized = re.sub(r"[^a-z0-9]", "", slug.lower())
            if token and (normalized == token or normalized.endswith(token)):
                matched.add(slug)
    if len(matched) != 1:
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
    return next(iter(matched))


def material(area: str, *, skill_codes: list[str] | None = None,
             root: Path = ROOT, standards_root: Path | None = None) -> tuple[bytes, dict]:
    standards = standards_root or STD
    codes = skill_codes if skill_codes is not None else assigned_codes(area, root=root)
    slug = select_stack(codes, standards_root=standards)
    manifest_path = standards / "skills" / slug / "skill.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    domains = manifest.get("domains")
    if (not isinstance(domains, list) or not domains
            or len(domains) != len(set(domains))
            or any(not isinstance(d, str) or not d.startswith("STD-") for d in domains)):
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
    catalog_bytes = (standards / "catalog.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    pin = {"catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
           "catalog_version": catalog["catalog_version"]}
    module = _resolver()
    module.STD = standards
    module.DIR = standards / "skills"
    try:
        body, receipt = module.assemble(pin, [slug], domains)
    except (ValueError, KeyError, TypeError) as exc:
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS") from exc
    if not receipt["rule_ids"]:
        raise RuleContextBlocked("DOMINIOS_NO_RESUELTOS")
    receipt["area"] = area
    receipt["selected_stack"] = slug
    receipt["selected_domains"] = domains
    return body.encode("utf-8"), receipt
