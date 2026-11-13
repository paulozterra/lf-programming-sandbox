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


def _backend_screen(folder):
    """Keep 13 pinned sources, but constrain this test's obligations to BE."""
    pinpath=folder/"SOURCE_PIN.json"
    pin=json.loads(pinpath.read_text("utf-8"))
    for name in ("screen_contract.json", "direct_rules.json", "effective_rules.json"):
        file=folder/name
        obj=json.loads(file.read_text("utf-8"))
        if name=="screen_contract.json":
            obj["contract"]["fields"]=[]
            obj["contract"]["visual"]["variants"]=[]
        elif name=="direct_rules.json":
            for row in obj["linked_rules"]:
                row["categoria"]="seguridad" if row["code"]=="SYN-R-1" else "api"
        else:
            for row in obj["rules"]:
                row["categoria"]="seguridad" if row["code"]=="SYN-R-1" else "api"
        file.write_text(json.dumps(obj,sort_keys=True,ensure_ascii=False,indent=2)+"\n")
        next(x for x in pin["files"] if x["file"]==name)["sha256"]=hashlib.sha256(
            file.read_bytes()).hexdigest()
    pinpath.write_text(json.dumps(pin,sort_keys=True,ensure_ascii=False,indent=2)+"\n")


def _git_main(root, files):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "--", *files], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "test main source"], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "main"], cwd=root, text=True).strip()


def _scenario(tmp_path, *, adds_rule=False, missing=False, declared=True,
              attested=False, drift=False, backend_only=False, by_rule=False):
    code, folder=prepare_description_screen(tmp_path)
    if backend_only:
        _backend_screen(folder)
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
             if x["source_requirement_id"]=="SYN-R-1"
             and x["scope_id"].endswith("-BACKEND"))
    dependency={"kind":"endpoint", "method":"GET",
                "route":"/api/missing" if missing else "/api/items",
                **({"rule_code":"SYN-R-1"} if by_rule
                   else {"requirement_id":rid}),
                "adds_rule":adds_rule}
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
    requirements=[{"requirement_id":"REQ-SOURCE","source_requirement_id":"RULE-SOURCE",
                   "scope_id":"SYN-FRONTEND"},
                  {"requirement_id":"REQ-DERIVED","source_requirement_id":"RULE-SOURCE",
                   "scope_id":"SYN-BACKEND",
                   "derived_from_requirement_id":"REQ-SOURCE"}]
    deps=[{"kind":"endpoint","method":"GET","route":"/api/items",
           "rule_code":"RULE-SOURCE","adds_rule":False}]
    selected=select(deps,requirements)
    assert set(selected)=={"REQ-DERIVED"}
    assert selected["REQ-DERIVED"]["key"]=="GET /api/items"

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
    assert stages["stages"]["A4"]["host_simulated_dependency_attestation"]["status"].startswith("UNVERIFIED:")


@pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="Actual PG02-PG05 lot generation requires disposable selector DB")
def test_confirmed_dependency_reaches_real_plan_lots(tmp_path):
    package, ledger, dependency, endpoint, session = _scenario(
        tmp_path, adds_rule=True, attested=True, backend_only=True)
    assert package["package_readiness_candidate"] == "READY_CANDIDATE"
    report = assess(index(tmp_path), package["requirements"], registry=ledger,
                    root=tmp_path, declared_dependencies=[dependency])
    atom = atomize.atomize(package, tmp_path, "a"*40,
                          run="t72-after", reuse_assessment=report)
    folder=tmp_path/"pilot/runs/t72-after"
    (folder/"reuse_assessment.json").write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8")
    (folder/"atomized_inputs.json").write_bytes(intake.canonical(atom))
    planned=plan_lots.plan(tmp_path,"t72-after")
    assert planned["lots"]
    assert any(endpoint in lot["write_paths"] for lot in planned["lots"])
    assert all("REQ-SYN-R-1" not in lot["requirement_ids"]
               for lot in planned["lots"] if lot["area"] == "DATA")


