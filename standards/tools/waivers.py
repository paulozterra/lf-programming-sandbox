"""Registro de excepciones C8. JSON único, consultas deterministas, sin dependencias externas."""
import argparse
import datetime as dt
import fnmatch
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "standards/catalog.json"
REGISTRY = ROOT / "standards/waivers/waivers.json"
OUTPUT = ROOT / "standards/WAIVERS.md"
ID = re.compile(r"^WAIVER-\d{4,}$")
REF = re.compile(r"WAIVER-\d{4,}")
SUPPRESS = re.compile(r"eslint-disable(?:-next-line|-line)?|@ts-ignore|@ts-expect-error|prettier-ignore|@SuppressWarnings|#\s*noqa|NOSONAR|#\s*type:\s*ignore")
UTC = dt.timezone.utc


def load():
    return json.loads(CATALOG.read_text(encoding="utf-8")), json.loads(REGISTRY.read_text(encoding="utf-8"))


def parse_date(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("fecha ISO-8601 debe terminar en Z")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("fecha debe ser UTC")
    return parsed


def target_key(target):
    if target.get("kind") == "STD_RULE":
        return {"kind": "STD_RULE", "rule_id": target.get("rule_id"), "controls": target.get("controls", [])}
    if target.get("kind") == "LINTER_RULE":
        return {"kind": "LINTER_RULE", "tool": target.get("tool"), "rule": target.get("rule")}
    return target


def validate(catalog, registry):
    errors = []
    settings = catalog["waiver_settings"]
    rules = {r["id"]: r for r in catalog["rules"]}
    waivers = registry.get("waivers", [])
    if not isinstance(waivers, list):
        return ["waivers debe ser lista"]
    if registry.get("schema_version") != "LF_WAIVERS_V1":
        errors.append("schema_version inválido")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(registry.get("registry_version", ""))):
        errors.append("registry_version inválido")
    ids = set()
    for w in waivers:
        wid = w.get("waiver_id", "<sin id>")
        for field in ("waiver_id", "target", "catalog_version", "kind", "scope", "reason",
                      "requested_by", "approved_by", "approved_at", "expires_at", "status", "evidence"):
            if field not in w:
                errors.append(f"{wid}: falta {field}")
        if not ID.fullmatch(str(wid)):
            errors.append(f"{wid}: id inválido")
        if wid in ids:
            errors.append(f"{wid}: id duplicado")
        ids.add(wid)
        approved_version = w.get("catalog_version")
        current_version = catalog.get("catalog_version")
        version_pattern = r"\d+\.\d+\.\d+"
        if (not isinstance(approved_version, str)
                or not re.fullmatch(version_pattern, approved_version)):
            errors.append(f"{wid}: catalog_version semver inválido")
        elif (not isinstance(current_version, str)
                or not re.fullmatch(version_pattern, current_version)
                or tuple(map(int, approved_version.split("."))) > tuple(map(int, current_version.split(".")))):
            errors.append(f"{wid}: catalog_version posterior al catálogo actual")
        if w.get("kind") not in ("REAL", "TEST_FIXTURE"):
            errors.append(f"{wid}: kind inválido")
        if w.get("status") not in ("ACTIVE", "REVOKED"):
            errors.append(f"{wid}: status inválido")
        if not isinstance(w.get("reason"), str) or not w["reason"].strip():
            errors.append(f"{wid}: reason obligatorio")
        requester = w.get("requested_by")
        approver = w.get("approved_by")
        if not isinstance(requester, str) or not requester.strip():
            errors.append(f"{wid}: requested_by obligatorio")
        if approver not in settings["approvers"] or approver == requester or (isinstance(approver, str) and approver.startswith("agent:")):
            errors.append(f"{wid}: approved_by inválido")
        if not isinstance(w.get("evidence"), str) or not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/\d+", w["evidence"]):
            errors.append(f"{wid}: evidence debe ser URL real de PR")
        scope = w.get("scope", {})
        paths = scope.get("paths", []) if isinstance(scope, dict) else []
        if not isinstance(paths, list) or not paths:
            errors.append(f"{wid}: scope.paths obligatorio")
            paths = []
        for path in paths:
            if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts or path in ("*", "**", "**/*") or "\\" in path:
                errors.append(f"{wid}: scope.paths inválido")
            if w.get("kind") == "TEST_FIXTURE" and not path.startswith("standards/tests/fixtures/"):
                errors.append(f"{wid}: TEST_FIXTURE fuera de fixtures")
        target = w.get("target", {})
        max_days = settings["test_fixture_max_days"] if w.get("kind") == "TEST_FIXTURE" else None
        if not isinstance(target, dict):
            target = {}
        if target.get("kind") == "STD_RULE":
            rule_id = target.get("rule_id")
            rule = rules.get(rule_id)
            if rule_id == "STD-GEN-05" or not rule or not rule.get("waiver_policy", {}).get("allowed", False):
                errors.append(f"{wid}: RULE_NOT_WAIVABLE {rule_id}")
            controls = target.get("controls", [])
            if not isinstance(controls, list):
                errors.append(f"{wid}: controls inválido")
                controls = []
            if rule and rule.get("waiver_policy", {}).get("eligible_controls") is not None and (not controls or not set(controls) <= set(rule["waiver_policy"]["eligible_controls"])):
                errors.append(f"{wid}: control no elegible")
            if max_days is None and rule:
                max_days = settings["max_days"].get(rule["severity"])
                if max_days is None:
                    errors.append(f"{wid}: RULE_NOT_WAIVABLE por severidad")
        elif target.get("kind") == "LINTER_RULE":
            tool, lint_rule = target.get("tool"), target.get("rule")
            if not isinstance(tool, str) or not tool or not isinstance(lint_rule, str) or not lint_rule:
                errors.append(f"{wid}: objetivo linter inválido")
            if f"{tool}:{lint_rule}" in settings["linter_rule_denylist"]:
                errors.append(f"{wid}: RULE_NOT_WAIVABLE denylist")
            if max_days is None:
                max_days = settings["linter_rule_max_days"]
        else:
            errors.append(f"{wid}: target.kind inválido")
        try:
            start, end = parse_date(w.get("approved_at")), parse_date(w.get("expires_at"))
            if end <= start or (max_days is not None and end > start + dt.timedelta(days=max_days)):
                errors.append(f"{wid}: vencimiento excede plazo máximo o fechas incoherentes")
            if w.get("status") == "REVOKED":
                revoked = parse_date(w.get("revoked_at"))
                if revoked < start or not w.get("revocation_reason"):
                    errors.append(f"{wid}: REVOKED exige revoked_at y revocation_reason")
        except (TypeError, ValueError):
            errors.append(f"{wid}: fecha inválida")
        if w.get("status") == "REVOKED" and (not w.get("revoked_at") or not w.get("revocation_reason")):
            errors.append(f"{wid}: REVOKED incompleto")
    for w in waivers:
        old = w.get("supersedes")
        if old and (old not in ids or old == w.get("waiver_id")):
            errors.append(f"{w.get('waiver_id')}: supersedes inválido")
    return errors


