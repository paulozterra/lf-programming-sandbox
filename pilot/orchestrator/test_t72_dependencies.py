"""T7.2: synthetic 13-source screen; no production catalogue copies."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from analysis.host.test_t71_general import prepare_description_screen, launch
from pilot.orchestrator import atomize, plan_lots, intake
from pilot.orchestrator.reuse_assessment import index, assess, ReuseBlocked
from pilot.orchestrator.contract_validate import _check_skeleton, ContractBlocked


def _file(root, relative, contents):
    path=root/relative
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return relative


def _inventory(folder, dependencies):
    path=folder/"inventory.json"
    doc=json.loads(path.read_text("utf-8"))
    doc["dependencies"]=dependencies
    path.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    pinpath=folder/"SOURCE_PIN.json"
    pin=json.loads(pinpath.read_text("utf-8"))
    next(row for row in pin["files"] if row["file"]=="inventory.json")["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    pinpath.write_text(json.dumps(pin,ensure_ascii=False,sort_keys=True,indent=2)+"\n")


def _git_main(root, files):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "--", *files], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "test main source"], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "main"], cwd=root, text=True).strip()


def _scenario(tmp_path, *, adds_rule=False, missing=False, declared=True,
              attested=False, drift=False):
    code, folder=prepare_description_screen(tmp_path)
    endpoint_path=_file(tmp_path,
        "apps/time-service/src/main/java/lf/sandbox/time/catalog/ExistingItems.java",
        'public class ExistingItems {\n@GetMapping("/api/items")\n'
        'public String list() { return "ok"; }\n}\n')
    session_path=_file(tmp_path,
        "apps/time-service/src/main/java/lf/sandbox/time/catalog/ExistingSession.java",
        'public class ExistingSession {\n'
        'public boolean authenticated() { return true; }\n}\n')
    pkg=launch(tmp_path,"t72-before","Implementa "+code)["package"]
    rid=next(x["requirement_id"] for x in pkg["requirements"]
             if x["source_requirement_id"]=="SYN-R-1")
    dependency={"kind":"endpoint", "method":"GET",
                "route":"/api/missing" if missing else "/api/items",
                "requirement_id":rid, "adds_rule":adds_rule}
    if adds_rule:
        dependency["reuse_component_signature"]="type:ExistingSession"
    _inventory(folder,[dependency] if declared else [])
    if attested:
        _git_main(tmp_path,[endpoint_path, session_path])
        if drift:
            file=tmp_path/endpoint_path
            file.write_text(file.read_text(encoding="utf-8") + "// drift\\n", encoding="utf-8")
    pkg=launch(tmp_path,"t72-after","Implementa "+code)["package"]
    ledger={"schema_version":"T7_IMPLEMENTED_REGISTRY_V1","entries":[]}
    return pkg, ledger, dependency, endpoint_path, session_path


def test_declared_existing_endpoint_without_new_rule_reuses_as_is(tmp_path):
    package,ledger,dep,endpoint,_=_scenario(tmp_path)
    result=assess(index(tmp_path),package["requirements"],registry=ledger,root=tmp_path,
                  declared_dependencies=[dep])
    row=next(x for x in result["obligations"] if x["requirement_id"]==dep["requirement_id"])
    assert row["decision"]=="REUSE_AS_IS"
    assert row["path"]==endpoint
    assert row["write_paths"]==[]
    assert row["reused_endpoints"]==["GET /api/items"]
    assert row["reuse_context"][0]["path"]==endpoint


def test_declared_existing_endpoint_with_new_session_rule_extends(tmp_path):
    package,ledger,dep,endpoint,session=_scenario(tmp_path,adds_rule=True)
    result=assess(index(tmp_path),package["requirements"],registry=ledger,root=tmp_path,
                  declared_dependencies=[dep])
    row=next(x for x in result["obligations"] if x["requirement_id"]==dep["requirement_id"])
    assert row["decision"]=="EXTEND"
    assert row["write_paths"]==[endpoint]
    assert [x["path"] for x in row["reuse_context"]]==[session]
    assert row["reused_endpoints"]==["GET /api/items"]
    atom=atomize.atomize(package,tmp_path,"a"*40,run="t72-after",reuse_assessment=result)
    assert any(endpoint in a["paths"] for a in atom["atoms"])


def test_declared_missing_endpoint_fails_closed(tmp_path):
    package,ledger,dep,_,_=_scenario(tmp_path,missing=True)
    with pytest.raises(ReuseBlocked,match="DEPENDENCIA_DECLARADA_AUSENTE"):
        assess(index(tmp_path),package["requirements"],registry=ledger,root=tmp_path,
               declared_dependencies=[dep])


def test_no_declared_dependencies_preserves_old_assessment(tmp_path):
    package,ledger,_,_,_=_scenario(tmp_path,declared=False)
    idx=index(tmp_path)
    original=assess(idx,package["requirements"],registry=ledger,root=tmp_path)
    empty=assess(idx,package["requirements"],registry=ledger,root=tmp_path,
                 declared_dependencies=[])
    assert original==empty


def test_existing_endpoint_contract_identity_is_source_bound(tmp_path):
    package,ledger,dep,_,_=_scenario(tmp_path,adds_rule=True)
    report=assess(index(tmp_path),package["requirements"],registry=ledger,root=tmp_path,
                  declared_dependencies=[dep])
    extended=[endpoint for row in report["obligations"] if row["decision"]=="EXTEND"
              for endpoint in row["reused_endpoints"]]
    skeleton={"schema_version":"T2_CONTRACT_SKELETON_V1","functional_module":"synthetic",
              "production_authority":False,"fields":[{"field_code":"value","required":False}],
              "errors":[{"error_code":"E"}],"requirement_ids":["REQ-SYN"],
              "rules":[],"reused_endpoints":extended,"extended_endpoints":extended}
    _check_skeleton(skeleton,"synthetic")
    skeleton["extended_endpoints"]=["GET /api/parallel"]
    with pytest.raises(ContractBlocked,match="REUTILIZACION_INDETERMINADA"):
        _check_skeleton(skeleton,"synthetic")

def test_rule_code_links_primary_requirement_even_with_derived_child():
    from pilot.orchestrator.declared_dependencies import select
    requirements=[{"requirement_id":"REQ-SOURCE","source_requirement_id":"RULE-SOURCE"},
                  {"requirement_id":"REQ-DERIVED","source_requirement_id":"RULE-SOURCE",
                   "derived_from_requirement_id":"REQ-SOURCE"}]
    deps=[{"kind":"component","signature":"export:ExistingComponent",
           "rule_code":"RULE-SOURCE","adds_rule":False}]
    selected=select(deps,requirements)
    assert set(selected)=={"REQ-SOURCE"}
    assert selected["REQ-SOURCE"]["key"]=="export:ExistingComponent"

def test_main_attested_dependencies_make_a9_ready(tmp_path):
    package, _, dep, endpoint, session = _scenario(
        tmp_path, adds_rule=True, attested=True)
    assert package["package_readiness_candidate"] == "READY_CANDIDATE"
    assert package["research_stop"]["decision"] == "STOP"
    from analysis.host.run_a1_a8_fixture import run_f3
    stages = run_f3(fixtures=tmp_path/"analysis/fixtures/other_pinned_screen",
                    request="Implementa SYN-CATALOG-LIST")
    evidence = stages["stages"]["A4"]["host_simulated_dependency_attestation"]
    assert evidence["status"] == "CONFIRMED"
    assert evidence["production_authority"] is False
    assert evidence["entries"][0]["evidence"][0]["path"] == endpoint
    assert all(row["attestation_mode"] == "SIMULATED"
               and len(row["main_commit_sha"]) == 40
               for row in evidence["entries"][0]["evidence"])


def test_unconfirmed_main_dependency_never_becomes_ready(tmp_path):
    package, _, _, _, _ = _scenario(tmp_path, missing=True, attested=True)
    assert package["package_readiness_candidate"] != "READY_CANDIDATE"
    assert package["research_stop"]["decision"] != "STOP"


def test_main_sha_drift_does_not_attest(tmp_path):
    package, _, _, _, _ = _scenario(tmp_path, attested=True, drift=True)
    assert package["package_readiness_candidate"] != "READY_CANDIDATE"
    from analysis.host.run_a1_a8_fixture import run_f3
    stages = run_f3(fixtures=tmp_path/"analysis/fixtures/other_pinned_screen",
                    request="Implementa SYN-CATALOG-LIST")
    assert stages["stages"]["A4"]["host_simulated_dependency_attestation"]["status"] == "UNVERIFIED"


@pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="Actual PG02-PG05 lot generation requires disposable selector DB")
def test_confirmed_dependency_reaches_real_plan_lots(tmp_path):
    package, ledger, dependency, endpoint, session = _scenario(
        tmp_path, adds_rule=True, attested=True)
    assert package["package_readiness_candidate"] == "READY_CANDIDATE"
    report = assess(index(tmp_path), package["requirements"], registry=ledger,
                    root=tmp_path, declared_dependencies=[dependency])
    atom = atomize.atomize(package, tmp_path, "a"*40,
                          run="t72-after", reuse_assessment=report)
    folder=tmp_path/"pilot/runs/t72-after"
    (folder/"atomized_inputs.json").write_bytes(intake.canonical(atom))
    planned=plan_lots.plan(tmp_path,"t72-after")
    assert planned["lots"]
    assert any(endpoint in lot["write_paths"] for lot in planned["lots"])
    assert all("REQ-SYN-R-1" not in lot["requirement_ids"]
               for lot in planned["lots"] if lot["area"] == "DATA")

