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

def acceptance(area, paths, *, run=None, contract_path=None):
    def item(name, argv, timeout=600):
        return {"name":name,"argv":argv,"timeout_seconds":timeout,"max_output_bytes":32000}
    if area=="CONTRATO":
        if not run or len(paths)!=1:
            raise ValueError("T2_CONTRACT_ACCEPTANCE_INPUT_MISSING")
        return [item("openapi-contract", ["python3",
            "pilot/orchestrator/contract_validate.py",
            "--contract", paths[0], "--path", paths[0],
            "--package", f"pilot/runs/{run}/analysis.json",
            "--lots", f"pilot/runs/{run}/lots.json"])]
    if area=="BACKEND":
        commands = [item("backend-package",
                         ["mvn","-B","-q","-f","apps/time-service/pom.xml","package"])]
        if contract_path:
            commands.append(item("backend-openapi-runtime",
                ["python3","pilot/orchestrator/check_backend_live.py",
                 "--contract",contract_path], 300))
        return commands
    if area=="FRONTEND":
        checks = [item("frontend-install",["npm","--prefix","frontend","ci"]),
                item("frontend-lint",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-lint"]),
                item("frontend-types",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-typecheck"]),
                item("frontend-build",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-build"]),
                item("frontend-prettier",["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-prettier"])]
        if contract_path:
            checks.extend([
                item("frontend-client-generate",["npm","--prefix","frontend","run","gen:api"]),
                item("frontend-client-no-drift",["npm","--prefix","frontend","run","check:api"]),
                item("frontend-no-manual-fetch",["npm","--prefix","frontend","run","check:no-manual-fetch"])])
        return checks
    if area=="DATA":
        return [item("data-migration-visible",["psql","-X","-v","ON_ERROR_STOP=1","-f",paths[0]],180)]
    raise ValueError("T1_AREA_INVALID")

def generate(root, run, lots):
    folder=Path(root)/"pilot/runs"/run
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
        if lot["area"]=="DATA":
            protected.remove("db/**")
            protected.extend(["db/**/test/**","db/**/fixtures/**"])
        template={"task_spec":{
            "schema_version":1,"task_id":"LF-WORKER-NATIVE-"+task.upper(),
            "base_head_sha":"<FILL_AT_REGISTRATION>",
            "source_snapshot_sha256":"<FILL_AT_REGISTRATION>",
            "max_attempts":1,"allow_deletions":False,"max_changed_files":len(paths),
            "max_context_bytes":200000,"max_patch_bytes":60000,
            "objective":"Implementar "+lot["area"]+" en "+run+"; requisitos "+", ".join(
                lot["requirement_ids"])+"; seguir package A9 sin inferencias",
            "write_path_patterns":paths,
            "context_path_patterns": (
                [f"pilot/runs/{run}/analysis.json", f"pilot/runs/{run}/lots.json"]
                if lot["area"]=="CONTRATO" else
                ([lot["contract_path"], f"pilot/runs/{run}/analysis.json"]
                 if lot.get("contract_path") else [])),
            "protected_path_patterns":protected,
            "acceptance_commands":acceptance(lot["area"],paths,run=run,
                                             contract_path=lot.get("contract_path")),
            "contract_context_policy": ({
                "role": "AUTHOR", "contract_path": paths[0], "read_only": False
            } if lot["area"]=="CONTRATO" else {
                "role": "CONSUMER", "contract_path": lot["contract_path"],
                "read_only": True, "source": "verified_prior_lot"
            } if lot.get("contract_path") else None),
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