@pytest.mark.parametrize("by_rule", [True, False])
def test_endpoint_dependency_binds_backend_not_frontend(tmp_path, by_rule):
    package, ledger, dep, endpoint, session = _scenario(
        tmp_path, attested=True, by_rule=by_rule)
    from pilot.orchestrator.declared_dependencies import select
    mapping = select([dep], package["requirements"])
    assert len(mapping) == 1
    backend_id = next(iter(mapping))
    assert backend_id.endswith("-BACKEND") or next(
        r for r in package["requirements"] if r["requirement_id"] == backend_id
    )["scope_id"].endswith("-BACKEND")
    report = assess(index(tmp_path), package["requirements"], registry=ledger,
                    root=tmp_path, declared_dependencies=[dep])
    by_id = {row["requirement_id"]: row["decision"] for row in report["obligations"]}
    assert by_id[backend_id] == "REUSE_AS_IS"
    assert any(r["source_requirement_id"] == "SYN-R-1"
               and r["scope_id"].endswith("-FRONTEND")
               and by_id[r["requirement_id"]] == "BUILD_NEW"
               for r in package["requirements"])
    from analysis.host.run_a1_a8_fixture import run_f3
    stage = run_f3(fixtures=tmp_path/"analysis/fixtures/other_pinned_screen",
                   request="Implementa SYN-CATALOG-LIST")
    attest = stage["stages"]["A4"]["host_simulated_dependency_attestation"]
    assert attest["status"] == "CONFIRMED"
    assert attest["entries"][0]["requirement_id"] == backend_id


def test_endpoint_rule_code_without_backend_requirement_blocks():
    from pilot.orchestrator.declared_dependencies import select, DependencyBlocked
    deps = [{"kind":"endpoint","method":"GET","route":"/api/items",
             "rule_code":"RULE-X","adds_rule":False}]
    requirements = [{"requirement_id":"REQ-RULE-X",
                     "source_requirement_id":"RULE-X",
                     "scope_id":"SYN-FRONTEND"}]
    with pytest.raises(DependencyBlocked, match="DEPENDENCIA_AREA_INCOMPATIBLE"):
        select(deps, requirements)
    with pytest.raises(DependencyBlocked, match="DEPENDENCIA_SIN_REQUISITO"):
        select([{**deps[0], "rule_code":"UNKNOWN"}], requirements)

@pytest.mark.parametrize("by_rule", [True, False])
@pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="PG02-PG05 requires a real disposable selector database")
def test_mixed_frontend_build_and_backend_reuse_plans_without_phantom_lot(tmp_path, by_rule):
    package, ledger, dep, endpoint, _ = _scenario(
        tmp_path, attested=True, by_rule=by_rule)
    assert package["package_readiness_candidate"] == "READY_CANDIDATE"
    from pilot.orchestrator.declared_dependencies import select
    backend_id = next(iter(select([dep], package["requirements"])))
    frontend = [r["requirement_id"] for r in package["requirements"]
                if r["source_requirement_id"] == "SYN-R-1"
                and r["scope_id"].endswith("-FRONTEND")]
    assert frontend and backend_id not in frontend
    report = assess(index(tmp_path), package["requirements"], registry=ledger,
                    root=tmp_path, declared_dependencies=[dep])
    by_id = {row["requirement_id"]: row["decision"] for row in report["obligations"]}
    assert by_id[backend_id] == "REUSE_AS_IS"
    assert all(by_id[x] == "BUILD_NEW" for x in frontend)
    folder = tmp_path/"pilot/runs/t72-after"
    (folder/"reuse_assessment.json").write_text(
        json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",
        encoding="utf-8")
    atoms = atomize.atomize(package, tmp_path, "a"*40, run="t72-after",
                           reuse_assessment=report)
    assert all(backend_id not in a["requirement_ids"] for a in atoms["atoms"])
    assert any(any(fid in a["requirement_ids"] for fid in frontend)
               for a in atoms["atoms"])
    # A scoped BACKEND may still have other BUILD_NEW requirements; only
    # the attested endpoint obligation is excluded from write-bearing lots.
    (folder/"atomized_inputs.json").write_bytes(intake.canonical(atoms))
    planned = plan_lots.plan(tmp_path, "t72-after")
    assert planned["lots"]
    assert all(backend_id not in lot["requirement_ids"] for lot in planned["lots"])
    assert any(lot["area"] == "FRONTEND" for lot in planned["lots"])

