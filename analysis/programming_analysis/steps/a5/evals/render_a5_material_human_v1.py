"""Readable full source-only A5 result for the synthetic Login B2B fixture.

Lists EVERY decision item and each original source key/value. Not a real LF
operational readback or independent semantic verdict.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def pretty(value):
    if value is None: return "sin dato (null)"
    if value is True: return "verdadero"
    if value is False: return "falso"
    if isinstance(value,(dict,list)):
        return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)
    return str(value)

def render(out):
    lines=[
        "# A5 — Inicio de sesión B2B — lectura íntegra en humano",
        "",
        "**Datos SINTÉTICOS de evaluación. NO contiene lectura real LF.**",
        "**Juez semántico independiente: NO EJECUTADO.**",
        "",
        "## Resultado y límite operativo",
        "",
    ]
    for key in ("schema_version","status","target_ref","business","scope_disposition",
                "candidate_independent_scope_available","source_attested",
                "independent_judge_verified","a6_allowed","no_write_performed"):
        lines.append("- "+key+": "+pretty(out.get(key)))
    profiles=out.get("rule_profiles",{})
    cards=profiles.get("rules",[]) if isinstance(profiles,dict) else []
    lines.extend(["","## Ficha completa por regla única y capa",""])
    for i,rule in enumerate(cards,1):
        lines.append("### Regla "+str(i)+" de "+str(len(cards))+": "+str(rule.get("rule_code")))
        for key in ("rule_source_ref","title","description","rule_status","pending_decision",
                    "implementation_scope","scope_approved_source_candidate",
                    "inheritance","policy_dependencies","policy_objects","material_item_ids",
                    "implementation_impacts","layer_classification","layer_verification_state",
                    "unresolved_layer_evidence","rule_source_row","rule_fingerprint_sha256"):
            lines.append("- "+key+": "+pretty(rule.get(key)))
        for layer in ("FRONTEND","BACKEND"):
            lines.append("- **"+layer+"**:")
            for key,value in rule["layers"][layer].items():
                lines.append("  - "+key+": "+pretty(value))
        lines.append("")
    lines.append("### Reglas excluidas con identidad incompleta")
    for item in profiles.get("unresolved_rule_identities",[]) if isinstance(profiles,dict) else []:
        lines.append("- "+pretty(item))
    lines.append("")
    lines.extend(["## Detalle íntegro de cada elemento material",""])
    for idx,item in enumerate(out.get("decision_items",[]),1):
        lines.append("### Elemento "+str(idx)+" de "+str(len(out["decision_items"])))
        for key in ("decision_item_id","kind","source_stage","source_path","subject_ref",
                    "subject_code","title","description","requested_action","definition_action",
                    "decision_classification","owner_decision_required","material_question",
                    "owner_role","next_action","source_payload_sha256"):
            lines.append("- "+key+": "+pretty(item.get(key)))
        lines.append("- **Todos los datos originales recibidos:**")
        for key,value in item["source_payload"].items():
            lines.append("  - "+key+": "+pretty(value))
        lines.append("")
    lines.extend(["## Decisiones y controles globales",""])
    for key in ("decision_context","architecture_decision_items","pending_owner_decisions","pending_evidence_items",
                "unresolved_material_questions","material_coverage",
                "material_adr_triggers_true","material_adr_triggers_unknown"):
        lines.append("### "+key)
        lines.append("")
        lines.append("~~~json")
        lines.append(json.dumps(out.get(key),ensure_ascii=False,sort_keys=True,indent=2))
        lines.append("~~~")
        lines.append("")
    lines.extend(["## Contratos de origen íntegros (sin pérdida)",""])
    snap=out.get("material_ledger",{}).get("upstream_contract_snapshot",{})
    for stage in ("A3","A4"):
        lines.append("### "+stage)
        lines.append("")
        lines.append("~~~json")
        lines.append(json.dumps(snap.get(stage),ensure_ascii=False,sort_keys=True,indent=2))
        lines.append("~~~")
        lines.append("")
    return "\n".join(lines)+"\n"

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: render_a5_material_human_v1.py OUTPUT_DIRECTORY")
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    a5=load("a5_human_renderer_consumer",ROOT/"validators/run.py")
    example=load("a5_human_renderer_fixture",ROOT/"evals/test_a5_material_decisions_v1.py")
    data=example.full_input();readback=example.sidecar()
    result=a5.run(data,readback)
    if result.get("status")=="BLOCKED":
        raise SystemExit("A5_SYNTHETIC_FIXTURE_BLOCKED:"+str(result.get("blocking_codes")))
    (output/"a5_login_b2b_material_completo_ejemplo.md").write_text(
        render(result),encoding="utf-8")
    (output/"a5_login_b2b_material_completo_ejemplo.json").write_text(
        json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print("A5_HUMAN_FIXTURE_GENERATED: items="+str(len(result["decision_items"])))

if __name__=="__main__":
    main()
