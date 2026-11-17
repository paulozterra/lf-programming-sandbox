"""T40: positive control of the hidden exam with the examiner's reference.

The examiner publishes, next to each exam, an age-encrypted reference package
pilot/holdouts/<task>.reference.json.age (plaintext schema LF_EXAM_REFERENCE_V1:
task, holdout_sha256, patch). The reference is a correct solution written by
the examiner; it is bound to one exam version by holdout_sha256.

Two uses, same code path (the original vendored run_verified_worker):

* rehearsal (capa 1): before a lot or exam change is merged, the reference must
  pass visible + hidden acceptance on the registered base (exam_rehearsal.py);
* control (capa 2): when a constructor proposal does not pass, the Worker runs
  the reference in the same job. If the reference does not pass either, the
  defect is the examiner's (or the route's): the attempt is not charged.

Nothing here is shown to the constructor except the verdict line
EXAMINER_DEFECT_NOT_CHARGED.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from programming_agent_runner.hashutil import canonical_json_bytes, strict_json_loads
from programming_agent_runner.model_client import ModelError, ModelResponse

SCHEMA = "LF_EXAM_REFERENCE_V1"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
VERDICT_DEFECT = "EXAMINER_DEFECT_NOT_CHARGED"
MAX_BYTES = 1_000_000


def reference_ref(task: str) -> str:
    if not isinstance(task, str) or not TASK.fullmatch(task):
        raise ValueError("EXAM_REFERENCE_TASK_INVALID")
    return f"pilot/holdouts/{task}.reference.json.age"


def changed_paths(patch: str) -> list[str]:
    paths = []
    for line in patch.splitlines():
        if line.startswith("+++ "):
            target = line[4:].split("\t", 1)[0]
            if target != "/dev/null":
                paths.append(target[2:] if target.startswith("b/") else target)
    # deletions: "--- a/x" followed by "+++ /dev/null"
    lines = patch.splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.startswith("--- a/") and lines[i + 1].startswith("+++ /dev/null"):
            paths.append(line[6:].split("\t", 1)[0])
    return sorted(set(paths))


def parse_reference(raw: bytes, task: str, holdout_sha256: str) -> str:
    """Return the reference patch, or raise ValueError."""
    if len(raw) > MAX_BYTES:
        raise ValueError("EXAM_REFERENCE_TOO_LARGE")
    data = strict_json_loads(raw.decode("utf-8"))
    if (not isinstance(data, dict)
            or set(data) != {"schema_version", "task", "holdout_sha256", "patch"}
            or data["schema_version"] != SCHEMA or data["task"] != task
            or not isinstance(data["holdout_sha256"], str)
            or not SHA64.fullmatch(data["holdout_sha256"])
            or not isinstance(data["patch"], str) or not data["patch"].strip()):
        raise ValueError("EXAM_REFERENCE_INVALID")
    if data["holdout_sha256"] != holdout_sha256:
        raise ValueError("EXAM_REFERENCE_FOR_OTHER_EXAM")
    return data["patch"]


def load_reference(private: Path, task: str, holdout_sha256: str) -> str | None:
    """Reference patch decrypted by the workflow into private/reference.json."""
    file = Path(private) / "reference.json"
    if file.is_symlink() or not file.is_file():
        return None
    return parse_reference(file.read_bytes(), task, holdout_sha256)


class ReferenceClient:
    """Model-client stand-in that answers with the examiner's reference."""
    provider = "native-subscription"
    model = "gpt-native"

    def __init__(self, patch: str) -> None:
        self.patch = patch
        self.calls = 0

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> ModelResponse:
        self.calls += 1
        if self.calls != 1:
            raise ModelError("NATIVE_SINGLE_ATTEMPT_ONLY")
        proposal = {"schema_version": 1, "summary": "examiner reference (control)",
                    "patch": self.patch, "changed_paths": changed_paths(self.patch)}
        text = canonical_json_bytes(proposal).decode("utf-8")
        return ModelResponse(response_id="examiner-reference", requested_model=self.model,
                             resolved_model="gpt-native:chat-subscription",
                             output_text=text, usage={})


def run_reference(source: Path, spec, oracle, patch: str, work_parent: Path) -> dict:
    """Run the reference through the same verified Worker. Returns
    {"status": PASS|FAIL|BLOCKED, "reason": str} without any exam detail."""
    from programming_agent_runner.verified_worker import run_verified_worker
    work_parent = Path(work_parent)
    work_parent.mkdir(parents=True, exist_ok=True)
    try:
        outcome = run_verified_worker(source, spec, ReferenceClient(patch), oracle,
                                      work_parent=work_parent)
        receipt = outcome.receipt
        return {"status": str(receipt.get("status")), "reason": str(receipt.get("reason"))}
    except Exception as exc:  # the control itself failing is a route defect
        return {"status": "BLOCKED", "reason": "CONTROL_ERROR:" + type(exc).__name__}


def defect_record(task: str, run_id: int, holdout_sha256: str, control: dict) -> dict:
    return {"schema_version": "LF_EXAM_CONTROL_V1", "task": task, "run_id": run_id,
            "holdout_sha256": holdout_sha256, "verdict": VERDICT_DEFECT,
            "reference_status": control.get("status")}


def feedback_line() -> dict:
    return {"name": "examiner-control", "status": "BLOCKED", "reason": VERDICT_DEFECT,
            "returncode": None,
            "stdout_excerpt": "La solución de referencia del examinador tampoco pasa: "
                              "el defecto es del examen o de la ruta. Este intento NO se cobra; "
                              "el examinador debe corregirlo antes de un nuevo envío.",
            "stderr_excerpt": ""}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n", "utf-8")
