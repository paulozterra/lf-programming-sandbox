"""Offline API-lot rehearsal to the exact model gate, without API/oracle.

Acceptance is recomputed by the trusted generate_chain function, not copied
from the workflow and never guessed from a case-specific screen.
"""
import json
import sys
from pathlib import Path

import pytest

from pilot.worker_v08 import api_lot
from pilot.worker_v08.lf_rule_context import material

ROOT=Path(__file__).resolve().parents[2]


def fixtures(tmp_path, area, monkeypatch):
    task="synthlot"
    slug="synth"
    module="module"
    lotpath=("contracts/module.openapi.yaml" if area=="CONTRATO"
             else "apps/time-service/pom.xml")
    paths=[lotpath]
    if area=="CONTRATO":
        policy=json.loads((ROOT/"pilot/orchestrator/atomize_rules_v1.json").read_text())
        loc=tmp_path/"pilot/orchestrator/atomize_rules_v1.json"
        loc.parent.mkdir(parents=True)
        loc.write_text(json.dumps(policy))
        skeleton=policy["contract_lot"]["skeleton_path"].format(module=module)
        commands=api_lot.acceptance(area, paths, run=slug, module=module,
                                    skeleton_path=skeleton)
    else:
        commands=api_lot.acceptance(area, paths, run=slug, infra_dependencies=[])
    lot={"id":"SOL-001","area":area,"write_paths":paths,
         "contract_module":module if area=="CONTRATO" else None,
         "infra_missing_dependencies":[] if area=="INFRA" else None}
    templates=tmp_path/f"pilot/runs/{slug}/templates"
    templates.mkdir(parents=True)
    spec={"schema_version":1,"task_id":"LF-WORKER-NATIVE-SYNTHLOT",
          "objective":"synthetic offline only",
          "base_head_sha":"a"*40,"source_snapshot_sha256":"b"*64,
          "max_attempts":1,"allow_deletions":False,"max_changed_files":1,
          "max_context_bytes":100000,"max_patch_bytes":40000,
          "write_path_patterns":paths,
          "context_path_patterns":[f".lf/worker-context/{task}/lf_rules.receipt.json"],
          "protected_path_patterns":[],
          "acceptance_commands":commands}
    (templates/f"{task}.task.json").write_text(json.dumps({"task_spec":spec}))
    (templates.parent/"lots.json").write_text(json.dumps({"lots":[lot]}))
    (templates.parent/"chain_plan.json").write_text(json.dumps({
        "request_id":slug,"bindings":[{"task_name":task,"lot_id":"SOL-001",
             "template_path":f"pilot/runs/{slug}/templates/{task}.task.json"}]}))
    context=tmp_path/f".lf/worker-context/{task}"
    context.mkdir(parents=True)
    receipt=material(area,skill_codes=["SPRINGBOOT_EXP"])[1]
    (context/"lf_rules.receipt.json").write_text(json.dumps(receipt))
    (context/"receipt.json").write_text(json.dumps({"skills":[{"code":"SPRINGBOOT_EXP"}]}))
    register=tmp_path/f"pilot/worker_v08/native_tasks/{task}.json"
    register.parent.mkdir(parents=True)
    register.write_text(json.dumps({"holdout_sha256":"c"*64,
        "holdout_ref":f"pilot/holdouts/{task}.oracle.json.age"}))
    monkeypatch.setattr(api_lot, "load_registration",lambda root,t: (spec,"c"*64))
    return task, spec, templates/f"{task}.task.json"


@pytest.mark.parametrize("area",("CONTRATO","INFRA"))
def test_api_admission_uses_exact_generated_acceptance_no_paid_call(
        tmp_path, monkeypatch, capsys, area):
    task,spec,template=fixtures(tmp_path,area,monkeypatch)
    admitted=api_lot.admit(tmp_path,task)
    assert admitted["acceptance_commands"]==spec["acceptance_commands"]
    assert admitted["area"]==area
    monkeypatch.setattr(sys,"argv",["api_lot.py","admission",
                      "--control",str(tmp_path),"--task",task])
    api_lot.main()
    result=json.loads(capsys.readouterr().out)
    assert result["status"]=="READY_AT_WORKER_GATE"
    assert result["api_calls"]==0
    assert result["acceptance_commands"]==spec["acceptance_commands"]


@pytest.mark.parametrize("area",("CONTRATO","INFRA"))
def test_api_changed_or_missing_generated_acceptance_blocks(
        tmp_path,monkeypatch,area):
    task,spec,template=fixtures(tmp_path,area,monkeypatch)
    modified=json.loads(template.read_text())
    modified["task_spec"]["acceptance_commands"][0]["argv"].append("unexpected")
    template.write_text(json.dumps(modified))
    with pytest.raises(api_lot.ApiLotBlocked,match="API_LOT_GENERATED_ACCEPTANCE_DRIFT"):
        api_lot.admit(tmp_path,task)


@pytest.mark.parametrize("area",("CONTRATO","INFRA"))
def test_api_missing_rules_or_waiver_context_blocks(tmp_path,monkeypatch,area):
    task,spec,template=fixtures(tmp_path,area,monkeypatch)
    (tmp_path/f".lf/worker-context/{task}/lf_rules.receipt.json").unlink()
    with pytest.raises(api_lot.ApiLotBlocked,match="API_LOT_EVIDENCE_MISSING"):
        api_lot.admit(tmp_path,task)
