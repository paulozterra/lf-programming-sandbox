#!/usr/bin/env python3
"""T1 deterministic chain-plan and task-template generation, no registration."""
from __future__ import annotations
# Resolve the trusted repository package when executed as a script.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path
from pilot.config import project_config as _project

import hashlib
import json
from pathlib import Path

from chain_contract import validate_plan
from worker_template_contract import validate_template_worker
from native_write_scope import validate_write_paths
from affected_tests import is_project_test, project_test_files, project_test_globs

def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")

def save(path, value):
    content=canonical(value)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():
        raise ValueError("T1_OUTPUT_SYMLINK")
    if path.exists():
        if path.read_bytes()!=content:
            raise ValueError("T1_OUTPUT_DRIFT:"+str(path))
    else:
        with path.open("xb") as f:
            f.write(content)

def enforce_generated_scope(area: str, paths: list[str]) -> None:
    """No generator may issue a path that CP3.5 rejects for its area."""
    try:
        validate_write_paths(paths, area=area)
    except ValueError as exc:
        raise ValueError("SCOPE_GENERACION_INTEGRACION_DIVERGE:" + str(area)) from exc


def lot_protection(area, paths):
    """T54 phase 3b: protected patterns of a generated lot, from project config.

    protected_base minus the area's unprotect entries (and unprotect_if_written
    entries the lot actually writes), plus the area's own protections.
    """
    policy=_project.lot_policy()
    rules=policy["areas"][area]
    protected=list(policy["protected_base"])
    for entry in rules["unprotect_if_written"]:
        if entry in paths:
            protected.remove(entry)
    for entry in rules["unprotect"]:
        protected.remove(entry)
    protected += rules["protect"]
    # Defense in depth: control-plane protection is unconditional.
    for entry in _project.CONTROL_PLANE_PROTECTED:
        if entry not in protected:
            protected.append(entry)
    return protected


