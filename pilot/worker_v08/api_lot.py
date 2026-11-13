#!/usr/bin/env python3
"""T8 API-lot admission from trusted main. Never calls a model during admission.

The generated lot template and its acceptance policy are both derived from
pilot/orchestrator/generate_chain.py, not copied into the API workflow.
All missing/ambiguous evidence blocks before private oracle or API access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
from generate_chain import acceptance
from native_run import load_registration
from register_task_context import FORMAT_COMMAND
from lf_rule_context import material

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SLUG = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class ApiLotBlocked(ValueError):
    pass


def block(reason: str):
    raise ApiLotBlocked(reason)


def read(root: Path, relative: str) -> dict:
    if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
        block("API_LOT_PATH_INVALID")
    file = root / relative
    if file.is_symlink() or not file.is_file():
        block("API_LOT_EVIDENCE_MISSING")
    obj = json.loads(file.read_text("utf-8"))
    if not isinstance(obj, dict):
        block("API_LOT_EVIDENCE_INVALID")
    return obj


def find_binding(root: Path, task: str):
    plans = list((root / "pilot/runs").glob("*/chain_plan.json"))
    plans.extend((root / "pilot/orchestrator/chain_plans").glob("*.json"))
    found = []
    for file in sorted(plans):
        if file.is_symlink():
            block("API_LOT_PLAN_SYMLINK")
        plan = json.loads(file.read_text("utf-8"))
        slug = plan.get("request_id")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            continue
        for binding in plan.get("bindings", []):
            if binding.get("task_name") == task:
                found.append((slug, binding))
    unique = {(slug, row["lot_id"]): (slug, row)
              for slug, row in found}
    if len(unique) != 1:
        block("API_LOT_BINDING_UNRESOLVED")
    return next(iter(unique.values()))


def admit(root: Path, task: str) -> dict:
    if not TASK.fullmatch(task):
        block("API_LOT_TASK_INVALID")
    registered, sha = load_registration(root, task)
    slug, binding = find_binding(root, task)
    lots = read(root, f"pilot/runs/{slug}/lots.json")
    matching = [lot for lot in lots.get("lots", [])
                if lot.get("id") == binding.get("lot_id")]
    if len(matching) != 1:
        block("API_LOT_BINDING_UNRESOLVED")
    lot = matching[0]
    area = lot.get("area")
    if area not in ("CONTRATO", "INFRA"):
        block("API_LOT_AREA_NOT_SUPPORTED")
    path = binding.get("template_path")
    if path != f"pilot/runs/{slug}/templates/{task}.task.json":
        block("API_LOT_TEMPLATE_INVALID")
    template = read(root, path).get("task_spec")
    if not isinstance(template, dict):
        block("API_LOT_TEMPLATE_INVALID")
    paths = lot.get("write_paths")
    if (not isinstance(paths, list) or not paths
            or template.get("write_path_patterns") != paths
            or registered.get("write_path_patterns") != paths):
        block("API_LOT_SCOPE_DRIFT")

    module = lot.get("contract_module")
    skeleton = None
    if area == "CONTRATO":
        policy = read(root, "pilot/orchestrator/atomize_rules_v1.json")["contract_lot"]
        skeleton_pattern = (f"pilot/runs/{slug}/templates/{{module}}.skeleton.json"
                            if (root / f"pilot/runs/{slug}/reuse_assessment.json").is_file()
                            else policy["skeleton_path"])
        if not isinstance(module, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", module):
            block("API_LOT_CONTRACT_MODULE_INVALID")
        skeleton = skeleton_pattern.format(module=module)
    expected = acceptance(area, paths, run=slug, module=module,
                          skeleton_path=skeleton,
                          has_contract=bool(lot.get("contract_context_ref")),
                          infra_dependencies=lot.get("infra_missing_dependencies"))
    if template.get("acceptance_commands") != expected:
        block("API_LOT_GENERATED_ACCEPTANCE_DRIFT")
    commands = registered.get("acceptance_commands")
    # Registering a BACKEND alias can add only the existing pinned Spotless
    # command, never silently remove or replace a generated acceptance.
    if commands not in (expected, expected + [FORMAT_COMMAND]):
        block("API_LOT_GENERATED_ACCEPTANCE_DRIFT")
    for key in ("task_id", "objective"):
        if registered.get(key) != template.get(key):
            block("API_LOT_TASK_CONTRACT_DRIFT")
    if not set(template.get("protected_path_patterns", [])).issubset(
            registered.get("protected_path_patterns", [])):
        block("API_LOT_TASK_CONTRACT_DRIFT")
    references = [p for p in registered.get("context_path_patterns", [])
                  if p == f".lf/worker-context/{task}/lf_rules.receipt.json"]
    if len(references) != 1:
        block("DOMINIOS_NO_RESUELTOS")
    actual = read(root, references[0])
    profile = read(root, f".lf/worker-context/{task}/receipt.json")
    identities = [x["code"] for x in profile.get("skills", [])]
    _, expected_rules = material(area, skill_codes=identities)
    if (actual.get("selected_domains") != expected_rules["selected_domains"]
            or actual.get("rule_ids") != expected_rules["rule_ids"]
            or actual.get("assembled_sha256") != expected_rules["assembled_sha256"]):
        block("DOMINIOS_NO_RESUELTOS")
    registration = read(root, f"pilot/worker_v08/native_tasks/{task}.json")
    if (registration.get("holdout_sha256") != sha
            or registration.get("holdout_ref") != f"pilot/holdouts/{task}.oracle.json.age"):
        block("API_LOT_PRIVATE_ORACLE_NOT_REGISTERED")
    return {"task": task, "run": slug, "area": area,
            "base_sha": registered["base_head_sha"],
            "holdout_sha256": sha, "holdout_ref": registration["holdout_ref"],
            "acceptance_commands": commands,
            "rule_ids": actual["rule_ids"], "task_spec": registered}


def execute(root: Path, source: Path, private: Path, task: str, model: str):
    """Live API path uses the unmodified vendored verified Worker."""
    import os
    sys.path.insert(0, str(root / "vendor/programming-agent/src"))
    from programming_agent_runner.worker_spec import parse_worker_task
    from programming_agent_runner.hashutil import source_snapshot_sha256
    from programming_agent_runner.worker_oracle import load_hidden_oracle, assert_hidden_oracle_external
    from programming_agent_runner.verified_worker import run_verified_worker, validate_verified_worker_receipt
    from programming_agent_runner.anthropic_messages import AnthropicMessagesClient
    from lf_rule_gate import evaluate, coverage
    evidence = admit(root, task)
    spec = parse_worker_task(evidence["task_spec"])
    head = subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"], text=True).strip()
    if (head != evidence["base_sha"]
            or source_snapshot_sha256(source) != spec.source_snapshot_sha256
            or spec.max_attempts != 1):
        block("API_LOT_SOURCE_DRIFT")
    oracle_path = private / "holdout.oracle.json"
    if oracle_path.is_symlink() or not oracle_path.is_file():
        block("API_LOT_PRIVATE_ORACLE_MISSING")
    oracle = load_hidden_oracle(oracle_path, evidence["holdout_sha256"])
    assert_hidden_oracle_external(source, oracle)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or model not in ("claude-haiku-5-5", "claude-sonnet-5-5"):
        block("API_LOT_MODEL_UNAVAILABLE")
    client = AnthropicMessagesClient(api_key=api_key, model=model,
                                     timeout_seconds=90, max_output_tokens=8000)
    del api_key
    outcome = run_verified_worker(source, spec, client, oracle, work_parent=private)
    if validate_verified_worker_receipt(outcome.receipt, outcome.patch):
        block("API_LOT_VENDOR_RECEIPT_INVALID")
    if outcome.receipt["status"] != "PASS" or not outcome.patch:
        block("API_LOT_WORKER_NONPASS")
    gate = evaluate(outcome.patch, evidence["rule_ids"], root=root)
    public = private / "public"
    public.mkdir(parents=True, exist_ok=True)
    (public / "lf-rule-report.json").write_text(
        json.dumps({"schema_version":"T8_RULE_REPORT_V1",
                    "status":gate["status"], "rules":coverage(gate),
                    "violations":gate["violations"]},
                   sort_keys=True, indent=2)+"\n", encoding="utf-8")
    if gate["status"] != "PASS":
        block("API_LOT_RULE_REJECTED")
    (public / "worker.patch").write_text(outcome.patch, encoding="utf-8")
    print("API_LOT_VERIFIED_WORKER_PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("admission", "execute"))
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--private", type=Path)
    p.add_argument("--task", required=True)
    p.add_argument("--model", default="claude-sonnet-5-5")
    p.add_argument("--github-output", type=Path)
    a = p.parse_args()
    try:
        evidence = admit(a.control, a.task)
        if a.phase == "admission":
            if a.github_output:
                with a.github_output.open("a", encoding="utf-8") as out:
                    for key in ("base_sha", "holdout_sha256", "holdout_ref"):
                        out.write(f"{key}={evidence[key]}\n")
            print(json.dumps({"status":"READY_AT_WORKER_GATE",
                              "area":evidence["area"],
                              "acceptance_commands":evidence["acceptance_commands"],
                              "rules":len(evidence["rule_ids"]),
                              "api_calls":0},sort_keys=True))
            return
        if not a.source or not a.private:
            block("API_LOT_PRIVATE_WORKSPACE_MISSING")
        execute(a.control,a.source,a.private,a.task,a.model)
    except (ApiLotBlocked, ValueError, OSError, KeyError, TypeError) as exc:
        print("API_LOT_BLOCKED:"+str(exc).split(":",1)[0],file=sys.stderr)
        raise SystemExit(1)


if __name__=="__main__":
    main()