def _same_endpoint_chain(tmp_path, *, extend=True, protect_tests=True):
    """Exercise real generate_chain with two sourced obligations in one lot."""
    import sys
    directory = str(Path(__file__).resolve().parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    from pilot.orchestrator import generate_chain

    root = tmp_path
    run = "t72-same-endpoint"
    folder = root/"pilot/runs"/run
    folder.mkdir(parents=True)
    controller = "apps/time-service/src/main/java/lf/sandbox/time/catalog/ExistingItems.java"
    text = 'public class ExistingItems {\n@GetMapping("/api/items")\n}\n'
    (root/controller).parent.mkdir(parents=True)
    (root/controller).write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    class_test = "apps/time-service/src/test/java/lf/sandbox/time/catalog/ExistingItemsTest.java"
    endpoint_test = "apps/time-service/visible-tests/catalog/ItemsEndpointCheck.java"
    for path, content in (
        (class_test, "class ExistingItemsTest { }\n"),
        (endpoint_test, 'class ItemsEndpointCheck { String route = "/api/items"; }\n'),
    ):
        (root/path).parent.mkdir(parents=True, exist_ok=True)
        (root/path).write_text(content, encoding="utf-8")
    scope = "SYN-CATALOG-BACKEND"
    reuse_id = "REQ-EXISTING-FILTER"
    extend_id = "REQ-SESSION-ENFORCEMENT"
    rows = [
        {"requirement_id": reuse_id, "decision": "REUSE_AS_IS",
         "path": controller, "sha256": sha, "write_paths": [],
         "reuse_context": [{"path": controller, "sha256": sha}],
         "reused_endpoints": ["GET /api/items"]},
        {"requirement_id": extend_id,
         "decision": "EXTEND" if extend else "BUILD_NEW",
         "path": controller if extend else None,
         "sha256": sha if extend else None,
         "write_paths": [controller] if extend else [],
         "reuse_context": [],
         "reused_endpoints": ["GET /api/items"] if extend else []},
    ]
    (folder/"analysis.json").write_text(json.dumps({
        "requirements": [
            {"requirement_id": rid, "scope_id": scope}
            for rid in (reuse_id, extend_id)]}), encoding="utf-8")
    (folder/"reuse_assessment.json").write_text(json.dumps({
        "schema_version": "T7_REUSE_ASSESSMENT_V1",
        "obligations": rows}), encoding="utf-8")
    lots = {"schema_version":"CP33_LOTS_CANDIDATE_V1",
            "production_authority":False, "handoff_allowed":False,
            "worker_invoked":False,
            "lots":[{"id":"LOT-BACKEND-1","area":"BACKEND",
                     "write_paths":[controller],"depends_on":[],
                     "requirement_ids":[reuse_id, extend_id]}]}
    if not protect_tests:
        (root/class_test).unlink()
        (root/endpoint_test).unlink()
    return generate_chain, root, run, lots, controller, class_test, endpoint_test


def test_same_lot_reuse_and_extend_writes_controller_and_protects_both_tests(tmp_path):
    generate_chain, root, run, lots, controller, class_test, endpoint_test = _same_endpoint_chain(tmp_path)
    plan = generate_chain.generate(root, run, lots)
    assert len(plan["bindings"]) == 1
    spec = json.loads((root/plan["bindings"][0]["template_path"]).read_text())["task_spec"]
    assert controller in spec["write_path_patterns"]
    assert controller not in spec["context_path_patterns"]
    assert controller not in spec["protected_path_patterns"]
    assert {class_test, endpoint_test} <= set(spec["protected_path_patterns"])
    assert "/api/items" in spec["objective"]
    assert "conservar el comportamiento existente" in spec["objective"]
    assert class_test in spec["objective"] and endpoint_test in spec["objective"]


def test_same_lot_without_extend_cannot_write_reuse_only_controller(tmp_path):
    generate_chain, root, run, lots, *_ = _same_endpoint_chain(tmp_path, extend=False)
    with pytest.raises(ValueError, match="REUTILIZACION_INDETERMINADA"):
        generate_chain.generate(root, run, lots)


def test_same_lot_overlap_without_existing_tests_stays_blocked(tmp_path):
    generate_chain, root, run, lots, *_ = _same_endpoint_chain(tmp_path, protect_tests=False)
    with pytest.raises(ValueError, match="REUTILIZACION_INDETERMINADA"):
        generate_chain.generate(root, run, lots)