def parse_suppression(line):
    if not SUPPRESS.search(line):
        return []
    targets = []
    m = re.search(r"eslint-disable(?:-next-line|-line)?\b([^\n]*)", line)
    if m:
        fragment = re.split(r"\s+--|\*/|\n", m.group(1))[0].strip()
        rules = [x.strip() for x in fragment.split(",") if x.strip()]
        if not rules:
            return [("MISSING_LINTER_RULE", None)]
        targets += [{"kind": "LINTER_RULE", "tool": "eslint", "rule": r} for r in rules]
    for control in ("@ts-ignore", "@ts-expect-error"):
        if control in line:
            targets.append({"kind": "STD_RULE", "rule_id": "STD-FE-03", "controls": [control]})
    if "prettier-ignore" in line:
        targets.append({"kind": "STD_RULE", "rule_id": "STD-FE-07", "controls": []})
    # Java: forma singular y array; una regla por cada literal.
    java = re.search(r"""@SuppressWarnings\s*\(\s*(\{[^}]*\}|"[^"]*"|'[^']*')\s*\)""", line)
    if java:
        values = re.findall(r"""["']([^"']+)["']""", java.group(1))
        targets.extend({"kind": "LINTER_RULE", "tool": "java", "rule": value} for value in values)
    m = re.search(r"#\s*noqa:\s*([\w, ]+)", line)
    if m:
        targets += [{"kind": "LINTER_RULE", "tool": "python", "rule": x.strip()} for x in m.group(1).split(",") if x.strip()]
    elif re.search(r"#\s*noqa\b", line):
        return [("MISSING_LINTER_RULE", None)]
    if "NOSONAR" in line:
        targets.append({"kind": "LINTER_RULE", "tool": "sonar", "rule": "NOSONAR"})
    if re.search(r"#\s*type:\s*ignore", line):
        targets.append({"kind": "LINTER_RULE", "tool": "mypy", "rule": "type-ignore"})
    return targets


