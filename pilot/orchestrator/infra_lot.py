#!/usr/bin/env python3
"""T3: deterministic missing-dependency admission, never edits build manifests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POLICY = HERE / "dependency_allowlist_v1.json"
SAFE_ID = re.compile(r"[a-z][a-z0-9-]*\Z")


class DependencyBlocked(ValueError):
    pass


def deny(reason):
    raise DependencyBlocked(reason)


def policy():
    try:
        data = json.loads(POLICY.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        deny("T3_ALLOWLIST_INVALID")
    if (data.get("schema_version") != "T3_DEPENDENCY_ALLOWLIST_V1"
            or data.get("infra", {}).get("area") != "INFRA"
            or data["infra"].get("profile_area") != "BACKEND"
            or not isinstance(data.get("targets"), dict)
            or not isinstance(data.get("requirements_by_area"), dict)):
        deny("T3_ALLOWLIST_INVALID")
    seen = set()
    for target, spec in data["targets"].items():
        if target not in ("maven", "npm") or not isinstance(spec.get("dependencies"), list):
            deny("T3_ALLOWLIST_INVALID")
        for item in spec["dependencies"]:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or not SAFE_ID.fullmatch(item["id"])
                    or not isinstance(item.get("version"), str)
                    or not re.fullmatch(r"[0-9]+(?:[.][0-9]+)*(?:[.-][a-zA-Z0-9]+)*", item["version"])
                    or item["id"] in seen):
                deny("T3_ALLOWLIST_INVALID")
            seen.add(item["id"])
    for area, ids in data["requirements_by_area"].items():
        if area not in ("DATA", "BACKEND", "FRONTEND") or not isinstance(ids, list):
            deny("T3_ALLOWLIST_INVALID")
        if any(identifier not in seen for identifier in ids):
            deny("T3_ALLOWLIST_INVALID")
    return data


def _manifest(root, name):
    # Only checked-out project manifests. Never read a file supplied by analysis.
    p = Path(root) / name
    if p.is_symlink() or not p.is_file():
        deny("T3_BASE_MANIFEST_MISSING")
    return p.read_text(encoding="utf-8")


def installed(root, config):
    observed = {}
    targets = config["targets"]
    if "maven" in targets:
        xml = _manifest(root, targets["maven"]["manifest"])
        try:
            tree = ET.fromstring(xml)
        except ET.ParseError:
            deny("T3_POM_INVALID")
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        for entry in tree.findall("m:dependencies/m:dependency", ns):
            g = entry.findtext("m:groupId", default="", namespaces=ns)
            a = entry.findtext("m:artifactId", default="", namespaces=ns)
            v = entry.findtext("m:version", default=None, namespaces=ns)
            observed[("maven", g, a)] = v
    if "npm" in targets:
        pkg = json.loads(_manifest(root, targets["npm"]["manifest"]))
        if not isinstance(pkg, dict):
            deny("T3_NPM_MANIFEST_INVALID")
        for group in ("dependencies", "devDependencies"):
            for name, version in pkg.get(group, {}).items():
                observed[("npm", name)] = version
    return observed


def requirements(atoms, package, config):
    areas = {a["area"] for a in atoms if a.get("area") in ("DATA", "BACKEND", "FRONTEND")}
    required = set()
    for area in areas:
        required.update(config["requirements_by_area"].get(area, []))
    # The only supported explicit request is typed dependency IDs from the
    # source package. Unknown IDs block; never guess a Maven/npm coordinate.
    explicit = package.get("dependency_requirements", [])
    if not isinstance(explicit, list) or any(not isinstance(x, str) for x in explicit):
        deny("DEPENDENCIA_NO_PERMITIDA")
    required.update(explicit)
    all_ids = {item["id"] for spec in config["targets"].values()
               for item in spec["dependencies"]}
    if required - all_ids:
        deny("DEPENDENCIA_NO_PERMITIDA:" + ",".join(sorted(required - all_ids)))
    return sorted(required)


def unresolved(package, atoms, root=ROOT):
    config = policy()
    ids = requirements(atoms, package, config)
    observed = installed(root, config)
    missing = []
    for target, spec in config["targets"].items():
        for item in spec["dependencies"]:
            if item["id"] not in ids:
                continue
            if target == "maven":
                key = (target, item["group_id"], item["artifact_id"])
            else:
                key = (target, item["name"])
            found = observed.get(key)
            if found is None:
                missing.append({**item, "target": target})
            elif found != item["version"]:
                deny("DEPENDENCIA_VERSION_NO_PERMITIDA:" + item["id"])
    return missing, config


def expected_config_missing(root, config):
    db = config["database"]
    props_path = Path(root) / db["config_files"][1]
    example_path = Path(root) / db["config_files"][2]
    if props_path.is_symlink() or example_path.is_symlink():
        deny("T3_CONFIG_UNSAFE")
    if not props_path.is_file() or not example_path.is_file():
        return True
    props = props_path.read_text(encoding="utf-8")
    example = example_path.read_text(encoding="utf-8")
    for key, value in db["properties"].items():
        if (key + "=" + value) not in props.splitlines():
            return True
    return any(not re.search(r"(?m)^" + re.escape(key) + r"=\s*$", example)
               for key in db["env_vars"])


def infra_atom(package, atoms, root=ROOT):
    missing, config = unresolved(package, atoms, root)
    if not missing and not (any(a.get("area") == "DATA" for a in atoms)
                            and expected_config_missing(root, config)):
        return None
    db = config["database"]
    if not any(a.get("area") == db["requires_area"] for a in atoms):
        # Generic dependency-only INFRA may modify manifest, not DB config.
        paths = sorted({
            entry for item in missing
            for entry in (
                [config["targets"][item["target"]]["manifest"]] +
                ([config["targets"]["npm"]["lockfile"]] if item["target"]=="npm" else [])
            )
        })
    else:
        paths = list(db["config_files"])
    if not paths or len(paths) > config["infra"]["max_changed_files"]:
        deny("T3_INFRA_SCOPE_INVALID")
    impacted = [a for a in atoms if a["area"] in ("DATA", "BACKEND", "FRONTEND")]
    identifiers = sorted({rid for a in impacted for rid in a.get("requirement_ids", [])})
    if not identifiers:
        deny("T3_INFRA_REQUIREMENTS_MISSING")
    signature = hashlib.sha256(("\n".join(paths) + "|" + ",".join(x["id"] for x in missing)).encode()).hexdigest()[:12]
    return {
        "atom_id": "ATOM-INFRA-" + signature,
        "scope_id": "INFRA-" + signature, "front_id": "T3-INFRA-" + signature,
        "area": "INFRA", "functional_module": "infra-" + signature,
        "requirement_ids": identifiers, "paths": paths, "depends_on": [],
        "outcome_id": "OUTCOME-INFRA-" + signature,
        "business_outcome": "Preparar únicamente dependencias permitidas y configuración de base trazada",
        "missing_dependencies": missing,
        "policy_ref": "pilot/orchestrator/dependency_allowlist_v1.json",
        "source_refs": sorted({x.get("front_id", "") for x in impacted if x.get("front_id")})
    }
