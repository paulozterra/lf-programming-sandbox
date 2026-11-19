"""T49.1 structural credential isolation for untrusted Worker execution."""
from pathlib import Path
import re
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / ".github/workflows/worker-native.yml"


def audit(doc):
    jobs = doc.get("jobs", {})
    job = jobs.get("native", {})
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        return ["INVALID_STEPS"]
    inherited = {}
    inherited.update(doc.get("env", {}) or {})
    inherited.update(job.get("env", {}) or {})
    problems = []
    def forbidden(env):
        return [k for k, v in (env or {}).items()
                if k in {"GH_TOKEN", "GITHUB_TOKEN"}
                or re.search(r"\$\{\{\s*secrets\.", str(v), re.I)]
    problems += ["INHERITED:" + k for k in forbidden(inherited)]
    worker_positions = []
    for index, step in enumerate(steps):
        script = str(step.get("run", ""))
        is_worker = bool(re.search(r"native_run[.]py\s+execute\b", script))
        if is_worker:
            worker_positions.append(index)
        if is_worker or "source/" in script or "proposal/" in script:
            problems += [f"UNTRUSTED:{index}:{k}" for k in forbidden(step.get("env"))]
    if len(worker_positions) != 1:
        problems.append("WORKER_EXECUTE_COUNT")
    elif worker_positions[0] == 0:
        problems.append("TRUST_GATE_MISSING")
    else:
        position = worker_positions[0]
        gate = steps[position - 1]
        if (gate.get("name") != "Recheck request lifecycle (trusted control only; no proposal execution)"
                or "control/pilot/worker_v08/request_lifecycle_gate.py" not in str(gate.get("run", ""))
                or gate.get("env", {}).get("GH_TOKEN") != "${{ github.token }}"
                or "source/" in str(gate.get("run", ""))
                or "proposal/" in str(gate.get("run", ""))):
            problems.append("TRUST_GATE_NOT_ADJACENT")
    return problems


def test_real_workflow_no_token_exposed():
    assert audit(yaml.safe_load(FILE.read_text())) == []


@pytest.mark.parametrize("attack", [
    "worker_gh", "worker_github", "worker_secret", "inherited_job",
    "inherited_workflow", "source_secret", "missing_gate",
])
def test_structural_negative_cases(attack):
    doc = yaml.safe_load(FILE.read_text())
    steps = doc["jobs"]["native"]["steps"]
    worker = next(step for step in steps if "native_run.py execute" in str(step.get("run", "")))
    if attack == "worker_gh":
        worker["env"]["GH_TOKEN"] = "${{ github.token }}"
    elif attack == "worker_github":
        worker["env"]["GITHUB_TOKEN"] = "fake"
    elif attack == "worker_secret":
        worker["env"]["KEY"] = "${{ secrets.PRIVATE }}"
    elif attack == "inherited_job":
        doc["jobs"]["native"]["env"]["GH_TOKEN"] = "fake"
    elif attack == "inherited_workflow":
        doc["env"] = {"SHARED": "${{ secrets.PRIVATE }}"}
    elif attack == "source_secret":
        steps.insert(steps.index(worker), {"name": "run source",
            "run": "python source/run.py", "env": {"GITHUB_TOKEN": "fake"}})
    else:
        steps.pop(steps.index(worker) - 1)
    assert audit(doc), attack
