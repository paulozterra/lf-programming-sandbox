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
    for key in ("requirements","applicable_rules"):
        codes=[[(v.get("source_requirement_id"),v.get("rule_code"))
                 for v in p[key]] for p in packages]
        assert codes[0]==codes[1]==codes[2]
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
