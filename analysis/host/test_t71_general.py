"""T7.1: offline multi-screen catalogue, real requests, conservative traceability."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from analysis.host.request_catalog import resolve, CatalogueBlocked
from analysis.host.fixture_readback_host import FixtureHost
from analysis.host.run_a1_a9_fixture import run_f4
from analysis.host.run_a1_a5_fixture import LEGACY_FIXTURES

ROOT=Path(__file__).resolve().parents[2]


def prepare(tmp_path):
    catalogue=tmp_path/"analysis/fixtures"
    shutil.copytree(ROOT/"analysis/fixtures",catalogue)
    legacy=catalogue/LEGACY_FIXTURES.name
    pin=json.loads((legacy/"SOURCE_PIN.json").read_text("utf-8"))
    original=pin["fixture_id"]
    third=catalogue/"other_pinned_screen"
    shutil.copytree(legacy,third)
    alternate=original+"-COPY"
    pin["fixture_id"]=alternate
    for name in ("screen_contract.json","inventory.json","decision_asof.json"):
        file=third/name
        obj=json.loads(file.read_text("utf-8"))
        if "target_ref" in obj:
            obj["target_ref"]=alternate
        if "subject_ref" in obj:
            obj["subject_ref"]=alternate
        if name=="screen_contract.json":
            obj["contract"]["metadata"]["screen_code"]=alternate
        file.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
        next(x for x in pin["files"] if x["file"]==name)["sha256"]=hashlib.sha256(
            file.read_bytes()).hexdigest()
    # The new 13-file fixture carries actual LF rule descriptions in direct
    # readback rather than relying on Login's hardcoded A6 corpus. An inherited
    # transversal rule receives its own description in the effective readback.
    direct_file=third/"direct_rules.json"
    direct=json.loads(direct_file.read_text("utf-8"))
    for row in direct["linked_rules"]:
        row["descripcion"]=str(row["title"])+" comprobada"
    direct_file.write_text(json.dumps(direct,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    next(x for x in pin["files"] if x["file"]=="direct_rules.json")["sha256"]=hashlib.sha256(
        direct_file.read_bytes()).hexdigest()
    eff_file=third/"effective_rules.json"
    eff=json.loads(eff_file.read_text("utf-8"))
    for row in eff["rules"]:
        if not any(x["code"]==row["code"] for x in direct["linked_rules"]):
            row["descripcion"]=str(row["title"])+" comprobada"
    eff_file.write_text(json.dumps(eff,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    next(x for x in pin["files"] if x["file"]=="effective_rules.json")["sha256"]=hashlib.sha256(
        eff_file.read_bytes()).hexdigest()
    # Pin a new 12-source fiche: semantic_signals is OPTIONAL, not canonical.
    pin["files"]=[x for x in pin["files"] if x["file"]!="semantic_signals.json"]
    (third/"semantic_signals.json").unlink()
    (third/"SOURCE_PIN.json").write_text(json.dumps(pin,sort_keys=True,indent=2)+"\n")
    note=[p for p in catalogue.glob("*/SOURCE_PIN.json")
          if json.loads(p.read_text())["schema_version"]=="SOURCE_SCREEN_PIN_V1"]
    assert len(note)>=1
    note_code=json.loads(note[0].read_text())["fixture_id"]
    return original,alternate,note_code


def launch(root,run,phrase):
    path=root/"pilot/runs"/run
    path.mkdir(parents=True)
    (path/"request.md").write_text(phrase+"\n",encoding="utf-8")
    return run_f4(root,slug=run)


def test_three_screen_catalogue_including_two_13_source_fiches(tmp_path):
    original,alternate,note=prepare(tmp_path)
    for index,code in enumerate((original,alternate,note)):
        outcome=launch(tmp_path,"t71-"+str(index),
                       "Implementa "+code)
        assert outcome["state"]["stage"]=="INTAKE_ACCEPTED"
        assert set(outcome["source"]["stages"])=={"A1","A2","A3","A4","A5"}
        assert all(outcome["source"][stage] for stage in ("a6","a7","a8"))
        assert outcome["package"]["requirements"]
        assert outcome["package"]["simulation_mode"]=="SIMULATED_SANDBOX_ONLY"


def test_same_covered_requirement_set_for_three_wordings(tmp_path):
    original,_,_=prepare(tmp_path)
    phrases=["Implementa "+original,
             "Crea la pantalla "+original+" con las reglas vigentes",
             "Desarrolla "+original+" con Usuario obligatorio y Contraseña obligatoria"]
    packages=[launch(tmp_path,"wording-"+str(i),text)["package"]
              for i,text in enumerate(phrases)]
    # Cryptographic request SHA and A1-stage fingerprints MUST differ because
    # literal requests differ. Semantic, source-backed obligations do not.
    # The whole implementation-facing source scope must be invariant to
    # wording. Literal request identity, evidence hashes, and stage fingerprints
    # are intentionally NOT interchangeable across distinct requests.
    for key in ("classification","requirements","material_fronts",
                "scope_proposals","applicable_rules"):
        assert packages[0][key]==packages[1][key]==packages[2][key],key
    assert len({p["request_sha256"] for p in packages})==3


def test_minimal_and_detailed_no_new_obligation(tmp_path):
    original,_,_=prepare(tmp_path)
    a=launch(tmp_path,"minimal","Implementa "+original)
    b=launch(tmp_path,"detailed",
             "Implementa "+original+" con Usuario obligatorio y Contraseña obligatoria")
    assert [r["source_requirement_id"] for r in a["package"]["requirements"]]==[
        r["source_requirement_id"] for r in b["package"]["requirements"]]


def test_unknown_screen_and_untraced_behavior_block(tmp_path):
    original,_,_=prepare(tmp_path)
    with pytest.raises(ValueError,match="PEDIDO_AMBIGUO"):
        launch(tmp_path,"ambiguous","Implementa esta pantalla")
    with pytest.raises(ValueError,match="PEDIDO_EXCEDE_FICHA") as err:
        launch(tmp_path,"extra","Implementa "+original+" y agrega pagos con tarjeta")
    assert "pagos" in str(err.value)
    assert "tarjeta" in str(err.value)
    assert not (tmp_path/"pilot/runs/extra/analysis.json").exists()


def test_host_import_and_pinned_explicit_read_are_independent_of_catalogue_count(tmp_path):
    original,alternate,_=prepare(tmp_path)
    import analysis.host.fixture_readback_host as host
    assert host.DEFAULT_FIXTURES is None
    for code in (original,alternate):
        resolved=resolve(tmp_path,("Implementa "+code).encode())[1]
        obj=FixtureHost(resolved).read_all("Implementa "+code)
        assert obj["semantic_signals.json"]["a1_structured"]["target_hints"]==[code]
        assert obj["semantic_signals.json"]["a1_structured"]["objective"]["problem_statement"]=="Implementa "+code


def test_implementation_intent_uses_canonical_a9_registration_and_sha(tmp_path):
    from analysis.host.request_trace import implementation_state, RequestTraceBlocked
    code=json.loads((LEGACY_FIXTURES/"SOURCE_PIN.json").read_text())["fixture_id"]
    assert implementation_state(tmp_path,code)=="CREATE"
    file=tmp_path/"generated/component.txt"
    file.parent.mkdir(parents=True)
    file.write_text("verified")
    source=tmp_path/"pilot/runs/request/analysis.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({
        "schema_version":"ANALYSIS_IMPLEMENTATION_PACKAGE_V1",
        "request_context":{"target_ref":code},
        "programming_context_snapshot":{"target":code}}))
    registry=tmp_path/"pilot/registry/implemented.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({
        "schema_version":"T7_IMPLEMENTED_REGISTRY_V1",
        "entries":[{"request":"request","status":"ATTESTED",
                    "files":[{"path":"generated/component.txt",
                              "sha256":hashlib.sha256(file.read_bytes()).hexdigest()}]}]}))
    assert implementation_state(tmp_path,code)=="MODIFY"
    file.write_text("drift")
    with pytest.raises(RequestTraceBlocked,match="ANALISIS_SENALES_NO_DERIVABLES"):
        implementation_state(tmp_path,code)


def test_depth_signal_unknown_when_pinned_rule_categories_do_not_prove_materiality(tmp_path):
    import copy
    from analysis.host.request_trace import signals
    code=json.loads((LEGACY_FIXTURES/"SOURCE_PIN.json").read_text())["fixture_id"]
    data=FixtureHost(LEGACY_FIXTURES).read_all()
    modified=copy.deepcopy(data)
    for row in modified["effective_rules.json"]["rules"]:
        row["categoria"]="unclassified"
    derived=signals(tmp_path,code,"Implementa "+code,modified)
    assert derived["a2_signals"]["depth_signals"]["materiality_level"]=="UNKNOWN"
    assert derived["a2_signals"]["depth_signals"]["authority_state"]=="UNKNOWN"


def prepare_description_screen(tmp_path):
    """Generate an uncommitted, real-shape 13-source synthetic screen.

    No user-provided screen fixture is copied into repository history.
    """
    _,previous,_=prepare(tmp_path)
    folder=tmp_path/"analysis/fixtures/other_pinned_screen"
    pin_path=folder/"SOURCE_PIN.json"
    pin=json.loads(pin_path.read_text("utf-8"))
    target="SYN-CATALOG-LIST"
    pin["fixture_id"]=target
    descriptions=[
        "Un usuario con sesión iniciada ve su lista de recordatorios.",
        "Puede filtrar la lista de recordatorios por prioridad alta, media, baja o todas.",
        "Si la sesión expiró, la pantalla manda al login.",
        "El servicio responde el error genérico del sistema.",
        "Mis recordatorios sin duplicar componentes existentes.",
        "El estado de sesión no expone datos privados.",
        "Verificación opcional sin implementación vigente.",
        "Recuerda la sesión si el estado lo permite.",
    ]
    direct_path=folder/"direct_rules.json"
    direct=json.loads(direct_path.read_text("utf-8"))
    for i,row in enumerate(direct["linked_rules"]):
        row["descripcion"]=descriptions[i]
        row["title"]=descriptions[i].rstrip(".")
        row["code"]="SYN-R-"+str(i+1)
    for i,row in enumerate(direct["valor_config"]):
        row["code"]="SYN-R-"+str(i+1)
    direct_path.write_text(json.dumps(direct,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    eff_path=folder/"effective_rules.json"
    eff=json.loads(eff_path.read_text("utf-8"))
    # Global effective rule has its own independently pinned description.
    for i,row in enumerate(eff["rules"]):
        ref=row["source_ref"]
        corresponding=next((x for x in direct["linked_rules"]
                            if x["source_ref"]==ref),None)
        if corresponding:
            row["code"]=corresponding["code"]
            row["title"]=corresponding["title"]
            row.pop("descripcion",None)
        else:
            row["code"]="SYN-R-GLOBAL"
            row["title"]="Estado de sesión privado"
            row["descripcion"]=descriptions[5]
    eff_path.write_text(json.dumps(eff,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    screen_path=folder/"screen_contract.json"
    screen=json.loads(screen_path.read_text("utf-8"))
    screen["target_ref"]=target
    screen["contract"]["metadata"]["screen_code"]=target
    screen["contract"]["context"]["module_code"]="SYN-M-CATALOG"
    for item in screen["contract"]["rules"]:
        replacement=next((x for x in direct["linked_rules"]
                          if x["source_ref"]==item["source_ref"]),None)
        assert replacement is not None
        item["code"]=replacement["code"]
        item["title"]=replacement["title"]
    screen["contract"]["fields"][0]["field_code"]="SYN-F-LIST"
    screen["contract"]["fields"][1]["field_code"]="SYN-F-PRIORITY"
    screen["contract"]["errors"][0]["error_code"]="SYN-ERR-GENERIC"
    screen_path.write_text(json.dumps(screen,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    inventory_path=folder/"inventory.json"
    inventory=json.loads(inventory_path.read_text("utf-8"))
    inventory["target_ref"]=target
    inventory_path.write_text(json.dumps(inventory,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    asof_path=folder/"decision_asof.json"
    asof=json.loads(asof_path.read_text("utf-8"))
    asof["subject_ref"]=target
    asof_path.write_text(json.dumps(asof,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    # A 13th legacy signal file may exist but is never semantically trusted
    # for a different request, and cannot override the live request text.
    sample=json.loads((ROOT/"analysis/fixtures"/LEGACY_FIXTURES.name/
                       "semantic_signals.json").read_text("utf-8"))
    signal_path=folder/"semantic_signals.json"
    signal_path.write_text(json.dumps(sample,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    if not any(x["file"]=="semantic_signals.json" for x in pin["files"]):
        original=json.loads((ROOT/"analysis/fixtures"/LEGACY_FIXTURES.name/
                             "SOURCE_PIN.json").read_text("utf-8"))
        pin["files"].append(next(x for x in original["files"]
                                 if x["file"]=="semantic_signals.json"))
    for entry in pin["files"]:
        entry["sha256"]=hashlib.sha256((folder/entry["file"]).read_bytes()).hexdigest()
    assert len(pin["files"])==13
    pin_path.write_text(json.dumps(pin,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    # A real registered page is proof of REUTILIZAR by index, not a stopword.
    login=tmp_path/"frontend/src/app/login/page.tsx"
    login.parent.mkdir(parents=True)
    login.write_text("export default function Login() { return null; }\n")
    return target,folder


def test_three_user_request_styles_against_new_13_file_rule_descriptions(tmp_path):
    code,folder=prepare_description_screen(tmp_path)
    a="Implementa "+code
    b=(f'Quiero la pantalla {code} "Mis recordatorios": un usuario con sesión '
       'iniciada ve su lista de recordatorios y puede filtrarla por prioridad '
       '(alta, media, baja o todas). Si no tiene sesión o la sesión expiró, '
       'la pantalla lo manda al login y el servicio responde el error genérico '
       'del sistema. No quiero que se dupliquen cosas que ya existen.')
    c="Implementa "+code+" y que se pueda ordenar por fecha de vencimiento"
    minimal=launch(tmp_path,"synthetic-minimal",a)["package"]
    detailed=launch(tmp_path,"synthetic-detailed",b)["package"]
    for key in ("requirements","applicable_rules","classification",
                "material_fronts","scope_proposals"):
        assert minimal[key]==detailed[key],key
    with pytest.raises(ValueError,match="PEDIDO_EXCEDE_FICHA") as error:
        launch(tmp_path,"synthetic-excess",c)
    fragments=json.loads(str(error.value).split(":",1)[1])
    assert fragments==["ordenar","fecha","vencimiento"]


def test_missing_description_blocks_without_legacy_login_fallback(tmp_path):
    code,folder=prepare_description_screen(tmp_path)
    direct=folder/"direct_rules.json"
    pin=folder/"SOURCE_PIN.json"
    doc=json.loads(direct.read_text("utf-8"))
    missing=doc["linked_rules"][0]["code"]
    doc["linked_rules"][0].pop("descripcion")
    direct.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    manifest=json.loads(pin.read_text("utf-8"))
    next(x for x in manifest["files"] if x["file"]=="direct_rules.json")["sha256"]=hashlib.sha256(
        direct.read_bytes()).hexdigest()
    pin.write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    with pytest.raises(ValueError,match="REGLA_SIN_DESCRIPCION") as error:
        launch(tmp_path,"synthetic-missing","Implementa "+code)
    assert missing in str(error.value)


def test_registered_component_is_reuse_not_stop_word(tmp_path):
    code,folder=prepare_description_screen(tmp_path)
    from analysis.host.request_trace import trace
    data=FixtureHost(folder).read_all()
    # The registered /login page exists, but login is deliberately absent
    # from the synthetic rule descriptions for this isolated assertion.
    source=data["screen_contract.json"]["contract"]
    without_login=json.loads(json.dumps(source,ensure_ascii=False))
    for r in without_login["rules"]:
        r["title"]="Regla sin identidad de componente"
    reuse=trace("Implementa "+code+" reutiliza login",code,without_login,
                root=tmp_path,data={
                    **data,"direct_rules.json":{"linked_rules":[]},
                    "effective_rules.json":{"rules":[]}})
    assert any(x["term"]=="login" and x["decision"]=="REUTILIZAR"
               and x["evidence"].startswith("CODE_INDEX:") for x in reuse)
