"""Valida la estructura del catálogo de estándares (standards/catalog.json).

Uso: python3 standards/tools/validate_catalog.py [ruta]
Sale con 1 si hay errores. Solo usa la librería estándar.
"""

import json
import re
import sys
from pathlib import Path

RULE_ID = re.compile(r"^STD-[A-Z]+-\d{2}$")
REQUIRED_RULE_FIELDS = {"id", "domain", "rule", "severity", "status", "enforcement"}
ENFORCEMENT_WITH_COMMAND = {"active", "shadow"}


def validate(catalog: dict) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != "LF_STANDARDS_CATALOG_V1":
        errors.append("schema_version debe ser LF_STANDARDS_CATALOG_V1")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(catalog.get("catalog_version", ""))):
        errors.append("catalog_version debe ser semver (x.y.z)")
    severities = set(catalog.get("severity_values", []))
    states = set(catalog.get("enforcement_states", {}))
    domains = {d["id"] for d in catalog.get("domains", [])}
# Proteccion deliberada C8: cualquier cambio de política exige diff de código revisable en C9.
    settings = catalog.get("waiver_settings")
    if not isinstance(settings, dict):
        errors.append("waiver_settings obligatorio")
    else:
        if not isinstance(settings.get("approvers"), list) or not settings["approvers"] or any(
            not isinstance(a, str) or not a.strip() or a.startswith("agent:") for a in settings["approvers"]
        ):
            errors.append("waiver_settings.approvers inválido")
        if not isinstance(settings.get("max_days"), dict) or any(
            type(n) is not int or n < 1 for n in settings["max_days"].values()
        ) or not settings["max_days"]:
            errors.append("waiver_settings.max_days inválido")
        if any(type(settings.get(key)) is not int or settings[key] < 1
               for key in ("linter_rule_max_days", "test_fixture_max_days")):
            errors.append("waiver_settings plazos inválidos")
        deny = settings.get("linter_rule_denylist")
        if not isinstance(deny, list) or len(deny) != len(set(deny)) or not all(isinstance(x, str) and ":" in x for x in deny):
            errors.append("waiver_settings.linter_rule_denylist inválida")
    seen: set[str] = set()
    for rule in catalog.get("rules", []):
        rid = rule.get("id", "<sin id>")
        missing = REQUIRED_RULE_FIELDS - rule.keys()
        if missing:
            errors.append(f"{rid}: faltan campos {sorted(missing)}")
            continue
        if not RULE_ID.match(rid):
            errors.append(f"{rid}: id con formato inválido")
        if rid in seen:
            errors.append(f"{rid}: id duplicado")
        seen.add(rid)
        if not rid.startswith(rule["domain"] + "-"):
            errors.append(f"{rid}: no coincide con su dominio {rule['domain']}")
        if rule["domain"] not in domains:
            errors.append(f"{rid}: dominio desconocido {rule['domain']}")
        if rule["severity"] not in severities:
            errors.append(f"{rid}: severidad desconocida {rule['severity']}")
        state = rule["enforcement"].get("state")
        if state not in states:
            errors.append(f"{rid}: estado de control desconocido {state}")
        if state in ENFORCEMENT_WITH_COMMAND and not rule["enforcement"].get("command"):
            errors.append(f"{rid}: un control '{state}' necesita 'command'")
        policy = rule.get("waiver_policy")
        if policy is not None:
            if not isinstance(policy, dict) or type(policy.get("allowed")) is not bool:
                errors.append(f"{rid}: waiver_policy.allowed inválido")
            elif policy["allowed"]:
                # Invariantes C8: L1 de seguridad nunca se vuelve dispensable por un CHG.
                non_waivable = {
                    "STD-GEN-03", "STD-GEN-04", "STD-GEN-05", "STD-GEN-06", "STD-GEN-07",
                    "STD-DB-06", "STD-DB-08", "STD-API-04", "STD-GIT-03", "STD-SB-02",
                    "STD-SEC-01", "STD-SEC-02", "STD-SEC-04", "STD-AUD-01", "STD-AUD-03",
                    "STD-CONS-01", "STD-CONS-02", "STD-CONS-03", "STD-CONS-04", "STD-MSG-02"
                }
                if rid in non_waivable:
                    errors.append(f"{rid}: L1/security no admite waiver")
                if rid == "STD-FE-03" and policy.get("eligible_controls") != ["@ts-ignore", "@ts-expect-error"]:
                    errors.append(f"{rid}: eligible_controls inválidos")
            elif not isinstance(policy.get("reason"), str) or not policy["reason"].strip():
                errors.append(f"{rid}: waiver_policy.reason obligatorio")
        examples = rule.get("examples")
        if examples is not None and not (examples.get("good") and examples.get("bad")):
            errors.append(f"{rid}: 'examples' necesita 'good' y 'bad'")
    decisions = [d.get("id") for d in catalog.get("decisions", [])]
    expected = [f"D{i}" for i in range(1, len(decisions) + 1)]
    if decisions != expected:
        errors.append(f"decisiones fuera de secuencia: {decisions}")
    return errors


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "standards/catalog.json")
    errors = validate(json.loads(path.read_text(encoding="utf-8")))
    for error in errors:
        print(f"ERROR {error}")
    if not errors:
        print(f"OK {path}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