def evaluate(catalog, registry, path, target, as_of):
    matches = [w for w in registry["waivers"] if target_key(w["target"]) == target_key(target)]
    if target.get("kind") == "STD_RULE":
        matching = [w for w in registry["waivers"] if w["target"].get("kind") == "STD_RULE" and w["target"].get("rule_id") == target.get("rule_id") and (not target.get("controls") or set(target["controls"]) <= set(w["target"].get("controls", [])))]
    else:
        matching = matches
    if not matching:
        rules = {r["id"]: r for r in catalog["rules"]}
        code = "RULE_NOT_WAIVABLE" if target.get("kind") == "STD_RULE" and not rules.get(target.get("rule_id"), {}).get("waiver_policy", {}).get("allowed") else "NO_WAIVER"
        return "NOT_AUTHORIZED", code, []
    reason = "OUT_OF_SCOPE"
    for w in matching:
        if not any(fnmatch.fnmatchcase(path, pat) for pat in w["scope"]["paths"]):
            continue
        if w["status"] == "REVOKED":
            reason = "REVOKED"
        elif any(x.get("supersedes") == w["waiver_id"] for x in registry["waivers"]):
            reason = "SUPERSEDED"
        elif parse_date(w["expires_at"]) <= as_of:
            reason = "EXPIRED"
        else:
            return "AUTHORIZED", None, [w["waiver_id"]]
    return "NOT_AUTHORIZED", reason, [w["waiver_id"] for w in matching]


def check_refs(catalog, registry, roots, as_of):
    errors = []
    for root in roots:
        base = ROOT / root
        paths = [base] if base.is_file() else sorted(base.rglob("*")) if base.exists() else []
        for path in paths:
            if not path.is_file() or any(p in path.parts for p in (".git", "node_modules", "target", ".next")) or path.suffix not in (".ts", ".tsx", ".js", ".jsx", ".java", ".py", ".mjs"):
                continue
            rel = path.relative_to(ROOT).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not SUPPRESS.search(line):
                    continue
                targets = parse_suppression(line)
                if not targets:
                    errors.append(f"STD-GEN-05 {rel}:{number}: UNPARSED_SUPPRESSION")
                    continue
                refs = REF.findall(line)
                if not refs:
                    errors.append(f"STD-GEN-05 {rel}:{number}: NO_WAIVER")
                    continue
                for target in targets:
                    if isinstance(target, tuple):
                        errors.append(f"STD-GEN-05 {rel}:{number}: {target[0]}")
                        continue
                    eligible = {w["waiver_id"] for w in registry["waivers"] if w["waiver_id"] in refs}
                    decision, reason, ids = evaluate(catalog, {"waivers": [w for w in registry["waivers"] if w["waiver_id"] in eligible]}, rel, target, as_of)
                    if decision != "AUTHORIZED":
                        code = "TARGET_MISMATCH" if reason == "NO_WAIVER" and eligible else (reason or "TARGET_MISMATCH")
                        errors.append(f"STD-GEN-05 {rel}:{number}: {code} {refs}")
                for ref in refs:
                    if not any(w["waiver_id"] == ref for w in registry["waivers"]):
                        errors.append(f"STD-GEN-05 {rel}:{number}: NO_WAIVER {ref}")
    return sorted(set(errors))


