#!/usr/bin/env python3
"""T1 deterministic chain-plan and task-template generation, no registration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from chain_contract import validate_plan

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

def acceptance(area, paths, *, run=None, module=None, has_contract=False, skeleton_path=None, infra_dependencies=None):
    def item(name, argv, timeout=600):
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
        result=[item("backend-package",["mvn","-B","-q","-f","apps/time-service/pom.xml","package"])]
        if has_contract:
            result += [
                item("backend-start-openapi",["mvn","-B","-q","-f","apps/time-service/pom.xml",
                                              "spring-boot:start"]),
                item("backend-contract-operations",
                     ["python3","pilot/orchestrator/contract_validate.py",
                      "--compare-live","http://127.0.0.1:8080/v3/api-docs"]),
                item("backend-stop-openapi",["mvn","-B","-q","-f","apps/time-service/pom.xml",
                                             "spring-boot:stop"]),
            ]
        return result
    if area=="FRONTEND":
        result=[item("frontend-install",["npm","--prefix","frontend","ci"]),
                item("frontend-lint",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-lint"]),
                item("frontend-types",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-typecheck"]),
                item("frontend-build",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-build"]),
                item("frontend-prettier",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-prettier"])]
        if has_contract:
            result += [
                item("frontend-generate-api",["npm","--prefix","frontend","run","gen:api"]),
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
        for item in infra_dependencies:
            argv += ["--dependency-id",item["id"]]
        if "apps/time-service/src/main/resources/application.properties" in paths:
            argv += ["--database"]
        result=[item("infra-allowlist-and-env",argv)]
        if "apps/time-service/pom.xml" in paths:
            result.append(item("infra-build",["mvn","-U","-B","-q","-f",
                                              "apps/time-service/pom.xml",
                                              "-DskipTests","package"]))
        if "frontend/package.json" in paths:
            result.extend([
                item("infra-npm-ci",["npm","--prefix","frontend","ci"]),
                item("infra-generated-client",["npm","--prefix","frontend","run","gen:api"]),
            ])
        return result
    if area=="DATA":
        return [item("data-classpath-migrations",["python3","pilot/orchestrator/infra_validate.py",
                                                  "--check-data",*paths]),
                item("data-migration-visible",["psql","-X","-v","ON_ERROR_STOP=1","-f",paths[0]],180)]
    raise ValueError("T1_AREA_INVALID")

def generate(root, run, lots):
    folder=Path(root)/"pilot/runs"/run
    contract_lots=[lot for lot in lots["lots"] if lot["area"]=="CONTRATO"]
    contract_by_path={lot["write_paths"][0]:lot["contract_module"]
                      for lot in contract_lots}
    policy=json.loads((Path(__file__).parent/"atomize_rules_v1.json").read_text())
    skeleton_template=policy.get("contract_lot", {}).get("skeleton_path")
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
            path=Path(root)/skeleton_template.format(module=module)
            save(path,skeleton)
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
        protected=[".github/**",".lf/**","pilot/**","vendor/**",
                   "apps/time-service/src/test/**","apps/time-service/visible-tests/**",
                   "apps/time-service/pom.xml","apps/time-service/src/main/resources/**",
                   "frontend/package.json","frontend/package-lock.json",
                   "frontend/src/**/__tests__/**","db/**"]
        if lot["area"]=="INFRA":
            for manifest in ("frontend/package.json", "frontend/package-lock.json"):
                if manifest in paths:
                    protected.remove(manifest)
            protected.remove("apps/time-service/pom.xml")
            protected.remove("apps/time-service/src/main/resources/**")
            protected += ["apps/time-service/src/main/resources/db/**",
                          "frontend/src/**", "apps/time-service/src/main/java/**"]
        if lot["area"]=="DATA":
            protected.remove("apps/time-service/src/main/resources/**")
            protected += ["apps/time-service/src/main/resources/application.properties",
                          "apps/time-service/src/main/resources/static/**"]
            protected.remove("db/**")
            protected.extend(["db/**/test/**","db/**/fixtures/**"])
        dependency_contract=lot.get("contract_context_ref")
        if dependency_contract and dependency_contract not in contract_by_path:
            raise ValueError("T2_CONTRACT_CONTEXT_UNBOUND")
        module=lot.get("contract_module") or contract_by_path.get(dependency_contract)
        if dependency_contract:
            protected.append("contracts/**")
        elif lot["area"]=="CONTRATO":
            protected.append("contracts/*.skeleton.json")
        if lot["area"]=="INFRA":
            context_paths=["pilot/orchestrator/dependency_allowlist_v1.json",
                           "apps/time-service/pom.xml",
                           "apps/time-service/src/main/resources/application.properties"]
        else:
            context_paths=(
                [skeleton_template.format(module=module)]
                if lot["area"]=="CONTRATO" else [dependency_contract]
                if dependency_contract else [])
        if lot.get("infra_context_ref"):
            context_paths.append(lot["infra_context_ref"])
        context_paths=sorted(set(context_paths))
        template={"task_spec":{
            "schema_version":1,"task_id":"LF-WORKER-NATIVE-"+task.upper(),
            "base_head_sha":"<FILL_AT_REGISTRATION>",
            "source_snapshot_sha256":"<FILL_AT_REGISTRATION>",
            "max_attempts":1,"allow_deletions":False,"max_changed_files":len(paths),
            "max_context_bytes":200000,"max_patch_bytes":60000,
            "objective":("Aplicar exclusivamente dependencias y configuración de la allowlist T3"
                         if lot["area"]=="INFRA" else
                         "Implementar "+lot["area"]+" en "+run+"; requisitos "+", ".join(
                            lot["requirement_ids"])+"; seguir package A9 sin inferencias"),
            "write_path_patterns":paths,
            "context_path_patterns":context_paths,
            "protected_path_patterns":protected,
            "acceptance_commands":acceptance(lot["area"],paths,run=run,module=module,
                                             has_contract=bool(dependency_contract),
                                             skeleton_path=(skeleton_template.format(module=module)
                                                            if module and skeleton_template else None),
                                             infra_dependencies=lot.get("infra_missing_dependencies")),
            "context_derivation":"pilot/worker_v08/derive_context.py",
        }}
        output[tpath]=template
    plan={"schema_version":"CP36_CHAIN_PLAN_V1","request_id":run,
          "production_authority":False,
          "lots_sha256":hashlib.sha256(canonical(lots)).hexdigest(),
          "bindings":rows}
    validate_plan(plan,lots,run)
    for path,data in sorted(output.items()):
        save(Path(root)/path,data)
    save(Path(root)/"pilot/orchestrator/chain_plans"/(run+".json"),plan)
    return plan
