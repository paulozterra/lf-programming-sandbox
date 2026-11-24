import hashlib, json
from pathlib import Path
import pytest
from analysis.host.request_trace import implementation_state, RequestTraceBlocked

CODE="SBX-SYNTH-SCREEN"


def _setup(root: Path, entries):
    run=root/"pilot/runs/req/analysis.json"
    run.parent.mkdir(parents=True)
    run.write_text(json.dumps({"request_context":{"target_ref":CODE},
                               "programming_context_snapshot":{"target":CODE}}))
    reg=root/"pilot/registry/implemented.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"schema_version":"T7_IMPLEMENTED_REGISTRY_V1",
                               "entries":entries}))


def _file(root: Path, name: str, text="v1"):
    f=root/name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return {"path":name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}


def _e(area, status, files, reasons=()):
    return {"request":"req","area":area,"status":status,"files":files,
            "reasons":list(reasons)}


def test_non_attested_lot_does_not_hide_attested_implementation(tmp_path):
    fe=_file(tmp_path,"fe/page.tsx"); be=_file(tmp_path,"be/Svc.java")
    _setup(tmp_path,[_e("FRONTEND","ATTESTED",[fe]),
                     _e("BACKEND","NO_DERIVABLE",[be],["INTEGRATED_FILES_MISSING"])])
    assert implementation_state(tmp_path,CODE)=="MODIFY"


def test_later_modified_file_is_partial_evidence(tmp_path):
    be=_file(tmp_path,"be/Svc.java"); fe=_file(tmp_path,"fe/page.tsx")
    (tmp_path/"fe/page.tsx").write_text("changed by a later integration")
    _setup(tmp_path,[_e("BACKEND","ATTESTED",[be]),_e("FRONTEND","NO_DERIVABLE",[fe])])
    assert implementation_state(tmp_path,CODE)=="MODIFY"


def test_only_non_attested_still_blocks(tmp_path):
    fe=_file(tmp_path,"fe/page.tsx")
    _setup(tmp_path,[_e("FRONTEND","NO_DERIVABLE",[fe],["RULE_BINDING_MISSING"])])
    with pytest.raises(RequestTraceBlocked,match="ANALISIS_SENALES_NO_DERIVABLES"):
        implementation_state(tmp_path,CODE)


def test_infra_and_contract_alone_do_not_prove_implementation(tmp_path):
    i=_file(tmp_path,"infra/x.yml"); c=_file(tmp_path,"contracts/x.yaml")
    _setup(tmp_path,[_e("INFRA","ATTESTED",[i]),_e("CONTRATO","ATTESTED",[c])])
    with pytest.raises(RequestTraceBlocked,match="ANALISIS_SENALES_NO_DERIVABLES"):
        implementation_state(tmp_path,CODE)


def test_deleted_attested_file_is_contradiction(tmp_path):
    fe=_file(tmp_path,"fe/page.tsx"); be=_file(tmp_path,"be/Svc.java")
    (tmp_path/"be/Svc.java").unlink()
    _setup(tmp_path,[_e("FRONTEND","ATTESTED",[fe]),_e("BACKEND","ATTESTED",[be])])
    with pytest.raises(RequestTraceBlocked,match="ANALISIS_SENALES_NO_DERIVABLES"):
        implementation_state(tmp_path,CODE)


def test_all_attested_drifted_blocks(tmp_path):
    fe=_file(tmp_path,"fe/page.tsx")
    (tmp_path/"fe/page.tsx").write_text("drift")
    _setup(tmp_path,[_e("FRONTEND","ATTESTED",[fe])])
    with pytest.raises(RequestTraceBlocked,match="ANALISIS_SENALES_NO_DERIVABLES"):
        implementation_state(tmp_path,CODE)
