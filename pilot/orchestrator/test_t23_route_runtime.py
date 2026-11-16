"""T23: generated Python command pinning and genuine isolated visible PASS."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from pilot.orchestrator.generate_chain import acceptance
from pilot.orchestrator.worker_template_contract import validate_template_worker
from pilot.worker_v08.install_lf_python import write_wrapper
from pilot.worker_v08.native_route_defect import classify, convert, migration, verified_migration

ROOT = Path(__file__).resolve().parents[2]
TASK = "synthetic1"
BASE = "a" * 40
SHA = "b" * 40
ORIGINAL = {"holdout_sha256": "f" * 64, "holdout_ref": "pilot/holdouts/opaque.age",
            "task_spec": {"base_head_sha": BASE, "acceptance_commands": [
                {"name": "contract-source-coverage",
                 "argv": ["python3", "pilot/orchestrator/contract_validate.py",
                          "--contract", "contracts/test.openapi.yaml"]}]}}


def test_every_generated_area_pins_python_and_static_gate_blocks_legacy():
    inputs = {
        "CONTRATO": dict(paths=["contracts/test.openapi.yaml"],
                         run="req-synthetic", module="synthetic",
                         skeleton_path="pilot/runs/req-synthetic/templates/skeleton.json"),
        "BACKEND": dict(paths=["apps/time-service/src/main/java/New.java"],
                        has_contract=True),
        "FRONTEND": dict(paths=["frontend/src/pages/new.tsx"], has_contract=True),
        "INFRA": dict(paths=["apps/time-service/pom.xml"], infra_dependencies=[]),
        "DATA": dict(paths=["apps/time-service/src/main/resources/db/migration/V1.sql"]),
    }
    for area, arguments in inputs.items():
        commands = acceptance(area, **arguments)
        assert commands
        for row in commands:
            assert row["argv"][0] not in ("python", "python3", "python3.12"), (
                "TEMPLATE_PYTHON_NO_FIJADO:" + area)
            if row["argv"][0] == "lf-python":
                assert row["argv"][1].endswith(".py")
    from unittest.mock import patch
    from pilot.orchestrator.worker_template_contract import TaskSpecError
    # The static check executes before the vendored schema decoder.
    bad = {"task_spec": {"acceptance_commands": [{
        "argv": ["python3", "pilot/orchestrator/contract_validate.py"]}]}}
    for area in inputs:
        with pytest.raises(ValueError, match="TEMPLATE_PYTHON_NO_FIJADO:" + area):
            validate_template_worker(bad, area)


def test_route_block_only_for_allowlisted_tool_environment_codes():
    failure = {"kind": "VISIBLE_ACCEPTANCE_ONLY", "commands": [{
        "name": "contract-source-coverage", "status": "FAIL",
        "reason": "EXIT_NONZERO", "returncode": 2,
        "stdout_excerpt": "",
        "stderr_excerpt": "BLOCKED:CONTRACT_SPEC_VALIDATOR_UNAVAILABLE\n",
    }]}
    assert classify(failure, ORIGINAL)
    for changed in [
        {"stderr_excerpt": "BLOCKED:CONTRACT_OPENAPI_INVALID\n"},
        {"stderr_excerpt": "AssertionError: incorrect contract"},
        {"name": "constructor-owned-test"},
        {"reason": "PROPOSAL_INVALID"},
    ]:
        copy = json.loads(json.dumps(failure))
        copy["commands"][0].update(changed)
        assert not classify(copy, ORIGINAL)
    mixed = json.loads(json.dumps(failure))
    mixed["commands"].append({
        "name": "constructor-owned-test", "status": "FAIL", "reason": "EXIT_NONZERO",
        "returncode": 1, "stderr_excerpt": "invalid source"})
    assert not classify(mixed, ORIGINAL)


def test_reversible_migration_keeps_holdout_base_and_all_non_launcher_fields(tmp_path):
    fixed, changed = convert(ORIGINAL)
    assert changed == 1
    assert fixed["task_spec"]["acceptance_commands"][0]["argv"][0] == "lf-python"
    assert fixed["holdout_sha256"] == ORIGINAL["holdout_sha256"]
    assert fixed["holdout_ref"] == ORIGINAL["holdout_ref"]
    artifact = migration(TASK, ORIGINAL, fixed, "1" * 64, "2" * 64,
                         43783407265, SHA, BASE)
    path = tmp_path / "pilot/worker_v08/route_migrations" / (TASK + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(artifact))
    assert verified_migration(tmp_path, TASK, fixed, proposal_sha=SHA) == artifact
    tampered = json.loads(json.dumps(fixed))
    tampered["task_spec"]["base_head_sha"] = "c" * 40
    assert verified_migration(tmp_path, TASK, tampered, proposal_sha=SHA) is None
    assert verified_migration(tmp_path, TASK, fixed, proposal_sha="d" * 40) is None


def test_synthetic_applied_valid_contract_passes_with_exact_worker_isolated_path():
    # The route's pinned dependency manifest is installed into a disposable venv.
    # No inherited PYTHONPATH or user site-packages may supply the validator.
    with tempfile.TemporaryDirectory(prefix="lf-t23-") as tmp:
        home = Path(tmp)
        runtime = home / "lf-python-runtime"
        subprocess.run([sys.executable, "-m", "venv", str(runtime)], check=True)
        python = runtime / "bin/python"
        subprocess.run([str(python), "-m", "pip", "install",
                        "--disable-pip-version-check", "--no-input",
                        "-r", str(ROOT / "pilot/worker_v08/python_runtime_requirements.txt")],
                       check=True, stdout=subprocess.DEVNULL)
        wrapper = home / "lf-python"
        write_wrapper(wrapper, python)
        # GitHub-hosted runner is isolated and permits installation at the
        # same path that the real native workflow uses.
        subprocess.run(["sudo", "install", "-m", "755", str(wrapper),
                        "/usr/local/bin/lf-python"], check=True)
        source = home / "candidate"
        contract = source / "contracts/synthetic.openapi.yaml"
        contract.parent.mkdir(parents=True)
        source_tool = source / "pilot/orchestrator/contract_validate.py"
        source_tool.parent.mkdir(parents=True)
        source_tool.write_bytes((ROOT / "pilot/orchestrator/contract_validate.py").read_bytes())
        contract.write_text("""openapi: 3.0.3
info: {title: Synthetic Proposal, version: 1.0.0}
paths:
  /items:
    get:
      x-requirement-ids: [REQ-SYNTHETIC]
      responses:
        '200': {description: success}
""")
        skeleton = source / "pilot/runs/req-synthetic/templates/synthetic.json"
        skeleton.parent.mkdir(parents=True)
        skeleton.write_text(json.dumps({
            "schema_version": "T2_CONTRACT_SKELETON_V1",
            "functional_module": "synthetic", "production_authority": False,
            "fields": [], "errors": [], "rules": [],
            "requirement_ids": ["REQ-SYNTHETIC"]}))
        command = acceptance("CONTRATO", ["contracts/synthetic.openapi.yaml"],
                             run="req-synthetic", module="synthetic",
                             skeleton_path="pilot/runs/req-synthetic/templates/synthetic.json")[0]
        assert command["argv"][0] == "lf-python"
        result = subprocess.run(command["argv"], cwd=source,
                                env={"PATH": "/usr/local/bin:/usr/bin:/bin",
                                     "HOME": str(home), "LANG": "C.UTF-8"},
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr[-2000:]
        assert result.stdout.strip() == ""
