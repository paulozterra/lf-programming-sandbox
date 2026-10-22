"""Genera la versión para el agente (LLM) del catálogo: standards/CATALOGO.md.

La única fuente es standards/catalog.json; este archivo nunca se edita a mano.
Uso: python3 standards/tools/render_llm.py [--check]
Con --check sale con 1 si CATALOGO.md no coincide con lo que se generaría.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"
OUTPUT = ROOT / "CATALOGO.md"

STATE_LABEL = {
    "active": "exigido en CI",
    "shadow": "CI en modo sombra",
    "review": "revisor PG-11",
    "planned": "control pendiente",
}


def render(catalog: dict) -> str:
    lines = [
        f"# Catálogo de estándares LF · v{catalog['catalog_version']}",
        "",
        "> Archivo generado desde `standards/catalog.json` con `standards/tools/render_llm.py`. No editar a mano.",
        "",
        f"Estado: `{catalog['status']}`.",
        "",
        "## Precedencia",
        "",
    ]
    lines += [f"{i}. {item}" for i, item in enumerate(catalog["precedence"], 1)]
    lines += ["", f"**Legado:** {catalog['legacy_policy']}", "", "## Decisiones", ""]
    lines += [f"- **{d['id']}** ({d['adr']}) · {d['topic']}: {d['decision']}" for d in catalog["decisions"]]
    by_domain: dict[str, list[dict]] = {}
    for rule in catalog["rules"]:
        by_domain.setdefault(rule["domain"], []).append(rule)
    for domain in catalog["domains"]:
        rules = by_domain.get(domain["id"], [])
        status = f" · {domain['status']}" if domain.get("status") else ""
        lines += ["", f"## {domain['id']} · {domain['title']} ({domain['level']}){status}", ""]
        for rule in rules:
            severity = rule["severity"]
            if rule.get("severity_condition"):
                severity += f" ({rule['severity_condition']})"
            state = STATE_LABEL[rule["enforcement"]["state"]]
            lines.append(f"### {rule['id']} · {severity} · {state}")
            lines.append("")
            lines.append(rule["rule"])
            policy = rule.get("waiver_policy", {})
            if policy.get("allowed"):
                control = ", ".join(policy.get("eligible_controls", []))
                lines.append(f"Waiver: permitido" + (f" solo para {control}" if control else ""))
            else:
                lines.append("Waiver: prohibido" + (f" — {policy['reason']}" if policy.get("reason") else " (por defecto)"))
            if rule.get("lf_rule_refs"):
                lines.append("")
                lines.append("Reglas LF de origen: " + ", ".join(f"`{ref}`" for ref in rule["lf_rule_refs"]))
            if rule.get("examples"):
                lines.append("")
                lines += [f"- ✅ `{example}`" for example in rule["examples"]["good"]]
                lines += [f"- ❌ `{example}`" for example in rule["examples"]["bad"]]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    content = render(json.loads(CATALOG.read_text(encoding="utf-8")))
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print("ERROR CATALOGO.md desactualizado: ejecutar python3 standards/tools/render_llm.py")
            return 1
        print("OK CATALOGO.md al día")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Generado {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