def render(registry):
    rows = ["# Waivers · v" + registry["registry_version"], "", "> Generado desde `standards/waivers/waivers.json`. No editar a mano.", "", "| ID | Tipo | Objetivo | Alcance | Estado | Aprobador | Vence | PR |", "|---|---|---|---|---|---|---|---|"]
    for w in registry["waivers"]:
        target = w["target"]
        obj = target.get("rule_id") or f"{target.get('tool')}:{target.get('rule')}"
        rows.append(f"| {w['waiver_id']} | {w['kind']} | {obj} | {', '.join(w['scope']['paths'])} | {w['status']} | {w['approved_by']} | {w['expires_at']} | {w['evidence']} |")
    return "\n".join(rows) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    rend = sub.add_parser("render"); rend.add_argument("--check", action="store_true")
    check = sub.add_parser("check-refs"); check.add_argument("roots", nargs="+"); check.add_argument("--as-of")
    listing = sub.add_parser("list"); listing.add_argument("--path", required=True)
    group = listing.add_mutually_exclusive_group(required=True)
    group.add_argument("--rule"); group.add_argument("--linter")
    listing.add_argument("--as-of"); listing.add_argument("--format", choices=["json"], default="json")
    audit = sub.add_parser("audit"); audit.add_argument("--as-of")
    args = p.parse_args(argv)
    catalog, registry = load()
    if args.cmd == "validate":
        errors = validate(catalog, registry)
        for e in errors: print("ERROR", e)
        if not errors: print("OK waivers")
        return int(bool(errors))
    if args.cmd == "render":
        content = render(registry)
        if args.check:
            ok = OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == content
            print("OK WAIVERS.md al día" if ok else "ERROR WAIVERS.md desactualizado")
            return int(not ok)
        OUTPUT.write_text(content, encoding="utf-8")
        return 0
    day = parse_date(args.as_of) if getattr(args, "as_of", None) else dt.datetime.now(UTC)
    if args.cmd == "check-refs":
        errors = check_refs(catalog, registry, args.roots, day)
        for e in errors: print(e)
        if not errors: print("OK citas de waivers")
        return int(bool(errors))
    if args.cmd == "list":
        if args.rule:
            target = {"kind": "STD_RULE", "rule_id": args.rule, "controls": []}
        else:
            tool, name = args.linter.split(":", 1)
            target = {"kind": "LINTER_RULE", "tool": tool, "rule": name}
        decision, reason, matches = evaluate(catalog, registry, args.path, target, day)
        print(json.dumps({"catalog_version": catalog["catalog_version"], "registry_version": registry["registry_version"], "as_of": day.isoformat().replace("+00:00", "Z"), "path": args.path, "target": target, "decision": decision, "reason_code": reason, "matches": matches}))
        return 0
    if args.cmd == "audit":
        used = set()
        for directory in ("backend/src", "frontend/src", "standards/tests/fixtures"):
            root = ROOT / directory
            if root.exists():
                for path in root.rglob("*"):
                    if path.is_file() and path.suffix in (".ts", ".tsx", ".js", ".jsx", ".java", ".py", ".mjs"):
                        used.update(REF.findall(path.read_text(encoding="utf-8", errors="replace")))
        for w in registry["waivers"]:
            flags = []
            if w["status"] == "REVOKED": flags.append("REVOKED")
            remaining = parse_date(w["expires_at"]) - day
            if remaining <= dt.timedelta(0): flags.append("EXPIRED")
            elif remaining <= dt.timedelta(days=7): flags.append("EXPIRING_SOON")
            if w["waiver_id"] not in used: flags.append("UNUSED")
            print(json.dumps({"waiver_id": w["waiver_id"], "flags": flags}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
