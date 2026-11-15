"""T16: real vendored Worker schema gate for every generated/native task.

The only temporary substitutions are the two registration-time SHA pins. No
schema is copied or reimplemented here: parse_worker_task is authoritative.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor/programming-agent/src"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from programming_agent_runner.worker_spec import parse_worker_task, TaskSpecError

AREAS = frozenset({"CONTRATO", "INFRA", "DATA", "BACKEND", "FRONTEND"})
BASE_PLACEHOLDER = "<FILL_AT_REGISTRATION>"


def validate_template_worker(template: dict, area: str, *, pending_shas: bool = False) -> None:
    """Raise one stable area-coded error; never inspect an encrypted oracle."""
    if area not in AREAS:
        raise ValueError("TEMPLATE_WORKER_SCHEMA_INVALID:" + str(area))
    try:
        if not isinstance(template, dict) or not isinstance(template.get("task_spec"), dict):
            raise TaskSpecError("missing task_spec")
        spec = dict(template["task_spec"])
        if pending_shas:
            if (spec.get("base_head_sha") != BASE_PLACEHOLDER
                    or spec.get("source_snapshot_sha256") != BASE_PLACEHOLDER):
                raise TaskSpecError("template SHA placeholders are not exact")
            spec["base_head_sha"] = "0" * 40
            spec["source_snapshot_sha256"] = "0" * 64
        parsed = parse_worker_task(spec)
        if parsed.to_dict() != spec:
            raise TaskSpecError("Worker roundtrip drift")
    except (TaskSpecError, ValueError, TypeError, KeyError) as exc:
        raise ValueError("TEMPLATE_WORKER_SCHEMA_INVALID:" + area) from exc


def normalize_legacy_registration_template(template: dict, area: str) -> dict:
    """Accept only the known pre-T16 trace outside the Worker task contract.

    Needed for already-approved pending plans generated before T16. The
    original committed templates remain untouched; this normalization occurs
    solely in the disposable preparation worktree before registration. A
    different extra field or an altered trace cannot be silently discarded.
    """
    from copy import deepcopy

    normalized = deepcopy(template)
    spec = normalized.get("task_spec") if isinstance(normalized, dict) else None
    if not isinstance(spec, dict):
        raise ValueError("TEMPLATE_WORKER_SCHEMA_INVALID:" + str(area))
    if "context_derivation" in spec:
        trace = spec.pop("context_derivation")
        if trace != "pilot/worker_v08/derive_context.py":
            raise ValueError("TEMPLATE_WORKER_SCHEMA_INVALID:" + str(area))
    validate_template_worker(normalized, area)
    return normalized
