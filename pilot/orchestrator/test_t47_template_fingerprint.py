"""T47: immutable source-template fingerprint and legacy replay (offline)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from pilot.orchestrator import t4_admission as admission

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
from register_task_context import canonical, native_registration_bytes
from native_run import load_registration

BASE = "a" * 40
SOURCE = "b" * 64
TASK = "sampletask"
PATH = "pilot/runs/req-987/templates/sampletask.task.json"


def pack(tmp_path):
    folder = tmp_path / "pilot/worker_v08/native_tasks"
    folder.mkdir(parents=True)
    source = tmp_path / PATH
    source.parent.mkdir(parents=True)
    spec = {"schema_version": 1, "task_id": "LF-WORKER-NATIVE-SAMPLETASK",
            "objective": "Original", "write_path_patterns": ["frontend/src/demo.ts"],
            "context_path_patterns": ["contracts/demo.openapi.yaml"],
            "protected_path_patterns": ["pilot/**"],
            "acceptance_commands": [{"name": "check", "argv": ["true"]}],
            "max_patch_bytes": 60000, "max_changed_files": 1}
    source.write_bytes(canonical({"task_spec": spec}))
    stamp = hashlib.sha256(canonical(spec)).hexdigest()
    def register(**extras):
        (folder / (TASK + ".json")).write_bytes(canonical({
            "template_path": PATH, "template_sha256": stamp,
            "task_spec": {**spec, "base_head_sha": BASE, **extras}}))
    register()
    return source, spec, register


def variant(root, changed=lambda _: set()):
    return admission.registration_variant(root, TASK, PATH, changed)


def test_t47_derived_context_protection_commands_do_not_change_fingerprint(tmp_path):
    _, _, write = pack(tmp_path)
    write(context_path_patterns=["contracts/demo.openapi.yaml", "new-context"],
          protected_path_patterns=["pilot/**", "generated/**"],
          acceptance_commands=[{"name": "check", "argv": ["true"]},
                               {"name": "formatter", "argv": ["true"]}])
    assert variant(tmp_path) is None


@pytest.mark.parametrize("delta", [
    {"objective": "Changed"},
    {"acceptance_commands": [{"name": "changed", "argv": ["false"]}]},
    {"brand_new_unknown_template_field": {"unknown": True}},
])
def test_t47_any_template_field_change_is_variant(tmp_path, delta):
    source, spec, _ = pack(tmp_path)
    source.write_bytes(canonical({"task_spec": {**spec, **delta}}))
    assert variant(tmp_path) == TASK + "2"


def test_t47_changed_relevant_source_still_forces_variant(tmp_path):
    pack(tmp_path)
    assert variant(tmp_path, lambda _: {"frontend/src/demo.ts"}) == TASK + "2"
    assert variant(tmp_path, lambda _: {"standards/CAMBIOS.md"}) is None


def test_t47_missing_or_partial_stamp_fails_closed(tmp_path):
    _, spec, _ = pack(tmp_path)
    registered = tmp_path / "pilot/worker_v08/native_tasks/sampletask.json"
    for value in ({"task_spec": {**spec, "base_head_sha": BASE}, "template_path": PATH},
                  {"task_spec": {**spec, "base_head_sha": BASE},
                   "template_path": "pilot/runs/req-100/templates/other.task.json",
                   "template_sha256": hashlib.sha256(canonical(spec)).hexdigest()}):
        registered.write_bytes(canonical(value))
        assert variant(tmp_path) == TASK + "2"


def test_t47_register_schema_retains_stamp_and_rejects_unpaired(tmp_path):
    spec = {"schema_version": 1, "task_id": "LF-WORKER-NATIVE-SAMPLETASK",
            "base_head_sha": BASE, "source_snapshot_sha256": SOURCE,
            "objective": "noop", "write_path_patterns": ["frontend/src/demo.ts"],
            "context_path_patterns": [], "protected_path_patterns": [],
            "acceptance_commands": [], "max_attempts": 1,
            "max_patch_bytes": 60000, "max_changed_files": 1}
    stamp = hashlib.sha256(canonical(spec)).hexdigest()
    raw = native_registration_bytes(spec, SOURCE, task_name=TASK,
                                    template_path=PATH, template_sha256=stamp)
    obj = json.loads(raw)
    assert obj["template_sha256"] == stamp and obj["template_path"] == PATH
    with pytest.raises(ValueError):
        native_registration_bytes(spec, SOURCE, task_name=TASK,
                                  template_path=PATH)


@pytest.mark.parametrize("task,request", [
    ("req286backend2", "req-286"), ("req186backend2", "req-186"),
])
def test_t47_real_legacy_template_context_replay(task, request):
    """Historical main evidence: derive using the same pinned register() path."""
    path = f"pilot/runs/{request}/templates/{task}.task.json"
    record = json.loads(
        (ROOT / "pilot/worker_v08/native_tasks" / (task + ".json")).read_text("utf-8"))
    assert "template_sha256" not in record
    assert admission.registration_variant(ROOT, task, path, lambda _: set()) is None
