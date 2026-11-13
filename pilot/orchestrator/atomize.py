#!/usr/bin/env python3
"""T1 A9→area-sourced, deterministically bounded atoms. Offline; no model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RULES = HERE / "atomize_rules_v1.json"
REPO = "paulozterra/lf-programming-sandbox"
SAFE = re.compile(r"[a-z][a-z0-9-]{0,45}\Z")
MODULE_SAFE = re.compile(r"[a-z0-9][a-z0-9-]{0,45}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class AtomBlocked(ValueError):
    pass


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def _slug(source, rules):
    """Resolve functional module from area-free scope, with versioned prefixes."""
    if not isinstance(source, str) or not source:
        raise AtomBlocked("ATOM_IDENTITY_INVALID")
    base = source.lower()
    for area in rules["order"]:
        suffix = "-" + area.lower()
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    result = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not result:
        raise AtomBlocked("ATOM_IDENTITY_INVALID")
    for prefix in sorted(rules["scope_module_prefixes"], key=len, reverse=True):
        if result.startswith(prefix):
            result = result[len(prefix):]
            break
    if not MODULE_SAFE.fullmatch(result):
        raise AtomBlocked("ATOM_IDENTITY_INVALID")
    return result


JAVA_PACKAGE = re.compile(r"[a-z][a-z0-9]*\Z")
JAVA_CLASS = re.compile(r"[A-Z][A-Za-z0-9]*\Z")
JAVA_RESERVED = frozenset({
    "abstract", "assert", "boolean", "break", "byte", "case", "catch",
    "char", "class", "const", "continue", "default", "do", "double",
    "else", "enum", "extends", "final", "finally", "float", "for",
    "goto", "if", "implements", "import", "instanceof", "int",
    "interface", "long", "native", "new", "package", "private",
    "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "true", "false",
    "null", "record", "sealed", "permits", "var", "yield",
})


def _java_module(module):
    token = module.replace("-", "")
    if token and token[0].isdigit():
        token = "m" + token
    if not JAVA_PACKAGE.fullmatch(token) or token in JAVA_RESERVED:
        raise AtomBlocked("ATOM_JAVA_PACKAGE_INVALID:" + str(module))
    return token


def _rules():
    data = json.loads(RULES.read_text(encoding="utf-8"))
    if (data.get("schema_version") != "T1_ATOMIZE_RULES_V1"
            or not isinstance(data.get("scope_module_prefixes"), list)
            or not all(isinstance(p, str) and p.endswith("-")
                       and re.fullmatch(r"[a-z][a-z0-9-]*-", p)
                       for p in data["scope_module_prefixes"])
            or len(set(data["scope_module_prefixes"])) != len(data["scope_module_prefixes"])):
        raise AtomBlocked("ATOM_RULES_INVALID")
    return data


def _next_version(root):
    # The staging root often contains only request artifacts. Include the
    # checked-out repository migrations so the next version is not reset to V1.
    numbers = []
    for base in (HERE.parents[1], Path(root)):
        for file in (base / "apps/time-service/src/main/resources/db/migration").glob("V*__*.sql"):
            match = re.fullmatch(r"V([0-9]+)__[a-z0-9_]+\.sql", file.name)
            if match:
                numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _class(module, suffix):
    name = "".join(part.capitalize() for part in module.split("-")) + suffix
    if name and name[0].isdigit():
        name = "M" + name
    if not JAVA_CLASS.fullmatch(name):
        raise AtomBlocked("ATOM_JAVA_CLASS_INVALID:" + str(module))
    return name


def _route(area, module, rules, root, *, data_ordinal=0):
    service = rules["service"]
    if area == "DATA":
        return [rules["routes"]["DATA"].format(
            service=service, next=_next_version(root)+data_ordinal, module=module.replace("-", "_"))]
    if area == "BACKEND":
        return [rules["routes"]["BACKEND"].format(
            service=service, service_java=service.split("-")[0],
            module_java=_java_module(module), **{"class": _class(module, suffix)})
            for suffix in rules["backend_classes"]]
    if area == "FRONTEND":
        return [p.format(module=module) for p in rules["routes"]["FRONTEND"]]
    raise AtomBlocked("ATOM_AREA_UNRESOLVED")


def _area(front, requirements, business_rules, rules):
    direct = front.get("execution_area")
    source = front.get("source_ref")
    if direct is not None or source is not None:
        if direct in rules["order"] and isinstance(source, str) and source:
            return direct, {"method": "A7_EXPLICIT", "source_ref": source}
        raise AtomBlocked("ATOM_AREA_UNRESOLVED:" + str(front.get("front_id")))
    front_kind = front.get("front_kind")
    categories = {r.get("categoria") for r in business_rules
                  if r.get("front_id") == front.get("front_id")}
    signals = " ".join(str(v) for r in requirements for v in
                       r.get("acceptance_checks", [r.get("acceptance_signal", "")]))
    # When a front has no typed category/kind, only a uniquely scoped
    # requirement (one front, one requirement) may supply its acceptance text.
    candidates = []
    for area in rules["order"]:
        policy = rules["patterns"][area]
        if front_kind in policy["front_kinds"]:
            candidates.append((area, "front_kind:" + front_kind))
        if categories.intersection(policy["categories"]):
            candidates.append((area, "categoria:" + sorted(categories.intersection(policy["categories"]))[0]))
        if signals and re.search(policy["acceptance_regex"], signals):
            candidates.append((area, "acceptance_checks"))
    areas = {x[0] for x in candidates}
    if len(areas) != 1:
        return None, {"method": "UNRESOLVED", "front_id": front.get("front_id"),
                      "candidate_areas": sorted(areas)}
    return next(iter(areas)), {"method": "T1_RULES_V1", "rule": sorted(
        reason for area, reason in candidates if area in areas)[0],
        "rules_ref": "pilot/orchestrator/atomize_rules_v1.json"}


def atomize(package, root, base_head_sha, *, run, reuse_assessment=None):
    rules = _rules()
    if (not isinstance(package, dict) or package.get("schema_version") !=
            "ANALYSIS_IMPLEMENTATION_PACKAGE_V1" or
            not isinstance(run, str) or not SAFE.fullmatch(run) or
            not isinstance(base_head_sha, str) or not SHA40.fullmatch(base_head_sha)):
        raise AtomBlocked("ATOM_INPUT_INVALID")
    # T7 accepts only an already verified deterministic obligation ledger.
    # No report means the historical T1/T2/T3 flow is bit-for-bit unchanged.
    reuse = {}
    if reuse_assessment is not None:
        if (reuse_assessment.get("schema_version") != "T7_REUSE_ASSESSMENT_V1"
                or not isinstance(reuse_assessment.get("obligations"), list)):
            raise AtomBlocked("REUTILIZACION_INDETERMINADA")
        reuse = {row["requirement_id"]: row for row in reuse_assessment["obligations"]}
        if len(reuse) != len(reuse_assessment["obligations"]):
            raise AtomBlocked("REUTILIZACION_INDETERMINADA")
        if set(reuse) != {r["requirement_id"] for r in package["requirements"]}:
            raise AtomBlocked("REUTILIZACION_INDETERMINADA")
    scopes = {s["scope_id"]: s for s in package["scope_proposals"]}
    req_by_scope = {}
    for item in package["requirements"]:
        req_by_scope.setdefault(item["scope_id"], []).append(item)
    fronts = package["material_fronts"]
    business_rules = package.get("applicable_rules", [])
    rows, provenance, unresolved = [], {}, []
    data_ordinal = 0
    # One front per semantic atom. A9 fronts are individually accounted for.
    for scope_id in sorted(scopes):
        scope = scopes[scope_id]
        refs = sorted(scope.get("material_front_refs", []))
        selected = [f for f in fronts if f["front_id"] in refs and scope_id in f["scope_ids"]]
        if len(selected) != len(refs):
            raise AtomBlocked("ATOM_FRONT_COVERAGE_INVALID:" + scope_id)
        original_reqs = req_by_scope.get(scope_id, [])
        reqs = [r for r in original_reqs
                if not reuse or reuse[r["requirement_id"]]["decision"] != "REUSE_AS_IS"]
        if not original_reqs:
            raise AtomBlocked("ATOM_REQUIREMENT_MISSING:" + scope_id)
        if not reqs:
            continue
        for front in sorted(selected, key=lambda f: f["front_id"]):
            if reuse:
                all_bindings = [r for r in business_rules
                                if r.get("front_id") == front["front_id"]]
                if all_bindings and not any(
                        r.get("requirement_id") in {item["requirement_id"] for item in reqs}
                        for r in all_bindings):
                    continue
            related = [r for r in reqs if any(rule.get("requirement_id") == r["requirement_id"]
                       and rule.get("front_id") == front["front_id"] for rule in business_rules)]
            # Old synthetic A9 samples have one front/requirement in each scope.
            if not related and len(refs) == 1 and len(reqs) == 1:
                related = reqs
            if not related and not (front.get("execution_area") in rules["order"]
                                    and isinstance(front.get("source_ref"), str)
                                    and front["source_ref"]):
                unresolved.append({"scope_id": scope_id, "front_id": front["front_id"],
                                   "why": {"method": "NO_RULE_OR_REQUIREMENT"}})
                continue
            area, area_source = _area(front, related, business_rules, rules)
            if area is None:
                unresolved.append({"scope_id": scope_id, "front_id": front["front_id"],
                                   "why": area_source})
                continue
            module = _slug(scope_id, rules)
            atom_id = "ATOM-" + hashlib.sha256((scope_id + "|" + front["front_id"]).encode()).hexdigest()[:12]
            paths = _route(area, module, rules, root, data_ordinal=data_ordinal)
            if reuse:
                chosen = [reuse[r["requirement_id"]] for r in related]
                extends = [row for row in chosen if row["decision"] == "EXTEND"]
                builds = [row for row in chosen if row["decision"] == "BUILD_NEW"]
                # A screen may add a new rule to one existing endpoint while
                # introducing separate requirements in the same material front.
                # Preserve both sourced existing paths and policy-derived new paths.
                if extends:
                    existing = sorted({p for row in extends
                                       for p in row.get("write_paths", [])})
                    if not existing or any(
                            not isinstance(p, str) or not (root / p).is_file()
                            for p in existing):
                        raise AtomBlocked("REUTILIZACION_INDETERMINADA")
                    paths = sorted(set(existing + (paths if builds else [])))
            if area == "DATA":
                data_ordinal += 1
            groups = [paths[i:i + rules["max_paths"]] for i in range(0, len(paths), rules["max_paths"])]
            for i, group in enumerate(groups):
                suffix = ("-" + str(i + 1)) if len(groups) > 1 else ""
                identifier = atom_id + suffix
                row = {"atom_id": identifier, "scope_id": scope_id,
                       "front_id": front["front_id"], "area": area,
                       "functional_module": module,
                       "requirement_ids": sorted(r["requirement_id"] for r in reqs),
                       "paths": group, "depends_on": [],
                       "outcome_id": "OUTCOME-" + identifier,
                       "business_outcome": " | ".join(r["outcome"] for r in sorted(
                           related, key=lambda x: x["requirement_id"]))}
                rows.append(row)
                provenance[identifier] = {
                    "scope_id": {"source": "A9.scope_proposals", "value": scope_id},
                    "front_id": {"source": "A9.material_fronts", "value": front["front_id"]},
                    "area": area_source,
                    "paths": {"source": "pilot/orchestrator/atomize_rules_v1.json",
                              "route": area, "functional_module": module,
                              "java_package_token": _java_module(module) if area == "BACKEND" else None},
                    "business_outcome": {"source": "A9.requirements",
                                         "requirement_ids": [r["requirement_id"] for r in related]},
                    "atom_id": {"source": "SHA256(scope_id|front_id)"},
                    "outcome_id": {"source": "atom_id"},
                }
    # Virtual contract boundary, owned by T2 orchestrator rather than PG04/05.
    # Pair only BE/FE atoms having the exact same derived functional module.
    by_module = {}
    for row in rows:
        by_module.setdefault(row["functional_module"], {}).setdefault(row["area"], []).append(row)
    for module, areas in sorted(by_module.items()):
        if not {"BACKEND", "FRONTEND"}.issubset(areas):
            continue
        # A9 retains sourced screen fields/errors in the material ledger.
        # API operation paths do not exist here: the constructor supplies them.
        # Old pre-A9 synthetic T1 fixtures retain their legacy execution path.
        if "programming_context_snapshot" not in package:
            continue
        import contract_generate
        try:
            contract_generate._contract_sections(package)
        except contract_generate.ContractBlocked as exc:
            raise AtomBlocked(str(exc)) from exc
        policy = rules["contract_lot"]
        if (policy.get("schema_version") != "T2_CONTRACT_LOT_POLICY_V1"
                or policy.get("profile_area") != "BACKEND"
                or policy.get("area") != "CONTRATO"):
            raise AtomBlocked("T2_CONTRACT_POLICY_INVALID")
        members = areas["BACKEND"] + areas["FRONTEND"]
        contract_id = "ATOM-" + hashlib.sha256(("CONTRATO|" + module).encode()).hexdigest()[:12]
        if contract_id in {a["atom_id"] for a in rows}:
            raise AtomBlocked("T2_CONTRACT_ID_COLLISION")
        path = policy["write_path"].format(module=module)
        contract = {
            "atom_id": contract_id, "scope_id": module,
            "front_id": "T2-CONTRACT-" + hashlib.sha256(module.encode()).hexdigest()[:12],
            "area": "CONTRATO", "functional_module": module,
            "requirement_ids": sorted(set(r for member in members
                                           for r in member["requirement_ids"])),
            "paths": [path], "depends_on": [],
            "outcome_id": "OUTCOME-" + contract_id,
            "business_outcome": "Formalizar el contrato de API compartido de los requisitos de origen",
            "source_refs": sorted({
                provenance[m["atom_id"]]["area"].get("source_ref", "")
                for m in members
            } - {""}),
        }
        if not contract["source_refs"]:
            raise AtomBlocked("T2_CONTRACT_SOURCE_REFS_MISSING")
        # Materialize an evidence-only skeleton in the next deterministic
        # planning stage; preflight here ensures no partial contract lot.
        try:
            contract_generate.generate(module, package, rows)
        except contract_generate.ContractBlocked as exc:
            raise AtomBlocked(str(exc)) from exc
        rows.append(contract)
        provenance[contract_id] = {
            "area": {"method": "T2_CONTRACT_POLICY_V1",
                     "rules_ref": "pilot/orchestrator/atomize_rules_v1.json"},
            "paths": {"source": "pilot/orchestrator/atomize_rules_v1.json",
                      "route": "CONTRATO", "functional_module": module},
            "business_outcome": {"source": "A9.requirements",
                                 "requirement_ids": contract["requirement_ids"]},
            "scope_id": {"source": "BE_FE_SHARED_MODULE", "value": module},
            "front_id": {"source": "T2_CONTRACT_DERIVED", "value": contract["front_id"]},
            "depends_on": {"source": "T2_CONTRACT_PRECEDENCE"},
        }
        for member in members:
            member["depends_on"].append(contract_id)
    # T3: one shared infrastructure atom from a versioned allowlist, created
    # only if checked-out manifests/configuration lack a required dependency.
    from pilot.orchestrator import infra_lot
    try:
        infra = infra_lot.infra_atom(package, rows)
    except infra_lot.DependencyBlocked as exc:
        raise AtomBlocked(str(exc)) from exc
    if infra is not None:
        rows.append(infra)
        provenance[infra["atom_id"]] = {
            "area": {"method": "T3_ALLOWLIST_V1",
                     "rules_ref": infra["policy_ref"]},
            "paths": {"source": infra["policy_ref"], "route": "INFRA"},
            "depends_on": {"source": "T3_MISSING_DEPENDENCY_GUARD"},
            "business_outcome": {"source": "A9.area_and_allowlist",
                                 "requirement_ids": infra["requirement_ids"]},
        }
        consuming = {"DATA"} if any(a["area"]=="DATA" for a in rows) else {
            a["area"] for a in rows if a["area"] in ("BACKEND", "FRONTEND")}
        for member in rows:
            if member["area"] in consuming and member["atom_id"] != infra["atom_id"]:
                member["depends_on"] = sorted(set(member["depends_on"] + [infra["atom_id"]]))
    if unresolved:
        raise AtomBlocked("ATOM_AREA_UNRESOLVED:" + json.dumps(
            unresolved, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    order = {"INFRA": -2, "CONTRATO": -1, **{a: i for i, a in enumerate(rules["order"])}}
    # Across scopes chain all areas in stable order; no imaginary dependencies.
    rows.sort(key=lambda r: (order[r["area"]], r["scope_id"], r["atom_id"]))
    last = None
    for row in rows:
        if last is not None and row["area"] not in ("INFRA","CONTRATO") and order[last["area"]] < order[row["area"]]:
            row["depends_on"] = sorted(set(row["depends_on"] + [last["atom_id"]]))
        last = row
        provenance[row["atom_id"]]["depends_on"] = {
            "source": "T1_AREA_ORDER_T2_CONTRACT_T3_INFRA", "order": ["INFRA","CONTRATO"] + rules["order"]}
    # A fully reused A9 scope deliberately has no write atom. Record the
    # exact coverage and the reuse receipt hash for PG02-PG05 validation.
    reused_scopes = []
    if reuse:
        for sid, items in sorted(req_by_scope.items()):
            if all(reuse[item["requirement_id"]]["decision"] == "REUSE_AS_IS"
                   for item in items):
                reused_scopes.append({"scope_id": sid,
                                      "requirement_ids": sorted(
                                          item["requirement_id"] for item in items)})
    reuse_digest = (hashlib.sha256(canonical(reuse_assessment)).hexdigest()
                    if reuse_assessment is not None else None)
    return {
        **({"reused_scopes": reused_scopes,
            "reuse_assessment_sha256": reuse_digest}
           if reuse_assessment is not None else {}),
        "schema_version": "T1_ATOMIZED_INPUTS_V1",
        "simulation_only": True,
        "project_ref": "lf_java",
        "target_binding": {
            "repo_full_name": REPO,
            "base_head_sha": base_head_sha,
            "target_binding_ref": "atomize://t1/" + run,
        },
        "atoms": rows,
        "provenance": provenance,
        "rules_sha256": hashlib.sha256(RULES.read_bytes()).hexdigest(),
    }