def acceptance(area, paths, *, run=None, module=None, has_contract=False, skeleton_path=None, infra_dependencies=None):
    def item(name, argv, timeout=600):
        if argv and Path(argv[0]).name in ("python", "python2", "python3", "python3.12"):
            argv = ["lf-python", *argv[1:]]
        if argv and (Path(argv[0]).name.startswith("python")
                     and argv[0] != "lf-python"):
            raise ValueError("TEMPLATE_PYTHON_NO_FIJADO:" + area)
        return {"name":name,"argv":argv,"timeout_seconds":timeout,"max_output_bytes":32000}
    if area=="CONTRATO":
        if not run or not module or len(paths)!=1 or not skeleton_path:
            raise ValueError("T2_CONTRACT_ACCEPTANCE_SOURCE_MISSING")
        return [item("contract-source-coverage",
            ["python3","pilot/orchestrator/contract_validate.py",
             "--contract",paths[0],"--skeleton",
             skeleton_path,
             "--module",module])]
    if area=="BACKEND":
        # T54 phase 3b: build file from the project's maven component.
        pom=_project.area_component("BACKEND","maven")["build_file"]
        result=[item("backend-package",["mvn","-B","-q","-f",pom,"package"])]
        if has_contract:
            result += [
                item("backend-start-openapi",["mvn","-B","-q","-f",pom,
                                              "spring-boot:start"]),
                item("backend-contract-operations",
                     ["python3","pilot/orchestrator/contract_validate.py",
                      "--compare-live","http://127.0.0.1:8080/v3/api-docs"]),
                item("backend-stop-openapi",["mvn","-B","-q","-f",pom,
                                             "spring-boot:stop"]),
            ]
        return result
    if area=="FRONTEND":
        web=_project.area_component("FRONTEND","npm")
        client=web["generated_client"]
        result=[item("frontend-install",["npm","--prefix",web["root"],"ci"]),
                item("frontend-lint",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-lint"]),
                item("frontend-types",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-typecheck"]),
                item("frontend-build",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-build"]),
                item("frontend-prettier",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-prettier"]),
                # One pinned trusted browser command. Encrypted oracles run the
                # exact same gate with examiner-selected routes/assertions.
                item("frontend-browser-visible",["python3","pilot/worker_v08/playwright_gate.py",
                                                 "--path","/","--selector","body"],240)]
        # Declarative browser cases kept in the component's visible test root
        # protect existing behavior; an empty suite passes without cases.
        suites=[r for r in web["test_roots"] if r.rstrip("/").endswith("visible-tests")]
        if len(suites)==1:
            result.append(item("frontend-visible-suite",["python3","pilot/worker_v08/playwright_gate.py",
                                                       "--suite",suites[0].rstrip("/"),"--mutation-check"],420))
        if has_contract:
            if client is None:
                raise ValueError("T2_GENERATED_CLIENT_NOT_CONFIGURED")
            result += [
                item("frontend-generate-api",["npm","--prefix",web["root"],"run",client["script"]]),
                item("frontend-typed-client-diff",["python3","pilot/orchestrator/contract_validate.py",
                                                "--check-client","."]),
                item("frontend-no-manual-fetch",["python3","pilot/orchestrator/contract_validate.py",
                                                "--check-frontend","."]),
            ]
        return result
    if area=="INFRA":
        if not isinstance(infra_dependencies, list):
            raise ValueError("T3_INFRA_DEPENDENCIES_MISSING")
        argv=["python3","pilot/orchestrator/infra_validate.py",
              "--check-infra","--root","."]
        for dependency in infra_dependencies:
            argv += ["--dependency-id",dependency["id"]]
        infra=_project.area_components("INFRA")
        if any(cfg_file in paths for _,c in infra if c["kind"]=="maven"
               for cfg_file in c["config_files"]):
            argv += ["--database"]
        result=[item("infra-allowlist-and-env",argv)]
        for _,c in infra:
            if c["kind"]=="maven" and c["build_file"] in paths:
                result.append(item("infra-build",["mvn","-U","-B","-q","-f",
                                                  c["build_file"],
                                                  "-DskipTests","package"]))
        for _,c in infra:
            if c["kind"]=="npm" and c["build_file"] in paths:
                result.append(item("infra-npm-ci",["npm","--prefix",c["root"],"ci"]))
                if c["generated_client"] is not None:
                    result.append(item("infra-generated-client",
                        ["npm","--prefix",c["root"],"run",c["generated_client"]["script"]]))
        return result
    if area=="DATA":
        return [item("data-classpath-migrations",["python3","pilot/orchestrator/infra_validate.py",
                                                  "--check-data",*paths]),
                item("data-migration-visible",["psql","-X","-v","ON_ERROR_STOP=1","-f",paths[0]],180)]
    raise ValueError("T1_AREA_INVALID")

def _existing_behavior_tests(root, source_path, endpoints):
    """Discover exact existing Java/controller tests and reused endpoint tests."""
    source = Path(source_path)
    if (source.suffix != ".java" or not source.name
            or not isinstance(endpoints, list) or not endpoints
            or not all(isinstance(ep, str) and " " in ep for ep in endpoints)):
        raise ValueError("REUTILIZACION_INDETERMINADA")
    routes = {ep.split(" ", 1)[1] for ep in endpoints}
    matched = []
    for name in _project.area_component("BACKEND", "maven")["test_roots"]:
        directory = Path(root) / name
        if directory.is_symlink():
            raise ValueError("REUTILIZACION_INDETERMINADA")
        if not directory.is_dir():
            continue
        for file in sorted(directory.rglob("*")):
            if file.is_symlink():
                raise ValueError("REUTILIZACION_INDETERMINADA")
            if not file.is_file() or file.suffix not in (".java", ".py", ".ts", ".tsx"):
                continue
            paired = file.stem in (source.stem + "Test", source.stem + "Tests",
                                  source.stem + "IT")
            try:
                route_match = any(route in file.read_text(encoding="utf-8")
                                  for route in routes)
            except (UnicodeError, OSError) as exc:
                raise ValueError("REUTILIZACION_INDETERMINADA") from exc
            if paired or route_match:
                matched.append(file.relative_to(root).as_posix())
    if not matched:
        raise ValueError("REUTILIZACION_INDETERMINADA")
    return sorted(set(matched))


def _visible_suite_root():
    roots=[r.rstrip("/") for r in _project.area_component("FRONTEND","npm")["test_roots"]
           if r.rstrip("/").endswith("visible-tests")]
    return roots[0] if len(roots)==1 else None


def _item(name, argv, timeout=600):
    return {"name":name,"argv":argv,"timeout_seconds":timeout,"max_output_bytes":32000}


def _characterization_objective(lot, requirement_by_id):
    rules = "; ".join(
        r + (": " + requirement_by_id[r]["outcome"]
             if isinstance(requirement_by_id.get(r, {}).get("outcome"), str) else "")
        for r in lot["characterized_requirement_ids"])
    return ("Caracterizar el comportamiento EXISTENTE (no cambiar código) de "
            + ", ".join(lot["characterized_files"])
            + " creando solo " + lot["write_paths"][0]
            + ": casos JSON declarativos para playwright_gate.py (claves id, path, selector, text, title,"
            " count, css, box, viewport; cada caso con al menos una aserción concreta; los de css/box deben"
            " fallar si ese valor cambia) que pasen contra la app actual; campo covers con exactamente: "
            + ", ".join(lot["characterized_requirement_ids"]) + ". Reglas a conservar: " + rules)


def _unprotect_affected(root, protected, affected):
    """Make exactly the lot's affected tests writable; keep every other test protected."""
    result = [p for p in protected if p not in affected]
    test_globs = project_test_globs()
    if any(g in result for g in test_globs):
        result = [p for p in result if p not in test_globs]
        result.extend(f.relative_to(root).as_posix() for f in project_test_files(Path(root))
                      if f.relative_to(root).as_posix() not in affected)
    return result


def generate(root, run, lots, *, persist=True, allow_source_drift=frozenset(),
             completed=None):
    """Build the chain plan and task templates.

    persist=False returns {"plan": plan, "templates": {path: template}} without
    writing, so CP3.6 can regenerate a pending lot with the current generator.
    allow_source_drift lists files that already-integrated lots of the same
    request legitimately changed; their analysis-time reuse hashes are not
    re-checked when regenerating later lots. completed carries the verified
    CP3.6 merge receipts for preserving already-integrated characterization
    templates during read-only regeneration, never during initial planning.
    """
    allow_source_drift=frozenset(allow_source_drift)
    completed = {} if completed is None else completed
    if completed and persist:
        raise ValueError("T1_COMPLETED_REGENERATION_ONLY")
    folder=storage_path("requests_root", root=Path(root))/run
    report_path=folder/"reuse_assessment.json"
    reuse_rows=[]
    modify_scope={}
    package_for_reuse=None
    scope_by_requirement={}
    requirement_by_id={}
    if report_path.exists():
        if report_path.is_symlink():
            raise ValueError("REUTILIZACION_INDETERMINADA")
        assessment=json.loads(report_path.read_text(encoding="utf-8"))
        if assessment.get("schema_version")!="T7_REUSE_ASSESSMENT_V1":
            raise ValueError("REUTILIZACION_INDETERMINADA")
        reuse_rows=assessment.get("obligations",[])
        if not isinstance(reuse_rows,list):
            raise ValueError("REUTILIZACION_INDETERMINADA")
        package_for_reuse=json.loads((folder/"analysis.json").read_text(encoding="utf-8"))
        scope_by_requirement={r["requirement_id"]:r["scope_id"]
                              for r in package_for_reuse["requirements"]}
        requirement_by_id={r["requirement_id"]:r
                           for r in package_for_reuse["requirements"]}
        # A modification may write the target's own existing files (A9
        # MODIFY_SCOPE, SHA-pinned); behavior reused there is retained and
        # protected by its existing tests, as for an explicit EXTEND.
        modify_scope={}
        if package_for_reuse.get("classification",{}).get("implementation_state")=="EXISTING":
            for front in package_for_reuse.get("non_atomized_fronts",[]):
                ref=front.get("candidate_ref") if isinstance(front,dict) else None
                if front.get("obligation_mode")=="MODIFY_SCOPE" and isinstance(ref,str) \
                        and ref.startswith("repo://") and "@" in ref:
                    path,_,digest=ref[len("repo://"):].rpartition("@")
                    modify_scope[path]=digest
    contract_lots=[lot for lot in lots["lots"] if lot["area"]=="CONTRATO"]
    contract_by_path={lot["write_paths"][0]:lot["contract_module"]
                      for lot in contract_lots}
    policy=json.loads((Path(__file__).parent/"atomize_rules_v1.json").read_text())
    skeleton_template=policy.get("contract_lot", {}).get("skeleton_path")
    if report_path.exists() and contract_lots:
        # T7's generated bot PR may write only under its own run directory.
        # Keep generated skeletons beside the task templates, not under
        # contracts/, and let T2's existing validator consume that location.
        skeleton_template=f"pilot/runs/{run}/templates/{{module}}.skeleton.json"
    if contract_lots:
        import sys
        directory=Path(__file__).parent
        if str(directory) not in sys.path:
            sys.path.insert(0,str(directory))
        import contract_generate
        if not isinstance(skeleton_template,str) or "{module}" not in skeleton_template:
            raise ValueError("T2_SKELETON_PATH_POLICY_INVALID")
        package=json.loads((folder/"analysis.json").read_text(encoding="utf-8"))
        atoms=json.loads((folder/"atomized_inputs.json").read_text(encoding="utf-8"))["atoms"]
        for lot in contract_lots:
            module=lot["contract_module"]
            skeleton=contract_generate.generate(module,package,atoms)
            if report_path.exists():
                source_scopes={scope_by_requirement[r] for r in lot["requirement_ids"]
                               if r in scope_by_requirement}
                reused=sorted({endpoint for row in reuse_rows
                               if scope_by_requirement.get(row.get("requirement_id")) in source_scopes
                               for endpoint in row.get("reused_endpoints",[])})
                if reused:
                    skeleton["reused_endpoints"]=reused
                    extended=sorted({endpoint for row in reuse_rows
                                     if row.get("decision")=="EXTEND"
                                     and scope_by_requirement.get(row.get("requirement_id")) in source_scopes
                                     for endpoint in row.get("reused_endpoints",[])})
                    if extended:
                        skeleton["extended_endpoints"]=extended
            path=Path(root)/skeleton_template.format(module=module)
            if persist:
                save(path,skeleton)
    # T7 only: a typed, evidence-backed reuse report is optional for legacy
    # chains. No report means no claim of reuse, never an implicit BUILD_NEW.
    rows=[]
    output={}
    for pos,lot in enumerate(lots["lots"],1):
        task=f"{run.replace('-','')[:16]}{lot['area'].lower()}{pos}"
        if len(task)>32 or not task[0].isalpha():
            raise ValueError("T1_TASK_INVALID")
        tpath=f"pilot/runs/{run}/templates/{task}.task.json"
        rows.append({"lot_id":lot["id"],"task_name":task,"template_path":tpath,
                     "holdout_metadata_path":f"pilot/runs/{run}/claude_meta/{task}.json"})
        paths=sorted(lot["write_paths"])
        enforce_generated_scope(lot["area"], paths)
        if lot.get("lot_kind") == "CHARACTERIZATION" and lot["id"] in completed:
            # A completed suite is historical evidence, not a new writable file.
            # Keep its original binding/template; do not run CREATE admission
            # on it or accidentally protect the suite against itself.
            suite_root = _visible_suite_root()
            proof = completed[lot["id"]]
            if (not suite_root or len(paths) != 1
                    or not paths[0].startswith(suite_root + "/")
                    or proof.get("lot_id") != lot["id"]
                    or proof.get("expected_files") != paths
                    or paths[0] not in allow_source_drift):
                raise ValueError("CARACTERIZACION_ALCANCE_INVALIDO")
            suite = Path(root) / paths[0]
            historical = Path(root) / tpath
            if (not suite.is_file() or suite.is_symlink()
                    or not historical.is_file() or historical.is_symlink()):
                raise ValueError("CARACTERIZACION_ALCANCE_INVALIDO")
            template = json.loads(historical.read_text(encoding="utf-8"))
            spec = template.get("task_spec", {}) if isinstance(template, dict) else {}
            if (not isinstance(spec, dict)
                    or spec.get("task_id") != "LF-WORKER-NATIVE-" + task.upper()
                    or spec.get("write_path_patterns") != paths):
                raise ValueError("CARACTERIZACION_ALCANCE_INVALIDO")
            output[tpath] = template
            continue
        protected=lot_protection(lot["area"], paths)
        dependency_contract=lot.get("contract_context_ref")
        if dependency_contract and dependency_contract not in contract_by_path:
            raise ValueError("T2_CONTRACT_CONTEXT_UNBOUND")
        module=lot.get("contract_module") or contract_by_path.get(dependency_contract)
        if dependency_contract:
            protected.append("contracts/**")
        elif lot["area"]=="CONTRATO":
            protected.append("contracts/*.skeleton.json")
        if lot["area"]=="INFRA":
            context_paths=(["pilot/orchestrator/dependency_allowlist_v1.json"]
                           + list(_project.lot_policy()["areas"]["INFRA"]["context_files"]))
        else:
            context_paths=(
                [skeleton_template.format(module=module)]
                if lot["area"]=="CONTRATO" else [dependency_contract]
                if dependency_contract else [])
        if lot.get("infra_context_ref"):
            context_paths.append(lot["infra_context_ref"])
        retained_behavior=[]
        if report_path.exists():
            import hashlib as _hashlib
            active_scopes={scope_by_requirement[r] for r in lot["requirement_ids"]
                           if r in scope_by_requirement}
            selected=[r for r in reuse_rows
                      if scope_by_requirement.get(r.get("requirement_id")) in active_scopes]
            # An existing REUSE_AS_IS source is writable only if another
            # obligation in THIS lot explicitly extends that exact file.
            extended = {}
            for row in selected:
                if (row.get("decision") == "EXTEND"
                        and row.get("requirement_id") in lot["requirement_ids"]):
                    for path in row.get("write_paths", []):
                        if path in paths:
                            extended.setdefault(path, []).append(row)
            for obligation in selected:
                for reference in obligation.get("reuse_context", []):
                    src, sha = reference.get("path"), reference.get("sha256")
                    if (not isinstance(src, str) or not isinstance(sha, str)
                            or not (Path(root)/src).is_file()
                            or (src not in allow_source_drift and
                                _hashlib.sha256((Path(root)/src).read_bytes()).hexdigest()!=sha)):
                        raise ValueError("REUTILIZACION_INDETERMINADA")
                    if src in paths:
                        matching = [row for row in extended.get(src, [])
                                    if row.get("path") == src
                                    and (row.get("sha256") == sha
                                         or src in allow_source_drift)]
                        in_scope = (obligation.get("decision") == "REUSE_AS_IS"
                                    and modify_scope.get(src) == sha)
                        if obligation.get("decision") != "REUSE_AS_IS" or not (matching or in_scope):
                            raise ValueError("REUTILIZACION_INDETERMINADA")
                        endpoints = obligation.get("reused_endpoints", [])
                        char = next((x for x in lots["lots"]
                                     if x["id"] == lot.get("characterized_by")
                                     and x.get("lot_kind") == "CHARACTERIZATION"
                                     and src in x.get("characterized_files", [])
                                     and obligation["requirement_id"]
                                         in x.get("characterized_requirement_ids", [])), None)
                        # Non-Java retained behavior is protected by the
                        # characterization suite this lot depends on.
                        tests = (list(char["write_paths"]) if char is not None
                                 else _existing_behavior_tests(root, src, endpoints))
                        protected.extend(tests)
                        retained_behavior.append({
                            "path":src,"endpoints":sorted(set(endpoints)),
                            "protected_tests":tests,
                            "reuse_requirement_id":obligation["requirement_id"],
                            "existing_outcome":requirement_by_id.get(
                                obligation["requirement_id"],{}).get("outcome"),
                            "extend_requirement_ids":sorted(
                                row["requirement_id"] for row in matching)})
                        continue
                    if src not in context_paths:
                        context_paths.append(src)
                    protected.append(src)
            context_paths.append("pilot/runs/"+run+"/reuse_assessment.json")
        # Every generated task needs an existing public source anchor: the
        # real Worker rejects empty context_path_patterns.
        # T26.3: only as a last resort. analysis.json is large; adding it to a
        # task that already has real context can exceed max_context_bytes.
        if not context_paths:
            context_paths.append("pilot/runs/" + run + "/analysis.json")
        context_paths=sorted(set(context_paths))
        # T26: project tests planned into this lot ("pruebas afectadas") are
        # writable; every other project test stays protected.
        affected_tests={p for p in paths if is_project_test(p)}
        if affected_tests:
            protected=_unprotect_affected(root, protected, affected_tests)
        characterization = lot.get("lot_kind") == "CHARACTERIZATION"
        if characterization:
            suite_root = _visible_suite_root()
            if (not suite_root or len(paths) != 1
                    or not paths[0].startswith(suite_root + "/") or (Path(root)/paths[0]).exists()):
                raise ValueError("CARACTERIZACION_ALCANCE_INVALIDO")
            # Only its own new file is writable; every existing case stays protected.
            protected = [p for p in protected if p != suite_root + "/**"]
            protected += sorted(f.relative_to(root).as_posix()
                                for f in (Path(root)/suite_root).glob("*.json"))
            context_paths = sorted(set(lot["characterized_files"]
                                       + ["pilot/worker_v08/playwright_gate.py"]
                                       + [f.relative_to(root).as_posix()
                                          for f in sorted((Path(root)/suite_root).glob("*.json"))][:3]))
        protected=sorted(set(protected))
        behavior_note = ("; conservar el comportamiento existente: "
                         + "; ".join(
                             ", ".join(row["endpoints"]) + " en " + row["path"]
                             + ("; debe seguir funcionando: " + row["existing_outcome"]
                                if isinstance(row["existing_outcome"],str) and row["existing_outcome"]
                                else "")
                             + ("; no modificar sus tests protegidos: "
                                + ", ".join(t for t in row["protected_tests"]
                                            if t not in affected_tests)
                                if [t for t in row["protected_tests"] if t not in affected_tests]
                                else "")
                             for row in retained_behavior)) if retained_behavior else ""
        if affected_tests:
            behavior_note += ("; pruebas afectadas (editables): "
                              + ", ".join(sorted(affected_tests))
                              + "; adaptar solo sus precondiciones al nuevo comportamiento,"
                              " sin eliminar ni debilitar sus aserciones existentes")
        template={"task_spec":{
            "schema_version":1,"task_id":"LF-WORKER-NATIVE-"+task.upper(),
            "base_head_sha":"<FILL_AT_REGISTRATION>",
            "source_snapshot_sha256":"<FILL_AT_REGISTRATION>",
            "max_attempts":1,"allow_deletions":False,"max_changed_files":len(paths),
            "max_context_bytes":200000,"max_patch_bytes":60000,
            "objective":(_characterization_objective(lot, requirement_by_id)
                         if characterization else
                         "Aplicar exclusivamente dependencias y configuración de la allowlist T3"
                         if lot["area"]=="INFRA" else
                         "Implementar "+lot["area"]+" en "+run+"; requisitos "+", ".join(
                            lot["requirement_ids"])+"; seguir package A9 sin inferencias"+behavior_note),
            "write_path_patterns":paths,
            "context_path_patterns":context_paths,
            "protected_path_patterns":protected,
            "acceptance_commands":(acceptance(lot["area"],paths,run=run) + [
                _item("characterization-covers",["lf-python","pilot/worker_v08/characterization_covers.py",
                      "--suite-file",paths[0],"--requires",",".join(lot["characterized_requirement_ids"])],120)]
                if characterization else
                acceptance(lot["area"],paths,run=run,module=module,
                                             has_contract=bool(dependency_contract),
                                             skeleton_path=(skeleton_template.format(module=module)
                                                            if module and skeleton_template else None),
                                             infra_dependencies=lot.get("infra_missing_dependencies"))),
        }}
        validate_template_worker(template, lot["area"], pending_shas=True)
        output[tpath]=template
    plan={"schema_version":"CP36_CHAIN_PLAN_V1","request_id":run,
          "production_authority":False,
          "lots_sha256":hashlib.sha256(canonical(lots)).hexdigest(),
          "bindings":rows}
    validate_plan(plan,lots,run)
    if not persist:
        return {"plan": plan, "templates": output}
    for path,data in sorted(output.items()):
        save(Path(root)/path,data)
    save(storage_path("chain_plans_root", root=Path(root))/(run+".json"),plan)
    return plan
